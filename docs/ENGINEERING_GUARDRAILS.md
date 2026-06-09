# Engineering Guardrails

## Commit Convention

The repository uses Conventional Commits:

- `feat:` — new feature
- `fix:` — bug fix
- `refactor:` — internal restructuring without functional change
- `docs:` — documentation change
- `test:` — tests or validation assets
- `chore:` — maintenance and housekeeping
- `ci:` — CI/CD workflow changes

Examples:

- `feat(orchestrator): split task execution into handlers`
- `fix(task-api): validate payload before publishing event`
- `refactor(llm): unify provider adapter layer`
- `docs(roadmap): add 6-month delivery plan`
- `ci(github): enforce commit message format`

## Branch Naming

Use one of the following prefixes:

- `feature/...`
- `fix/...`
- `refactor/...`
- `docs/...`
- `chore/...`
- `research/...`

Examples:

- `feature/hybrid-rag-search`
- `fix/jira-sync-timeout`
- `refactor/orchestrator-state-machine`
- `docs/roadmap-6m`

## Pull Request Rules

- No direct push to `main`.
- All changes must go through Pull Request.
- At least one reviewer approval is required.
- CI checks must pass before merge.
- Architecture-related changes must update docs when relevant.
- AI-generated changes must be reviewed by a human before merge.

## Remote Repository Rule

Use the following remote policy:

- `origin` — canonical main team repository.
- `upstream` — optional, only when forks are used.

Rules:

- Protected branch settings must be configured on the remote repository.
- `main` must be protected from direct pushes.
- Required status checks must be enabled on the remote.
- Review requirements must be enforced on the remote.

## CI Enforcement Recommendation

Recommended checks:

- commit message validation;
- smoke checks for core services;
- lint and formatting checks;
- basic integration checks for critical connectors;
- prompt regression checks for high-impact agent flows.
