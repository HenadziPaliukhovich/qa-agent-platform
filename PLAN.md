# QA Agent Platform — Long-Term Development Plan

## 0. Initial project state (2026-06-09)

На момент старта планирования в корне репозитория присутствуют:
- Системные и служебные файлы: `.DS_Store`, `.git`, `.gitignore`, `.commitlintrc.yml`, `.github`, `.run`, `.scripts`, `.venv`.
- Документация: `README.md`, `CONTRIBUTING.md`, каталог `docs/`.
- Контейнеризация и оркестрация: `Dockerfile`, `docker-compose.yml`.
- Кодовая база: директории `backend/`, `frontend/`, `infra/`, `scripts/`.

Фактическое содержание подпроектов (backend, frontend, infra) было частично уточнено в ходе анализа репозитория и зафиксировано ниже в разделе текущей архитектурной оценки.

Этот файл является основным master-plan документом проекта и должен постоянно поддерживаться в актуальном состоянии.

## 1. Strategic vision

Цель: превратить репозиторий в реально полезную для QA-лида платформу, которая помогает тестировать сложные продукты за счёт многоагентной архитектуры, локального LLM, настраиваемого доменного контекста и управляемых QA workflow.

Важно: платформа не должна быть жёстко привязана к одному технологическому стеку или одному типу продукта. Несмотря на текущий фокус на mobile social casino, архитектура должна быть stack-agnostic и domain-configurable.

Платформа должна закрывать полный контур ежедневной QA-работы:
- анализ требований;
- формирование вопросов и рисков;
- генерация тест-кейсов, чек-листов и сценариев;
- работа с доменным контекстом;
- запуск одиночных задач и последовательных workflow;
- интеграция с внешними рабочими системами команды;
- постепенный переход от ручной аналитики к полуавтоматизированным QA flow.

Ключевые принципы:
- Practicality: каждая итерация должна приносить ощутимую пользу в ежедневной работе QA.
- Stack-agnostic design: приложение не должно зависеть от конкретного backend/frontend/infra стека тестируемого продукта.
- Domain-first product model: все данные, контексты, агенты и workflow должны быть привязаны к доменам.
- UI-configurable domains: домены должны создаваться и настраиваться из UI, а не быть захардкоженными в коде.
- Event-driven readiness: ядро платформы должно уметь работать с событийной моделью, но без жёсткой зависимости только от Kafka.
- Local-first AI: LLM работает локально или в дешёвом гибридном режиме.
- Extensible-by-design: архитектура допускает новые домены, интеграции, агентов и pipeline без переписывания ядра.
- Transparency: действия AI и цепочки решений должны быть объяснимы, наблюдаемы и воспроизводимы.
- Human-in-the-loop: QA управляет постановкой задач, контекстом, доменами, запуском флоу и принимает финальные решения.

## 2. Product constraints and non-goals

### 2.1 Hard constraints

Следующие требования считаются обязательными архитектурными ограничениями:
- Приложение не должно быть привязано к одному прикладному стеку тестируемого продукта.
- Домены должны быть продуктовой сущностью и настраиваться через UI.
- Domain model не должна быть жёстко задана только через код и enums.
- Контекст должен назначаться через домен и управляться пользователем.
- Workflow должны быть конфигурируемыми поверх доменов, а не жёстко пришиты к одному use case.

### 2.2 Explicit non-goals

Следующее НЕ является целевым подходом:
- hardcoded domain list only in code;
- жёсткая привязка к social casino как единственно возможному типу продукта;
- жёсткая привязка ко входным данным только через `service_name` или только через конкретный микросервисный стек;
- построение логики доменов только через кодовые ветвления без UI-level configuration.

## 3. Current architecture assessment

После первичного анализа репозитория уже можно зафиксировать, что проект не является пустым scaffold. В backend уже существует сервисный каркас, который частично соответствует целевой архитектуре платформы.

### 3.1 What already exists

#### Repository governance foundation
Уже присутствуют и частично настроены:
- `.commitlintrc.yml`;
- `.github/pull_request_template.md`;
- `.github/ISSUE_TEMPLATE/*`;
- `docs/adr/*`;
- GitHub Actions workflow для commitlint и repo guardrails;
- обновлённый `CONTRIBUTING.md`.

Это означает, что Stage 0 частично уже реализован на уровне файлов репозитория. Дальше остаётся довести GitHub branch protection и required checks в remote settings.

#### Backend service layout
В `backend/services` уже присутствуют сервисы:
- `qa_task_api`;
- `qa_orchestrator`;
- `qa_llm_gateway`;
- `qa_rag_service`;
- `qa_result_service`;
- `qa_integration_service`.

В `backend/shared` уже существуют общие модули и артефакты:
- `artifacts.py`;
- `normalization.py`;
- `resilience.py`;
- `contracts/events.json`;
- `schemas/task_state.json`.

Это уже хороший фундамент для event-driven multi-service платформы.

#### Task execution foundation
`qa_task_api` уже умеет:
- принимать задачи через API;
- валидировать `task_type`;
- сохранять задачу и task events в Postgres;
- публиковать событие `qa.agent.task.created`;
- работать как входная точка платформы для task execution.

`qa_orchestrator` уже умеет:
- слушать события создания задач;
- выбирать handler по `task_type`;
- публиковать статусы `running/completed/failed`;
- сохранять результат через result persistence;
- выступать как базовый task dispatcher/executor.

#### LLM gateway foundation
`qa_llm_gateway` уже умеет:
- строить prompt под конкретный `task_type`;
- работать в task-specific режиме;
- нормализовывать ответы модели в структурированный JSON;
- использовать общие normalization helpers.

#### RAG / knowledge foundation
`qa_rag_service` уже умеет:
- сохранять knowledge documents;
- чанкать контент;
- сохранять chunks в БД;
- хранить metadata (`project_id`, `service_name`, `doc_type`, `tags`, `source`);
- отдавать список и содержимое документов.

Это означает, что knowledge base foundation уже есть, хотя и не в целевой domain-first форме.

### 3.2 What is partially implemented but needs redesign

#### Project/service-based context model
Сейчас knowledge layer построен вокруг `project_id` и `service_name`. Это полезно как промежуточный шаг, но недостаточно для целевой product model.

Нужно перейти к модели:
- `domain`;
- `domain profile`;
- `domain context files`;
- `domain retrieval scope`;
- `domain metadata`;
- позже — `subdomains`, `tags`, `ownership`, `versioning`.

#### Hardcoded task typing and domain assumptions
Сейчас task-oriented слой выглядит полезным, но логика platform evolution не должна упираться в жёстко заданный список доменов или один конкретный стек.

Нужно прийти к модели, где:
- task families расширяемы;
- domain behavior partly configurable;
- prompts and retrieval policies можно настраивать на уровне domain profile;
- новые домены можно добавлять без изменения кода ядра в большинстве сценариев.

#### Task engine without workflow engine
Сейчас уже есть execution foundation для отдельных задач. Но пока отсутствует полноценный workflow engine.

Нужно добавить:
- `WorkflowDefinition`;
- `WorkflowRun`;
- последовательности шагов;
- chaining outputs between steps;
- restart from step;
- artifacts per step;
- execution logs and progress tracking.

#### Integration layer exists as a service but is not yet confirmed as a product capability
Наличие `qa_integration_service` — хороший знак, но без детального анализа пока нельзя считать, что интеграционный слой уже соответствует требованиям по Jira, Confluence, TestRail, Slack, Postman, Figma и OAuth.

### 3.3 What is currently missing or not yet confirmed

Следующие capability пока либо отсутствуют явно, либо не подтверждены текущим анализом:
- domain CRUD как продуктовая сущность;
- UI для domain management;
- context file lifecycle management (upload/edit/delete/version);
- прозрачный выбор домена при запуске задач;
- workflow UI и workflow runtime;
- artifact lineage across multi-step runs;
- OAuth connection management;
- rich integration hub;
- event ingestion abstraction beyond a narrow transport view;
- полноценная observability and audit trail;
- RBAC;
- object storage strategy for files.

## 4. Gap analysis and transition target

Главная мысль после анализа: проект уже имеет правильный технический вектор, но пока оперирует не теми сущностями, которые нужны для целевой product model.

### 4.1 Current implicit model

Сейчас система фактически мыслит такими сущностями:
- project;
- service_name;
- task_type;
- task;
- task_event;
- knowledge_document;
- knowledge_chunk.

### 4.2 Target product model

Целевая модель платформы должна мыслить такими сущностями:
- domain;
- domain_profile;
- context_file;
- context_collection;
- retrieval_scope;
- task;
- workflow_definition;
- workflow_run;
- workflow_step_run;
- artifact;
- integration_connection;
- oauth_session;
- event_source_binding.

### 4.3 Strategic transition

Главный переход проекта на ближайшие этапы:
- от `project/service_name` → к `domain/domain_profile/context`;
- от hardcoded domain assumptions → к UI-configurable domains;
- от `single task execution` → к `task + workflow execution`;
- от `documents in storage` → к `managed context lifecycle`;
- от `isolated integrations` → к `integration hub`;
- от transport-coupled event logic → к extensible event-source abstraction;
- от `service skeleton` → к coherent QA product platform.

## 5. Core capability map

Конечная версия платформы должна включать следующие обязательные capability-блоки:

1. Domain Management
- создание домена из UI;
- редактирование имени, описания, тегов, owner, параметров;
- настройка domain profile;
- архивирование/деактивация домена;
- выбор домена при запуске task/workflow.

2. Domain Context Management
- загрузка файлов контекста;
- хранение файлов по доменам;
- редактирование и удаление файлов;
- индексация и использование файлов в RAG/LLM анализе;
- возможность направить LLM только на релевантный контекст выбранного домена.

3. Task and Workflow Execution
- запуск одиночных задач;
- запуск последовательных workflow;
- шаблоны pipeline под типовые QA процессы;
- контроль входов, выходов и артефактов каждого шага.

4. Multi-Agent QA Platform
- orchestration слой;
- доменные агенты;
- task-specific агенты;
- integration агенты;
- knowledge/context агенты.

5. External Integrations Hub
- Jira;
- Confluence;
- TestRail;
- Slack;
- Postman;
- Figma;
- OAuth там, где это применимо.

6. Governance and Delivery Foundation
- правила коммитов и quality gates в GitHub remote;
- CI/CD;
- трассируемость изменений;
- observability и audit trail.

## 6. Main development directions

1. GitHub governance and commit policy.
2. Platform stabilization based on existing services.
3. Domain management and UI-configurable domain model.
4. Transition from project/service model to domain/context model.
5. Workflow engine introduction.
6. Domain QA agents and domain profiles.
7. Frontend workspace for QA.
8. Integration hub and OAuth.
9. Event-driven extension through pluggable event sources.
10. Analytics, quality gates, release readiness.
11. Reliability, security, scalability.

## 7. Stage 0 — GitHub remote governance and commit rules

Это приоритет №1 и должно быть завершено раньше, чем активная разработка платформенных фич.

Цели этапа:
- Зафиксировать единые правила коммитов и ветвления.
- Подготовить репозиторий к безопасной и дисциплинированной совместной разработке.
- Встроить контроль качества на уровне GitHub remote.

Подзадачи:
- Определить commit convention.
- Настроить branch protection rules для `main`.
- Настроить required checks.
- Поддерживать commit lint локально и в CI.
- Поддерживать PR templates, issue templates и ADR discipline.
- Определить release tagging и versioning policy.

Статус:
- Часть файловой базы already done.
- Осталось завершить remote settings в GitHub.

## 8. Stage 1 — Stabilize and document current platform skeleton

Это обязательный этап после анализа фактического состояния backend.

Цели этапа:
- Понять и зафиксировать реальную ответственность уже существующих сервисов.
- Привести текущий скелет платформы к понятной и документированной архитектуре.
- Избежать лишнего переписывания там, где уже есть полезный foundation.

Подзадачи:
- Проанализировать и задокументировать:
  - `qa_task_api`;
  - `qa_orchestrator`;
  - `qa_llm_gateway`;
  - `qa_rag_service`;
  - `qa_result_service`;
  - `qa_integration_service`.
- Уточнить фактические контракты между сервисами.
- Описать event topics, payload shape и boundaries.
- Описать текущую data model в БД.
- Зафиксировать что оставить, что переработать, что удалить.
- Проверить, какие части платформы слишком жёстко завязаны на текущие assumptions и требуют abstraction.

Результат этапа:
- появляется честная карта существующей архитектуры;
- дальнейший roadmap опирается на код, а не только на идеальный дизайн.

## 9. Stage 2 — Domain management and stack-agnostic platform model

Это новый ключевой этап, вытекающий из требований stack-agnostic design и UI-configurable domains.

Цели этапа:
- Ввести домены как полноценную продуктовую сущность.
- Позволить создавать и настраивать домены через UI.
- Отвязать продуктовую модель от жёстко заданного стека тестируемой системы.

Подзадачи:
- Ввести сущность `Domain`.
- Ввести сущность `DomainProfile`.
- Определить configurable fields domain profile:
  - имя;
  - описание;
  - tags;
  - business scope;
  - supported artifacts;
  - prompt policy settings;
  - retrieval policy settings;
  - event source settings;
  - optional integration bindings.
- Реализовать CRUD доменов.
- Реализовать UI для создания/редактирования доменов.
- Сделать так, чтобы новые домены могли появляться без изменений в коде ядра в типовых случаях.
- Отделить product domain configuration от low-level service structure.

Результат этапа:
- домены становятся first-class configurable product entity.

## 10. Stage 3 — Transition to domain/context model

Цели этапа:
- Поверх существующего knowledge layer добавить управляемый lifecycle контекстных файлов по доменам.

Подзадачи:
- Ввести сущность `ContextFile`.
- Связать контекстные файлы с `Domain`.
- Реализовать upload/edit/delete/version replace для context files.
- Связать retrieval с domain scope.
- Обновить task API так, чтобы задача ссылалась на домен.
- Показывать в артефактах, какой контекст был использован.
- Подготовить дальнейшую поддержку context groups и versioned knowledge collections.

Результат этапа:
- knowledge layer становится продуктовой domain-aware capability.

## 11. Stage 4 — Workflow engine introduction

Цели этапа:
- Эволюционировать от execution одиночных задач к управляемым QA workflow.

Подзадачи:
- Ввести `WorkflowDefinition`.
- Ввести `WorkflowRun`.
- Поддержать linear workflows на первом этапе.
- Позволить шагам использовать outputs предыдущих шагов.
- Сохранять step artifacts и execution logs.
- Обновить UI/API под запуск workflow.
- Сделать workflow stack-agnostic и domain-aware.

Примеры целевых workflow:
- requirements analysis → questions → risks → test cases;
- context review → change impact analysis → regression checklist;
- domain kickoff → requirement digest → test plan.

Результат этапа:
- появляется управляемый execution engine для QA processes.

## 12. Stage 5 — Domain QA agents and profiles

Доменные агенты не должны быть полностью жёстко захардкожены под один продукт. Базовая модель должна позволять:
- иметь преднастроенные домены (например, Payments, Session, Rewards, Responsible Gaming);
- добавлять новые домены через UI;
- настраивать domain profile так, чтобы behavior платформы адаптировался без полного кодового расширения.

Первым реальным доменным агентом всё ещё остаётся Payments Agent как наиболее полезный для текущего проекта.

Подзадачи:
- описать baseline domain profile для Payments;
- адаптировать prompts, handlers и artifacts под доменную логику;
- выделить task families for domain workflows;
- добавить domain-specific context and retrieval policy;
- определить, какие аспекты domain behavior configurable, а какие требуют code extension.

Результат этапа:
- платформа становится реально полезной для твоего проекта, не теряя общей расширяемости.

## 13. Stage 6 — Frontend QA workspace

Цели этапа:
- Дать QA-лиду и manual QA команде рабочий UI.

Крупные разделы интерфейса:
- Dashboard;
- Domains;
- Domain Profiles;
- Context Files;
- Tasks;
- Workflows;
- Artifacts;
- Integrations;
- Settings.

Основные пользовательские флоу:
- создать домен;
- настроить domain profile;
- загрузить и поддерживать контекст;
- выбрать домен при запуске task/workflow;
- наблюдать прогресс выполнения;
- просматривать артефакты;
- использовать интеграции.

Результат этапа:
- появляется usable рабочее место для ежедневной работы с платформой.

## 14. Stage 7 — Integration hub and OAuth

Обязательные интеграции:
- Jira;
- Confluence;
- TestRail;
- Slack;
- Postman;
- Figma.

Подзадачи:
- единая модель `IntegrationConnection`;
- secure token management;
- connect/disconnect flows;
- OAuth support where applicable;
- export/import use cases для QA artifacts и контекста;
- привязка интеграций к доменам там, где это имеет продуктовый смысл.

Результат этапа:
- платформа встраивается в реальный рабочий стек QA-команды.

## 15. Stage 8 — Event-source abstraction and product intelligence

Цели этапа:
- Использовать реальные события и telemetry как источник QA-аналитики, не ограничиваясь только одним транспортом.

Подзадачи:
- ввести abstraction для event sources;
- поддержать Kafka как один из источников;
- предусмотреть дальнейшую поддержку других event/log sources;
- привязать события к доменам и сценариям;
- использовать event-informed QA analysis.

Результат этапа:
- платформа остаётся event-ready, но не становится заложником одного транспорта.

## 16. Stage 9 — Artifacts, analytics and quality gates

Цели этапа:
- Помочь принимать решения о качестве и готовности к релизу.

Подзадачи:
- унификация артефактов;
- traceability across domains/tasks/workflows/context;
- quality gates;
- dashboards and reporting for QA lead.

## 17. Stage 10 — Reliability, security and scalability

Подзадачи:
- observability;
- structured logging;
- retries/timeouts/circuit breakers;
- audit trail;
- backup/restore для контекста и метаданных;
- RBAC;
- performance optimization;
- AI cost control.

## 18. Detailed Stage 1 issue backlog

Ниже — детальный backlog для ближайшего этапа стабилизации и документирования текущего skeleton.

### 18.1 Service mapping issues

1. Document `qa_task_api` responsibilities
- Описать API surface, входные payload, allowed task types, DB writes, published events, dependencies.
- Definition of done: есть документ или ADR/tech note с описанием сервиса и его контрактов.

2. Document `qa_orchestrator` responsibilities
- Описать runtime, event consumption, dispatching model, handler boundaries, result persistence path.
- Definition of done: описан текущий execution lifecycle задачи.

3. Document `qa_llm_gateway` responsibilities
- Описать prompt building, supported task modes, normalized outputs, model abstraction limitations.
- Definition of done: видно, какие части уже reusable, а какие слишком tightly coupled.

4. Document `qa_rag_service` responsibilities
- Описать текущую knowledge model, document storage, chunking, metadata scheme, retrieval limitations.
- Definition of done: зафиксировано, как перейти от current knowledge model к domain/context model.

5. Document `qa_result_service` responsibilities
- Описать хранение результатов, artifact contracts, retrieval endpoints, связи с task lifecycle.
- Definition of done: ясно, как artifacts живут после выполнения задач.

6. Document `qa_integration_service` responsibilities
- Проверить текущие возможности, контракты и реальное состояние интеграционного слоя.
- Definition of done: ясно, это foundation под Integration Hub или пока только placeholder.

### 18.2 Contract and data model issues

7. Map current database schema
- Вытащить и описать таблицы, связи, ограничения и несоответствия target product model.
- Definition of done: есть схема current DB model и список gaps.

8. Map current event contracts
- Зафиксировать topics, payload shapes, producers, consumers и слабые места контрактов.
- Definition of done: есть event contract map.

9. Audit current task model
- Проверить, какие поля есть у task, чего не хватает для domain/workflow future model.
- Definition of done: готов список обязательных изменений task schema.

10. Audit current artifact model
- Проверить, как сейчас сохраняются artifacts и как к ним добавить traceability.
- Definition of done: понятна дорожка к artifact lineage.

### 18.3 Architecture transition issues

11. Define domain entity draft
- Спроектировать `Domain` и `DomainProfile` как новую product сущность.
- Definition of done: есть draft schema и границы ответственности.

12. Define stack-agnostic event source abstraction
- Спроектировать abstraction layer для event/log sources без жёсткой привязки только к Kafka.
- Definition of done: понятно, как оставить Kafka support, не делая его единственным путём.

13. Define domain configuration strategy
- Решить, какие параметры домена настраиваются через UI, а какие требуют code/plugin expansion.
- Definition of done: есть матрица configurable vs code-defined behavior.

14. Define migration path from `project/service_name` to `domain/profile/context`
- Описать эволюционный переход без разрушения текущего skeleton.
- Definition of done: есть phased migration strategy.

### 18.4 Execution planning issues

15. Define first thin-slice implementation
- Выбрать минимальный вертикальный срез: Domain CRUD + Payments domain profile + context upload + one domain-scoped task.
- Definition of done: есть конкретный MVP slice для следующей разработки.

16. Define architecture decision backlog
- Выделить решения, которые надо оформить отдельными ADR.
- Definition of done: есть список ADR-кандидатов.

## 19. Updated near-term priorities

Теперь практический порядок выглядит так:
1. Завершить GitHub remote governance.
2. Стабилизировать и задокументировать текущий backend skeleton.
3. Ввести domain management как UI-configurable capability.
4. Перевести knowledge layer на domain/context model.
5. Добавить workflow engine.
6. Сделать первого доменного агента Payments.
7. Построить UI для доменов, контекста, задач и workflow.
8. Развить integration hub.
9. Подключить event-source abstraction и product intelligence.

## 20. MVP definition

Первый реально полезный MVP платформы должен включать:
- GitHub governance completed;
- documented current backend skeleton;
- UI-configurable domain model;
- хотя бы один домен (`Payments`) как baseline profile, но не как hardcoded-only сущность;
- context file upload/edit/delete по доменам;
- domain-scoped retrieval;
- одиночные задачи;
- хотя бы один последовательный workflow;
- базовый web UI;
- хотя бы одну рабочую внешнюю интеграцию.

## 21. Target end-state

Целевое состояние платформы:
- QA создаёт или выбирает домен в UI;
- настраивает domain profile;
- загружает и поддерживает доменный контекст;
- запускает отдельную задачу или workflow;
- получает прозрачные артефакты с указанием использованного контекста;
- экспортирует результат в рабочие системы команды;
- при необходимости использует реальные события и интеграции как дополнительные источники анализа;
- может адаптировать платформу под новые домены и разные продуктовые стеки без полного переписывания ядра.

Этот файл должен обновляться по мере уточнения архитектуры, реализации сервисов и продуктовых приоритетов.