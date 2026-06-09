# ADR — Architecture Decision Records

В этой директории фиксируются архитектурные решения проекта.

## Когда создавать ADR

Создавай ADR, если решение:
- влияет на архитектуру платформы;
- меняет важный контракт или способ интеграции;
- вводит новый инфраструктурный или технологический стандарт;
- затрагивает domain context, workflow engine, agent runtime или integration hub.

## Базовый шаблон ADR

Имя файла:
`NNNN-short-title.md`

Пример:
`0001-adopt-domain-context-service.md`

Рекомендуемая структура:

1. Title
2. Status
3. Context
4. Decision
5. Consequences
6. Alternatives considered

## Статусы

- Proposed
- Accepted
- Superseded
- Rejected
