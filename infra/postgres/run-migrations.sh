#!/usr/bin/env sh
set -eu

DB_HOST="${POSTGRES_HOST:-postgres}"
DB_PORT="${POSTGRES_PORT:-5432}"
DB_NAME="${POSTGRES_DB:-qa_agent}"
DB_USER="${POSTGRES_USER:-qa}"
DB_PASSWORD="${POSTGRES_PASSWORD:-qa}"
MIGRATIONS_DIR="${MIGRATIONS_DIR:-/migrations}"

export PGPASSWORD="$DB_PASSWORD"

until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1; do
  echo "Waiting for Postgres at ${DB_HOST}:${DB_PORT}/${DB_NAME}..."
  sleep 2
done

echo "Postgres is ready."

psql -v ON_ERROR_STOP=1 \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" <<'SQL'
create table if not exists schema_migrations (
  version varchar(255) primary key,
  applied_at timestamptz not null default now()
);
SQL

apply_file() {
  file_path="$1"
  version="$(basename "$file_path")"

  already_applied="$(psql -t -A \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -c "select 1 from schema_migrations where version = '$version' limit 1;")"

  if [ "$already_applied" = "1" ]; then
    echo "Skipping already applied migration: $version"
    return
  fi

  echo "Applying migration: $version"
  psql -v ON_ERROR_STOP=1 \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -f "$file_path"

  psql -v ON_ERROR_STOP=1 \
    -h "$DB_HOST" \
    -p "$DB_PORT" \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    -c "insert into schema_migrations(version) values ('$version');"
}

find "$MIGRATIONS_DIR" -maxdepth 2 -type f -name '*.sql' | sort | while IFS= read -r file; do
  apply_file "$file"
done

echo "All migrations applied."
