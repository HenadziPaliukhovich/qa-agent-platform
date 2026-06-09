# QA Agent Platform — First Thin Slice Implementation Plan

## Goal

Построить первый вертикальный срез платформы, который уже отражает новую продуктовую модель:
- домены настраиваются из UI;
- контекст привязан к домену;
- задача запускается в рамках выбранного домена;
- LLM использует доменный контекст;
- результат сохраняется как артефакт.

Этот thin slice должен доказать, что платформа уже ушла от модели `project/service_name` к модели `domain/profile/context/task`.

## Thin slice scope

Первый thin slice включает только минимально необходимое:
- Domain CRUD;
- DomainProfile configuration;
- UI для создания и редактирования доменов;
- upload/list/delete context files for domain;
- один domain-scoped task flow;
- retrieval только по выбранному домену;
- сохранение результата и used-context references.

Вне scope этого thin slice:
- полноценный workflow engine;
- OAuth integrations;
- сложная role model;
- multi-tenant permissions;
- полноценный event-source abstraction layer;
- advanced artifact lineage across multi-step workflows.

## Target user flow

1. QA открывает UI.
2. Создаёт домен.
3. Заполняет базовый domain profile.
4. Загружает контекстные файлы в домен.
5. Выбирает домен и запускает задачу `requirements_analysis`.
6. Платформа достаёт контекст только выбранного домена.
7. LLM формирует результат.
8. Результат сохраняется как artifact с указанием domain и использованного контекста.
9. QA видит результат в UI.

## Proposed backend changes

### 1. New entities

Добавить новые сущности:
- `domains`;
- `domain_profiles`;
- `domain_context_files`;
- `domain_context_chunks`;
- `task_context_links`;
- при необходимости расширение `artifacts`/`task_results` таблиц полями domain metadata.

### 2. Domains table

Минимальный состав полей `domains`:
- `domain_id`;
- `name`;
- `slug`;
- `description`;
- `status` (`active|archived`);
- `tags` JSONB;
- `created_at`;
- `updated_at`.

### 3. Domain profiles table

Минимальный состав полей `domain_profiles`:
- `domain_id`;
- `business_scope` text;
- `prompt_policy` JSONB;
- `retrieval_policy` JSONB;
- `supported_artifacts` JSONB;
- `event_source_settings` JSONB;
- `integration_bindings` JSONB;
- `updated_at`.

На первом этапе допустим один profile на домен.

### 4. Domain context files

Минимальный состав полей `domain_context_files`:
- `context_file_id`;
- `domain_id`;
- `title`;
- `file_name`;
- `content_type`;
- `source`;
- `tags` JSONB;
- `raw_content` text;
- `version`;
- `status` (`active|deleted`);
- `created_at`;
- `updated_at`.

Chunks можно хранить в отдельной таблице `domain_context_chunks`:
- `chunk_id`;
- `context_file_id`;
- `domain_id`;
- `chunk_index`;
- `content`;
- `token_estimate`;
- `metadata` JSONB.

### 5. Task model extension

Расширить task model:
- добавить `domain_id`;
- добавить `context_scope` (`domain_default|manual_selection`);
- добавить `selected_context_ids` JSONB nullable;
- добавить `used_context_snapshot` в result/artifact layer.

### 6. Retrieval behavior

На первом thin slice retrieval должен быть простым и прозрачным:
- задача получает `domain_id`;
- RAG service ищет только в `domain_context_chunks` выбранного домена;
- если есть `selected_context_ids`, retrieval ограничивается ими;
- результат retrieval возвращает top relevant chunks + source references.

Важное правило:
- никакого cross-domain retrieval по умолчанию.

### 7. LLM invocation path

Текущий execution path адаптировать так:
- `qa_task_api` принимает `domain_id`;
- `qa_orchestrator` передаёт `domain_id` в retrieval и generation chain;
- `qa_rag_service` возвращает domain-scoped context;
- `qa_llm_gateway` получает prompt + injected context;
- `qa_result_service` сохраняет artifact вместе с used context references.

## Proposed API changes

### Domains API

Нужны новые endpoints:
- `POST /api/domains`
- `GET /api/domains`
- `GET /api/domains/{domain_id}`
- `PUT /api/domains/{domain_id}`
- `POST /api/domains/{domain_id}/archive`

### Domain profile API

- `GET /api/domains/{domain_id}/profile`
- `PUT /api/domains/{domain_id}/profile`

### Domain context API

- `POST /api/domains/{domain_id}/context-files`
- `GET /api/domains/{domain_id}/context-files`
- `GET /api/domains/{domain_id}/context-files/{context_file_id}`
- `PUT /api/domains/{domain_id}/context-files/{context_file_id}`
- `DELETE /api/domains/{domain_id}/context-files/{context_file_id}`

На первом этапе можно поддержать текстовый upload/paste вместо полноценного binary file ingestion.

### Task API changes

Расширить `POST /api/tasks`:
- `domain_id` becomes required for thin-slice path;
- `context_scope` optional;
- `selected_context_ids` optional.

Также нужен endpoint просмотра результатов по домену или задаче, если его ещё нет в usable форме.

## Proposed frontend scope

### New screens

Нужны минимальные UI-экраны:
- Domains list;
- Create/Edit Domain form;
- Domain details;
- Domain context files list;
- Add/Edit context file form;
- Run task form;
- Task result view.

### Minimal UI flow

#### 1. Domains list
Показывает:
- name;
- description;
- tags;
- status;
- count of context files.

Действия:
- create domain;
- open domain;
- archive domain.

#### 2. Domain form
Поля:
- name;
- slug;
- description;
- tags;
- business scope;
- prompt policy (simple JSON textarea or structured fields later);
- retrieval policy.

На первом этапе допустим простой admin-style form.

#### 3. Context management view
Показывает список файлов контекста домена.

Действия:
- add context;
- edit context;
- delete context;
- preview context content.

#### 4. Run task view
Поля:
- domain selector;
- task type;
- input text;
- context scope;
- optional explicit context selection.

На первом этапе достаточно поддержать один task type:
- `requirements_analysis`.

#### 5. Result view
Показывает:
- task metadata;
- domain;
- normalized result;
- used context sources;
- created artifact info.

## Proposed first implementation order

### Step 1. DB migration
Сначала добавить новые таблицы и расширить task/result schema.

Definition of done:
- миграции применяются локально;
- таблицы доступны в Postgres;
- старый flow не ломается.

### Step 2. Domains backend API
Сделать CRUD для `domains` и `domain_profiles`.

Definition of done:
- домен можно создать, прочитать, обновить и архивировать через API.

### Step 3. Domain context backend API
Сделать CRUD для context files и chunking pipeline.

Definition of done:
- можно добавить текстовый context file;
- он режется на chunks;
- можно посмотреть список файлов домена;
- можно удалить файл.

### Step 4. Retrieval refactor
Адаптировать `qa_rag_service` под retrieval по `domain_id`.

Definition of done:
- retrieval возвращает только доменный контекст.

### Step 5. Task path refactor
Обновить `qa_task_api` и `qa_orchestrator` для передачи `domain_id`.

Definition of done:
- задача запускается только в рамках домена;
- context references попадают в result.

### Step 6. Result persistence upgrade
Обновить result/artifact persistence.

Definition of done:
- результат хранит `domain_id` и used context snapshot.

### Step 7. Frontend thin slice
Сделать минимальный UI для domains, context files, run task, result view.

Definition of done:
- пользователь может пройти весь thin-slice flow без ручных SQL/API манипуляций.

## Suggested artifact contract for thin slice

Минимально artifact/result должен содержать:
- `task_id`;
- `domain_id`;
- `task_type`;
- `input_snapshot`;
- `normalized_output`;
- `used_context` array:
  - `context_file_id`;
  - `title`;
  - `chunk_id`;
  - `chunk_index`;
  - `preview`.
- `created_at`.

Это критично для explainability и trust.

## Design decisions to lock early

Нужно зафиксировать заранее:
1. Domain deletion policy: hard delete vs archive only.
2. Context deletion policy: soft delete preferred.
3. Whether `slug` is unique globally.
4. Whether one domain can have exactly one profile or multiple profiles later.
5. Whether context editing creates new version or in-place update on thin slice.
6. Whether task execution without domain should be forbidden after migration.

Рекомендация для thin slice:
- domains: archive, не hard delete;
- context files: soft delete;
- one profile per domain;
- domain required for new UI flow;
- context edit may create version 1→2 later, but first slice can support in-place update + updated_at.

## Risks

Основные риски thin slice:
- сломать текущий task flow при добавлении `domain_id`;
- дублировать knowledge model вместо аккуратной миграции;
- сделать UI-only domains, но не довести domain-aware execution path;
- преждевременно усложнить profile configuration.

Как снизить риски:
- сохранить backward compatibility внутри backend на переходный период;
- начать с text-based context ingestion;
- сделать один task type end-to-end;
- не строить workflow engine в этом же slice.

## Thin slice success criteria

Thin slice считается успешным, если:
- QA может создать домен из UI;
- QA может загрузить контекст в этот домен;
- QA может запустить `requirements_analysis` внутри этого домена;
- retrieval использует только доменный контекст;
- результат показывает, какой контекст был использован;
- весь flow работает без ручного вмешательства в БД.

## Recommended next issue breakdown

После принятия этого implementation plan имеет смысл сразу создать набор implementation issues:
1. DB schema for domains and context files.
2. Domain CRUD API.
3. Domain profile API.
4. Domain context file CRUD + chunking.
5. Domain-scoped retrieval in RAG service.
6. Task API support for `domain_id`.
7. Orchestrator support for domain-aware execution.
8. Result service support for used-context snapshot.
9. Frontend Domains page.
10. Frontend Domain Context page.
11. Frontend Run Task page.
12. Frontend Result page.