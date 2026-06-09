# ADR 0003: Domain context storage model

## Status

Proposed

## Context

Платформа должна поддерживать работу LLM с контекстом, который:
- загружается пользователем;
- привязан к домену;
- редактируется и удаляется через UI;
- используется в retrieval во время выполнения задач.

Текущий knowledge layer уже умеет хранить документы и чанки, но он не отражает новый продуктовый lifecycle контекста:
- контекст должен быть доменным;
- контекст должен управляться как пользовательский ресурс;
- retrieval должен быть объяснимым;
- модель хранения должна быть достаточно простой для первого thin slice.

При этом преждевременное введение сложной binary ingestion pipeline, object storage abstraction, rich version graph и многоуровневого lifecycle сделает первый вертикальный срез слишком тяжёлым.

Нужна storage model, которая:
- поддерживает тонкий, реалистичный first slice;
- совместима с будущим развитием;
- позволяет прозрачно связывать контекст с задачами и артефактами.

## Decision

Принято решение ввести domain-scoped context storage model, состоящую из двух основных сущностей:
- `domain_context_files`;
- `domain_context_chunks`.

### `domain_context_files`

Эта сущность представляет пользовательский контекстный ресурс внутри домена.

Минимальная ответственность:
- принадлежность к домену;
- идентичность файла;
- человекочитаемое имя;
- исходный текстовый контент;
- metadata и lifecycle status.

Ожидаемые поля первого этапа:
- `context_file_id`;
- `domain_id`;
- `title`;
- `file_name`;
- `content_type`;
- `source`;
- `tags` JSONB;
- `raw_content`;
- `version`;
- `status` (`active|deleted`);
- `created_at`;
- `updated_at`.

### `domain_context_chunks`

Эта сущность представляет retrieval-ready представление контекста.

Минимальная ответственность:
- связь с `context_file_id` и `domain_id`;
- chunk order;
- chunk content;
- token estimate;
- metadata для explainability.

Ожидаемые поля первого этапа:
- `chunk_id`;
- `context_file_id`;
- `domain_id`;
- `chunk_index`;
- `content`;
- `token_estimate`;
- `metadata` JSONB.

### Storage behavior for thin slice

Для первого thin slice принимаются следующие решения:
- ingestion на первом этапе text-first;
- допускается paste/upload текстового контента без полноценного binary file pipeline;
- при создании или изменении контекстного файла chunks строятся заново;
- удаление context file реализуется как soft delete через `status`, а не hard delete;
- редактирование в thin slice допускается как in-place update;
- version field сохраняется уже на первом этапе, но полноценная version lineage откладывается на будущее.

### Explainability rule

Каждый retrieval и artifact contract должен иметь возможность сослаться на:
- `domain_id`;
- `context_file_id`;
- `chunk_id`;
- `chunk_index`;
- preview или fragment chunk content.

Это решение нужно для trust, traceability и пользовательского понимания, почему модель выдала конкретный результат.

## Consequences

Плюсы:
- модель хранения проста и реалистична для первого рабочего среза;
- контекст становится управляемым ресурсом внутри домена;
- retrieval-ready слой отделён от пользовательского file layer;
- soft delete уменьшает риск потери данных;
- explainability можно строить уже в первой версии.

Минусы и компромиссы:
- text-first ingestion ограничивает типы поддерживаемых файлов на раннем этапе;
- in-place update не даёт полноценной истории изменений;
- возможна временная дубликация логики рядом с legacy knowledge storage;
- позже придётся отдельно проектировать object storage и binary ingestion.

Дополнительные последствия:
- потребуется отдельная миграционная стратегия между legacy knowledge tables и domain context tables;
- в будущем понадобится decision по version graph и restore behavior;
- нужно следить, чтобы chunk rebuilding не создавал несогласованность при update/delete сценариях.

## Alternatives considered

- Использовать существующую knowledge model без введения domain-specific storage сущностей.
- Сразу строить полноценную binary/object-storage pipeline.
- Делать hard delete для context files.
- Вводить сложное полноценное versioning уже в первом thin slice.
