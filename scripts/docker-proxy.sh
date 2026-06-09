#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT_DIR="$ROOT_DIR/.agent-proxy"
DOCKER_BIN="/Applications/Docker.app/Contents/Resources/bin/docker"
COMPOSE_CMD=("$DOCKER_BIN" compose)

mkdir -p "$OUT_DIR"

usage() {
  cat <<'EOF'
Usage:
  scripts/docker-proxy.sh logs <service> [tail]
  scripts/docker-proxy.sh logs-all [tail]
  scripts/docker-proxy.sh psql-tables
  scripts/docker-proxy.sh psql-query <SQL>
  scripts/docker-proxy.sh psql-describe <table>
  scripts/docker-proxy.sh redis-ping
  scripts/docker-proxy.sh kafka-topics
  scripts/docker-proxy.sh health
  scripts/docker-proxy.sh ps

Examples:
  scripts/docker-proxy.sh logs qa_task_api 120
  scripts/docker-proxy.sh logs-all 200
  scripts/docker-proxy.sh psql-tables
  scripts/docker-proxy.sh psql-query "select * from domains limit 5;"
  scripts/docker-proxy.sh psql-describe domains
  scripts/docker-proxy.sh redis-ping
  scripts/docker-proxy.sh kafka-topics
  scripts/docker-proxy.sh health
  scripts/docker-proxy.sh ps
EOF
}

write_output() {
  local name="$1"
  shift
  local file="$OUT_DIR/$name.txt"
  {
    echo "# Generated: $(date -Iseconds)"
    echo "# Command: $*"
    echo
    "$@"
  } > "$file" 2>&1 || true
  echo "$file"
}

cmd_logs() {
  local service="${1:-}"
  local tail="${2:-120}"
  if [[ -z "$service" ]]; then
    echo "service is required" >&2
    exit 1
  fi
  write_output "logs-${service}" "${COMPOSE_CMD[@]}" logs --tail "$tail" "$service"
}

cmd_logs_all() {
  local tail="${1:-120}"
  write_output "logs-all" "${COMPOSE_CMD[@]}" logs --tail "$tail"
}

cmd_psql_tables() {
  write_output "psql-tables" "${COMPOSE_CMD[@]}" exec -T postgres psql -U qa -d qa_agent -c "\\dt"
}

cmd_psql_query() {
  local sql="${1:-}"
  if [[ -z "$sql" ]]; then
    echo "SQL is required" >&2
    exit 1
  fi
  write_output "psql-query" "${COMPOSE_CMD[@]}" exec -T postgres psql -U qa -d qa_agent -c "$sql"
}

cmd_psql_describe() {
  local table="${1:-}"
  if [[ -z "$table" ]]; then
    echo "table is required" >&2
    exit 1
  fi
  write_output "psql-describe-${table}" "${COMPOSE_CMD[@]}" exec -T postgres psql -U qa -d qa_agent -c "\d ${table}"
}

cmd_redis_ping() {
  write_output "redis-ping" "${COMPOSE_CMD[@]}" exec -T redis redis-cli ping
}

cmd_kafka_topics() {
  write_output "kafka-topics" "${COMPOSE_CMD[@]}" exec -T kafka kafka-topics --bootstrap-server kafka:9092 --list
}

cmd_health() {
  local file="$OUT_DIR/health.txt"
  {
    echo "# Generated: $(date -Iseconds)"
    for url in \
      http://127.0.0.1:8001/health \
      http://127.0.0.1:8002/health \
      http://127.0.0.1:8003/health \
      http://127.0.0.1:8004/health \
      http://127.0.0.1:8005/health
    do
      echo "## $url"
      curl -sS "$url" || true
      echo
      echo
    done
  } > "$file" 2>&1
  echo "$file"
}

cmd_ps() {
  write_output "docker-ps" "${COMPOSE_CMD[@]}" ps
}

main() {
  local sub="${1:-}"
  case "$sub" in
    logs)
      shift
      cmd_logs "$@"
      ;;
    logs-all)
      shift
      cmd_logs_all "$@"
      ;;
    psql-tables)
      cmd_psql_tables
      ;;
    psql-query)
      shift
      cmd_psql_query "$*"
      ;;
    psql-describe)
      shift
      cmd_psql_describe "$@"
      ;;
    redis-ping)
      cmd_redis_ping
      ;;
    kafka-topics)
      cmd_kafka_topics
      ;;
    health)
      cmd_health
      ;;
    ps)
      cmd_ps
      ;;
    *)
      usage
      exit 1
      ;;
  esac
}

main "$@"
