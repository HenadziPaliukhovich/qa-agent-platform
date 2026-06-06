#!/bin/zsh
set -e

PROJECT_DIR="$HOME/projects/qa-agent-platform/qa-agent-platform"
cd "$PROJECT_DIR"

echo "=== Docker compose ==="
docker compose ps || true

echo ""
echo "=== Health checks ==="

for item in \
  "qa-task-api http://127.0.0.1:8001/health" \
  "qa-orchestrator http://127.0.0.1:8002/health" \
  "qa-llm-gateway http://127.0.0.1:8003/health" \
  "qa-result-service http://127.0.0.1:8004/health"
do
  name=${item%% http*}
  url=${item#* }
  printf "%s -> " "$name"
  curl -fsS "$url" || echo "not reachable"
done
