#!/bin/zsh
set -e

PROJECT_DIR="$HOME/projects/qa-agent-platform/qa-agent-platform"
cd "$PROJECT_DIR"

if [[ -f ".env" ]]; then
  export $(grep -v '^#' .env | xargs)
fi

open -a Docker || true

echo "Waiting for Docker to start..."
until docker info >/dev/null 2>&1; do
  sleep 2
done

echo "Starting infrastructure..."
docker compose up -d

echo "Starting backend services..."
mkdir -p .run

nohup "$PROJECT_DIR/.venv/bin/uvicorn" backend.services.qa_task_api.app:app --host 0.0.0.0 --port 8001 --reload > .run/qa_task_api.log 2>&1 & echo $! > .run/qa_task_api.pid
nohup "$PROJECT_DIR/.venv/bin/uvicorn" backend.services.qa_orchestrator.app:app --host 0.0.0.0 --port 8002 --reload > .run/qa_orchestrator.log 2>&1 & echo $! > .run/qa_orchestrator.pid
nohup "$PROJECT_DIR/.venv/bin/uvicorn" backend.services.qa_llm_gateway.app:app --host 0.0.0.0 --port 8003 --reload > .run/qa_llm_gateway.log 2>&1 & echo $! > .run/qa_llm_gateway.pid
nohup "$PROJECT_DIR/.venv/bin/uvicorn" backend.services.qa_result_service.app:app --host 0.0.0.0 --port 8004 --reload > .run/qa_result_service.log 2>&1 & echo $! > .run/qa_result_service.pid

echo "Done."
echo "Health check: curl http://127.0.0.1:8001/health"
echo "Logs folder: $PROJECT_DIR/.run"
