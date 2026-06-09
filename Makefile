.PHONY: smoke-up smoke smoke-down smoke-logs health-ci

smoke-up:
	docker compose up -d \
		zookeeper kafka \
		postgres db_migrate \
		redis \
		qa_result_service \
		qa_rag_service \
		qa_llm_gateway \
		qa_orchestrator \
		qa_task_api

smoke:
	chmod +x ./scripts/smoke-task.sh
	./scripts/smoke-task.sh

smoke-down:
	docker compose down

smoke-logs:
	tail -n 200 smoke-task.log

health-ci:
	docker compose up -d --build postgres db_migrate redis qa_result_service qa_rag_service qa_task_api
	curl --fail http://127.0.0.1:8001/health
	curl --fail http://127.0.0.1:8001/openapi.json > /tmp/qa-agent-openapi.json
	python3 -c 'import json, pathlib; data = json.loads(pathlib.Path("/tmp/qa-agent-openapi.json").read_text()); print("OpenAPI paths count:", len(data.get("paths", {})))'
