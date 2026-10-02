from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from tendergraph.alerts.models import (
    AlertDigest,
    AlertRefreshResult,
)
from tendergraph.alerts.repository import AlertRepository
from tendergraph.matching.service import CompanyMatchingService
from tendergraph.product.models import ProductState
from tendergraph.product.repository import ProductRepository


class MissingCompanyProfileError(RuntimeError):
    pass


class AlertService:
    def __init__(
        self,
        *,
        product_repository: ProductRepository,
        alert_repository: AlertRepository,
        matching_service: CompanyMatchingService,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._product_repository = product_repository
        self._alert_repository = alert_repository
        self._matching_service = matching_service
        self._now_provider = now_provider or (lambda: datetime.now(UTC))

    @staticmethod
    def _normalize_now(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _state_with_profile(self, account_id: UUID) -> ProductState:
        state = self._product_repository.get_state(account_id)
        if state is None or state.profile is None:
            raise MissingCompanyProfileError(
                "A company profile is required before personalized alerts can run"
            )
        return state

    def get_digest(self, account_id: UUID) -> AlertDigest:
        now = self._normalize_now(self._now_provider())
        state = self._state_with_profile(account_id)
        preferences = self._alert_repository.get_preferences(account_id)
        items = self._alert_repository.list_events(
            account_id,
            min_match_score=preferences.min_match_score,
            limit=preferences.max_items,
        )
        unread_count, total_count = self._alert_repository.event_counts(
            account_id,
            min_match_score=preferences.min_match_score,
        )
        return AlertDigest(
            account_id=account_id,
            profile_name=state.profile.company_name,
            generated_at=now,
            last_refreshed_at=preferences.last_refreshed_at,
            unread_count=unread_count,
            total_count=total_count,
            items=items,
        )

    def refresh(self, account_id: UUID) -> AlertRefreshResult:
        now = self._normalize_now(self._now_provider())
        state = self._state_with_profile(account_id)
        preferences = self._alert_repository.get_preferences(account_id)

        if not preferences.enabled:
            return AlertRefreshResult(
                checked_at=now,
                eligible_count=0,
                new_count=0,
                digest=self.get_digest(account_id),
            )

        result = self._matching_service.match(
            state.profile,
            limit=50,
            retrieval_depth=100,
        )
        cutoff = now.date() - timedelta(days=preferences.lookback_days - 1)
        known_opportunities = {
            item.publication_number for item in state.opportunities
        }
        eligible = [
            match
            for match in result.matches
            if match.publication_date >= cutoff
            and match.match_score >= preferences.min_match_score
            and match.signals.deadline_status != "closed"
            and match.publication_number not in known_opportunities
        ]

        new_count = self._alert_repository.insert_new_events(
            account_id,
            eligible,
            now,
        )
        self._alert_repository.touch_refresh(account_id, now)

        return AlertRefreshResult(
            checked_at=now,
            eligible_count=len(eligible),
            new_count=new_count,
            digest=self.get_digest(account_id),
        )

    def mark_seen(self, account_id: UUID, publication_number: str) -> None:
        now = self._normalize_now(self._now_provider())
        self._alert_repository.mark_seen(account_id, publication_number, now)

    def mark_all_seen(self, account_id: UUID) -> None:
        now = self._normalize_now(self._now_provider())
        self._alert_repository.mark_all_seen(account_id, now)
