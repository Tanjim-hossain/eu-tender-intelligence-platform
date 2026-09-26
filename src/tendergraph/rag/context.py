from __future__ import annotations

from tendergraph.rag.evidence import (
    TenderEvidence,
)


def _value(
    item: TenderEvidence,
) -> str:
    if item.estimated_value is None:
        return "Not stated"

    currency = (
        item.estimated_value_currency
        or ""
    )

    return (
        f"{item.estimated_value} "
        f"{currency}"
    ).strip()


def _deadline(
    item: TenderEvidence,
) -> str:
    if item.earliest_deadline is None:
        return "Not stated"

    return (
        item.earliest_deadline
        .isoformat()
    )


def format_evidence(
    item: TenderEvidence,
) -> str:
    parts = [
        f"[{item.citation_id}]",
        (
            "Publication number: "
            f"{item.publication_number}"
        ),
        f"Title: {item.title}",
        (
            "Buyer: "
            f"{item.buyer_name or 'Not stated'}"
        ),
        (
            "Buyer country: "
            f"{item.buyer_country}"
        ),
        (
            "Procedure: "
            f"{item.procedure_type or 'Not stated'}"
        ),
        (
            "Estimated value: "
            f"{_value(item)}"
        ),
        (
            "Earliest deadline: "
            f"{_deadline(item)}"
        ),
        (
            "CPV codes: "
            + (
                ", ".join(item.cpv_codes)
                or "Not stated"
            )
        ),
        (
            "Performance countries: "
            + (
                ", ".join(
                    item.performance_countries
                )
                or "Not stated"
            )
        ),
    ]

    if item.description:
        parts.append(
            "Description: "
            f"{item.description}"
        )

    if (
        item.lot_description_text
        and item.lot_description_text
        != item.description
    ):
        parts.append(
            "Lot information: "
            f"{item.lot_description_text}"
        )

    parts.append(
        "Source: "
        f"{item.source_html_url}"
    )

    return "\n".join(parts)


def build_evidence_context(
    evidence: list[TenderEvidence],
) -> str:
    if not evidence:
        raise ValueError(
            "At least one evidence item "
            "is required"
        )

    return "\n\n".join(
        format_evidence(item)
        for item in evidence
    )
