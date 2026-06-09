# ADR 0005: Task execution contract with `domain_id`

## Status

Proposed

## Context

После введения доменов как first-class product entity и определения domain-scoped retrieval необходимо зафиксировать, как именно меняется task execution contract.

Текущий task flow уже существует и опирается на модель, где задача содержит `task_type`, input и вспомогательные execution-поля. Однако для новой product model этого недостаточно.

Если task execution contract не будет явно domain-aware:
- retrieval не сможет надёжно ограничиваться правильным scope;
- UI не сможет запускать задачу в контексте конкретного домена;
- artifacts и results не смогут однозначно указывать, в рамках какой предметной области была выполнена задача;
- сохранится разрыв между доменной моделью и execution path.

Для thin slice нужен минимальный, но чёткий контракт, который:
- связывает задачу с доменом;
- поддерживает базовую конфигурацию retrieval scope;
- сохраняет совместимость на переходный период;
- не требует сразу строить workflow engine.

## Decision

Принято решение сделать `domain_id` обязательной частью нового domain-aware task execution path.

Минимальные правила:
- каждая новая domain-aware задача должна содержать `domain_id`;
- task execution contract расширяется полями `domain_id`, `context_scope`, `selected_context_ids`;
- `domain_id` становится основным execution scope для retrieval и generation;
- orchestration и result persistence обязаны передавать и сохранять `domain_id` дальше по execution chain.

Предлагаемая модель полей:
- `domain_id`: обязательный идентификатор домена для нового thin-slice flow;
- `context_scope`: optional enum-like field, например `domain_default|manual_selection`;
- `selected_context_ids`: optional список context files для явного ограничения retrieval.

Поведение thin slice:
- если задача запускается из нового UI flow, `domain_id` обязателен;
- если `context_scope` не указан, используется безопасное поведение `domain_default`;
- если указаны `selected_context_ids`, retrieval ограничивается ими внутри выбранного домена.

Переходный режим:
- legacy path может временно существовать без `domain_id`;
- новый UI и новый execution сценарий должны использовать только domain-aware contract;
- backward compatibility допустима только как transitional measure.

Принцип решения:
- `domain_id` — это не optional metadata, а execution primitive для новой модели.

## Consequences

Плюсы:
- execution path становится согласованным с domain model;
- retrieval behavior становится контролируемым;
- UI получает простой и понятный контракт запуска задач;
- результаты и артефакты можно однозначно связывать с доменом;
- платформа получает фундамент для будущих workflow.

Минусы и компромиссы:
- придётся расширять task schema и API;
- в переходный период будет существовать dual-mode execution;
- часть текущих клиентов или внутренних flows потребует адаптации.

Дополнительные последствия:
- orchestrator должен уметь обрабатывать `domain_id` и `selected_context_ids`;
- task validation должна учитывать новую модель;
- нужно отдельно документировать момент отключения legacy path.

## Alternatives considered

- Оставить `domain_id` только как optional metadata у задачи.
- Вычислять домен неявно через `project_id`, `service_name` или контекстные файлы.
- Поддерживать execution без домена как равноправный основной режим.
- Отложить доменный execution contract до появления workflow engine.
