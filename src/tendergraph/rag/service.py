from __future__ import annotations

import re

from tendergraph.rag.answer import (
    GroundedAnswer,
    validate_selected_grounded_answer,
)
from tendergraph.rag.evidence import (
    TenderEvidence,
)
from tendergraph.rag.prompts import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from tendergraph.rag.provider import (
    LLMProvider,
)


class GroundedRAGService:
    def __init__(
        self,
        provider: LLMProvider,
    ) -> None:
        self._provider = provider

    def answer(
        self,
        *,
        question: str,
        evidence: list[TenderEvidence],
    ) -> GroundedAnswer:
        if not evidence:
            raise ValueError(
                "Evidence must not be empty"
            )

        allowed_citations = {
            item.citation_id
            for item in evidence
        }

        if (
            len(allowed_citations)
            != len(evidence)
            or any(
                re.fullmatch(
                    r"T[1-9]\d*",
                    item.citation_id,
                )
                is None
                for item in evidence
            )
        ):
            raise ValueError(
                "Evidence citation IDs must "
                "be unique T1-style IDs"
            )

        user_prompt = build_user_prompt(
            question=question,
            evidence=evidence,
        )

        response = self._provider.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        return validate_selected_grounded_answer(
            response,
            allowed_citations=(
                allowed_citations
            ),
        )
