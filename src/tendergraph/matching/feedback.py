"""Conservative account-specific ranking, without changing the profile-fit score."""
from __future__ import annotations

from collections import Counter

from tendergraph.matching.models import CompanyMatchResult, TenderMatch
from tendergraph.product.models import StoredOpportunityState


def rerank_matches(
    result: CompanyMatchResult,
    feedback: list[StoredOpportunityState],
    *,
    limit: int,
) -> CompanyMatchResult:
    excluded = {
        item.publication_number for item in feedback
        if item.disposition == "ignored" or item.pipeline_stage == "no_bid"
    }
    positive: Counter[tuple[str, str]] = Counter()
    negative: Counter[tuple[str, str]] = Counter()
    for item in feedback:
        snapshot = item.snapshot
        if snapshot is None or not snapshot.buyer_name:
            continue
        key = (snapshot.buyer_country, snapshot.buyer_name.strip().casefold())
        if item.pipeline_stage == "no_bid":
            negative[key] += 1
        elif item.disposition == "saved":
            positive[key] += 1

    ranked: list[tuple[float, TenderMatch]] = []
    for match in result.matches:
        if match.publication_number in excluded:
            continue
        key = (match.buyer_country, (match.buyer_name or "").strip().casefold())
        # Cap feedback influence at five points; never alter the reported fit.
        adjustment = max(-5, min(5, 2 * (positive[key] - negative[key])))
        if adjustment:
            field = "why_matches" if adjustment > 0 else "risks"
            reasons = match.why_matches if adjustment > 0 else match.risks
            match = match.model_copy(update={
                field: [*reasons, "Ranking adjusted using your saved/no-bid buyer history "
                        f"({adjustment:+d} ranking points; fit unchanged)."],
            })
        ranked.append((match.match_score + adjustment, match))
    ranked.sort(key=lambda pair: (-pair[0], -pair[1].rrf_score, pair[1].publication_number))
    selected = [match for _, match in ranked[:limit]]
    return result.model_copy(update={"matches": selected, "count": len(selected)})
