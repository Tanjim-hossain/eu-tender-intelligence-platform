from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Literal, Protocol

from tendergraph.rag.context import build_evidence_context, format_evidence
from tendergraph.rag.errors import InvalidGeneratedAnswer
from tendergraph.rag.evidence import TenderEvidence
from tendergraph.rag.service import GroundedRAGService
from tendergraph.rag.settings import AnswerMode


class NoticeRef(Protocol):
    @property
    def publication_number(self) -> str: ...


class SearchBackend(Protocol):
    def search(
        self, query: str, *, limit: int, retrieval_depth: int
    ) -> Sequence[NoticeRef]: ...


class EvidenceBackend(Protocol):
    def fetch(self, publication_numbers: list[str]) -> list[TenderEvidence]: ...


class EvidenceReranker(Protocol):
    def rerank(
        self,
        query: str,
        publication_numbers: list[str],
        documents: dict[str, str],
        *,
        limit: int,
    ) -> Sequence[NoticeRef]: ...


@dataclass(frozen=True, slots=True)
class AnswerResult:
    question: str
    mode: AnswerMode
    status: Literal["evidence_only", "answered", "no_results", "insufficient_evidence"]
    text: str
    citations: tuple[str, ...]
    evidence: tuple[TenderEvidence, ...]
    context_truncated: bool = False


class TenderAnswerService:
    """Retrieve, optionally rerank, fetch evidence, then render or generate."""

    def __init__(
        self,
        search: SearchBackend,
        repository: EvidenceBackend,
        *,
        mode: AnswerMode = "evidence",
        generator: GroundedRAGService | None = None,
        reranker: EvidenceReranker | None = None,
        max_context_chars: int = 40000,
    ) -> None:
        if (mode == "evidence") != (generator is None):
            raise ValueError("Generation mode and generator must agree")
        if max_context_chars < 2000:
            raise ValueError("Context budget must be at least 2000 characters")
        self._search = search
        self._repository = repository
        self._mode = mode
        self._generator = generator
        self._reranker = reranker
        self._max_context_chars = max_context_chars

    def answer(
        self,
        *,
        question: str,
        query: str | None = None,
        evidence_limit: int = 5,
        retrieval_depth: int = 20,
    ) -> AnswerResult:
        question = " ".join(question.split())
        query = " ".join((query if query is not None else question).split())
        if not question or len(question) > 2000:
            raise ValueError("Question must contain 1 to 2000 characters")
        if not query or len(query) > 2000:
            raise ValueError("Query must contain 1 to 2000 characters")
        if (
            not 1 <= evidence_limit <= 10
            or not evidence_limit <= retrieval_depth <= 100
        ):
            raise ValueError("Invalid evidence limit or retrieval depth")
        hits = self._search.search(
            query,
            limit=retrieval_depth if self._reranker else evidence_limit,
            retrieval_depth=retrieval_depth,
        )
        if not hits:
            return AnswerResult(
                question,
                self._mode,
                "no_results",
                "No tender evidence was retrieved. Try a more specific search query.",
                (),
                (),
            )

        ids = [hit.publication_number for hit in hits]
        if len(set(ids)) != len(ids):
            raise RuntimeError("Duplicate retrieved notices")
        records = self._repository.fetch(ids)
        by_id = {item.publication_number: item for item in records}
        if len(by_id) != len(records) or set(by_id) != set(ids):
            raise RuntimeError("Retrieved notices and evidence do not match")
        if self._reranker:
            # Use the same document representation as the existing evaluation.
            from dataclasses import asdict

            from tendergraph.search.reranker import reranker_document_text

            reranked = self._reranker.rerank(
                query,
                ids,
                {
                    key: reranker_document_text(asdict(item))
                    for key, item in by_id.items()
                },
                limit=min(evidence_limit, len(ids)),
            )
            ids = [hit.publication_number for hit in reranked]
            if not ids or len(set(ids)) != len(ids) or not set(ids) <= set(by_id):
                raise RuntimeError("Invalid reranker results")

        # Fresh IDs always follow final evidence order, including after reranking.
        evidence = [
            replace(by_id[key], citation_id=f"T{index}")
            for index, key in enumerate(ids[:evidence_limit], start=1)
        ]
        truncated = False
        if self._generator is None:
            text = (
                "Retrieved tender evidence (no generated answer). "
                "These are search matches, not verified answers to the question.\n\n"
                + build_evidence_context(evidence)
            )
            citations = tuple(item.citation_id for item in evidence)
            status: Literal[
                "evidence_only", "answered", "no_results", "insufficient_evidence"
            ] = "evidence_only"
        else:
            # Never silently cut off a source mid-field. Remove whole notices
            # at the end, and explicitly mark shortened long descriptions.
            bounded: list[TenderEvidence] = []
            used = 0
            for item in evidence:
                clipped = replace(
                    item,
                    description=self._clip(item.description),
                    lot_description_text=self._clip(item.lot_description_text),
                )
                truncated |= clipped != item
                size = len(format_evidence(clipped)) + (2 if bounded else 0)
                if used + size > self._max_context_chars:
                    truncated = True
                    break
                bounded.append(clipped)
                used += size
            if not bounded:
                raise InvalidGeneratedAnswer("Evidence exceeds the context budget")
            evidence = bounded
            try:
                answer = self._generator.answer(
                    question=question,
                    evidence=evidence,
                )
            except ValueError as exc:
                raise InvalidGeneratedAnswer(
                    "Generated answer failed citation validation; inspect sources or retry"
                ) from exc
            selected = set(
                answer.selected_citations
            )

            evidence = [
                item
                for item in evidence
                if item.citation_id in selected
            ]

            text = answer.text
            citations = answer.citations
            status = "answered" if selected else "insufficient_evidence"
        return AnswerResult(
            question, self._mode, status, text, citations, tuple(evidence), truncated
        )

    @staticmethod
    def _clip(text: str | None) -> str | None:
        if text is None or len(text) <= 3000:
            return text
        return text[:3000] + " [source excerpt truncated]"
