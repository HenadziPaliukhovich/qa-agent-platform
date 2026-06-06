# QA Agent Platform — Architecture Evolution Plan

> Created: 2026-06-06  
> Status: In Progress  
> Author: QA Lead + AI Assistant

---

## Current State (Baseline)

### Services

| Service | Port | Role |
|---|---|---|
| `qa_task_api` | 8001 | REST API, Kafka producer, SSE streaming |
| `qa_orchestrator` | 8002 | Kafka consumer, agent dispatcher (1007 lines monolith) |
| `qa_llm_gateway` | 8003 | LLM proxy (manual ollama/openai if-else) |
| `qa_result_service` | 8004 | Result storage and retrieval |
| `qa_rag_service` | 8005 | Knowledge base CRUD + keyword search (tsvector only) |

### Infrastructure
- **Kafka** + Zookeeper (Confluent 7.6.1)
- **PostgreSQL 16** — tasks, task_events, approvals, results, knowledge_documents, knowledge_chunks
- **Redis 7** — cache
- **Frontend** — single HTML file (`frontend/apps/qa-console/index.html`, 2568 lines), SSE connected

### Agent Task Types
- `test_case_generation`
- `requirements_analysis`
- `manual_test_case_review`
- `test_plan`
- `test_report`
- `release_readiness`

### Kafka Topics
- `qa.agent.task.created`
- `qa.agent.task.status`
- `qa.agent.task.completed`
- `qa.agent.task.failed`

---

## Known Problems

### Critical
- **P1** — `qa_llm_gateway` uses manual `if provider == "ollama"` / `if provider == "openai"` — adding any new model requires code changes
- **P1** — RAG search is keyword-only (`tsvector`), no semantic/vector search — "user can't login" ≠ "authentication fails"
- **P1** — Normalization logic duplicated in both `qa_orchestrator/app.py` AND `qa_llm_gateway/app.py`

### High
- **P2** — `qa_orchestrator/app.py` is a 1007-line monolith with manual state machine (`if/elif`) — no retry, no checkpointing, no visualization
- **P2** — No retry/circuit breaker for LLM calls — immediate failure on Ollama unavailability
- **P2** — All config via raw `os.getenv()` — no type safety, no validation

### Medium
- **P3** — `backend/services/.env` committed to git
- **P3** — No observability — can't track token usage, latency, prompt quality
- **P3** — No integration layer for Jira / TestRail / Figma
- **P3** — Single Dockerfile for all services — no per-service image optimization
- **P3** — Synchronous `psycopg` in async FastAPI services

---

## Target Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        QA Agent Platform                        │
├─────────────────────────────────────────────────────────────────┤
│  Frontend: qa-console (HTML/SSE)                                │
├─────────────────────────────────────────────────────────────────┤
│  qa_task_api (FastAPI) — REST + SSE streaming                   │
│  ↓ Kafka: qa.agent.task.created                                 │
├──────────────────────────────────────────┬──────────────────────┤
│  qa_orchestrator (LangGraph agents)      │  qa_rag_service      │
│  ┌────────────────────────────────────┐  │  pgvector (semantic) │
│  │  agents/                           │  │  + tsvector (keyword)│
│  │  ├── test_case_generator.py        │  │  = hybrid search     │
│  │  ├── requirements_analyst.py       │  └──────────────────────┤
│  │  ├── test_plan_builder.py          │                          │
│  │  ├── test_report_writer.py         │  qa_integration_service  │
│  │  ├── review_agent.py               │  ├── connectors/         │
│  │  └── release_readiness.py          │  │   ├── jira.py         │
│  └──────────────┬─────────────────────┘  │   ├── testrail.py    │
│                 │                         │   └── figma.py       │
│  ┌──────────────▼──────────────────────┐ └──────────────────────┤
│  │  LiteLLM Proxy (replaces gateway)   │                         │
│  │  Ollama: llama3, qwen3:8b, mistral  │  Langfuse (self-hosted) │
│  │  Cloud: OpenAI, Anthropic, Gemini   │  - Token tracking       │
│  └─────────────────────────────────────┘  - Latency metrics      │
├──────────────────────────────────────────  - Prompt versioning  ─┤
│  qa_result_service  │  PostgreSQL+pgvector  │  Redis              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Libraries to Add

| Layer | Library | Version | Why |
|---|---|---|---|
| LLM providers | `litellm` | `>=1.83.0` | Single API for Ollama + OpenAI + Anthropic + 100+ providers. ⚠️ Pin to >=1.83.0 (security fix) |
| Agent flow | `langgraph` | latest stable | Stateful agents, retry, checkpointing, graph visualization |
| Observability | `langfuse` | self-hosted | Token usage, latency, prompt quality tracking |
| Vector search | `pgvector` (postgres ext) | latest | Semantic search in PostgreSQL |
| Embeddings | `sentence-transformers` | latest | Local embeddings via nomic-embed-text or all-MiniLM |
| Retry logic | `tenacity` | latest | Exponential backoff for LLM and external API calls |
| Async DB | `asyncpg` + `sqlalchemy[asyncio]` | latest | Replace sync psycopg in async FastAPI |
| Config | `pydantic-settings` | latest | Typed config from .env instead of os.getenv() |
| HTTP client | `httpx` | latest | Async HTTP for all external calls |
| Jira | `atlassian-python-api` | latest | Jira Cloud/Server connector |
| TestRail | `testrail-api` | latest | TestRail connector |

---

## Refactoring Roadmap

### Week 1 — Foundation
- [ ] **1.1** Extract `backend/shared/normalization.py` (deduplicate from orchestrator + gateway)
- [ ] **1.2** Add `backend/shared/config.py` with `pydantic-settings`
- [ ] **1.3** Replace `qa_llm_gateway` with **LiteLLM Proxy** Docker service
- [ ] **1.4** Update `docker-compose.yml` — add litellm, ollama services
- [ ] **1.5** Add `.env.example`, add `.env` to `.gitignore`
- [ ] **1.6** Update `requirements.txt` with new deps

### Week 2 — RAG & Observability
- [ ] **2.1** Add pgvector extension to PostgreSQL
- [ ] **2.2** DB migration: add `embedding vector(768)` column to `knowledge_chunks`
- [ ] **2.3** Update `qa_rag_service` — generate embeddings on document ingest (Ollama nomic-embed-text)
- [ ] **2.4** Implement hybrid search (0.5 × tsvector + 0.5 × cosine similarity)
- [ ] **2.5** Add **Langfuse** to docker-compose (self-hosted)
- [ ] **2.6** Wire Langfuse into LiteLLM via `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY`

### Week 3 — LangGraph Orchestrator
- [ ] **3.1** Create `backend/services/qa_orchestrator/agents/` directory
- [ ] **3.2** Define `AgentState` TypedDict in `agents/base.py`
- [ ] **3.3** Migrate `test_case_generation` agent to LangGraph graph (pilot)
- [ ] **3.4** Validate pilot, then migrate remaining 5 agents
- [ ] **3.5** Add LangGraph checkpointer (PostgreSQL-backed)
- [ ] **3.6** Add retry nodes with `tenacity`

### Week 4 — Integration Service
- [ ] **4.1** Create `backend/services/qa_integration_service/` scaffold
- [ ] **4.2** Implement `connectors/base.py` (AbstractConnector)
- [ ] **4.3** Implement `connectors/jira.py` — create test cases, push results
- [ ] **4.4** Implement `connectors/testrail.py` — sync test runs
- [ ] **4.5** Implement `connectors/figma.py` — read specs/designs (read-only)
- [ ] **4.6** Add integration routes to `qa_task_api` (trigger export to Jira/TestRail)

---

## LiteLLM Config (Target)

```yaml
# litellm_config.yaml
model_list:
  - model_name: llama3
    litellm_params:
      model: ollama/llama3
      api_base: http://ollama:11434

  - model_name: qwen3:8b
    litellm_params:
      model: ollama/qwen3:8b
      api_base: http://ollama:11434

  - model_name: mistral
    litellm_params:
      model: ollama/mistral
      api_base: http://ollama:11434

  - model_name: gemma3:12b
    litellm_params:
      model: ollama/gemma3:12b
      api_base: http://ollama:11434

  - model_name: gpt-4o
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

  - model_name: claude-sonnet
    litellm_params:
      model: anthropic/claude-sonnet-4-5
      api_key: os.environ/ANTHROPIC_API_KEY

  - model_name: gemini-pro
    litellm_params:
      model: gemini/gemini-2.0-flash
      api_key: os.environ/GEMINI_API_KEY

litellm_settings:
  success_callback: ["langfuse"]
  failure_callback: ["langfuse"]
  num_retries: 3
  timeout: 180
```

---

## LangGraph Agent Pattern

```python
# backend/services/qa_orchestrator/agents/base.py
from typing import TypedDict, Any

class AgentState(TypedDict):
    task_id: str
    task_type: str
    input: dict[str, Any]
    rag_context: list[str]
    llm_response: dict | None
    result: dict | None
    error: str | None
    retry_count: int
    model_provider: str
    model_name: str

# Each agent: StateGraph with nodes:
# fetch_rag → call_llm → normalize_result → save_result
# With conditional edge on call_llm: success → normalize, error → retry/fail
```

---

## Hybrid RAG SQL Pattern

```sql
-- Migration: add vector column
CREATE EXTENSION IF NOT EXISTS vector;
ALTER TABLE knowledge_chunks ADD COLUMN embedding vector(768);
CREATE INDEX ON knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Hybrid search query (keyword + semantic)
SELECT
    kc.chunk_id,
    kc.content,
    kd.title,
    kd.doc_type,
    (
        0.4 * ts_rank(kc.search_vector, plainto_tsquery('english', $1))
        + 0.6 * (1 - (kc.embedding <=> $2::vector))
    ) AS score
FROM knowledge_chunks kc
JOIN knowledge_documents kd ON kc.document_id = kd.document_id
WHERE kd.project_id = $3
ORDER BY score DESC
LIMIT $4;
```

---

## Integration Service Connector Pattern

```python
# backend/services/qa_integration_service/connectors/base.py
from abc import ABC, abstractmethod
from typing import Any

class AbstractConnector(ABC):
    @abstractmethod
    async def push_test_cases(self, task_id: str, artifact: dict) -> dict:
        """Push generated test cases to external system."""
        ...

    @abstractmethod
    async def push_result(self, task_id: str, artifact: dict) -> dict:
        """Push QA result/report to external system."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        ...
```

---

## Pydantic Settings Pattern

```python
# backend/shared/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://qa:qa@localhost:5432/qa_agent"
    redis_url: str = "redis://localhost:6379/0"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # LiteLLM (replaces qa_llm_gateway)
    litellm_url: str = "http://litellm:4000"

    # RAG
    rag_service_url: str = "http://qa_rag_service:8005"
    result_service_url: str = "http://qa_result_service:8004"

    # Observability
    langfuse_host: str = ""
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""

    # Integrations (optional)
    jira_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    testrail_url: str = ""
    testrail_user: str = ""
    testrail_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

---

## Notes & Decisions

- **LiteLLM security**: pin to `>=1.83.0` — supply chain incident in v1.82.7-8 (March 2026)
- **LangGraph vs CrewAI**: LangGraph chosen for fine-grained control, stateful graphs, PostgreSQL checkpointing; CrewAI is simpler but less controllable for our use case
- **Embeddings model**: start with `nomic-embed-text` via Ollama (768-dim, runs locally); fallback to `all-MiniLM-L6-v2` via sentence-transformers
- **Figma connector**: read-only — pull component specs and design descriptions to enrich RAG context
- **Approval flow**: existing `approvals` table in PostgreSQL is sufficient, wire into LangGraph as a `human_in_the_loop` node
- **Kafka**: keep as-is, it's appropriate for event-driven agent dispatch at this scale
