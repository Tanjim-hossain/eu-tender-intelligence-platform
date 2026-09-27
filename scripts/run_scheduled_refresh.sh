#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(
  cd "$(dirname "${BASH_SOURCE[0]}")"
  pwd
)"

REPO_ROOT="$(
  cd "${SCRIPT_DIR}/.."
  pwd
)"

export PATH="${HOME}/.local/bin:/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

cd "${REPO_ROOT}"

echo "============================================================"
echo "TenderGraph scheduled refresh"
echo "Started: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Repo:    ${REPO_ROOT}"
echo "============================================================"

if [[ ! -f ".env" ]]; then
  echo "ERROR: ${REPO_ROOT}/.env does not exist." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is not available on PATH." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is not available on PATH." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not available."

  if [[ -d "/Applications/Docker.app" ]]; then
    echo "Starting Docker Desktop..."
    /usr/bin/open -gja Docker

    docker_ready=0

    for _ in $(seq 1 45); do
      if docker info >/dev/null 2>&1; then
        docker_ready=1
        break
      fi

      sleep 2
    done

    if [[ "${docker_ready}" -ne 1 ]]; then
      echo "ERROR: Docker did not become ready within 90 seconds." >&2
      exit 1
    fi
  else
    echo "ERROR: Docker Desktop is not available." >&2
    exit 1
  fi
fi

echo
echo "Ensuring PostgreSQL service is running..."

docker compose \
  --env-file .env \
  -f infra/compose.yml \
  up -d postgres

postgres_ready=0

for _ in $(seq 1 30); do
  if docker compose \
    --env-file .env \
    -f infra/compose.yml \
    exec -T postgres \
    sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    >/dev/null 2>&1
  then
    postgres_ready=1
    break
  fi

  sleep 2
done

if [[ "${postgres_ready}" -ne 1 ]]; then
  echo "ERROR: PostgreSQL did not become ready within 60 seconds." >&2
  exit 1
fi

echo "PostgreSQL is ready."

echo
echo "Starting scheduled TED refresh..."

status=0
uv run --frozen --env-file .env \
  python scripts/scheduled_refresh.py "$@" || status=$?

echo
echo "============================================================"
echo "Finished: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "Exit:     ${status}"
echo "============================================================"

exit "${status}"
