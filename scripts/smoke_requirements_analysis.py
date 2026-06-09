#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter
from backend.shared.artifacts import ArtifactPayload

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8001")
DOMAIN_ID = os.getenv("DOMAIN_ID", "11111111-1111-1111-1111-111111111111")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama")
MODEL_NAME = os.getenv("MODEL_NAME", "llama3")

CASES = [
    {
        "name": "status-code-mapping",
        "input": {
            "text": "Login API should return 401 for invalid credentials and 423 for locked account.",
            "story_id": "story-101",
            "jira_key": "QA-101",
            "story_title": "Login status code mapping",
            "service_name": "auth-service",
            "owner_team": "identity",
            "platforms": ["web"],
            "linked_services": ["session-service"],
        },
        "expectations": {
            "min_non_empty_sections": 2,
            "summary_required": True,
        },
    },
    {
        "name": "short-underspecified-requirement",
        "input": {
            "text": "User can restore previous session after app restart.",
            "story_id": "story-102",
            "jira_key": "QA-102",
            "story_title": "Session restore",
            "service_name": "session-service",
            "owner_team": "mobile-platform",
            "platforms": ["ios", "android"],
            "linked_services": ["auth-service", "profile-service"],
        },
        "expectations": {
            "min_non_empty_sections": 2,
            "summary_required": True,
        },
    },
    {
        "name": "cross-service-flow",
        "input": {
            "text": "If player authentication succeeds, the app should restore the previously selected account and open the lobby.",
            "story_id": "story-103",
            "jira_key": "QA-103",
            "story_title": "Auth to lobby restore flow",
            "service_name": "gateway-service",
            "owner_team": "player-experience",
            "platforms": ["ios", "android", "web"],
            "linked_services": ["auth-service", "account-service", "lobby-service"],
        },
        "expectations": {
            "min_non_empty_sections": 2,
            "summary_required": True,
        },
    },
    {
        "name": "deposit-limits-and-bonus",
        "input": {
            "title": "Deposit with daily and monthly limits + welcome bonus",
            "story": "As a newly registered player I want to make a deposit so that I can receive a welcome bonus and play in the social casino.",
            "acceptance_criteria": [
                "User sees the current daily and monthly deposit limits before confirming the payment.",
                "If the entered amount exceeds daily or monthly limit, deposit is blocked and a clear message is shown.",
                "Eligible welcome bonus is automatically proposed for the first successful deposit.",
                "If bonus cannot be applied, user still can complete deposit without bonus and sees the reason.",
                "Deposit attempts that exceed limits are logged for further risk checks.",
            ],
            "story_id": "story-201",
            "jira_key": "QA-201",
            "story_title": "Deposit with limits and welcome bonus",
            "service_name": "payments-service",
            "owner_team": "payments",
            "platforms": ["ios", "android", "web"],
            "linked_services": ["bonus-service", "ledger-service", "risk-service"],
        },
        "expectations": {
            "min_non_empty_sections": 4,
            "summary_required": True,
            "required_phrases": ["limit", "bonus"],
        },
    },
    {
        "name": "withdrawal-ambiguous-basic",
        "input": {
            "title": "Withdrawal flow basic scenario",
            "story": "As a player I want to withdraw chips whenever I want so that I can get money from the social casino.",
            "acceptance_criteria": [
                "User can request withdrawal from the balance screen.",
                "Withdrawal is processed if everything is fine.",
                "User sees a generic error if something goes wrong.",
            ],
            "story_id": "story-202",
            "jira_key": "QA-202",
            "story_title": "Ambiguous withdrawal flow",
            "service_name": "payments-service",
            "owner_team": "payments",
            "platforms": ["ios", "android", "web"],
            "linked_services": ["wallet-service", "risk-service"],
        },
        "expectations": {
            "min_non_empty_sections": 4,
            "summary_required": True,
            "required_phrases": ["withdrawal", "error"],
        },
    },
]


def post_json(url: str, payload: dict) -> dict:
    req = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=60) as response:
        return json.load(response)


def get_json(url: str) -> dict:
    with urlopen(url, timeout=60) as response:
        return json.load(response)


def wait_for_result(task_id: str, timeout_seconds: int = 180) -> dict:
    deadline = time.time() + timeout_seconds
    url = f"{BASE_URL}/api/tasks/{task_id}/result"

    while time.time() < deadline:
        payload = get_json(url)
        state = payload.get("state")
        if state == "completed":
            return payload
        if state in {"failed", "error"}:
            raise RuntimeError(f"Task {task_id} failed: {json.dumps(payload, ensure_ascii=False)}")
        time.sleep(2)

    raise TimeoutError(f"Timed out waiting for task {task_id}")


def norm(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def count_non_empty_sections(result: dict) -> int:
    key_fields = [
        "clarity_findings",
        "coverage_gaps",
        "questions_for_refinement",
        "suggested_test_areas",
        "risks",
        "assumptions",
    ]
    count = 0
    for field in key_fields:
        items = result.get(field, [])
        if isinstance(items, list) and any(str(item).strip() for item in items):
            count += 1
    return count


def validate_quality(case: dict, result: dict) -> list[str]:
    errors: list[str] = []
    expectations = case.get("expectations", {})

    if result.get("artifact_type") != "qa_requirement_analysis":
        errors.append(f"unexpected artifact_type: {result.get('artifact_type')}")

    summary = result.get("summary", "")
    if expectations.get("summary_required", False):
        if not isinstance(summary, str) or not summary.strip():
            errors.append("summary is empty")

    qa_health = result.get("qa_health")
    if qa_health not in {"green", "yellow", "red"}:
        errors.append(f"invalid qa_health: {qa_health}")

    readiness_score = result.get("readiness_score")
    if not isinstance(readiness_score, int) or not (0 <= readiness_score <= 100):
        errors.append(f"invalid readiness_score: {readiness_score}")

    risks = result.get("risks", [])
    if not isinstance(risks, list):
        errors.append("risks is not a list")
    else:
        for idx, item in enumerate(risks):
            if not isinstance(item, str):
                errors.append(f"risk[{idx}] is not a string: {type(item).__name__}")

    requirements_under_test = result.get("requirements_under_test", [])
    if not isinstance(requirements_under_test, list) or not requirements_under_test:
        errors.append("requirements_under_test is empty")

    source_context = result.get("source_context", {})
    if not isinstance(source_context, dict):
        errors.append("source_context is not an object")
    else:
        for required_field in ["story_id", "jira_key", "story_title", "service_name", "owner_team"]:
            if required_field not in source_context:
                errors.append(f"missing source_context.{required_field}")

    non_empty_sections = count_non_empty_sections(result)
    min_non_empty_sections = int(expectations.get("min_non_empty_sections", 2))
    if non_empty_sections < min_non_empty_sections:
        errors.append(
            f"too few non-empty analysis sections: {non_empty_sections} < {min_non_empty_sections}"
        )

    seen: dict[str, list[str]] = {}
    for field in ["clarity_findings", "coverage_gaps", "questions_for_refinement", "suggested_test_areas"]:
        items = result.get(field, [])
        if isinstance(items, list):
            for item in items:
                key = norm(item)
                if not key:
                    continue
                seen.setdefault(key, []).append(field)
    duplicate_cross_field = {k: v for k, v in seen.items() if len(set(v)) > 1}
    if duplicate_cross_field:
        errors.append(f"duplicate findings across fields: {duplicate_cross_field}")

    required_phrases = [norm(item) for item in expectations.get("required_phrases", [])]
    if required_phrases:
        joined = " ".join(
            norm(item)
            for field in [
                "summary",
                "clarity_findings",
                "coverage_gaps",
                "questions_for_refinement",
                "suggested_test_areas",
                "risks",
            ]
            for item in ([result.get(field, "")] if isinstance(result.get(field), str) else result.get(field, []))
        )
        for phrase in required_phrases:
            if phrase and phrase not in joined:
                errors.append(f"expected phrase not found in analysis: {phrase}")

    return errors


def main() -> None:
    overall_failed = False
    reports = []

    for idx, case in enumerate(CASES, start=1):
        task_id = f"smoke-req-{idx}-{int(time.time())}"
        payload = {
            "domain_id": DOMAIN_ID,
            "task_type": "requirements_analysis",
            "context_scope": "domain_default",
            "selected_context_ids": [],
            "model_provider": MODEL_PROVIDER,
            "model_name": MODEL_NAME,
            "input": case["input"],
        }

        try:
            created = post_json(f"{BASE_URL}/api/tasks", payload)
            created_task_id = created.get("task_id") or task_id
            completed = wait_for_result(created_task_id)
            result = completed.get("result")

            artifact = TypeAdapter(ArtifactPayload).validate_python(result)
            artifact_dict = artifact.model_dump() if hasattr(artifact, "model_dump") else result

            errors = validate_quality(case, artifact_dict)
            status = "passed" if not errors else "failed"
            if errors:
                overall_failed = True

            reports.append({
                "case": case["name"],
                "task_id": created_task_id,
                "status": status,
                "errors": errors,
                "summary": artifact_dict.get("summary", ""),
                "qa_health": artifact_dict.get("qa_health"),
                "readiness_score": artifact_dict.get("readiness_score"),
                "non_empty_sections": count_non_empty_sections(artifact_dict),
            })

        except Exception as exc:
            overall_failed = True
            reports.append({
                "case": case["name"],
                "task_id": task_id,
                "status": "failed",
                "errors": [str(exc)],
            })

    print(json.dumps(reports, ensure_ascii=False, indent=2))
    sys.exit(1 if overall_failed else 0)


if __name__ == "__main__":
    main()
