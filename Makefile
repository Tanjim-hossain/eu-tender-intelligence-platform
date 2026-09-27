.PHONY: install check serve evaluate evaluate-local db-up db-health refresh scheduled-refresh

COMPOSE := docker compose --env-file .env -f infra/compose.yml
COUNTRIES ?= BEL NLD DEU ITA

install:
	uv sync --frozen

check:
	uv run --frozen ruff check .
	uv run --frozen mypy src scripts
	uv run --frozen pytest -q
	uv run --frozen python scripts/evaluate_answers.py

serve:
	uv run --frozen uvicorn tendergraph.api.app:app --host 127.0.0.1 --port 8000

evaluate:
	uv run --frozen python scripts/evaluate_answers.py

evaluate-local:
	uv run --frozen python scripts/evaluate_answers.py --live

db-up:
	$(COMPOSE) up -d postgres

db-health:
	$(COMPOSE) exec -T postgres sh -c 'pg_isready -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

refresh:
	@test -n "$(START_DATE)" || (echo "ERROR: START_DATE is required (YYYY-MM-DD)" && exit 2)
	@test -n "$(END_DATE)" || (echo "ERROR: END_DATE is required (YYYY-MM-DD)" && exit 2)
	uv run --frozen --env-file .env python scripts/refresh_tenders.py \
		--start-date "$(START_DATE)" \
		--end-date "$(END_DATE)" \
		--countries $(COUNTRIES)

scheduled-refresh:
	bash scripts/run_scheduled_refresh.sh $(SCHEDULE_ARGS)
