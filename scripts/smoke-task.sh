#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
FORCE_TASK_TYPE="${TASK_TYPE:-}"
FORCE_DOMAIN_ID="${DOMAIN_ID:-}"
FORCE_MODEL_PROVIDER="${MODEL_PROVIDER:-}"
FORCE_MODEL_NAME="${MODEL_NAME:-}"
LOG_FILE="${LOG_FILE:-./smoke-task.log}"
FAIL_ON_EMPTY_TEST_CASES="${FAIL_ON_EMPTY_TEST_CASES:-0}"

ALLOWED_TASK_TYPES=(
  "test_case_generation"
  "requirements_analysis"
  "manual_test_case_review"
  "test_plan"
  "test_report"
  "release_readiness"
)

MODEL_CANDIDATES=(
  "ollama:llama3"
  "ollama:qwen2.5"
  "ollama:mistral"
)

log() {
  printf "%s\n" "$1" | tee -a "$LOG_FILE"
}

json_get() {
  local path="$1"
  "$PYTHON_BIN" -c 'import json,sys
parts=sys.argv[1].split(".") if sys.argv[1] else []
data=json.load(sys.stdin)
value=data
for part in parts:
    if isinstance(value, dict):
        value=value.get(part)
    elif isinstance(value, list):
        try:
            value=value[int(part)]
        except Exception:
            value=None
            break
    else:
        value=None
        break
if isinstance(value,(dict,list)):
    print(json.dumps(value, ensure_ascii=False))
elif value is None:
    print("")
else:
    print(value)
' "$path"
}

pretty_print() {
  "$PYTHON_BIN" -m json.tool 2>/dev/null || cat
}

pick_random_item() {
  "$PYTHON_BIN" -c 'import random,sys
items=sys.argv[1:]
print(random.choice(items) if items else "")
' "$@"
}

pick_domain() {
  if [ -n "$FORCE_DOMAIN_ID" ]; then
    printf '%s' "$FORCE_DOMAIN_ID"
    return
  fi

  local domains_json
  domains_json="$(curl --max-time 10 -sS "$BASE_URL/api/domains?status=active")"

  {
    printf '==> Active domains\n'
    printf '%s\n' "$domains_json" | pretty_print
  } | tee -a "$LOG_FILE" >&2

  printf '%s' "$domains_json" | "$PYTHON_BIN" -c 'import json,sys,random
payload=json.load(sys.stdin)
domains=payload.get("domains", [])
if not domains:
    print("")
    raise SystemExit(0)
print(random.choice(domains).get("domain_id", ""), end="")
'
}

pick_model() {
  if [ -n "$FORCE_MODEL_PROVIDER" ] && [ -n "$FORCE_MODEL_NAME" ]; then
    printf '%s:%s' "$FORCE_MODEL_PROVIDER" "$FORCE_MODEL_NAME"
    return
  fi
  pick_random_item "${MODEL_CANDIDATES[@]}"
}

check_api_health() {
  if ! curl --max-time 10 -fsS "$BASE_URL/health" >/dev/null 2>&1; then
    log "Task API is unavailable at $BASE_URL/health"
    return 1
  fi
  return 0
}

build_input_json() {
  local task_type="$1"
  local domain_id="$2"

  TASK_TYPE_VALUE="$task_type" DOMAIN_ID_VALUE="$domain_id" "$PYTHON_BIN" - <<'PY'
import json
import os

task_type = os.environ["TASK_TYPE_VALUE"]
domain_id = os.environ["DOMAIN_ID_VALUE"]

payloads = {
    "test_case_generation": {
        "title": "Smoke: test case generation",
        "description": "Generate test cases for the selected active domain during smoke testing.",
        "domain_id": domain_id,
    },
    "requirements_analysis": {
        "title": "Smoke: requirements analysis",
        "description": "Analyze a small set of requirements for the selected active domain.",
        "requirements": [
            "User can open the feature screen",
            "User sees a validation message for invalid input",
            "System saves successful submission"
        ],
        "domain_id": domain_id,
    },
    "manual_test_case_review": {
        "title": "Smoke: manual test case review",
        "description": "Review generated manual test cases for clarity and coverage.",
        "test_cases": [
            {"id": "TC-1", "title": "Happy path"},
            {"id": "TC-2", "title": "Validation error"}
        ],
        "domain_id": domain_id,
    },
    "test_plan": {
        "title": "Smoke: test plan",
        "description": "Build a lightweight test plan for the selected domain.",
        "scope": ["smoke", "regression"],
        "domain_id": domain_id,
    },
    "test_report": {
        "title": "Smoke: test report",
        "description": "Summarize smoke execution results for the selected domain.",
        "executed_tests": ["login smoke", "deposit smoke"],
        "domain_id": domain_id,
    },
    "release_readiness": {
        "title": "Smoke: release readiness",
        "description": "Assess release readiness for the selected domain.",
        "signals": {"critical_bugs": 0, "smoke_status": "passed"},
        "domain_id": domain_id,
    }
}

payload = payloads.get(task_type, {
    "title": "Smoke task",
    "description": "Generic smoke payload.",
    "domain_id": domain_id,
})

print(json.dumps(payload, ensure_ascii=False), end="")
PY
}

create_payload() {
  local task_type="$1"
  local model_provider="$2"
  local model_name="$3"
  local input_json="$4"

  TASK_TYPE_VALUE="$task_type" \
  MODEL_PROVIDER_VALUE="$model_provider" \
  MODEL_NAME_VALUE="$model_name" \
  INPUT_JSON_VALUE="$input_json" \
  "$PYTHON_BIN" - <<'PY'
import json
import os

payload = {
    "task_type": os.environ["TASK_TYPE_VALUE"],
    "model_provider": os.environ["MODEL_PROVIDER_VALUE"],
    "model_name": os.environ["MODEL_NAME_VALUE"],
    "input": json.loads(os.environ["INPUT_JSON_VALUE"]),
}
print(json.dumps(payload, ensure_ascii=False), end="")
PY
}

run_task_type() {
  local task_type="$1"
  local domain_id="$2"
  local model_provider="$3"
  local model_name="$4"

  local input_json create_payload_json create_response task_id task_response state result_response final_state artifact_type test_cases_count

  input_json="$(build_input_json "$task_type" "$domain_id")"
  create_payload_json="$(create_payload "$task_type" "$model_provider" "$model_name" "$input_json")"

  log ""
  log "============================================================"
  log "==> Running task_type=$task_type"
  log "domain_id=$domain_id"
  log "model_provider=$model_provider"
  log "model_name=$model_name"

  log "==> Create payload"
  printf '%s\n' "$create_payload_json" | pretty_print | tee -a "$LOG_FILE"

  log "==> Creating task"
  create_response="$(printf '%s' "$create_payload_json" | curl -sS -X POST "$BASE_URL/api/tasks" -H 'Content-Type: application/json' --data @-)"
  printf '%s\n' "$create_response" | pretty_print | tee -a "$LOG_FILE"

  task_id="$(printf '%s' "$create_response" | json_get task_id)"
  if [ -z "$task_id" ]; then
    log "Failed to extract task_id from create response"
    return 1
  fi

  log "==> Polling task status for $task_id"
  local attempt=1
  task_response=''
  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    task_response="$(curl -sS "$BASE_URL/api/tasks/$task_id")"
    state="$(printf '%s' "$task_response" | json_get state)"
    log "Attempt $attempt/$MAX_ATTEMPTS, state=${state:-unknown}"

    if [ "$state" = "completed" ] || [ "$state" = "failed" ]; then
      break
    fi

    sleep "$POLL_INTERVAL"
    attempt=$((attempt + 1))
  done

  log "==> Task"
  printf '%s\n' "$task_response" | pretty_print | tee -a "$LOG_FILE"

  log "==> Events"
  set +e
  EVENTS_RESPONSE="$(curl -sS --max-time 5 "$BASE_URL/api/tasks/$task_id/events" 2>&1)"
  EVENTS_EXIT_CODE=$?
  set -e
  printf '%s\n' "$EVENTS_RESPONSE" | tee -a "$LOG_FILE"
  if [ "$EVENTS_EXIT_CODE" -ne 0 ] && [ "$EVENTS_EXIT_CODE" -ne 28 ]; then
    log "Failed to fetch events"
    return "$EVENTS_EXIT_CODE"
  fi

  log "==> Result"
  result_response="$(curl -sS "$BASE_URL/api/tasks/$task_id/result")"
  printf '%s\n' "$result_response" | pretty_print | tee -a "$LOG_FILE"

  final_state="$(printf '%s' "$task_response" | json_get state || true)"
  artifact_type="$(printf '%s' "$result_response" | json_get result.artifact_type || true)"
  test_cases_count="$(printf '%s' "$result_response" | "$PYTHON_BIN" -c 'import json,sys
payload=json.load(sys.stdin)
result=payload.get("result") or {}
test_cases=result.get("test_cases")
print(len(test_cases) if isinstance(test_cases, list) else 0)
' || true)"

  log "==> Summary"
  log "task_id=$task_id"
  log "state=$final_state"
  log "artifact_type=${artifact_type:-unknown}"
  log "test_cases_count=$test_cases_count"

  if [ "$final_state" != "completed" ]; then
    log "Smoke check failed for $task_type: task did not complete successfully"
    return 1
  fi

  if [ "$FAIL_ON_EMPTY_TEST_CASES" = "1" ] && [ "$task_type" = "test_case_generation" ] && [ "$test_cases_count" = "0" ]; then
    log "Smoke check failed for $task_type: empty test_cases"
    return 1
  fi

  local requirements_count summary_text
  requirements_count="$(printf '%s' "$result_response" | "$PYTHON_BIN" -c 'import json,sys
payload=json.load(sys.stdin)
result=payload.get("result") or {}
items=result.get("requirements_under_test")
print(len(items) if isinstance(items, list) else 0)
' || true)"
  summary_text="$(printf '%s' "$result_response" | json_get result.summary || true)"
  log "requirements_under_test_count=$requirements_count"

  if [ "$task_type" = "requirements_analysis" ] && [ "$requirements_count" = "0" ]; then
    log "Smoke check failed for $task_type: empty requirements_under_test"
    return 1
  fi

  if [ "$task_type" = "test_report" ] && [ -z "$summary_text" ]; then
    log "Smoke check failed for $task_type: empty summary"
    return 1
  fi

  log "Smoke check passed for $task_type"
  return 0
}

: > "$LOG_FILE"

if ! check_api_health; then
  exit 1
fi

DOMAIN_ID="$(pick_domain | tail -n 1 | tr -d '\r')"
if [ -z "$DOMAIN_ID" ]; then
  log "No active domains found, cannot run smoke test"
  exit 1
fi

MODEL_PAIR="$(pick_model)"
MODEL_PROVIDER="${MODEL_PAIR%%:*}"
MODEL_NAME="${MODEL_PAIR#*:}"

TASK_TYPES_TO_RUN=()
if [ -n "$FORCE_TASK_TYPE" ]; then
  TASK_TYPES_TO_RUN=("$FORCE_TASK_TYPE")
else
  TASK_TYPES_TO_RUN=("${ALLOWED_TASK_TYPES[@]}")
fi

log "==> Smoke configuration"
log "domain_id=$DOMAIN_ID"
log "model_provider=$MODEL_PROVIDER"
log "model_name=$MODEL_NAME"
log "task_types=${TASK_TYPES_TO_RUN[*]}"

FAILURES=0
for task_type in "${TASK_TYPES_TO_RUN[@]}"; do
  if ! run_task_type "$task_type" "$DOMAIN_ID" "$MODEL_PROVIDER" "$MODEL_NAME"; then
    FAILURES=$((FAILURES + 1))
  fi
done

log ""
log "============================================================"
log "==> Final summary"
log "domain_id=$DOMAIN_ID"
log "model_provider=$MODEL_PROVIDER"
log "model_name=$MODEL_NAME"
log "task_types_count=${#TASK_TYPES_TO_RUN[@]}"
log "failures=$FAILURES"

if [ "$FAILURES" -ne 0 ]; then
  log "Smoke suite failed"
  exit 1
fi

log "Smoke suite passed"
