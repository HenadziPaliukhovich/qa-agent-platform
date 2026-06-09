# ADR 0002: Migration from `project/service_name` to `domain/profile/context`

## Status

Proposed

## Context

Текущий backend уже содержит рабочий foundation:
- task API;
- orchestrator;
- RAG service;
- LLM gateway;
- result persistence.

При этом knowledge layer и часть execution model пока строятся вокруг `project_id` и `service_name`. Эта модель полезна как стартовая техническая структура, но она не соответствует целевому продукту, где основными сущностями должны стать домены, domain profiles, context files и domain-aware execution.

Полный одномоментный отказ от текущей модели создаёт высокий риск:
- сломать существующий task flow;
- потерять совместимость между сервисами;
- увеличить объём изменений в одном релизе;
- усложнить отладку и rollback.

С другой стороны, сохранение старой модели без стратегии миграции закрепит архитектурный долг и затормозит развитие UI-configurable domain model.

Нужна эволюционная стратегия миграции, которая позволит:
- использовать уже существующий foundation;
- постепенно вводить новые продуктовые сущности;
- сохранить переходный период совместимости;
- не блокировать разработку thin slice.

## Decision

Принято решение делать миграцию поэтапно, additive-first подходом.

Это означает:
- новые сущности `Domain`, `DomainProfile`, `ContextFile` и domain-scoped retrieval добавляются поверх текущей модели;
- текущие сущности `project_id` и `service_name` не удаляются немедленно;
- новая execution path вводится параллельно старой;
- после стабилизации нового пути старая модель постепенно де-преферируется и затем удаляется.

Этапы миграции:

1. **Introduce new product entities**
- Добавить таблицы и API для `domains`, `domain_profiles`, `domain_context_files`, `domain_context_chunks`.
- Не ломать текущие knowledge tables и task schema на первом шаге.

2. **Enable domain-aware thin slice**
- Добавить `domain_id` в новый task flow.
- Ввести domain-scoped retrieval.
- Начать сохранять used-context references в artifacts/results.
- UI thin slice строить уже на domain model.

3. **Run dual model in transition period**
- Существующие сценарии могут временно продолжать использовать `project_id/service_name`.
- Новый UI и новые execution сценарии должны использовать `domain_id`.
- Внутри сервисов допускается временная поддержка обеих моделей.

4. **Define mapping and migration rules**
- Для существующих knowledge documents должна быть определена стратегия привязки к доменам.
- Mapping может быть ручным, полуавтоматическим или seed-based на раннем этапе.
- Старые поля сохраняются до завершения миграции.

5. **De-prefer legacy model**
- После того как thin slice стабилен, новая модель становится recommended/default path.
- Старые поля и legacy flow помечаются как transitional.

6. **Retire legacy model later**
- Удаление или сильное упрощение legacy model выполняется только после того, как новые сценарии покрывают реальный рабочий процесс.

Принцип миграции:
- сначала additive changes;
- затем parallel usage;
- затем default switch;
- только потом cleanup.

## Consequences

Плюсы:
- снижается риск сломать текущий backend foundation;
- можно быстро двигаться к thin slice без big-bang rewrite;
- разработка UI-configurable domain model не блокируется состоянием legacy path;
- проще тестировать и откатывать изменения.

Минусы и компромиссы:
- некоторое время придётся поддерживать две модели одновременно;
- временно вырастет сложность кода и схем данных;
- нужно будет явно документировать, какой path legacy, а какой target;
- возможна путаница в API и внутренних контрактах, если migration boundaries не будут чётко описаны.

Дополнительные последствия:
- нужны отдельные ADR и tech notes по mapping strategy;
- нужен план deprecation;
- нужно следить, чтобы dual-model period не затянулся бесконечно.

## Alternatives considered

- Big-bang rewrite с немедленной заменой текущей модели на `domain/profile/context`.
- Сохранение текущей модели без явной migration strategy.
- Полный отказ от backward compatibility на раннем этапе.
- Попытка замаскировать старую модель под новую без явного введения новых сущностей.
