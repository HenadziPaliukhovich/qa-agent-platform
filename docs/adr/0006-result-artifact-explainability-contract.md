# ADR 0006: Result artifact explainability contract

## Status

Proposed

## Context

Платформа предназначена для QA-задач, где пользователю важно не только получить сгенерированный результат, но и понимать, на каком основании он был получен.

После введения domain-aware execution и domain-scoped retrieval возникает требование к explainability layer. Если результат сохраняется без ссылок на использованный контекст:
- QA не сможет быстро проверить, на чём основан вывод модели;
- доверие к платформе будет низким;
- сложнее будет дебажить ошибки retrieval или generation;
- артефакты окажутся слабосвязными с контекстом и execution history.

Для первого thin slice не нужна сложная полная provenance graph model, но нужен минимальный explainability contract, который:
- связывает результат с доменом;
- показывает использованные источники контекста;
- остаётся достаточно простым для ранней реализации.

## Decision

Принято решение: каждый domain-aware result/artifact должен сохранять минимальный explainability snapshot.

Этот snapshot становится обязательной частью нового result contract.

Минимальный состав explainability snapshot:
- `task_id`;
- `domain_id`;
- `task_type`;
- `input_snapshot`;
- `normalized_output`;
- `used_context` array.

Каждый элемент `used_context` должен содержать минимум:
- `context_file_id`;
- `title`;
- `chunk_id`;
- `chunk_index`;
- `preview` или краткий фрагмент использованного chunk content.

Если система знает дополнительные metadata, они могут добавляться, но перечисленные поля считаются минимально обязательными для thin slice.

Правила решения:
- explainability snapshot сохраняется вместе с результатом или artifact record;
- snapshot должен быть доступен UI для отображения пользователю;
- snapshot должен быть достаточно стабильным, чтобы использоваться для trust/debugging without rereading raw retrieval logs.

Что intentionally не входит в thin-slice contract:
- полная provenance graph across workflows;
- rich scoring/explanation of why each chunk was ranked;
- complete prompt transcript persistence как обязательная часть первой версии.

## Consequences

Плюсы:
- повышается доверие пользователя к результату;
- QA может быстро проверять источник выводов;
- проще дебажить retrieval и generation pipeline;
- появляется основа для будущей traceability model.

Минусы и компромиссы:
- result/artifact schema станет богаче и сложнее;
- возрастёт объём сохраняемых metadata;
- нужно будет аккуратно выбирать размер `preview`, чтобы не раздувать storage.

Дополнительные последствия:
- result service должен поддержать новый contract;
- UI result view должен уметь отображать used-context references;
- в будущем может понадобиться эволюция этого snapshot в более богатую lineage/provenance model.

## Alternatives considered

- Не сохранять explainability данные в artifact вообще.
- Сохранять только `domain_id` без used-context details.
- Сохранять только `chunk_id` без человекочитаемого preview.
- Сразу проектировать сложную full provenance graph model для первого thin slice.
