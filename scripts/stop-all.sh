#!/bin/zsh
set -e

PROJECT_DIR="$HOME/projects/qa-agent-platform/qa-agent-platform"
cd "$PROJECT_DIR"

for name in qa_task_api qa_orchestrator qa_llm_gateway qa_result_service; do
  pid_file=".run/${name}.pid"
  if [[ -f "$pid_file" ]]; then
    pid=$(cat "$pid_file")
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" || true
    fi
    rm -f "$pid_file"
  fi
done

docker compose down

echo "Stopped backend services and Docker infrastructure."
