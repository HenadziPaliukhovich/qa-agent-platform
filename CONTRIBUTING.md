# Contributing Guide — QA Agent Platform

## Overview

This project is an event-driven multi-agent QA platform for practical QA work in a social casino product context.

Этот документ фиксирует правила совместной работы, чтобы репозиторий оставался управляемым, прозрачным и безопасным.

## Branching model

- Основная ветка: `main`.
- Прямые push в `main` запрещены.
- Все изменения попадают в `main` только через Pull Request.
- Рабочие ветки создаются от `main`.

Рекомендуемые префиксы веток:
- `feature/...`
- `fix/...`
- `refactor/...`
- `docs/...`
- `chore/...`
- `research/...`
- `ci/...`

Примеры:
- `feature/payments-context-upload`
- `fix/workflow-run-status`
- `docs/update-roadmap`
- `ci/github-required-checks`

## Commit messages

Используем формат Conventional Commits:

```text
<type>(<scope>): <short summary>
```

### Allowed types

- `feat`
- `fix`
- `refactor`
- `docs`
- `test`
- `chore`
- `ci`
- `perf`
- `build`
- `revert`

### Scope is mandatory

Каждый коммит должен содержать scope.

Разрешённые scope:
- `backend`
- `frontend`
- `infra`
- `docs`
- `ci`
- `github`
- `context`
- `workflow`
- `orchestration`
- `agents`
- `integrations`
- `auth`
- `api`
- `artifacts`
- `payments`
- `session`
- `rewards`
- `rg`
- `testing`
- `platform`
- `repo`

Примеры корректных коммитов:
- `feat(context): add domain file upload metadata model`
- `fix(workflow): handle failed step retry status`
- `docs(repo): update contribution rules`
- `ci(github): add commit validation workflow`
- `feat(payments): add payments analysis task template`

### Commit guidance

- Один коммит — одна логическая мысль.
- Summary должен быть коротким и понятным.
- Breaking changes должны быть явно отмечены по правилам Conventional Commits.
- Не использовать размытые сообщения вроде `update`, `changes`, `fix stuff`.

## Pull request rules

- PR должен быть небольшим и логически цельным.
- Каждый PR должен объяснять контекст изменений и способ проверки.
- Все обязательные проверки CI должны быть зелёными до merge.
- Для изменений архитектуры нужно создавать или обновлять ADR.
- Изменения, сгенерированные AI, обязательно просматриваются человеком перед merge.

### Minimum PR expectations

Каждый PR должен содержать:
- Summary;
- linked issue / task;
- verification steps;
- impact/risk description;
- rollback idea для рискованных изменений.

## GitHub remote policy

На уровне GitHub репозитория должны быть включены следующие правила:
- branch protection для `main`;
- запрет force push;
- запрет прямых push;
- merge только через PR;
- обязательные required status checks;
- желательно минимум один approval review.

## Issue management

Для новых задач используем issue templates.

Минимальные типы задач:
- feature request;
- bug report;
- tech task;
- architecture decision request.

Если задача затрагивает продуктовый flow, domain context, workflow engine или integration hub, это должно быть явно отражено в issue.

## ADR policy

ADR хранятся в `docs/adr/`.

ADR обязателен, если изменение:
- меняет архитектурный слой;
- вводит новый platform contract;
- меняет стратегию интеграции;
- влияет на domain context management;
- влияет на workflow engine;
- влияет на model provider strategy.

## QA and engineering expectations

- Не дублировать бизнес-логику между модулями и сервисами.
- Для интеграций использовать адаптеры и явные контракты.
- Для LLM-вызовов предусматривать timeout, retries и логирование.
- Любые изменения, влияющие на домены (`payments`, `session`, `rewards`, `rg`), должны сопровождаться обновлением документации и сценарного контекста при необходимости.
- Если меняется публичный контракт API, это должно быть явно описано в PR и документации.

## Release and versioning policy

- Релизы оформляются тегами.
- Версионирование должно быть предсказуемым и отражать смысл изменений.
- Breaking changes нельзя смешивать с неописанными мелкими изменениями.

## Decision rule

Если есть сомнение, лучше:
- создать issue;
- зафиксировать вопрос в PR;
- завести ADR для архитектурного выбора;
чем вносить неявные изменения без обсуждения.
