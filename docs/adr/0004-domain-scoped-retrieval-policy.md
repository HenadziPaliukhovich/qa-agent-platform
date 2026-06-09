# ADR 0004: Domain-scoped retrieval policy

## Status

Proposed

## Context

Платформа переходит к модели, в которой домен становится основной продуктовой сущностью для контекста, задач и workflow. После введения `Domain`, `DomainProfile` и domain context storage нужно определить базовое правило retrieval.

Без явной retrieval policy возникают критичные риски:
- LLM может получать нерелевантный контекст из других предметных областей;
- пользователь не сможет понять, почему задача опиралась на те или иные документы;
- trust и explainability результата снизятся;
- поведение платформы станет непредсказуемым при росте числа доменов.

Особенно опасен implicit cross-domain retrieval по умолчанию. Он может казаться удобным на раннем этапе, но фактически размывает execution scope, затрудняет отладку и создаёт слабую продуктовую модель.

Для первого thin slice нужна retrieval policy, которая:
- понятна пользователю;
- совместима с UI-configurable domains;
- минимизирует риск загрязнения контекста;
- обеспечивает прозрачность используемых источников.

## Decision

Принято решение: retrieval по умолчанию должен быть строго domain-scoped.

Это означает:
- каждая domain-aware задача выполняется в рамках одного выбранного `domain_id`;
- retrieval ищет контекст только внутри этого домена;
- cross-domain retrieval по умолчанию запрещён;
- если позже потребуется multi-domain analysis, он должен быть отдельным явным режимом, а не скрытым default behavior.

Базовые правила thin slice:
- `domain_id` определяет основной retrieval scope;
- если пользователь не указал дополнительные ограничения, retrieval использует active context files выбранного домена;
- если переданы `selected_context_ids`, retrieval дополнительно ограничивается только этими context files;
- retrieval должен возвращать source references для использованных chunks.

Правила explainability:
- каждый retrieval result должен позволять сослаться на `domain_id`, `context_file_id`, `chunk_id`, `chunk_index` и краткий preview chunk content;
- эти ссылки должны быть доступны downstream-сервисам для сохранения в result/artifact contract.

Правила на будущее:
- cross-domain retrieval допускается только как explicit feature;
- такой режим должен быть явно виден в UI и API;
- он не должен переопределять стандартное безопасное поведение domain-scoped retrieval.

## Consequences

Плюсы:
- execution scope становится предсказуемым;
- снижается риск нерелевантного контекста и prompt contamination;
- пользователю проще доверять результату;
- проще дебажить retrieval и объяснять источник ответа;
- domain model получает реальный operational смысл, а не только роль контейнера.

Минусы и компромиссы:
- в некоторых сценариях может не хватать контекста из соседних доменов;
- придётся отдельно проектировать режимы multi-domain analysis позже;
- пользователю может понадобиться явный выбор context files при сложных кейсах.

Дополнительные последствия:
- API и UI должны явно передавать `domain_id`;
- result/artifact contract должен сохранять used-context references;
- retrieval service должен понимать active/deleted status context files и respect domain boundaries.

## Alternatives considered

- Делать retrieval по всем доступным документам без ограничения доменом.
- Использовать `project_id` или `service_name` как основной retrieval scope вместо домена.
- Разрешить cross-domain retrieval по умолчанию для повышения recall.
- Отложить решение о retrieval scope до более позднего этапа.
