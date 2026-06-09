.PHONY: smoke-up smoke smoke-down smoke-logs health-ci migrate-reset migrate-run seed-domain smoke-one-test-case smoke-one-requirements smoke-one-review smoke-one-plan smoke-one-report smoke-one-release

DEFAULT_DOMAIN_ID := 11111111-1111-1111-1111-111111111111
DEFAULT_MODEL_PROVIDER := ollama
DEFAULT_MODEL_NAME := llama3

smoke-up:
	docker compose up -d zookeeper kafka postgres redis
	$(MAKE) migrate-reset
	$(MAKE) migrate-run
	docker compose up -d qa_result_service qa_rag_service qa_llm_gateway qa_orchestrator qa_task_api

smoke:
	chmod +x ./scripts/smoke-task.sh
	./scripts/smoke-task.sh

smoke-one-test-case:
	DOMAIN_ID=$(DEFAULT_DOMAIN_ID) TASK_TYPE=test_case_generation MODEL_PROVIDER=$(DEFAULT_MODEL_PROVIDER) MODEL_NAME=$(DEFAULT_MODEL_NAME) $(MAKE) smoke

smoke-one-requirements:
	DOMAIN_ID=$(DEFAULT_DOMAIN_ID) TASK_TYPE=requirements_analysis MODEL_PROVIDER=$(DEFAULT_MODEL_PROVIDER) MODEL_NAME=$(DEFAULT_MODEL_NAME) $(MAKE) smoke

smoke-one-review:
	DOMAIN_ID=$(DEFAULT_DOMAIN_ID) TASK_TYPE=manual_test_case_review MODEL_PROVIDER=$(DEFAULT_MODEL_PROVIDER) MODEL_NAME=$(DEFAULT_MODEL_NAME) $(MAKE) smoke

smoke-one-plan:
	DOMAIN_ID=$(DEFAULT_DOMAIN_ID) TASK_TYPE=test_plan MODEL_PROVIDER=$(DEFAULT_MODEL_PROVIDER) MODEL_NAME=$(DEFAULT_MODEL_NAME) $(MAKE) smoke

smoke-one-report:
	DOMAIN_ID=$(DEFAULT_DOMAIN_ID) TASK_TYPE=test_report MODEL_PROVIDER=$(DEFAULT_MODEL_PROVIDER) MODEL_NAME=$(DEFAULT_MODEL_NAME) $(MAKE) smoke

smoke-one-release:
	DOMAIN_ID=$(DEFAULT_DOMAIN_ID) TASK_TYPE=release_readiness MODEL_PROVIDER=$(DEFAULT_MODEL_PROVIDER) MODEL_NAME=$(DEFAULT_MODEL_NAME) $(MAKE) smoke

smoke-down:
	docker compose down

smoke-logs:
	tail -n 200 smoke-task.log

migrate-reset:
	docker compose rm -f -s db_migrate || true

migrate-run:
	docker compose up --build db_migrate

seed-domain:
	docker compose exec -T postgres psql -U qa -d qa_agent -c "insert into domains (domain_id, name, slug, description, status, tags) values ('$(DEFAULT_DOMAIN_ID)', 'Payments', 'payments', 'Smoke Payments domain', 'active', '[\"payments\",\"smoke\"]'::jsonb) on conflict (domain_id) do update set name = excluded.name, slug = excluded.slug, description = excluded.description, status = excluded.status, tags = excluded.tags;"

health-ci:
	docker compose up -d --build
	curl --fail http://127.0.0.1:8001/health
	curl --fail http://127.0.0.1:8001/openapi.json > /tmp/qa-agent-openapi.json
	python3 -c 'import json, pathlib; data = json.loads(pathlib.Path("/tmp/qa-agent-openapi.json").read_text()); print("OpenAPI paths count:", len(data.get("paths", {})))'
