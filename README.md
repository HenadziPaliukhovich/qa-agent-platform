# QA Agent Platform

![QA Agent Smoke](https://github.com/HenadziPaliukhovich/qa-agent-platform/actions/workflows/smoke.yml/badge.svg)

Starter repository scaffold for an event-driven multi-agent QA platform.

## CI

The repository includes a GitHub Actions smoke workflow at `.github/workflows/smoke.yml` that runs on every push and pull request to `main` and `develop`, and it can also be started manually from the Actions tab with `workflow_dispatch`.[cite:274]

The workflow builds the QA services stack, waits for the API to become healthy, runs `./scripts/smoke-task.sh`, and uploads `smoke-task.log` as an artifact for investigation when a run fails.[cite:272][cite:274]
