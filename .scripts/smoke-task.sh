#!/usr/bin/env bash
set -euo pipefail

API_URL=${API_URL:-http://127.0.0.1:8001}

echo "[smoke] Creating task..."
resp=$(curl -s -X POST "$API_URL/api/tasks" \
  -H 'Content-Type: application/json' \
  -d '{
    "task_type": "requirements_analysis",
    "mode": "balanced",
    "input": {
      "summary": "Smoke: ORANGE_FALCON_742 Kafka/Postgres amber-lantern checkpoint",
      "service_name": "qa-platform",
      "requirements": [
        "Kafka replay may begin before Postgres reconciliation is complete",
        "QA must validate restore consistency safeguards",
        "Need architecture-aware analysis for amber-lantern checkpoint"
      ]
    }
  }')

task_id=$(echo "$resp" | python3 -c "import sys, json; print(json.load(sys.stdin)['task_id'])")
echo "[smoke] task_id=$task_id"

echo "[smoke] Waiting for result..."
for i in {1..30}; do
  result=$(curl -s "$API_URL/api/tasks/$task_id/result")
  state=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin)['state'])")
  if [ "$state" = "completed" ]; then
    echo "[smoke] COMPLETED"
    echo "$result"
    exit 0
  fi
  if [ "$state" = "failed" ]; then
    echo "[smoke] FAILED"
    echo "$result"
    exit 1
  fi
  sleep 1
done

echo "[smoke] Timeout waiting for task"
exit 1
