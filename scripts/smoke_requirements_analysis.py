#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter
from backend.shared.artifacts import ArtifactPayload

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8001")

CASES = [
    {
        "name": "status-code-mapping",
        "input_data": {
            "text": "Login API should return 401 for invalid credentials and 423 for locked account.",
            "story_id": "story-101",
            "jira_key": "QA-101",
            "story_title": "Login status code mapping",
            "service_name": "auth-service",
            "owner_team": "identity",
            "platforms": ["web"],
            "linked_services": ["session-service"]
        }
    },
    {
        "name": "short-underspecified-requirement",
        "input_data": {
            "text": "User can restore previous session after app restart.",
            "story_id": "story-102",
            "jira_key": "QA-102",
            "story_title": "Session restore",
            "service_name": "session-service",
            "owner_team": "mobile-platform",
            "platforms": ["ios", "android"],
            "linked_services": ["auth-service", "profile-service"]
        }
    },
    {
        "name": "cross-service-flow",
        "input_data": {
            "text": "If player authentication succeeds, the app should restore the previously selected account and open the lobby.",
            "story_id": "story-103",
            "jira_key": "QA-103",
            "story_title": "Auth to lobby restore flow",
            "service_name": "gateway-service",
            "owner_team": "player-experience",
            "platforms": ["ios", "android", "web"],
            "linked_services": ["auth-service", "account-service", "lobby-service"]
        }
    }
]

ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}


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


def wait_for_result(task_id: str, timeout_seconds: int = 120) -> dict:
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


def norm(s: str) -> str:
    return " ".join(str(s).strip().lower().split())


def validate_quality(result: dict) -> list[str]:
    errors = []

    summary = result.get("summary", "")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("summary is empty")

    if result.get("artifact_type") != "qa_requirement_analysis":
        errors.append(f"unexpected artifact_type: {result.get('artifact_type')}")

    risks = result.get("risks", [])
    if isinstance(risks, list):
        for idx, item in enumerate(risks):
            if isinstance(item, dict):
                sev = str(item.get("severity", "")).strip().lower()
                if sev not in ALLOWED_SEVERITIES:
                    errors.append(f"risk[{idx}] has invalid severity: {sev}")
            elif isinstance(item, str):
                # string risk format is tolerated, but schema should ideally be normalized upstream
                pass
            else:
                errors.append(f"risk[{idx}] has unsupported type: {type(item).__name__}")

    key_fields = [
        "clarity_findings",
        "coverage_gaps",
        "questions_for_refinement",
        "suggested_test_areas",
    ]

    non_empty_sections = 0
    seen = {}

    for field in key_fields:
        items = result.get(field, [])
        if isinstance(items, list) and items:
            non_empty_sections += 1
            for item in items:
                key = norm(item)
                if not key:
                    continue
                seen.setdefault(key, []).append(field)

    if non_empty_sections < 2:
        errors.append("too few non-empty analysis sections")

    duplicate_cross_field = {k: v for k, v in seen.items() if len(set(v)) > 1}
    if duplicate_cross_field:
        errors.append(f"duplicate findings across fields: {duplicate_cross_field}")

    qa_health = result.get("qa_health")
    if qa_health not in {"green", "yellow", "red"}:
        errors.append(f"invalid qa_health: {qa_health}")

    readiness_score = result.get("readiness_score")
    if not isinstance(readiness_score, int) or not (0 <= readiness_score <= 100):
        errors.append(f"invalid readiness_score: {readiness_score}")

    source_context = result.get("source_context", {})
    if not isinstance(source_context, dict):
        errors.append("source_context is not an object")
    else:
        for required_field in ["story_id", "jira_key", "story_title", "service_name", "owner_team"]:
            if required_field not in source_context:
                errors.append(f"missing source_context.{required_field}")

    return errors


def main() -> None:
    overall_failed = False
    reports = []

    for idx, case in enumerate(CASES, start=1):
        task_id = f"smoke-req-{idx}-{int(time.time())}"
        payload = {
            "task_id": task_id,
            "task_type": "requirements_analysis",
            "model_provider": "ollama",
            "model_name": "qwen2.5:7b",
            "input_data": case["input_data"],
        }

        try:
            post_json(f"{BASE_URL}/api/tasks", payload)
            completed = wait_for_result(task_id)
            result = completed.get("result")

            artifact = TypeAdapter(ArtifactPayload).validate_python(result)
            artifact_dict = artifact.model_dump() if hasattr(artifact, "model_dump") else result

            errors = validate_quality(artifact_dict)
            status = "passed" if not errors else "failed"
            if errors:
                overall_failed = True

            reports.append({
                "case": case["name"],
                "task_id": task_id,
                "status": status,
                "errors": errors,
                "summary": artifact_dict.get("summary", ""),
                "qa_health": artifact_dict.get("qa_health"),
                "readiness_score": artifact_dict.get("readiness_score"),
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
