from contextlib import ExitStack
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from tendergraph.api.app import create_app
from tendergraph.rag.errors import GenerationUnavailable, InvalidGeneratedAnswer
from tendergraph.rag.evidence import TenderEvidence
from tendergraph.rag.factory import build_answer_service
from tendergraph.rag.pipeline import TenderAnswerService
from tendergraph.rag.service import GroundedRAGService
from tendergraph.rag.settings import RAGSettings


@pytest.fixture
def record() -> TenderEvidence:
    return TenderEvidence(
        citation_id="T9",
        publication_number="123-2026",
        publication_date=date(2026, 9, 25),
        title="Cloud services",
        description="Managed cloud platform",
        lot_description_text=None,
        buyer_name="Example Buyer",
        buyer_country="BEL",
        cpv_codes=["72000000"],
        procedure_type="open",
        contract_natures=["services"],
        estimated_value=None,
        estimated_value_currency=None,
        earliest_deadline=None,
        latest_deadline=None,
        performance_countries=["BEL"],
        performance_regions=[],
        source_html_url="https://ted.europa.eu/en/notice/-/detail/123-2026",
    )


def make_service(record: TenderEvidence, **kwargs: object):
    search, repository = Mock(), Mock()
    search.search.return_value = [
        SimpleNamespace(publication_number=record.publication_number)
    ]
    repository.fetch.return_value = [record]
    return TenderAnswerService(search, repository, **kwargs), search, repository


def test_evidence_mode_and_source_mapping(record):
    service, search, repository = make_service(record)
    result = service.answer(question=" Who is the buyer? ", query="cloud services")
    assert result.status == "evidence_only"
    assert result.citations == ("T1",)
    assert result.evidence[0].citation_id == "T1"
    assert "Estimated value: Not stated" in result.text
    assert "no AI-generated answer" in result.text
    search.search.assert_called_once_with("cloud services", limit=5, retrieval_depth=20)
    repository.fetch.assert_called_once_with(["123-2026"])


def test_no_results_never_calls_generator_or_repository(record):
    provider = Mock()
    service, search, repository = make_service(
        record, mode="ollama", generator=GroundedRAGService(provider)
    )
    search.search.return_value = []
    result = service.answer(question="cloud")
    assert result.status == "no_results"
    assert result.citations == () and result.evidence == ()
    provider.generate.assert_not_called()
    repository.fetch.assert_not_called()


def test_generated_answer_uses_retrieved_sources(record):
    provider = Mock()
    provider.generate.return_value = "The buyer is Example Buyer [T1]."
    service, _, _ = make_service(
        record, mode="ollama", generator=GroundedRAGService(provider)
    )
    result = service.answer(question="Who is the buyer?")
    assert result.status == "answered"
    assert result.citations == ("T1",)
    assert "Example Buyer" in provider.generate.call_args.kwargs["user_prompt"]


@pytest.mark.parametrize("text", ["Uncited fact", "Wrong reference [T9].", ""])
def test_bad_generation_is_rejected(record, text):
    provider = Mock()
    provider.generate.return_value = text
    service, _, _ = make_service(
        record, mode="ollama", generator=GroundedRAGService(provider)
    )
    with pytest.raises(InvalidGeneratedAnswer):
        service.answer(question="Who is the buyer?")


def test_reorders_repository_results_and_relabels_after_reranking(record):
    second = replace(record, publication_number="456-2026", title="Other buyer")
    reranker = Mock()
    service, search, repository = make_service(record, reranker=reranker)
    search.search.return_value = [record, second]
    repository.fetch.return_value = [second, record]
    reranker.rerank.return_value = [second, record]
    result = service.answer(question="cloud", evidence_limit=2)
    assert [
        (item.citation_id, item.publication_number) for item in result.evidence
    ] == [("T1", "456-2026"), ("T2", "123-2026")]
    assert search.search.call_args.kwargs["limit"] == 20


def test_missing_evidence_is_not_silently_ignored(record):
    service, _, repository = make_service(record)
    repository.fetch.return_value = []
    with pytest.raises(RuntimeError, match="do not match"):
        service.answer(question="cloud")


def test_context_is_bounded_and_truncation_disclosed(record):
    provider = Mock()
    provider.generate.return_value = "Cloud service [T1]."
    service, _, _ = make_service(
        replace(record, description="x" * 100000),
        mode="ollama",
        generator=GroundedRAGService(provider),
        max_context_chars=5000,
    )
    result = service.answer(question="What service?")
    assert result.context_truncated
    assert "source excerpt truncated" in result.evidence[0].description
    assert len(provider.generate.call_args.kwargs["user_prompt"]) < 6000


def test_oversized_metadata_fails_before_model_call(record):
    provider = Mock()
    service, _, _ = make_service(
        replace(record, title="x" * 10000),
        mode="ollama",
        generator=GroundedRAGService(provider),
        max_context_chars=2000,
    )
    with pytest.raises(InvalidGeneratedAnswer, match="budget"):
        service.answer(question="cloud")
    provider.generate.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"question": " "},
        {"question": "cloud", "query": " "},
        {"question": "cloud", "evidence_limit": 0},
        {"question": "cloud", "evidence_limit": 5, "retrieval_depth": 4},
    ],
)
def test_invalid_input_does_not_retrieve(record, kwargs):
    service, search, _ = make_service(record)
    with pytest.raises(ValueError):
        service.answer(**kwargs)
    search.search.assert_not_called()


def test_default_factory_does_not_create_llm_clients(record):
    with (
        ExitStack() as resources,
        patch("tendergraph.rag.factory.OpenAIProvider") as remote,
        patch("tendergraph.rag.factory.OllamaProvider") as local,
    ):
        _, search, repository = make_service(record)
        settings = RAGSettings(_env_file=None, provider="evidence")
        service = build_answer_service(search, repository, settings, resources)
        assert service.answer(question="cloud").mode == "evidence"
        remote.assert_not_called()
        local.assert_not_called()


def test_ask_endpoint_runs_pipeline(record):
    app = create_app(use_lifespan=False)
    app.state.answer_service, _, _ = make_service(record)
    with TestClient(app) as client:
        response = client.post("/ask", json={"question": "Who is the buyer?"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "evidence_only"
    assert data["sources"][0]["citation_id"] == data["citations"][0] == "T1"
    assert data["sources"][0]["estimated_value"] is None


@pytest.mark.parametrize(
    "payload",
    [
        {"question": " "},
        {"question": "cloud", "query": " "},
        {"question": "cloud", "provider": "openai"},
        {"question": "cloud", "evidence_limit": 11},
        {"question": "cloud", "evidence_limit": 5, "retrieval_depth": 4},
    ],
)
def test_api_rejects_bad_requests_before_service(payload):
    app = create_app(use_lifespan=False)
    app.state.answer_service = Mock()
    with TestClient(app) as client:
        assert client.post("/ask", json=payload).status_code == 422
    app.state.answer_service.answer.assert_not_called()


@pytest.mark.parametrize(
    "error, code",
    [
        (GenerationUnavailable("secret upstream details"), 503),
        (InvalidGeneratedAnswer("secret model output"), 502),
    ],
)
def test_api_errors_are_sanitized(error, code):
    app = create_app(use_lifespan=False)
    app.state.answer_service = Mock()
    app.state.answer_service.answer.side_effect = error
    with TestClient(app) as client:
        response = client.post("/ask", json={"question": "cloud"})
    assert response.status_code == code
    assert "secret" not in response.text


def test_duplicate_citation_ids_fail_before_generation(record):
    provider = Mock()
    with pytest.raises(ValueError, match="unique"):
        GroundedRAGService(provider).answer(question="cloud", evidence=[record, record])
    provider.generate.assert_not_called()
