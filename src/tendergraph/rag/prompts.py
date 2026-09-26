from __future__ import annotations

from tendergraph.rag.context import (
    build_evidence_context,
)
from tendergraph.rag.evidence import (
    TenderEvidence,
)

SYSTEM_PROMPT = """
You are TenderGraph, an assistant for European
public-procurement analysis.

Rules:
1. Answer only from the supplied tender evidence.
2. Do not invent facts, amounts, deadlines, buyers,
   requirements, or tender conditions.
3. Cite factual claims using the supplied citation IDs,
   for example [T1] or [T2].
4. Never create a citation ID that is not present in
   the evidence.
5. If the evidence is insufficient, explicitly say that
   the available tender evidence is insufficient.
6. Distinguish missing information from negative facts.
   "Not stated" does not mean that something does not
   exist.
7. When comparing tenders, keep facts associated with
   the correct tender.
8. Be concise and factual.
""".strip()


def build_user_prompt(
    *,
    question: str,
    evidence: list[TenderEvidence],
) -> str:
    cleaned_question = " ".join(
        question.strip().split()
    )

    if not cleaned_question:
        raise ValueError(
            "Question must not be empty"
        )

    context = build_evidence_context(
        evidence
    )

    return (
        "Question:\n"
        f"{cleaned_question}\n\n"
        "Tender evidence:\n"
        f"{context}\n\n"
        "Answer the question using only the "
        "evidence above and cite supporting "
        "tenders with [T#] citations."
    )
