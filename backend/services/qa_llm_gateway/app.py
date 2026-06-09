from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.shared.normalization import (
    normalize_assumptions,
    normalize_clarity_findings,
    normalize_coverage_gaps,
    normalize_risks,
    normalize_risk_strings,
    normalize_string_list,
)

logger = logging.getLogger("qa-llm-gateway")


class GenerateRequest(BaseModel):
    task_type: str = Field(default="test_case_generation")
    prompt: str
    model_profile: str | None = None


class GenerateResponse(BaseModel):
    raw_output: Dict[str, Any]
    normalized_output: Dict[str, Any]


def _build_prompt(req: GenerateRequest) -> str:
    task_type = req.task_type or "test_case_generation"

    if task_type == "requirements_analysis":
        return (
            "You are a QA Lead reviewing a feature before refinement.\n"
            "Your job is to identify ambiguity, missing behavior, missing mappings, edge cases, "
            "and questions that product/engineering must clarify before implementation.\n"
            "Stay strictly and literally grounded in the provided requirement text.\n"
            "Do NOT invent business impact, data loss, crashes, account lockout, security issues, "
            "or any other dramatic consequences unless the requirement explicitly suggests them.\n"
            "Do NOT infer backend mechanics, synchronization models, account state models, or "
            "infrastructure (e.g. linked account data stores, progress sync flows, background jobs) "
            "from words like 'restore', 'linked', 'sync', 'reinstall', or 'failure'.\n"
            "Treat such words as high-level intent only, not as a specification of how the system works.\n"
            "If important behavior is not specified, surface it as clarity_findings, coverage_gaps, "
            "or questions_for_refinement instead of adding speculative details.\n"
            "For assumptions, include only assumptions that are truly necessary and strongly implied "
            "by the text. If the requirement is short or underspecified, prefer leaving assumptions "
            "empty and asking refinement questions instead.\n"
            "For risks, focus on ambiguous or inconsistent implementation behavior, not imagined "
            "business damage or data loss. Use severity carefully: low for minor clarity issues, "
            "medium for realistic implementation inconsistency, high only for major likely "
            "delivery/testability problems explicitly implied by the requirement.\n"
            "For questions_for_refinement, ask concrete questions about expected behavior, per-case "
            "handling, retryability, recoverability, ownership, fallback behavior, and platform scope.\n"
            "For suggested_test_areas, stay very close to the stated requirement and its immediate "
            "edge cases. Do not introduce new flows, entities, or scenarios that are not present in "
            "the input.\n"
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
            '  "defect_summary": ["..."],\n'
            '  "quality_risks": ["..."],\n'
            '  "recommendations": ["..."],\n'
            '  "go_no_go": "go|no_go|needs_discussion"\n'
            "}\n\n"
            f"Input: {req.prompt}"
        )

    if task_type == "release_readiness":
        return (
            "You are a QA Lead evaluating release readiness.\n"
            "Return ONLY valid JSON. No markdown. No explanations.\n"
            "Required JSON format:\n"
            "{\n"
            '  "summary": "short summary",\n'
            '  "release_scope": ["..."],\n'
            '  "known_issues": ["..."],\n'
            '  "risks": ["..."],\n'
            '  "blocking_issues": ["..."],\n'
            '  "qa_recommendation": "go|no_go|needs_discussion"\n'
            "}\n\n"
            f"Input: {req.prompt}"
        )

    # Default: generic test_case_generation-style prompt
    return (
        "You are a QA engineer generating test cases.\n"
        "Return ONLY valid JSON. No markdown. No explanations.\n"
        "Required JSON format:\n"
        "{\n"
        '  "summary": "short summary",\n'
        '  "test_cases": ["..."],\n'
        '  "qa_priority": "low|medium|high"\n'
        "}\n\n"
        f"Input: {req.prompt}"
    )


def _normalize_string_list(values: Any) -> List[str]:
    return normalize_string_list(values)


def _normalize_risks(values: Any) -> List[Dict[str, Any]]:
    return normalize_risks(values)


app = FastAPI()


@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest) -> GenerateResponse:
    prompt = _build_prompt(req)
    # ... rest of implementation calling LLM provider and normalizing output ...
    raise HTTPException(status_code=501, detail="Not implemented in this snippet")
