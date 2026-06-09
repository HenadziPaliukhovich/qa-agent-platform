# Domain Thin Slice API Draft

## Purpose

Этот документ описывает draft REST API для первого domain-first thin slice.

Цели API draft:
- зафиксировать contract для UI-configurable domains;
- описать CRUD для доменов и context files;
- описать запуск первой domain-aware задачи;
- согласовать request/response shape до начала реальной реализации.

Этот draft intentionally ориентирован на thin slice и не пытается покрыть все будущие workflow и integration сценарии.

## General principles

- Все новые domain-aware сценарии должны быть завязаны на `domain_id`.
- Архивирование предпочтительнее hard delete для доменов.
- Delete context file в thin slice должен быть soft delete.
- Response shape должен быть достаточно стабильным для UI.
- Ошибки должны быть человекочитаемыми и пригодными для дебага.

## Common response conventions

### Success envelope

На первом этапе можно использовать простой JSON без сложного envelope, но response должен быть консистентным.

### Error shape

Рекомендуемый error format:

```json
{
  "error": {
    "code": "domain_not_found",
    "message": "Domain was not found",
    "details": {
      "domain_id": "domain-123"
    }
  }
}
```

## 1. Domains API

### POST /api/domains

Создаёт новый домен.

#### Request

```json
{
  "name": "Payments",
  "slug": "payments",
  "description": "Payments domain for transaction and purchase flows",
  "tags": ["payments", "billing", "casino"]
}
```

#### Response 201

```json
{
  "domain_id": "domain-8f2c1a",
  "name": "Payments",
  "slug": "payments",
  "description": "Payments domain for transaction and purchase flows",
  "status": "active",
  "tags": ["payments", "billing", "casino"],
  "created_at": "2026-06-09T10:00:00Z",
  "updated_at": "2026-06-09T10:00:00Z"
}
```

### GET /api/domains

Возвращает список доменов.

#### Query params
- `status` optional (`active|archived`)
- `q` optional search string

#### Response 200

```json
{
  "domains": [
    {
      "domain_id": "domain-8f2c1a",
      "name": "Payments",
      "slug": "payments",
      "description": "Payments domain for transaction and purchase flows",
      "status": "active",
      "tags": ["payments", "billing"],
      "context_files_count": 3,
      "created_at": "2026-06-09T10:00:00Z",
      "updated_at": "2026-06-09T10:00:00Z"
    }
  ]
}
```

### GET /api/domains/{domain_id}

Возвращает одну запись домена.

#### Response 200

```json
{
  "domain_id": "domain-8f2c1a",
  "name": "Payments",
  "slug": "payments",
  "description": "Payments domain for transaction and purchase flows",
  "status": "active",
  "tags": ["payments", "billing"],
  "created_at": "2026-06-09T10:00:00Z",
  "updated_at": "2026-06-09T10:00:00Z"
}
```

### PUT /api/domains/{domain_id}

Обновляет metadata домена.

#### Request

```json
{
  "name": "Payments",
  "slug": "payments",
  "description": "Core payments and purchase flows",
  "tags": ["payments", "billing", "store"]
}
```

#### Response 200

```json
{
  "domain_id": "domain-8f2c1a",
  "name": "Payments",
  "slug": "payments",
  "description": "Core payments and purchase flows",
  "status": "active",
  "tags": ["payments", "billing", "store"],
  "created_at": "2026-06-09T10:00:00Z",
  "updated_at": "2026-06-09T10:30:00Z"
}
```

### POST /api/domains/{domain_id}/archive

Архивирует домен.

#### Response 200

```json
{
  "domain_id": "domain-8f2c1a",
  "status": "archived",
  "updated_at": "2026-06-09T11:00:00Z"
}
```

## 2. Domain Profile API

### GET /api/domains/{domain_id}/profile

Возвращает profile домена.

#### Response 200

```json
{
  "domain_id": "domain-8f2c1a",
  "business_scope": "Purchase, currency packs, payment retries, confirmation flows",
  "prompt_policy": {
    "strict_grounding": true,
    "prefer_questions_over_assumptions": true
  },
  "retrieval_policy": {
    "default_scope": "domain_default",
    "max_chunks": 5
  },
  "supported_artifacts": ["requirements_analysis", "test_cases"],
  "event_source_settings": {},
  "integration_bindings": [],
  "updated_at": "2026-06-09T10:00:00Z"
}
```

### PUT /api/domains/{domain_id}/profile

Создаёт или обновляет profile.

#### Request

```json
{
  "business_scope": "Purchase, currency packs, payment retries, confirmation flows",
  "prompt_policy": {
    "strict_grounding": true,
    "prefer_questions_over_assumptions": true
  },
  "retrieval_policy": {
    "default_scope": "domain_default",
    "max_chunks": 5
  },
  "supported_artifacts": ["requirements_analysis", "test_cases"],
  "event_source_settings": {},
  "integration_bindings": []
}
```

#### Response 200

```json
{
  "domain_id": "domain-8f2c1a",
  "business_scope": "Purchase, currency packs, payment retries, confirmation flows",
  "prompt_policy": {
    "strict_grounding": true,
    "prefer_questions_over_assumptions": true
  },
  "retrieval_policy": {
    "default_scope": "domain_default",
    "max_chunks": 5
  },
  "supported_artifacts": ["requirements_analysis", "test_cases"],
  "event_source_settings": {},
  "integration_bindings": [],
  "created_at": "2026-06-09T10:00:00Z",
  "updated_at": "2026-06-09T10:15:00Z"
}
```

## 3. Domain Context Files API

### POST /api/domains/{domain_id}/context-files

Создаёт context file внутри домена.

#### Request

```json
{
  "title": "Payments requirements baseline",
  "file_name": "payments-requirements-v1.md",
  "content_type": "text/markdown",
  "source": "manual-upload",
  "tags": ["requirements", "payments"],
  "raw_content": "Users can buy chips via card or app store billing..."
}
```

#### Response 201

```json
{
  "context_file_id": "ctx-91ab22",
  "domain_id": "domain-8f2c1a",
  "title": "Payments requirements baseline",
  "file_name": "payments-requirements-v1.md",
  "content_type": "text/markdown",
  "source": "manual-upload",
  "tags": ["requirements", "payments"],
  "version": 1,
  "status": "active",
  "chunk_count": 4,
  "created_at": "2026-06-09T10:20:00Z",
  "updated_at": "2026-06-09T10:20:00Z"
}
```

### GET /api/domains/{domain_id}/context-files

Возвращает список context files домена.

#### Query params
- `status` optional (`active|deleted`)
- `q` optional search string

#### Response 200

```json
{
  "context_files": [
    {
      "context_file_id": "ctx-91ab22",
      "domain_id": "domain-8f2c1a",
      "title": "Payments requirements baseline",
      "file_name": "payments-requirements-v1.md",
      "content_type": "text/markdown",
      "source": "manual-upload",
      "tags": ["requirements", "payments"],
      "version": 1,
      "status": "active",
      "chunk_count": 4,
      "created_at": "2026-06-09T10:20:00Z",
      "updated_at": "2026-06-09T10:20:00Z"
    }
  ]
}
```

### GET /api/domains/{domain_id}/context-files/{context_file_id}

Возвращает один context file с content preview или full content.

#### Response 200

```json
{
  "context_file_id": "ctx-91ab22",
  "domain_id": "domain-8f2c1a",
  "title": "Payments requirements baseline",
  "file_name": "payments-requirements-v1.md",
  "content_type": "text/markdown",
  "source": "manual-upload",
  "tags": ["requirements", "payments"],
  "raw_content": "Users can buy chips via card or app store billing...",
  "version": 1,
  "status": "active",
  "chunk_count": 4,
  "created_at": "2026-06-09T10:20:00Z",
  "updated_at": "2026-06-09T10:20:00Z"
}
```

### PUT /api/domains/{domain_id}/context-files/{context_file_id}

Обновляет metadata или content context file.

#### Request

```json
{
  "title": "Payments requirements baseline",
  "file_name": "payments-requirements-v2.md",
  "content_type": "text/markdown",
  "source": "manual-upload",
  "tags": ["requirements", "payments", "v2"],
  "raw_content": "Users can buy chips via card, app store billing, and promo bundle flow..."
}
```

#### Response 200

```json
{
  "context_file_id": "ctx-91ab22",
  "domain_id": "domain-8f2c1a",
  "title": "Payments requirements baseline",
  "file_name": "payments-requirements-v2.md",
  "content_type": "text/markdown",
  "source": "manual-upload",
  "tags": ["requirements", "payments", "v2"],
  "version": 2,
  "status": "active",
  "chunk_count": 5,
  "created_at": "2026-06-09T10:20:00Z",
  "updated_at": "2026-06-09T10:40:00Z"
}
```

### DELETE /api/domains/{domain_id}/context-files/{context_file_id}

Soft delete context file.

#### Response 200

```json
{
  "context_file_id": "ctx-91ab22",
  "domain_id": "domain-8f2c1a",
  "status": "deleted",
  "updated_at": "2026-06-09T11:00:00Z"
}
```

## 4. Domain-aware Task API

### POST /api/tasks

Расширенный task creation endpoint для thin slice.

#### Request

```json
{
  "domain_id": "domain-8f2c1a",
  "task_type": "requirements_analysis",
  "mode": "balanced",
  "approval_mode": "auto",
  "context_scope": "domain_default",
  "selected_context_ids": [],
  "input": {
    "requirement_text": "Users can buy chips via card or app store billing. Failed payments should show retry guidance."
  },
  "model_provider": "ollama",
  "model_name": "llama3"
}
```

#### Response 201

```json
{
  "task_id": "task-7c12e4",
  "domain_id": "domain-8f2c1a",
  "task_type": "requirements_analysis",
  "state": "created",
  "context_scope": "domain_default",
  "selected_context_ids": [],
  "created_at": "2026-06-09T10:50:00Z"
}
```

#### Validation rules
- `domain_id` required for domain-aware thin-slice flow.
- `task_type` initially allowed: `requirements_analysis`.
- `selected_context_ids` must belong to the same domain.
- `context_scope=manual_selection` requires non-empty `selected_context_ids`.

## 5. Task Result API

### GET /api/tasks/{task_id}

Возвращает metadata задачи.

#### Response 200

```json
{
  "task_id": "task-7c12e4",
  "domain_id": "domain-8f2c1a",
  "task_type": "requirements_analysis",
  "state": "completed",
  "context_scope": "domain_default",
  "selected_context_ids": [],
  "created_at": "2026-06-09T10:50:00Z",
  "updated_at": "2026-06-09T10:51:00Z"
}
```

### GET /api/tasks/{task_id}/result

Возвращает explainable result.

#### Response 200

```json
{
  "result_id": "result-81af2d",
  "task_id": "task-7c12e4",
  "domain_id": "domain-8f2c1a",
  "schema_name": "requirements_analysis.v1",
  "content_json": {
    "summary": "The requirement defines payment entry paths but leaves retry and failure behavior underspecified.",
    "clarity_findings": [
      "Retry guidance behavior is not fully defined for different failure types."
    ],
    "coverage_gaps": [
      "No detail is given for cancellation and partial payment flows."
    ],
    "assumptions": [],
    "risks": [
      {
        "title": "Inconsistent retry behavior",
        "severity": "medium",
        "description": "Different payment providers may surface different failure handling if retry rules are unspecified."
      }
    ],
    "questions_for_refinement": [
      "Should retry guidance differ for card failures versus app store failures?"
    ],
    "suggested_test_areas": [
      "Successful card purchase flow",
      "Failed payment retry guidance",
      "App store payment confirmation"
    ],
    "qa_priority": "high"
  },
  "used_context": [
    {
      "context_file_id": "ctx-91ab22",
      "title": "Payments requirements baseline",
      "chunk_id": "chunk-44a1b2",
      "chunk_index": 0,
      "preview": "Users can buy chips via card or app store billing..."
    }
  ],
  "created_at": "2026-06-09T10:51:00Z"
}
```

## 6. Optional domain result browsing API

### GET /api/domains/{domain_id}/tasks

Возвращает задачи по домену.

#### Response 200

```json
{
  "tasks": [
    {
      "task_id": "task-7c12e4",
      "domain_id": "domain-8f2c1a",
      "task_type": "requirements_analysis",
      "state": "completed",
      "created_at": "2026-06-09T10:50:00Z",
      "updated_at": "2026-06-09T10:51:00Z"
    }
  ]
}
```

## 7. Suggested implementation notes

- `context_files_count` and `chunk_count` can initially вычисляться query-time или materialize later.
- `PUT profile` может работать как upsert.
- Для thin slice допускается text-only ingestion.
- Domain archive должен запрещать новые task runs или хотя бы явно предупреждать об этом.
- Валидация slug uniqueness должна быть на уровне БД и API.
- Result endpoint должен быть стабилен для UI even if internal execution remains event-driven.

## 8. Open questions

1. Нужен ли `PATCH` вместо `PUT` для partial updates?
2. Нужно ли отдельное endpoint для restore deleted context file later?
3. Нужно ли запрещать task creation для archived domain сразу в v1?
4. Нужно ли сразу вводить pagination в list endpoints?
5. Нужно ли сразу отделять DTO для summary view и detail view?
