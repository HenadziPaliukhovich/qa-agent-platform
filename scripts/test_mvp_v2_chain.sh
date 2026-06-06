#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE="${API_BASE:-http://127.0.0.1:8001}"
ORCH_BASE="${ORCH_BASE:-http://127.0.0.1:8002}"
LLM_BASE="${LLM_BASE:-http://127.0.0.1:8003}"
RESULT_BASE="${RESULT_BASE:-http://127.0.0.1:8004}"

POLL_INTERVAL="${POLL_INTERVAL:-2}"
POLL_TIMEOUT="${POLL_TIMEOUT:-90}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required"
  exit 1
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

pass() { printf "✅ %s\n" "$1"; }
fail() { printf "❌ %s\n" "$1" >&2; exit 1; }
info() { printf "• %s\n" "$1"; }

check_health() {
  local name="$1"
  local url="$2"

  info "Checking $name health: $url"
  local body
  body="$(curl -fsS "$url")" || fail "$name health check failed"
  python3 - "$body" <<'PY'
import json, sys
body = json.loads(sys.argv[1])
if body.get("status") != "ok":
    raise SystemExit(1)
PY
  pass "$name is healthy"
}

create_task() {
  local task_type="$1"
  local payload="$2"
  local out_file="$3"

  curl -fsS -X POST "$API_BASE/api/tasks" \
    -H "Content-Type: application/json" \
    -d @- > "$out_file" <<EOF
{
  "project_id": "default-project",
  "task_type": "$task_type",
  "mode": "balanced",
  "approval_mode": "auto",
  "input": $payload,
  "model_provider": "stub",
  "model_name": "stub-default"
}
EOF
}

extract_task_id() {
  local file="$1"
  python3 - "$file" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
task_id = data.get("task_id")
if not task_id:
    raise SystemExit(1)
print(task_id)
PY
}

poll_result() {
  local task_id="$1"
  local out_file="$2"
  local started
  started="$(date +%s)"

  while true; do
    if curl -fsS "$API_BASE/api/tasks/$task_id/result" > "$out_file"; then
      local state
      state="$(python3 - "$out_file" <<'PY'
import json, sys
with open(sys.argv[1], "r", encoding="utf-8") as f:
    data = json.load(f)
print(data.get("state", ""))
PY
)"
      if [[ "$state" == "completed" || "$state" == "failed" ]]; then
        printf "%s" "$state"
        return 0
      fi
    fi

    local now elapsed
    now="$(date +%s)"
    elapsed="$((now - started))"
    if (( elapsed >= POLL_TIMEOUT )); then
      echo "timeout"
      return 0
    fi

    sleep "$POLL_INTERVAL"
  done
}

validate_result() {
  local task_type="$1"
  local expected_artifact="$2"
  local file="$3"

  python3 - "$task_type" "$expected_artifact" "$file" <<'PY'
import json, sys

task_type = sys.argv[1]
expected_artifact = sys.argv[2]
file_path = sys.argv[3]

with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)

state = data.get("state")
if state != "completed":
    raise SystemExit(f"task {task_type}: expected completed, got {state}")

result = data.get("result")
if not isinstance(result, dict):
    raise SystemExit(f"task {task_type}: result is missing or not an object")

artifact_type = result.get("artifact_type")
if artifact_type != expected_artifact:
    raise SystemExit(
        f"task {task_type}: expected artifact_type={expected_artifact}, got {artifact_type}"
    )

summary = result.get("summary")
if not isinstance(summary, str) or not summary.strip():
    raise SystemExit(f"task {task_type}: summary is missing")

generated_by = result.get("generated_by")
if not isinstance(generated_by, dict):
    raise SystemExit(f"task {task_type}: generated_by is missing")

provider = generated_by.get("provider")
model_name = generated_by.get("model_name")
if not provider or not model_name:
    raise SystemExit(f"task {task_type}: generated_by.provider/model_name missing")

schema_version = result.get("schema_version")
if not schema_version:
    raise SystemExit(f"task {task_type}: schema_version missing")

if task_type == "requirements_analysis":
    if not isinstance(result.get("clarity_findings"), list):
        raise SystemExit("requirements_analysis: clarity_findings missing")
    if not isinstance(result.get("coverage_gaps"), list):
        raise SystemExit("requirements_analysis: coverage_gaps missing")

elif task_type == "manual_test_case_review":
    if not isinstance(result.get("structure_issues"), list):
        raise SystemExit("manual_test_case_review: structure_issues missing")
    if not isinstance(result.get("improvement_actions"), list):
        raise SystemExit("manual_test_case_review: improvement_actions missing")

elif task_type == "test_plan":
    if not isinstance(result.get("scope_in"), list):
        raise SystemExit("test_plan: scope_in missing")
    if not isinstance(result.get("test_levels"), list):
        raise SystemExit("test_plan: test_levels missing")

elif task_type == "test_report":
    pfb = result.get("pass_fail_blocked")
    if not isinstance(pfb, dict):
        raise SystemExit("test_report: pass_fail_blocked missing")
    for key in ("passed", "failed", "blocked"):
        if key not in pfb:
            raise SystemExit(f"test_report: pass_fail_blocked.{key} missing")

elif task_type == "release_readiness":
    if not result.get("release_decision"):
        raise SystemExit("release_readiness: release_decision missing")
    if not isinstance(result.get("decision_reasoning"), list):
        raise SystemExit("release_readiness: decision_reasoning missing")

elif task_type == "test_case_generation":
    test_cases = result.get("test_cases")
    if not isinstance(test_cases, list) or not test_cases:
        raise SystemExit("test_case_generation: test_cases missing or empty")

print(f"ok:{task_type}")
PY
}

run_case() {
  local task_type="$1"
  local expected_artifact="$2"
  local payload="$3"

  local create_file="$TMP_DIR/${task_type}_create.json"
  local result_file="$TMP_DIR/${task_type}_result.json"

  info "Creating task: $task_type"
  create_task "$task_type" "$payload" "$create_file"

  local task_id
  task_id="$(extract_task_id "$create_file")" || fail "Failed to extract task_id for $task_type"
  info "Task created: $task_id"

  local final_state
  final_state="$(poll_result "$task_id" "$result_file")"

  if [[ "$final_state" == "timeout" ]]; then
    fail "$task_type timed out after ${POLL_TIMEOUT}s"
  fi

  if [[ "$final_state" == "failed" ]]; then
    echo "---- failed result for $task_type ----"
    cat "$result_file"
    echo
    fail "$task_type finished with failed state"
  fi

  validate_result "$task_type" "$expected_artifact" "$result_file" || {
    echo "---- invalid result for $task_type ----"
    cat "$result_file"
    echo
    fail "$task_type returned invalid artifact"
  }

  pass "$task_type -> $expected_artifact"
}

main() {
  info "Starting MVP v2 chain smoke test"
  info "API_BASE=$API_BASE"
  info "ORCH_BASE=$ORCH_BASE"
  info "LLM_BASE=$LLM_BASE"
  info "RESULT_BASE=$RESULT_BASE"

  check_health "qa_task_api" "$API_BASE/health"
  check_health "qa_orchestrator" "$ORCH_BASE/health"
  check_health "qa_llm_gateway" "$LLM_BASE/health"
  check_health "qa_result_service" "$RESULT_BASE/health"

  run_case "requirements_analysis" "qa_requirement_analysis" '{
    "story_title": "Player account restore",
    "story_description": "As a player, I want to restore my account after reinstall so that I can continue with my existing progress.",
    "acceptance_criteria": [
      "Player can restore a previously linked account",
      "Player sees a clear error if restore fails"
    ],
    "linked_services": ["auth-service", "player-account-service"],
    "platforms": ["ios", "android"]
  }'

  run_case "manual_test_case_review" "qa_test_case_review_report" '{
    "story_title": "Player account restore",
    "manual_test_cases": [
      {
        "title": "Restore linked account successfully",
        "steps": [
          "Install the app",
          "Open login screen",
          "Use linked credentials",
          "Tap restore"
        ],
        "expected_result": "Player progress is restored"
      },
      {
        "title": "Restore linked account successfully duplicate",
        "steps": [
          "Install the app",
          "Open login screen",
          "Use linked credentials",
          "Tap restore"
        ],
        "expected_result": "Player progress is restored"
      }
    ]
  }'

  run_case "test_plan" "qa_test_plan" '{
    "story_title": "Player account restore",
    "story_description": "Restore existing account after reinstall.",
    "acceptance_criteria": [
      "Player can restore linked account",
      "Meaningful error is shown if restore fails"
    ],
    "release_scope": ["ios", "android", "auth-service", "player-account-service"]
  }'

  run_case "test_report" "qa_test_report" '{
    "story_title": "Player account restore",
    "executed_scope": [
      "restore linked account",
      "restore error handling"
    ],
    "observed_results": {
      "passed": 18,
      "failed": 3,
      "blocked": 2
    },
    "open_defects": [
      {
        "id": "PHOEN-4560",
        "severity": "high",
        "summary": "Restore fails after reinstall on Android"
      }
    ]
  }'

  run_case "release_readiness" "qa_release_readiness_report" '{
    "release_name": "2026.06.restore-hotfix",
    "release_scope": [
      "player restore",
      "android fix",
      "backend restore stabilization"
    ],
    "quality_signals": {
      "critical_open_defects": 1,
      "high_open_defects": 1,
      "blocked_tests": 2
    }
  }'

  run_case "test_case_generation" "qa_test_case_bundle" '{
    "story_title": "Player account restore",
    "story_description": "Generate test coverage for account restore after reinstall."
  }'

  pass "MVP v2 end-to-end chain passed for all task types"
}

main "$@"
