"""Answer contract checks; not a factual-entailment grader."""
from __future__ import annotations

from typing import Any

from tendergraph.rag.answer import validate_selected_grounded_answer


def check_answer(
    text: str, *, allowed: set[str], expected_selected: set[str],
    forbidden_phrases: list[str] | None = None,
) -> dict[str, Any]:
    try:
        answer = validate_selected_grounded_answer(text, allowed_citations=allowed)
    except ValueError as exc:
        return {"contract_valid": False, "selection_match": False,
                "phrase_check_passed": False, "error": str(exc), "raw_output": text}
    forbidden = [phrase for phrase in forbidden_phrases or []
                 if phrase.casefold() in answer.text.casefold()]
    return {
        "contract_valid": True,
        "selection_match": set(answer.selected_citations) == expected_selected,
        "phrase_check_passed": not forbidden,
        "matched_forbidden_phrases": forbidden,
        "selected_citations": list(answer.selected_citations),
        "citations": list(answer.citations), "answer": answer.text, "raw_output": text,
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    passed = sum(row["passed"] is True for row in rows)
    return {"total": len(rows), "passed": passed, "failed": len(rows) - passed,
            "pass_rate": passed / len(rows) if rows else None}
