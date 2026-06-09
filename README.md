# QA Agent Platform

![QA Agent Smoke](https://github.com/HenadziPaliukhovich/qa-agent-platform/actions/workflows/smoke.yml/badge.svg)

Starter repository scaffold for an event-driven multi-agent QA platform.

## CI

The repository includes a GitHub Actions health workflow at `.github/workflows/smoke.yml` that runs on every push and pull request to `main` and `develop`, and it can also be started manually from the Actions tab with `workflow_dispatch`.

The workflow brings up the compose stack, waits for the API to become healthy, verifies `GET /health` and `GET /openapi.json`, and uploads `openapi.json` as an artifact for investigation.

## Local smoke suite

Use the local smoke flow for the real end-to-end QA agent check with migrations, orchestrator, LLM gateway, and Ollama-backed task execution.

### Full smoke run

```bash
cd ~/projects/qa-agent-platform/qa-agent-platform

make smoke-up
make seed-domain
make smoke
make smoke-logs
```

This flow brings up infrastructure and services, applies migrations, seeds an active default domain, runs smoke across 6 task types, and writes the final execution details to `smoke-task.log`.

The seeded default domain is:
- `domain_id=11111111-1111-1111-1111-111111111111`
- `slug=payments`
- `status=active`

### One-task smoke

For a faster local check, run smoke against a single task type.

```bash
cd ~/projects/qa-agent-platform/qa-agent-platform

make seed-domain
make smoke-one-test-case
make smoke-logs
```

Supported task-type shortcuts are exposed in the `Makefile` for `test_case_generation`, `requirements_analysis`, `manual_test_case_review`, `test_plan`, `test_report`, and `release_readiness`.
