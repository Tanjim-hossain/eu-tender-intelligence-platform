.PHONY: install check serve evaluate evaluate-local
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
