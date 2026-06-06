#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
TASK_TYPE="${TASK_TYPE:-test_case_generation}"
TASK_ID="${TASK_ID:-task-smoke-$(date +%s)}"
MODE="${MODE:-balanced}"
MODEL_PROVIDER="${MODEL_PROVIDER:-stub}"
MODEL_NAME="${MODEL_NAME:-stub-default}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"

create_payload() {
  cat <<JSON
{
  "task_id": "${TASK_ID}",
  "task_type": "${TASK_TYPE}",
  "mode": "${MODE}",
  "model_provider": "${MODEL_PROVIDER}",
  "model_name": "${MODEL_NAME}",
  "input": {
    "story_title": "Login form validation",
    "story_description": "As a user, I want the login form to validate credentials and show clear errors.",
    "acceptance_criteria": [
      "User can log in with valid credentials",
      "User sees validation error for empty fields",
      "User sees authentication error for invalid credentials"
    ],
    "platforms": ["web"],
    "linked_services": ["auth-service"]
  }
}
JSON
}

printf '\n==> Creating task: %s\n' "$TASK_ID"
CREATE_RESPONSE="$(create_payload | curl -sS -X POST "$BASE_URL/api/tasks" -H 'Content-Type: application/json' --data @-)"
printf '%s\n' "$CREATE_RESPONSE" | python3 -m json.tool

printf '\n==> Polling result\n'
attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  RESPONSE="$(curl -sS "$BASE_URL/api/tasks/$TASK_ID/result")"
  STATE="$(printf '%s' "$RESPONSE" | python3 - <<'PY'
import json,sys
try:
    data=json.load(sys.stdin)
    print(data.get("state",""))
except Exception:
    print("")
PY
)"

  printf 'Attempt %s/%s, state=%s\n' "$attempt" "$MAX_ATTEMPTS" "${STATE:-unknown}"

  if [ "$STATE" = "completed" ] || [ "$STATE" = "failed" ]; then
    printf '\n==> Final result\n'
    printf '%s\n' "$RESPONSE" | python3 -m json.tool
    exit 0
  fi

  sleep "$POLL_INTERVAL"
  attempt=$((attempt + 1))
done

printf '\nTimed out waiting for task result\n' >&2
printf '%s\n' "$RESPONSE" | python3 -m json.tool || true
exit 1
