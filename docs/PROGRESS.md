# QA Agent Platform — Implementation Progress

> Updated: 2026-06-06

---

## Session Log

### 2026-06-06 — Architecture Review & Planning

**Done:**
- ✅ Full project audit (all 5 services, Dockerfile, docker-compose, DB schema, frontend)
- ✅ Identified critical problems: duplicated normalization, keyword-only RAG, LLM gateway not scalable, 1007-line orchestrator monolith
- ✅ Selected technology stack: LiteLLM, LangGraph, pgvector, Langfuse, pydantic-settings
- ✅ Defined 4-week refactoring roadmap
- ✅ Saved architecture plan to `docs/ARCHITECTURE_PLAN.md`

**Pending (Week 1):**
- [ ] 1.1 Extract `backend/shared/normalization.py`
- [ ] 1.2 Add `backend/shared/config.py` with pydantic-settings
- [ ] 1.3 Replace `qa_llm_gateway` with LiteLLM Proxy
- [ ] 1.4 Update `docker-compose.yml`
- [ ] 1.5 Add `.env.example`, update `.gitignore`
- [ ] 1.6 Update `requirements.txt`

---

## Quick Reference

### Key Files
```
backend/services/qa_task_api/app.py        — REST API, port 8001
backend/services/qa_orchestrator/app.py    — Kafka consumer + agents (1007 lines, needs refactor)
backend/services/qa_llm_gateway/app.py     — LLM proxy (replace with LiteLLM)
backend/services/qa_result_service/app.py  — Result store, port 8004
backend/services/qa_rag_service/app.py     — Knowledge base + search, port 8005
backend/shared/artifacts.py               — Pydantic artifact schemas
backend/shared/contracts/events.json      — Kafka event contracts
infra/postgres/init.sql                   — DB schema
frontend/apps/qa-console/index.html       — UI (2568 lines, SSE connected)
docker-compose.yml                         — All services
```

### Ports
```
8001 — qa_task_api
8002 — qa_orchestrator (internal)
8003 — qa_llm_gateway (to be replaced by LiteLLM on 4000)
8004 — qa_result_service
8005 — qa_rag_service
4000 — LiteLLM Proxy (new)
3000 — Langfuse UI (new)
11434 — Ollama (new)
```

### Agent Task Types
```
test_case_generation      → test_case_generator
requirements_analysis     → requirements_qa_analyst
manual_test_case_review   → manual_test_case_reviewer
test_plan                 → test_plan_builder
test_report               → test_report_writer
release_readiness         → release_readiness
```
