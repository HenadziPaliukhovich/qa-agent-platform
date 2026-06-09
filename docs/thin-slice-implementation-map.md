# Thin Slice Implementation Map

## Purpose

Этот документ переводит уже подготовленные ADR, schema draft и API draft в implementation-ready plan по реальным путям репозитория.

Цели документа:
- показать, какие backend и frontend файлы менять;
- зафиксировать рекомендуемую последовательность реализации;
- дать основу для commit-by-commit execution.

Документ опирается на текущую структуру репозитория:
- `backend/services/qa_task_api/app.py`
- `backend/services/qa_orchestrator/*`
- `backend/services/qa_rag_service/app.py`
- `backend/services/qa_result_service/app.py`
- `backend/services/qa_llm_gateway/app.py`
- `backend/shared/*`
- `frontend/apps/qa-console/index.html`
- `infra/postgres/init.sql`

## 1. Backend implementation map

### 1.1 Database layer

#### Existing file
- `infra/postgres/init.sql`

#### Recommendation
На первом шаге не пытаться сразу полностью переписать `init.sql`. Лучше:
- либо добавить отдельный migration-style SQL файл рядом в `infra/postgres/`;
- либо временно расширить `init.sql`, если проект пока живёт без полноценной migration system.

#### Changes to implement
- добавить таблицы `domains`;
- добавить таблицы `domain_profiles`;
- добавить таблицы `domain_context_files`;
- добавить таблицы `domain_context_chunks`;
- добавить таблицу `task_context_links`;
- расширить `tasks` полями `domain_id`, `context_scope`, `selected_context_ids`;
- расширить `results` полями `domain_id`, `used_context`.

#### Suggested deliverable
- `infra/postgres/001_domain_thin_slice.sql` или аналогичный migration draft.

### 1.2 Task API service

#### Existing file
- `backend/services/qa_task_api/app.py`

#### Responsibilities for thin slice
- добавить domain-aware request model;
- валидировать `domain_id`;
- валидировать `context_scope` и `selected_context_ids`;
- сохранять новые поля в `tasks`;
- при необходимости создавать `task_context_links` для manual selection;
- публиковать event payload уже с `domain_id`.

#### Concrete change areas
- Pydantic request schema for `POST /api/tasks`;
- DB insert logic into `tasks`;
- task event payload shape;
- optional read endpoint adaptation if task details are returned from this service.

#### New endpoints to add here or in separate service
Если пока хочется минимизировать количество сервисов, domain CRUD endpoints можно временно добавить сюда как в platform entry API. Альтернатива — выделить отдельный lightweight domain API позже.

Для thin slice pragmatic option:
- разместить Domains API в `qa_task_api`.

### 1.3 Domain management API

#### Proposed location
- initially inside `backend/services/qa_task_api/app.py`

#### Why
Сейчас отдельного `domain_service` нет, а thin slice требует быстрый путь к working product. Для первой версии разумно не плодить новый микросервис.

#### Endpoints to implement
- `POST /api/domains`
- `GET /api/domains`
- `GET /api/domains/{domain_id}`
- `PUT /api/domains/{domain_id}`
- `POST /api/domains/{domain_id}/archive`
- `GET /api/domains/{domain_id}/profile`
- `PUT /api/domains/{domain_id}/profile`

#### Internal refactor recommendation
Чтобы `app.py` не стал слишком большим, лучше сразу вынести:
- domain repository helpers;
- profile repository helpers;
- validation helpers.

Возможные новые модули:
- `backend/services/qa_task_api/domain_repo.py`
- `backend/services/qa_task_api/domain_models.py`
- `backend/services/qa_task_api/domain_validation.py`

### 1.4 RAG service

#### Existing file
- `backend/services/qa_rag_service/app.py`

#### Responsibilities for thin slice
- добавить CRUD для domain context files;
- хранить файлы в `domain_context_files`;
- пересобирать chunks в `domain_context_chunks`;
- реализовать retrieval по `domain_id`;
- поддержать optional filter по `selected_context_ids`.

#### Endpoints to implement
- `POST /api/domains/{domain_id}/context-files`
- `GET /api/domains/{domain_id}/context-files`
- `GET /api/domains/{domain_id}/context-files/{context_file_id}`
- `PUT /api/domains/{domain_id}/context-files/{context_file_id}`
- `DELETE /api/domains/{domain_id}/context-files/{context_file_id}`

#### Internal refactor recommendation
Сейчас в `qa_rag_service/app.py` уже есть chunking logic и current knowledge endpoints. Для thin slice лучше не смешивать всё в одном большом блоке.

Возможные новые модули:
- `backend/services/qa_rag_service/domain_context_repo.py`
- `backend/services/qa_rag_service/domain_context_models.py`
- `backend/services/qa_rag_service/chunking.py`
- `backend/services/qa_rag_service/retrieval.py`

#### Migration note
Legacy endpoints `knowledge_documents` можно временно оставить без удаления.

### 1.5 Orchestrator

#### Existing files
- `backend/services/qa_orchestrator/app.py`
- `backend/services/qa_orchestrator/dispatcher.py`
- `backend/services/qa_orchestrator/handlers.py`
- `backend/services/qa_orchestrator/clients.py`
- `backend/services/qa_orchestrator/runtime.py`
- `backend/services/qa_orchestrator/builders.py`

#### Responsibilities for thin slice
- получить `domain_id` из task payload;
- вызывать retrieval только по домену;
- включать retrieved domain context в generation path;
- передавать used-context references в result persistence.

#### Most likely change points
- `clients.py` — новые client methods для domain context retrieval;
- `handlers.py` — сбор domain-aware execution flow for `requirements_analysis`;
- `builders.py` — если prompt/context assembly вынесен туда;
- `dispatcher.py` — минимально, если payload routing needs update.

#### Recommended implementation strategy
Сфокусироваться сначала только на `requirements_analysis` path и не пытаться одновременно адаптировать все handlers.

### 1.6 Result service

#### Existing file
- `backend/services/qa_result_service/app.py`

#### Responsibilities for thin slice
- сохранять `domain_id` вместе с результатом;
- сохранять `used_context` explainability snapshot;
- отдавать explainable result по `task_id`.

#### Concrete change areas
- request/response schema for result persistence;
- insert into extended `results` table;
- read endpoint for `GET /api/tasks/{task_id}/result` или equivalent current endpoint.

#### Internal recommendation
Если service пока очень простой, не нужно преждевременно дробить его. Достаточно аккуратно расширить schema contract.

### 1.7 LLM gateway

#### Existing file
- `backend/services/qa_llm_gateway/app.py`

#### Responsibilities for thin slice
- не требует большого redesign;
- должен продолжать принимать prompt и возвращать normalized output;
- при необходимости только обеспечить совместимость с injected context в prompt assembly.

#### Recommendation
Не делать major changes здесь на первом шаге. Основной фокус должен быть на task/rag/orchestrator/result path.

### 1.8 Shared layer

#### Existing files
- `backend/shared/artifacts.py`
- `backend/shared/normalization.py`
- `backend/shared/resilience.py`
- `backend/shared/contracts/events.json`
- `backend/shared/schemas/task_state.json`

#### Potential changes
- обновить `contracts/events.json`, если event payload теперь включает `domain_id` и related fields;
- обновить схемы task/result state, если они реально используются в runtime;
- при необходимости добавить shared DTO/helper modules для used-context contract.

## 2. Frontend implementation map

### Existing frontend
- `frontend/apps/qa-console/index.html`

### Current reality
Сейчас frontend выглядит как single-file app entry. Для thin slice это допустимо, но есть риск быстро превратить файл в трудно поддерживаемый монолит.

### Recommendation
Даже если пока UI остаётся в рамках одного приложения, лучше сразу логически разделить его на блоки:
- domains view;
- domain detail view;
- context management view;
- run task view;
- result view;
- API client layer;
- UI state helpers.

### Pragmatic options

#### Option A — keep one HTML but split JS/CSS assets
Если current frontend очень минимальный, можно оставить `index.html`, но вынести логику в отдельные файлы:
- `frontend/apps/qa-console/assets/app.js`
- `frontend/apps/qa-console/assets/api.js`
- `frontend/apps/qa-console/assets/domains.js`
- `frontend/apps/qa-console/assets/context-files.js`
- `frontend/apps/qa-console/assets/tasks.js`
- `frontend/apps/qa-console/assets/results.js`
- `frontend/apps/qa-console/assets/styles.css`

#### Option B — keep inline for now
Только если хочется максимально быстро пройти thin slice, но это хуже для дальнейшего роста.

#### Recommended choice
Option A.

### Screens / views to implement

#### 2.1 Domains list view
Responsibilities:
- show all domains;
- create domain action;
- archive domain action;
- navigate to domain detail.

#### 2.2 Domain detail / edit view
Responsibilities:
- edit domain metadata;
- edit domain profile;
- show context files summary;
- provide run task entry point.

#### 2.3 Domain context management view
Responsibilities:
- list context files;
- add context file;
- edit context file;
- delete context file;
- preview context.

#### 2.4 Run task view
Responsibilities:
- select domain;
- select task type;
- input requirement text;
- choose context scope;
- optionally choose explicit context files;
- submit task.

#### 2.5 Result view
Responsibilities:
- poll/fetch task state;
- render normalized result;
- render used-context references;
- provide navigation back to domain.

## 3. Recommended implementation sequence

### Commit 1 — schema draft to migration
Suggested commit scope:
- add migration SQL for domain thin slice.

Suggested commit message:
- `feat(db): add domain-first thin-slice schema`

### Commit 2 — domains and profiles API
Suggested commit scope:
- implement domain CRUD;
- implement domain profile upsert/get.

Suggested commit message:
- `feat(api): add domain and profile management endpoints`

### Commit 3 — domain context file storage
Suggested commit scope:
- implement domain context file CRUD;
- implement chunk rebuild logic.

Suggested commit message:
- `feat(rag): add domain context file storage and chunking`

### Commit 4 — domain-aware retrieval
Suggested commit scope:
- add retrieval by `domain_id`;
- support `selected_context_ids` filtering.

Suggested commit message:
- `feat(rag): support domain-scoped retrieval`

### Commit 5 — task contract update
Suggested commit scope:
- extend task request model;
- persist `domain_id`, `context_scope`, `selected_context_ids`;
- update event payload.

Suggested commit message:
- `feat(task-api): add domain-aware task contract`

### Commit 6 — orchestrator domain-aware execution
Suggested commit scope:
- inject domain retrieval into `requirements_analysis` flow;
- pass used context to result service.

Suggested commit message:
- `feat(orchestrator): run requirements analysis with domain context`

### Commit 7 — explainable results
Suggested commit scope:
- extend result persistence;
- expose used-context in result endpoint.

Suggested commit message:
- `feat(results): persist explainable domain-aware artifacts`

### Commit 8 — frontend domains and context management
Suggested commit scope:
- add domains UI;
- add context file management UI.

Suggested commit message:
- `feat(frontend): add domain and context management views`

### Commit 9 — frontend task run and result view
Suggested commit scope:
- add run task view;
- add result rendering with used-context references.

Suggested commit message:
- `feat(frontend): add domain-scoped task run and result views`

### Commit 10 — thin-slice stabilization
Suggested commit scope:
- add integration tests;
- add demo seed/setup docs;
- clean up rough edges.

Suggested commit message:
- `chore(thin-slice): stabilize domain-first vertical slice`

## 4. Suggested engineering rules during implementation

- Не делать workflow engine в этом же branch/phase.
- Не пытаться сразу заменить legacy knowledge model полностью.
- Не добавлять новую микросервисную декомпозицию без острой необходимости.
- Ограничить end-to-end flow одним task type: `requirements_analysis`.
- Сначала довести explainable domain-aware path до конца, потом обобщать.

## 5. Definition of done for the whole thin slice

Thin slice завершён, если:
- домен создаётся и редактируется из UI;
- context files управляются из UI;
- задача `requirements_analysis` запускается внутри домена;
- retrieval использует только доменный контекст;
- результат содержит used-context references;
- весь сценарий работает локально без ручного вмешательства в БД.
