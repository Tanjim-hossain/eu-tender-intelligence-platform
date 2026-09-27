import json
from pathlib import Path

import pytest

from tendergraph.rag.answer import validate_selected_grounded_answer
from tendergraph.rag.evaluation import check_answer, summarize

SUITE = json.loads((Path(__file__).parents[2] / "evaluation/answers/contract_cases.json").read_text())


@pytest.mark.parametrize("case", SUITE["cases"], ids=lambda case: case["id"])
def test_contract_fixture(case):
    result = check_answer(
        case["response"], allowed=set(SUITE["allowed_citations"]),
        expected_selected=set(case["expected_selected"]),
        forbidden_phrases=case.get("forbidden_phrases"),
    )
    assert result["contract_valid"] is case["expected_accept"]
    if case["expected_accept"]:
        assert result["selection_match"]
        assert result["phrase_check_passed"]


def test_none_never_passes_through_unverified_claims():
    answer = validate_selected_grounded_answer(
        "RELEVANT: NONE\nANSWER:\nThe winning bidder is X and the price is 10 million.",
        allowed_citations={"T1"},
    )
    assert answer.text == "The available tender evidence is insufficient to answer the question."
    assert answer.citations == ()


def test_empty_evaluation_does_not_claim_success():
    assert summarize([]) == {"total": 0, "passed": 0, "failed": 0, "pass_rate": None}
