from __future__ import annotations

import re
from dataclasses import dataclass

CITATION_PATTERN = re.compile(
    r"\[(T\d+)\]"
)


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    text: str
    citations: tuple[str, ...]


def extract_citations(
    text: str,
) -> tuple[str, ...]:
    citations = CITATION_PATTERN.findall(
        text
    )

    return tuple(
        dict.fromkeys(citations)
    )


def validate_grounded_answer(
    text: str,
    *,
    allowed_citations: set[str],
    require_citation: bool = True,
) -> GroundedAnswer:
    cleaned = text.strip()

    if not cleaned:
        raise ValueError(
            "Grounded answer must not be empty"
        )

    citations = extract_citations(
        cleaned
    )

    unknown = (
        set(citations)
        - allowed_citations
    )

    if unknown:
        raise ValueError(
            "Answer contains unknown citations: "
            f"{sorted(unknown)}"
        )

    if require_citation and not citations:
        raise ValueError(
            "Grounded answer must contain "
            "at least one citation"
        )

    return GroundedAnswer(
        text=cleaned,
        citations=citations,
    )
