from __future__ import annotations

import re
from dataclasses import dataclass

CITATION_PATTERN = re.compile(
    r"\[(T\d+)\]"
)

RELEVANCE_HEADER_PATTERN = re.compile(
    r"\A"
    r"RELEVANT:\s*"
    r"(?P<ids>NONE|T\d+(?:\s*,\s*T\d+)*)"
    r"\s*\n"
    r"ANSWER:\s*"
    r"\n?",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class GroundedAnswer:
    text: str
    citations: tuple[str, ...]
    selected_citations: tuple[str, ...] = ()


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
        selected_citations=citations,
    )


def validate_selected_grounded_answer(
    text: str,
    *,
    allowed_citations: set[str],
) -> GroundedAnswer:
    cleaned = text.strip()

    match = RELEVANCE_HEADER_PATTERN.match(
        cleaned
    )

    if match is None:
        raise ValueError(
            "Generated answer must contain "
            "the relevance header"
        )

    raw_ids = match.group("ids")

    if raw_ids.upper() == "NONE":
        selected: tuple[str, ...] = ()
    else:
        selected = tuple(
            item.strip().upper()
            for item in raw_ids.split(",")
        )

    if len(set(selected)) != len(selected):
        raise ValueError(
            "Relevant citation IDs must "
            "be unique"
        )

    unknown_selected = (
        set(selected)
        - allowed_citations
    )

    if unknown_selected:
        raise ValueError(
            "Relevance header contains "
            "unknown citations: "
            f"{sorted(unknown_selected)}"
        )

    answer_text = cleaned[
        match.end():
    ].strip()

    answer = validate_grounded_answer(
        answer_text,
        allowed_citations=allowed_citations,
        require_citation=bool(selected),
    )

    mentioned_citations = set(
        re.findall(
            r"\bT[1-9]\d*\b",
            answer.text,
            flags=re.IGNORECASE,
        )
    )

    unselected_mentions = (
        {item.upper() for item in mentioned_citations}
        - set(selected)
    )

    if unselected_mentions:
        raise ValueError(
            "Answer mentions evidence not "
            "selected as relevant: "
            f"{sorted(unselected_mentions)}"
        )

    if not selected:
        if answer.citations:
            raise ValueError(
                "Answer cites evidence while "
                "RELEVANT is NONE"
            )

        return GroundedAnswer(
            text="The available tender evidence is insufficient to answer the question.",
            citations=(),
            selected_citations=(),
        )

    if set(answer.citations) != set(selected):
        raise ValueError(
            "Answer citations must exactly "
            "match selected relevant evidence"
        )

    return GroundedAnswer(
        text=answer.text,
        citations=answer.citations,
        selected_citations=selected,
    )
