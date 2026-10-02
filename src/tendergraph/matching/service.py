from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol

from tendergraph.matching.models import (
    CompanyMatchResult,
    CompanyProfile,
    DeadlineStatus,
    MatchSignals,
    TenderMatch,
    ValueStatus,
)
from tendergraph.search.service import HybridSearchResult


class TenderSearchService(Protocol):
    def search(
        self,
        query: str,
        *,
        limit: int,
        retrieval_depth: int,
    ) -> list[HybridSearchResult]: ...


def build_profile_query(profile: CompanyProfile) -> str:
    parts: list[str] = []
    if profile.description:
        parts.append(profile.description)
    parts.extend(profile.services)
    parts.extend(profile.technologies)
    parts.extend(profile.industries)
    parts.extend(profile.keywords)

    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        key = part.casefold()
        if key not in seen:
            deduped.append(part)
            seen.add(key)

    return " ".join(deduped)


class CompanyMatchingService:
    def __init__(
        self,
        search_service: TenderSearchService,
        *,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._search_service = search_service
        self._now_provider = now_provider or (
            lambda: datetime.now(UTC)
        )

    def match(
        self,
        profile: CompanyProfile,
        *,
        limit: int = 10,
        retrieval_depth: int = 50,
    ) -> CompanyMatchResult:
        if not 1 <= limit <= 50:
            raise ValueError(
                "Match limit must be between 1 and 50"
            )
        if not limit <= retrieval_depth <= 100:
            raise ValueError(
                "Retrieval depth must be between limit and 100"
            )

        query = build_profile_query(profile)
        candidates = self._search_service.search(
            query,
            limit=retrieval_depth,
            retrieval_depth=retrieval_depth,
        )
        now = self._normalize_now(self._now_provider())
        matches = [
            self._score_candidate(
                profile,
                candidate,
                now=now,
            )
            for candidate in candidates
        ]
        matches.sort(
            key=lambda item: (
                -item.match_score,
                -item.rrf_score,
                item.publication_number,
            )
        )
        selected = matches[:limit]

        return CompanyMatchResult(
            profile_name=profile.company_name,
            query=query,
            count=len(selected),
            matches=selected,
        )

    @staticmethod
    def _normalize_now(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _score_candidate(
        self,
        profile: CompanyProfile,
        candidate: HybridSearchResult,
        *,
        now: datetime,
    ) -> TenderMatch:
        semantic_fit = self._semantic_fit(candidate)
        country_fit, country_status = self._country_fit(
            profile,
            candidate,
        )
        value_fit, value_status = self._value_fit(
            profile,
            candidate,
        )
        (
            deadline_fit,
            deadline_status,
            days_to_deadline,
        ) = self._deadline_fit(
            profile,
            candidate,
            now=now,
        )

        weighted_signals: list[tuple[float, float]] = [
            (semantic_fit, 0.65),
            (deadline_fit, 0.10),
        ]
        if profile.target_countries:
            weighted_signals.append((country_fit, 0.15))
        if (
            profile.preferred_min_value is not None
            or profile.preferred_max_value is not None
        ):
            weighted_signals.append((value_fit, 0.10))

        weight_total = sum(
            weight for _, weight in weighted_signals
        )
        score = 100 * sum(
            signal * weight
            for signal, weight in weighted_signals
        ) / weight_total

        signals = MatchSignals(
            semantic_fit=round(semantic_fit, 4),
            country_fit=round(country_fit, 4),
            value_fit=round(value_fit, 4),
            deadline_fit=round(deadline_fit, 4),
            country_status=country_status,
            value_status=value_status,
            deadline_status=deadline_status,
            days_to_deadline=days_to_deadline,
        )
        why_matches, risks = self._explain(
            profile,
            candidate,
            signals,
        )

        return TenderMatch(
            publication_number=candidate.publication_number,
            publication_date=candidate.publication_date,
            title=candidate.title,
            buyer_name=candidate.buyer_name,
            buyer_country=candidate.buyer_country,
            procedure_type=candidate.procedure_type,
            estimated_value=candidate.estimated_value,
            estimated_value_currency=(
                candidate.estimated_value_currency
            ),
            earliest_deadline=candidate.earliest_deadline,
            source_html_url=candidate.source_html_url,
            match_score=round(score, 1),
            signals=signals,
            why_matches=why_matches,
            risks=risks,
            rrf_score=candidate.rrf_score,
            lexical_rank=candidate.lexical_rank,
            semantic_rank=candidate.semantic_rank,
            semantic_score=candidate.semantic_score,
        )

    @staticmethod
    def _semantic_fit(
        candidate: HybridSearchResult,
    ) -> float:
        if candidate.semantic_score is not None:
            return max(
                0.0,
                min(1.0, candidate.semantic_score),
            )

        ranks = [
            rank
            for rank in (
                candidate.semantic_rank,
                candidate.lexical_rank,
            )
            if rank is not None
        ]
        if not ranks:
            return 0.0

        best_rank = min(ranks)
        return 1.0 / (1.0 + 0.12 * (best_rank - 1))

    @staticmethod
    def _country_fit(
        profile: CompanyProfile,
        candidate: HybridSearchResult,
    ) -> tuple[float, str]:
        if not profile.target_countries:
            return 1.0, "not_configured"
        if candidate.buyer_country.upper() in profile.target_countries:
            return 1.0, "matched"
        return 0.0, "mismatched"

    @staticmethod
    def _value_fit(
        profile: CompanyProfile,
        candidate: HybridSearchResult,
    ) -> tuple[float, ValueStatus]:
        minimum = profile.preferred_min_value
        maximum = profile.preferred_max_value
        if minimum is None and maximum is None:
            return 1.0, "not_configured"

        value = candidate.estimated_value
        currency = candidate.estimated_value_currency
        if value is None or currency is None:
            return 0.5, "unknown"
        if currency.upper() != profile.preferred_value_currency:
            return 0.5, "currency_mismatch"
        if minimum is not None and value < minimum:
            return 0.25, "below_range"
        if maximum is not None and value > maximum:
            return 0.25, "above_range"
        return 1.0, "within_range"

    @staticmethod
    def _deadline_fit(
        profile: CompanyProfile,
        candidate: HybridSearchResult,
        *,
        now: datetime,
    ) -> tuple[float, DeadlineStatus, int | None]:
        deadline = candidate.earliest_deadline
        if deadline is None:
            return 0.5, "unknown", None
        if deadline.tzinfo is None or deadline.utcoffset() is None:
            deadline = deadline.replace(tzinfo=UTC)
        else:
            deadline = deadline.astimezone(UTC)

        seconds_remaining = (
            deadline - now
        ).total_seconds()
        days_remaining = int(seconds_remaining // 86400)
        if seconds_remaining <= 0:
            return 0.0, "closed", days_remaining

        minimum_days = profile.min_days_to_deadline
        if minimum_days == 0 or days_remaining >= minimum_days:
            return 1.0, "open", days_remaining

        fit = max(0.0, days_remaining / minimum_days)
        return fit, "soon", days_remaining

    @classmethod
    def _explain(
        cls,
        profile: CompanyProfile,
        candidate: HybridSearchResult,
        signals: MatchSignals,
    ) -> tuple[list[str], list[str]]:
        why_matches: list[str] = []
        risks: list[str] = []

        if signals.semantic_fit >= 0.70:
            why_matches.append(
                "Strong semantic fit with the company capabilities"
            )
        elif signals.semantic_fit >= 0.55:
            why_matches.append(
                "Moderate semantic fit with the company capabilities"
            )
        else:
            risks.append(
                "Capability match is weak and should be reviewed manually"
            )

        if signals.country_status == "matched":
            why_matches.append(
                f"Buyer country {candidate.buyer_country} is a target market"
            )
        elif signals.country_status == "mismatched":
            risks.append(
                f"Buyer country {candidate.buyer_country} is outside the target markets"
            )

        if signals.value_status == "within_range":
            why_matches.append(
                "Estimated contract value is within the preferred range"
            )
        elif signals.value_status == "below_range":
            risks.append(
                "Estimated contract value is below the preferred range"
            )
        elif signals.value_status == "above_range":
            risks.append(
                "Estimated contract value is above the preferred range"
            )
        elif signals.value_status == "unknown":
            risks.append(
                "Estimated contract value is unavailable"
            )
        elif signals.value_status == "currency_mismatch":
            risks.append(
                "Contract value uses a different currency from the profile"
            )

        if signals.deadline_status == "open":
            if signals.days_to_deadline is not None:
                why_matches.append(
                    f"Deadline leaves {signals.days_to_deadline} days to respond"
                )
        elif signals.deadline_status == "soon":
            risks.append(
                "Deadline is sooner than the preferred preparation window"
            )
        elif signals.deadline_status == "closed":
            risks.append("Tender deadline has passed")
        else:
            risks.append("Tender deadline is unavailable")

        return why_matches, risks


def format_contract_value(
    value: Decimal | None,
    currency: str | None,
) -> str | None:
    if value is None or currency is None:
        return None
    return f"{currency.upper()} {value:,.0f}"
