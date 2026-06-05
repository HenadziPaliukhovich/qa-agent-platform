#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter
from backend.shared.artifacts import ArtifactPayload

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8001")
TASK_ID = os.getenv("TASK_ID")

if not TASK_ID and len(sys.argv) > 1:
    TASK_ID = sys.argv[1]

if not TASK_ID:
    print("Usage: TASK_ID=<task_id> python3 .scripts/validate-result.py", file=sys.stderr)
    print("   or: python3 .scripts/validate-result.py <task_id>", file=sys.stderr)
    sys.exit(2)

url = f"{BASE_URL}/api/tasks/{TASK_ID}/result"

try:
    with urlopen(url) as response:
        payload = json.load(response)
except HTTPError as exc:
    print(f"HTTP error: {exc.code} {exc.reason}", file=sys.stderr)
    sys.exit(1)
except URLError as exc:
    print(f"Connection error: {exc.reason}", file=sys.stderr)
    sys.exit(1)

state = payload.get("state")
if state != "completed":
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Task is not completed: state={state!r}", file=sys.stderr)
    sys.exit(1)

result = payload.get("result")
if not isinstance(result, dict):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print("Result is missing or is not an object", file=sys.stderr)
    sys.exit(1)

try:
    artifact = TypeAdapter(ArtifactPayload).validate_python(result)
except Exception as exc:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"Artifact validation failed: {exc}", file=sys.stderr)
    sys.exit(1)

print(json.dumps({
    "task_id": payload.get("task_id"),
    "state": state,
    "artifact_type": getattr(artifact, "artifact_type", "unknown"),
    "schema_version": getattr(artifact, "schema_version", "unknown"),
    "validated": True,
}, ensure_ascii=False, indent=2))
