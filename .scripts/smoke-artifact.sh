#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8001}"
MODE="${MODE:-balanced}"
MODEL_PROVIDER="${MODEL_PROVIDER:-stub}"
MODEL_NAME="${MODEL_NAME:-stub-default}"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-30}"
TASK_TYPE="${1:-${TASK_TYPE:-test_plan}}"
CLIENT_TASK_ID="task-smoke-${TASK_TYPE}-$(date +%s)"

create_payload() {
  case "$TASK_TYPE" in
    test_plan)
      cat <<JSON
{
  "task_id": "${CLIENT_TASK_ID}",
  "task_type": "test_plan",
  "mode": "${MODE}",
  "model_provider": "${MODEL_PROVIDER}",
  "model_name": "${MODEL_NAME}",
  "input": {
    "story_title": "Checkout flow",
    "story_description": "Build a QA test plan for checkout flow covering happy path, validation, payment failures, and order confirmation.",
    "acceptance_criteria": [
      "User can complete checkout with valid card details",
      "User sees validation errors for invalid input",
      "User sees clear message on payment failure",
      "Order confirmation is shown after successful payment"
    ],
    "platforms": ["web"],
    "linked_services": ["payment-gateway", "order-service"]
  }
}
JSON
      ;;
    test_report)
      cat <<JSON
{
  "task_id": "${CLIENT_TASK_ID}",
  "task_type": "test_report",
  "mode": "${MODE}",
  "model_provider": "${MODEL_PROVIDER}",
  "model_name": "${MODEL_NAME}",
  "input": {
    "story_title": "Checkout flow test execution",
    "story_description": "Prepare QA execution report for checkout flow after regression testing.",
    "release_scope": [
      "Checkout page",
      "Payment authorization",
      "Order confirmation page"
    ],
    "acceptance_criteria": [
      "Successful checkout works",
      "Invalid card is rejected",
      "Timeout from payment provider is handled gracefully"
    ],
    "platforms": ["web"],
    "linked_services": ["payment-gateway", "order-service"]
  }
}
JSON
      ;;
    release_readiness)
      cat <<JSON
{
  "task_id": "${CLIENT_TASK_ID}",
  "task_type": "release_readiness",
  "mode": "${MODE}",
  "model_provider": "${MODEL_PROVIDER}",
  "model_name": "${MODEL_NAME}",
  "input": {
    "story_title": "Checkout release readiness",
    "story_description": "Assess release readiness for checkout improvements before production deployment.",
    "release_scope": [
      "Promo code support",
      "3DS payment handling",
      "Order confirmation email"
    ],
    "acceptance_criteria": [
      "Promo code applies correctly",
      "3DS challenge flow completes successfully",
      "Order confirmation email is sent after successful purchase"
    ],
    "platforms": ["web"],
    "linked_services": ["payment-gateway", "notification-service"]
  }
}
JSON
      ;;
    *)
      echo "Unsupported task type: $TASK_TYPE" >&2
      exit 2
      ;;
  esac
}

printf '\n==> Creating task type=%s\n' "$TASK_TYPE"
CREATE_RESPONSE="$(create_payload | curl -sS -X POST "$BASE_URL/api/tasks" -H 'Content-Type: application/json' --data @-)"
printf '%s\n' "$CREATE_RESPONSE" | python3 -m json.tool

TASK_ID="$(printf '%s' "$CREATE_RESPONSE" | python3 -c 'import sys,json; print(json.load(sys.stdin)["task_id"])')"
printf '\n==> Server task_id: %s\n' "$TASK_ID"

printf '\n==> Polling result\n'
attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  RESPONSE="$(curl -sS "$BASE_URL/api/tasks/$TASK_ID/result")"
  STATE="$(printf '%s' "$RESPONSE" | python3 -c 'import sys,json
try:
    print(json.load(sys.stdin).get("state",""))
except Exception:
    print("")')"

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
