from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
import json
import os
import re
from typing import Any
import requests

from backend.shared.normalization import (
    extract_json_from_text,
    normalize_text,
    normalize_text_list,
    normalize_steps,
    normalize_severity,
    normalize_risks,
    normalize_test_cases,
    normalize_simple_objects,
)
from backend.shared.resilience import (
    retry_with_backoff,
    CircuitOpenError,
    MaxRetriesExceeded,
    OLLAMA_BREAKER,
    OPENAI_BREAKER,
)

app = FastAPI(title="qa-llm-gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY")
DEFAULT_PROVIDER = os.getenv("DEFAULT_PROVIDER", "stub")
OLLAMA_URL       = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_OLLAMA_MODEL = os.getenv("DEFAULT_OLLAMA_MODEL", "llama3")


class GenerateRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model_profile: str = "stub"
    prompt: str = ""
    keep_alive: str = "10m"
    task_id: str | None = None
    task_type: str | None = None
    context: str | None = None
    provider: str = "stub-default"
    model_name: str = ""


# ---------------------------------------------------------------------------
# Thin aliases (kept so _normalize_llm_payload call-sites stay unchanged)
# ---------------------------------------------------------------------------
_extract_json_from_text  = extract_json_from_text
_normalize_string_list   = normalize_text_list
_normalize_steps         = normalize_steps
_normalize_test_case_objects = normalize_test_cases
_normalize_risks         = normalize_risks
_normalize_simple_objects = normalize_simple_objects


# ---------------------------------------------------------------------------
# Health / model listing
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "qa-llm-gateway"}


@app.get("/circuit-status")
def circuit_status():
    """Returns current state of all circuit breakers. Useful for monitoring."""
    return {
        "ollama":  {"state": OLLAMA_BREAKER.state,  "name": OLLAMA_BREAKER.name},
        "openai":  {"state": OPENAI_BREAKER.state,  "name": OPENAI_BREAKER.name},
    }


@app.post("/circuit-reset/{name}")
def circuit_reset(name: str):
    """Manually reset a circuit breaker (e.g. after fixing an upstream issue)."""
    breakers = {"ollama": OLLAMA_BREAKER, "openai": OPENAI_BREAKER}
    if name not in breakers:
        raise HTTPException(status_code=404, detail=f"Unknown breaker: {name!r}")
    breakers[name].reset()
    return {"reset": name, "state": breakers[name].state}


@app.get("/models")
def list_models(provider: str = "ollama"):
    if provider == "ollama":
        try:
            resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return {"provider": "ollama", "models": [m["name"] for m in data.get("models", [])]}
        except Exception as exc:
            return {"provider": "ollama", "models": [], "error": str(exc)}
    return {"provider": provider, "models": []}


# ---------------------------------------------------------------------------
# Payload normalisation  (gateway-specific — wraps shared helpers)
# ---------------------------------------------------------------------------

def _normalize_llm_payload(
    raw_payload: Any,
    provider: str,
    model_name: str,
    task_type: str | None,
) -> dict:
    """Map raw LLM JSON output to a normalised artifact payload."""

    if not isinstance(raw_payload, dict):
        return {
            "summary": str(raw_payload).strip() if raw_payload else "",
            "clarity_findings": [],
            "coverage_gaps": [],
            "assumptions": [],
            "risks": [],
            "questions_for_refinement": [],
            "suggested_test_areas": [],
            "qa_priority": "",
            "structure_issues": [],
            "clarity_issues": [],
            "coverage_issues": [],
            "duplicates": [],
            "missing_negative_cases": [],
            "improvement_actions": [],
            "review_score": "",
            "scope_in": [],
            "scope_out": [],
            "test_levels": [],
            "priority_matrix": [],
            "dependencies": [],
            "env_requirements": [],
            "test_data_needs": [],
            "entry_criteria": [],
            "exit_criteria": [],
            "staffing_notes": [],
            "tested_scope": [],
            "not_tested_scope": [],
            "pass_fail_blocked": {},
            "key_defects": [],
            "blockers": [],
            "quality_assessment": "",
            "recommendation": "",
            "signoff_status": "",
            "release_decision": "",
            "decision_reasoning": [],
            "must_fix_before_release": [],
            "acceptable_known_issues": [],
            "follow_up_actions": [],
            "test_cases": [],
            "task_type": task_type,
            "provider": provider,
            "model_name": model_name,
        }

    summary = raw_payload.get("summary", "")
    if not isinstance(summary, str):
        summary = str(summary)

    return {
        "summary":                  summary.strip(),
        "clarity_findings":         _normalize_string_list(raw_payload.get("clarity_findings", [])),
        "coverage_gaps":            _normalize_string_list(raw_payload.get("coverage_gaps", [])),
        "assumptions":              _normalize_string_list(raw_payload.get("assumptions", [])),
        "risks":                    _normalize_risks(raw_payload.get("risks", [])),
        "questions_for_refinement": _normalize_string_list(raw_payload.get("questions_for_refinement", [])),
        "suggested_test_areas":     _normalize_string_list(raw_payload.get("suggested_test_areas", [])),
        "qa_priority":              str(raw_payload.get("qa_priority", "")).strip(),
        "structure_issues":         _normalize_string_list(raw_payload.get("structure_issues", [])),
        "clarity_issues":           _normalize_string_list(raw_payload.get("clarity_issues", [])),
        "coverage_issues":          _normalize_string_list(raw_payload.get("coverage_issues", [])),
        "duplicates":               _normalize_string_list(raw_payload.get("duplicates", [])),
        "missing_negative_cases":   _normalize_string_list(raw_payload.get("missing_negative_cases", [])),
        "improvement_actions":      _normalize_string_list(raw_payload.get("improvement_actions", [])),
        "review_score":             str(raw_payload.get("review_score", "")).strip(),
        "scope_in":                 _normalize_string_list(raw_payload.get("scope_in", [])),
        "scope_out":                _normalize_string_list(raw_payload.get("scope_out", [])),
        "test_levels":              _normalize_string_list(raw_payload.get("test_levels", [])),
        "priority_matrix":          raw_payload.get("priority_matrix", []),
        "dependencies":             _normalize_string_list(raw_payload.get("dependencies", [])),
        "env_requirements":         _normalize_string_list(raw_payload.get("env_requirements", [])),
        "test_data_needs":          _normalize_string_list(raw_payload.get("test_data_needs", [])),
        "entry_criteria":           _normalize_string_list(raw_payload.get("entry_criteria", [])),
        "exit_criteria":            _normalize_string_list(raw_payload.get("exit_criteria", [])),
        "staffing_notes":           _normalize_string_list(raw_payload.get("staffing_notes", [])),
        "tested_scope":             _normalize_string_list(raw_payload.get("tested_scope", [])),
        "not_tested_scope":         _normalize_string_list(raw_payload.get("not_tested_scope", [])),
        "pass_fail_blocked":        raw_payload.get("pass_fail_blocked", {}),
        "key_defects":              _normalize_simple_objects(raw_payload.get("key_defects", []), "summary"),
        "blockers":                 _normalize_string_list(raw_payload.get("blockers", [])),
        "quality_assessment":       str(raw_payload.get("quality_assessment", "")).strip(),
        "recommendation":           str(raw_payload.get("recommendation", "")).strip(),
        "signoff_status":           str(raw_payload.get("signoff_status", "")).strip(),
        "release_decision":         str(raw_payload.get("release_decision", "")).strip(),
        "decision_reasoning":       _normalize_string_list(raw_payload.get("decision_reasoning", [])),
        "must_fix_before_release":  _normalize_string_list(raw_payload.get("must_fix_before_release", [])),
        "acceptable_known_issues":  _normalize_string_list(raw_payload.get("acceptable_known_issues", [])),
        "follow_up_actions":        _normalize_string_list(raw_payload.get("follow_up_actions", [])),
        "test_cases":               _normalize_test_case_objects(raw_payload.get("test_cases", [])),
        "task_type":                task_type,
        "provider":                 provider,
        "model_name":               model_name,
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_prompt(req: GenerateRequest) -> str:
    task_type = req.task_type or "test_case_generation"

    if task_type == "requirements_analysis":
        return (
            "You are a QA Lead reviewing a feature before refinement.\n"
            "Your job is to identify ambiguity, missing behavior, missing mappings, edge cases, "
            "and questions that product/engineering must clarify before implementation.\n"
            "Stay strictly grounded in the provided requirement text.\n"
            "Do NOT invent business impact or dramatic consequences unless they are explicitly "
            "supported by the input.\n"
            "Do NOT claim crashes, data loss, account lockout, false negatives, security breaches, "
            "or other severe outcomes unless the requirement directly suggests them.\n"
            "Prefer wording like 'unclear behavior', 'ambiguous handling', 'missing mapping', "
            "'unspecified recovery behavior', 'inconsistent implementation risk'.\n"
            "If you mention additional status codes, flows, or scenarios not explicitly listed, "
            "present them only as possible coverage gaps or refinement questions, never as confirmed facts.\n"
            "Do not introduce extra HTTP/status codes as if they are required behavior unless they "
            "appear in the input.\n"
            "For risks, focus on implementation ambiguity and inconsistent handling, not imagined "
            "business damage.\n"
            "Use severity carefully: low for minor clarity issues, medium for realistic implementation "
            "inconsistency, high for major likely delivery/testability problems, critical only when "
            "the requirement explicitly implies severe business, security, legal, or regulatory impact.\n"
            "For assumptions, include only assumptions that are truly necessary and strongly implied "
            "by the text.\n"
            "For questions_for_refinement, ask concrete questions about expected behavior, per-code "
            "mapping, retryability, recoverability, ownership, fallback behavior, and platform scope.\n"
            "For suggested_test_areas, stay close to the stated requirement and its immediate edge cases.\n"
            "If the requirement is short or underspecified, prefer concise refinement questions and "
            "coverage gaps instead of speculative detail.\n"
            "Return ONLY valid JSON. No markdown. No explanations.\n"
            "Required JSON format:\n"
            "{\n"
            '  "summary": "short summary",\n'
            '  "clarity_findings": ["..."],\n'
            '  "coverage_gaps": ["..."],\n'
            '  "assumptions": ["..."],\n'
            '  "risks": [{"title":"...","severity":"low|medium|high|critical","description":"..."}],\n'
            '  "questions_for_refinement": ["..."],\n'
            '  "suggested_test_areas": ["..."],\n'
            '  "qa_priority": "low|medium|high"\n'
            "}\n\n"
            f"Input: {req.prompt}"
        )

    if task_type == "manual_test_case_review":
        return (
            "You are a QA Lead reviewing manual test cases.\n"
            "Return ONLY valid JSON. No markdown. No explanations.\n"
            "Required JSON format:\n"
            "{\n"
            '  "summary": "short summary",\n'
            '  "structure_issues": ["..."],\n'
            '  "clarity_issues": ["..."],\n'
            '  "coverage_issues": ["..."],\n'
            '  "duplicates": ["..."],\n'
            '  "missing_negative_cases": ["..."],\n'
            '  "improvement_actions": ["..."],\n'
            '  "review_score": "approved|needs_improvement|major_rework"\n'
            "}\n\n"
            f"Input: {req.prompt}"
        )

    if task_type == "test_plan":
        return (
            "You are a QA Lead building a risk-based test plan.\n"
            "Return ONLY valid JSON. No markdown. No explanations.\n"
            "Required JSON format:\n"
            "{\n"
            '  "summary": "short summary",\n'
            '  "scope_in": ["..."],\n'
            '  "scope_out": ["..."],\n'
            '  "test_levels": ["sanity","smoke","minimal_acceptance","acceptance"],\n'
            '  "priority_matrix": [{"area":"...","priority":"critical|high|medium|low"}],\n'
            '  "dependencies": ["..."],\n'
            '  "env_requirements": ["..."],\n'
            '  "test_data_needs": ["..."],\n'
            '  "entry_criteria": ["..."],\n'
            '  "exit_criteria": ["..."],\n'
            '  "staffing_notes": ["..."]\n'
            "}\n\n"
            f"Input: {req.prompt}"
        )

    if task_type == "test_report":
        return (
            "You are a QA Lead writing a testing report.\n"
            "Return ONLY valid JSON. No markdown. No explanations.\n"
            "Required JSON format:\n"
            "{\n"
            '  "summary": "short summary",\n'
            '  "tested_scope": ["..."],\n'
            '  "not_tested_scope": ["..."],\n'
            '  "pass_fail_blocked": {"passed":0,"failed":0,"blocked":0},\n'
            '  "key_defects": [{"id":"...","severity":"...","summary":"..."}],\n'
            '  "blockers": ["..."],\n'
            '  "risks": ["..."],\n'
            '  "quality_assessment": "...",\n'
            '  "recommendation": "...",\n'
            '  "signoff_status": "ready|caution|not_ready"\n'
            "}\n\n"
            f"Input: {req.prompt}"
        )

    if task_type == "release_readiness":
        return (
            "You are a QA Lead making a release readiness decision.\n"
            "Return ONLY valid JSON. No markdown. No explanations.\n"
            "Required JSON format:\n"
            "{\n"
            '  "summary": "short summary",\n'
            '  "release_decision": "ready|caution|not_ready",\n'
            '  "decision_reasoning": ["..."],\n'
            '  "must_fix_before_release": ["..."],\n'
            '  "acceptable_known_issues": ["..."],\n'
            '  "follow_up_actions": ["..."]\n'
            "}\n\n"
            f"Input: {req.prompt}"
        )

    # default: test_case_generation
    return (
        "You are a QA lead.\n"
        "Return ONLY valid JSON.\n"
        "No markdown.\n"
        "No code fences.\n"
        "No explanations.\n"
        "Required JSON format:\n"
        "{\n"
        '  "summary": "short summary",\n'
        '  "test_cases": [\n'
        '    {\n'
        '      "title": "test case title",\n'
        '      "steps": ["step 1", "step 2", "step 3"],\n'
        '      "expected_result": "expected outcome"\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        f"Input: {req.prompt}"
    )


# ---------------------------------------------------------------------------
# Provider backends
# ---------------------------------------------------------------------------

def _stub_result(req: GenerateRequest) -> dict:
    """Return canned stub data for offline / CI use."""
    task_type = req.task_type or "test_case_generation"

    if task_type == "requirements_analysis":
        output = {
            "summary": "Requirements are partially testable but need clarification on integration ownership and failure handling.",
            "clarity_findings": [
                "The source of truth for restored state is not explicit.",
                "Partial failure behavior is not described.",
            ],
            "coverage_gaps": [
                "No acceptance criteria for interrupted network.",
                "No expected behavior for blocked account restore.",
            ],
            "assumptions": ["Linked account credentials remain valid."],
            "risks": [{
                "title": "Cross-service inconsistency",
                "severity": "high",
                "description": "Auth state and player state may diverge during restore.",
            }],
            "questions_for_refinement": [
                "What happens if authentication succeeds but account restoration fails?",
            ],
            "suggested_test_areas": [],
            "qa_priority": "high",
        }
    elif task_type == "manual_test_case_review":
        output = {
            "summary": "Test cases cover the main path but need stronger negative coverage and clearer expected results.",
            "structure_issues": ["Some steps combine multiple user actions."],
            "clarity_issues": ["Expected results are too generic."],
            "coverage_issues": ["Missing negative coverage for invalid credentials and restore interruption."],
            "duplicates": ["Two positive-path cases overlap significantly."],
            "missing_negative_cases": ["restore with expired credentials", "restore with unstable network"],
            "improvement_actions": [
                "Split combined steps into atomic steps.",
                "Add explicit UI and backend expected outcomes.",
            ],
            "review_score": "needs_improvement",
        }
    elif task_type == "test_plan":
        output = {
            "summary": "The test plan focuses on critical account restore and service consistency risks.",
            "scope_in": ["restore linked account", "restore error handling", "purchase restoration"],
            "scope_out": ["restore happy path"],
            "test_levels": ["sanity", "smoke", "minimal_acceptance"],
            "priority_matrix": [
                {"area": "account restore", "priority": "critical"},
                {"area": "purchase restore", "priority": "high"},
            ],
            "dependencies": ["Auth service", "Player service", "Purchase service"],
            "env_requirements": ["staging environment with linked accounts"],
            "test_data_needs": ["accounts with purchases", "blocked accounts"],
            "entry_criteria": ["All services deployed to staging"],
            "exit_criteria": ["All critical cases passed", "No P1 defects open"],
            "staffing_notes": ["1 QA engineer, 2 days"],
        }
    elif task_type == "test_report":
        output = {
            "summary": "Testing completed with 2 blockers found in restore flow.",
            "tested_scope": ["account restore", "error handling"],
            "not_tested_scope": ["purchase restore — blocked by STAG-1234"],
            "pass_fail_blocked": {"passed": 8, "failed": 2, "blocked": 1},
            "key_defects": [
                {"id": "BUG-001", "severity": "critical", "summary": "Restore fails silently on network error"},
            ],
            "blockers": ["STAG-1234: purchase service unavailable"],
            "risks": ["partial restore state not rolled back"],
            "quality_assessment": "Not ready — blockers must be resolved before release.",
            "recommendation": "Fix BUG-001 and retest restore flow.",
            "signoff_status": "not_ready",
        }
    elif task_type == "release_readiness":
        output = {
            "summary": "Release is not ready due to unresolved critical defects.",
            "release_decision": "not_ready",
            "decision_reasoning": [
                "BUG-001 (critical) is unresolved.",
                "Purchase restore is not tested.",
            ],
            "must_fix_before_release": ["BUG-001"],
            "acceptable_known_issues": [],
            "follow_up_actions": ["Retest restore flow after BUG-001 fix."],
        }
    else:
        story = req.prompt[:200] if req.prompt else "feature"
        summary = f"Stub test cases for: {story}"
        output = {
            "summary": summary,
            "test_cases": [
                {
                    "id": "TC-001",
                    "title": "Verify happy path",
                    "steps": ["Open the feature", "Perform main action", "Verify result"],
                    "expected_result": "Feature works as expected",
                },
                {
                    "id": "TC-002",
                    "title": "Verify error handling",
                    "steps": ["Trigger error condition", "Observe response"],
                    "expected_result": "Error message displayed correctly",
                },
            ],
        }

    return _normalize_llm_payload(output, "stub", "stub", task_type)


def _openai_result(req: GenerateRequest) -> dict:
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    model_name = req.model_name or "gpt-4o-mini"
    prompt = _build_prompt(req)

    def _do_call() -> requests.Response:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp

    try:
        response = retry_with_backoff(
            _do_call,
            retries=3,
            base_delay=1.0,
            max_delay=15.0,
            breaker=OPENAI_BREAKER,
        )
    except CircuitOpenError as exc:
        raise HTTPException(status_code=503, detail=f"OpenAI unavailable (circuit open): {exc}") from exc
    except MaxRetriesExceeded as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI failed after retries: {exc.last_error}") from exc

    content = response.json()["choices"][0]["message"]["content"]
    parsed = extract_json_from_text(content)
    return _normalize_llm_payload(
        parsed if isinstance(parsed, dict) else {"summary": content},
        "openai",
        model_name,
        req.task_type,
    )


def _ollama_result(req: GenerateRequest) -> dict:
    model_name = req.model_name or DEFAULT_OLLAMA_MODEL
    prompt = _build_prompt(req)

    def _do_call() -> requests.Response:
        resp = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "keep_alive": req.keep_alive,
            },
            timeout=300,
        )
        resp.raise_for_status()
        return resp

    try:
        response = retry_with_backoff(
            _do_call,
            retries=3,
            base_delay=2.0,
            max_delay=20.0,
            breaker=OLLAMA_BREAKER,
        )
    except CircuitOpenError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable (circuit open): {exc}") from exc
    except MaxRetriesExceeded as exc:
        raise HTTPException(status_code=502, detail=f"Ollama failed after retries: {exc.last_error}") from exc

    raw = response.json().get("response", "")
    parsed = extract_json_from_text(raw)
    return _normalize_llm_payload(
        parsed if isinstance(parsed, dict) else {"summary": raw},
        "ollama",
        model_name,
        req.task_type,
    )


# ---------------------------------------------------------------------------
# Main endpoint
# ---------------------------------------------------------------------------

@app.post("/generate")
def generate(req: GenerateRequest) -> dict:
    provider = req.provider or DEFAULT_PROVIDER

    if provider == "openai":
        return _openai_result(req)
    if provider == "ollama":
        return _ollama_result(req)
    # stub / default
    return _stub_result(req)
