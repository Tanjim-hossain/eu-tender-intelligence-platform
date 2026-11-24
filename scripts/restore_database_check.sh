#!/usr/bin/env bash
# Restore ONLY to a newly created disposable database. Never overwrite the live DB.
set -euo pipefail
cd "$(dirname "$0")/.."
backup="${1:?Usage: bash scripts/restore_database_check.sh BACKUP fresh_restore_database}"
target="${2:?A new restore_check_... database name is required}"
[[ -s "$backup" ]] || { echo "Backup is missing or empty" >&2; exit 2; }
[[ "$target" =~ ^restore_check_[a-z0-9_]{1,40}$ ]] || { echo "Use a new restore_check_... database name" >&2; exit 2; }
compose=(docker compose --env-file .env -f infra/compose.yml)
"${compose[@]}" exec -T postgres pg_restore --list < "$backup" >/dev/null
"${compose[@]}" exec -T postgres sh -ec 'test "$1" != "$POSTGRES_DB"; createdb -U "$POSTGRES_USER" "$1"' sh "$target"
"${compose[@]}" exec -T postgres sh -ec 'pg_restore --exit-on-error --no-owner --no-acl -U "$POSTGRES_USER" --dbname="$1"' sh "$target" < "$backup"
"${compose[@]}" exec -T postgres sh -ec 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$1" -c "SELECT current_database(), count(*) FROM silver.tenders;"' sh "$target"
echo "Restore completed in $target; verify counts, search indexes and account isolation before declaring recovery successful."
echo "This script deliberately leaves the test database for inspection."
