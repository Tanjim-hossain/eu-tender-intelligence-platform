#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
umask 077
mkdir -p data/backups
output="data/backups/tendergraph-$(date -u +%Y%m%dT%H%M%SZ).dump"
temporary="$(mktemp data/backups/.backup.XXXXXX)"
trap 'rm -f "$temporary"' EXIT
compose=(docker compose --env-file .env -f infra/compose.yml)
"${compose[@]}" exec -T postgres sh -ec 'pg_dump --format=custom --no-owner --no-acl -U "$POSTGRES_USER" "$POSTGRES_DB"' > "$temporary"
"${compose[@]}" exec -T postgres pg_restore --list < "$temporary" >/dev/null
if [[ -e "$output" ]]; then
    echo "Backup already exists; refusing overwrite" >&2
    exit 1
fi
mv "$temporary" "$output"
echo "Backup created: $output"
