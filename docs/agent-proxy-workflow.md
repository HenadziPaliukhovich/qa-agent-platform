# Agent Proxy Workflow for Docker Logs and Database Diagnostics

This project uses a file-based proxy workflow for Docker logs, Compose state, health checks, and PostgreSQL diagnostics.[cite:111][cite:113] The workflow exists because the agent can modify repository files and read generated artifacts, but cannot directly use the Docker daemon from its execution environment due to Docker socket access limitations.[cite:107][cite:109][cite:110]

## Why this workflow exists

The repository includes a helper script at `scripts/docker-proxy.sh` that runs local Docker Compose and PostgreSQL commands on the developer machine, then writes the results into `.agent-proxy/*.txt` files inside the repository.[cite:111] Once these files exist, the agent can inspect them like any other project file and continue debugging without requiring direct Docker access.[cite:111][cite:113]

## How it works

The script uses the Docker CLI bundled inside Docker Desktop at `/Applications/Docker.app/Contents/Resources/bin/docker` and wraps `docker compose` commands.[cite:111] Each command writes timestamped output into `.agent-proxy`, preserving the exact shell command that produced the file for traceability.[cite:111]

## Supported commands

| Command | Purpose | Output file |
|---|---|---|
| `./scripts/docker-proxy.sh ps` | Capture `docker compose ps` state | `.agent-proxy/docker-ps.txt` |
| `./scripts/docker-proxy.sh health` | Capture HTTP health endpoints for local services | `.agent-proxy/health.txt` |
| `./scripts/docker-proxy.sh logs qa_task_api 120` | Capture service-specific logs | `.agent-proxy/logs-qa_task_api.txt` |
| `./scripts/docker-proxy.sh logs-all 200` | Capture logs for all compose services | `.agent-proxy/logs-all.txt` |
| `./scripts/docker-proxy.sh psql-tables` | Capture PostgreSQL table list | `.agent-proxy/psql-tables.txt` |
| `./scripts/docker-proxy.sh psql-query "select * from domains limit 5;"` | Capture arbitrary SQL query output | `.agent-proxy/psql-query.txt` |
| `./scripts/docker-proxy.sh psql-describe domains` | Describe a PostgreSQL table schema | `.agent-proxy/psql-describe-domains.txt` |
| `./scripts/docker-proxy.sh redis-ping` | Verify Redis connectivity from the container | `.agent-proxy/redis-ping.txt` |
| `./scripts/docker-proxy.sh kafka-topics` | List Kafka topics from the broker container | `.agent-proxy/kafka-topics.txt` |

The `logs <service>` command is already generic, so adding support for a new compose service usually does not require code changes.[cite:114] For a newly added service, the developer normally only needs to run `./scripts/docker-proxy.sh logs <service-name> <tail>`.[cite:114]

## Working agreement

The developer runs proxy commands locally whenever container state, service logs, Kafka state, Redis status, or PostgreSQL state must be inspected.[cite:111] The agent then reads the generated files in `.agent-proxy` and uses them as the primary evidence for diagnosis and next-step recommendations.[cite:111][cite:113]

Recommended loop:

1. Reproduce the issue locally.
2. Run one or more proxy commands that capture the failing service state.
3. Let the agent inspect the new `.agent-proxy` files.
4. Apply the next code or config fix.
5. Re-run the proxy commands to confirm the fix.

## When to use which command

Use `logs <service>` for targeted debugging of one service, especially `qa_task_api`, `qa_rag_service`, `qa_orchestrator`, or `qa_result_service` during endpoint and event-flow debugging.[cite:111] Use `logs-all` when the failure may be cross-service, such as Kafka delivery, orchestrator persistence, or multi-service startup issues.[cite:111]

Use `psql-tables` first when an API returns `500` and a schema mismatch is suspected, because it quickly shows whether required tables exist.[cite:106][cite:111] Use `psql-describe <table>` and `psql-query` when the tables exist but column shape, data state, or migration drift must be verified.[cite:111]

Use `health` after restarts to verify the basic service layer before deeper debugging.[cite:111] Use `redis-ping` and `kafka-topics` only when the problem appears to involve infrastructure dependencies rather than HTTP routes or SQL queries.[cite:111]

## How to extend the script

To add a new diagnostic command, make three changes in `scripts/docker-proxy.sh`.[cite:114] Add the new command to `usage()`, implement a new `cmd_<name>()` function, and register it in the `case` statement inside `main()`.[cite:114]

A new compose service usually does not require any script change for logs, because the generic `logs <service>` command already handles arbitrary service names.[cite:114] A script change is only needed when introducing a new diagnostic pattern, such as a custom `docker compose exec` command, a new health target group, or a specialized infrastructure check.[cite:114]

## Repository conventions

Generated proxy files live in `.agent-proxy/` and should be treated as temporary diagnostics artifacts rather than source files.[cite:111][cite:113] The script writes a timestamp and the originating command into every output file so results remain auditable during debugging sessions.[cite:111]

When debugging a new failure, prefer small, targeted captures first, such as one service log file and one PostgreSQL output file, before generating broad log dumps.[cite:111] This keeps the agent context cleaner and shortens the loop between reproduction and fix validation.[cite:111]
