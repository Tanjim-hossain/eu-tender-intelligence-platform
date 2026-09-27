from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from tendergraph.ingestion.models import (
    TedSearchRequest,
    TedSearchResponse,
)

TED_SEARCH_URL = (
    "https://api.ted.europa.eu/v3/notices/search"
)

RETRYABLE_STATUS_CODES = {
    429,
    500,
    502,
    503,
    504,
}


class TedApiError(RuntimeError):
    """Raised when communication with TED fails."""


class TedResponseValidationError(TedApiError):
    """Raised when TED violates our source contract."""


@dataclass(frozen=True, slots=True)
class TedSearchResult:
    """Raw and validated forms of one TED response."""

    raw: dict[str, Any]
    parsed: TedSearchResponse


@dataclass(frozen=True, slots=True)
class TedIterationPage:
    """One page returned during TED iteration."""

    page_number: int
    request: TedSearchRequest
    result: TedSearchResult


class TedClient:
    """HTTP client for the TED Search API."""

    def __init__(
        self,
        *,
        base_url: str = TED_SEARCH_URL,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.transport = transport

    def search(
        self,
        request: TedSearchRequest,
    ) -> TedSearchResult:
        """Execute and validate one TED request."""

        with httpx.Client(
            timeout=self.timeout_seconds,
            transport=self.transport,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        ) as client:
            for attempt in range(
                self.max_retries + 1
            ):
                try:
                    response = client.post(
                        self.base_url,
                        json=request.to_api_payload(),
                    )
                except httpx.RequestError as exc:
                    if attempt >= self.max_retries:
                        raise TedApiError(
                            "TED request failed after "
                            f"{attempt + 1} attempts"
                        ) from exc

                    self._backoff(attempt)
                    continue

                if (
                    response.status_code
                    in RETRYABLE_STATUS_CODES
                    and attempt < self.max_retries
                ):
                    self._backoff(attempt)
                    continue

                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise TedApiError(
                        "TED returned HTTP "
                        f"{response.status_code}: "
                        f"{response.text[:500]}"
                    ) from exc

                try:
                    payload = response.json()
                except ValueError as exc:
                    raise TedApiError(
                        "TED returned invalid JSON"
                    ) from exc

                if not isinstance(payload, dict):
                    raise TedApiError(
                        "TED response must be "
                        "a JSON object"
                    )

                try:
                    parsed = (
                        TedSearchResponse.model_validate(
                            payload
                        )
                    )
                except ValidationError as exc:
                    raise TedResponseValidationError(
                        "TED response violated the "
                        "expected source contract"
                    ) from exc

                return TedSearchResult(
                    raw=payload,
                    parsed=parsed,
                )

        raise RuntimeError(
            "Unreachable TED client state"
        )

    def iterate(
        self,
        request: TedSearchRequest,
        *,
        max_pages: int | None = None,
    ) -> Iterator[TedIterationPage]:
        """Iterate safely through TED results using scroll tokens."""

        if max_pages is not None and max_pages < 1:
            raise ValueError(
                "max_pages must be >= 1"
            )

        token = request.iteration_next_token

        seen_tokens: set[str] = (
            {token} if token else set()
        )

        page_number = 0
        retrieved_count = 0
        expected_total: int | None = None

        while True:
            page_number += 1

            page_request = request.model_copy(
                update={
                    "pagination_mode": "ITERATION",
                    "iteration_next_token": token,
                }
            )

            result = self.search(page_request)

            page_total = (
                result.parsed.total_notice_count
            )

            if expected_total is None:
                expected_total = page_total
            elif page_total != expected_total:
                raise TedApiError(
                    "TED totalNoticeCount changed "
                    "during iteration: "
                    f"{expected_total} -> {page_total}"
                )

            page_record_count = len(
                result.parsed.notices
            )

            if page_record_count == 0:
                if retrieved_count < expected_total:
                    raise TedApiError(
                        "TED returned an empty page "
                        "before all expected records "
                        "were retrieved: "
                        f"{retrieved_count}/"
                        f"{expected_total}"
                    )

                if (
                    expected_total == 0
                    and page_number == 1
                ):
                    yield TedIterationPage(
                        page_number=page_number,
                        request=page_request,
                        result=result,
                    )

                return

            retrieved_count += page_record_count

            if retrieved_count > expected_total:
                raise TedApiError(
                    "TED returned more records than "
                    "totalNoticeCount: "
                    f"{retrieved_count}/"
                    f"{expected_total}"
                )

            yield TedIterationPage(
                page_number=page_number,
                request=page_request,
                result=result,
            )

            # Critical termination condition.
            # Do not rely only on the scroll token.
            if retrieved_count >= expected_total:
                return

            if (
                max_pages is not None
                and page_number >= max_pages
            ):
                return

            next_token = (
                result.parsed.iteration_next_token
            )

            if not next_token:
                raise TedApiError(
                    "TED iteration token ended "
                    "before all expected records "
                    "were retrieved: "
                    f"{retrieved_count}/"
                    f"{expected_total}"
                )

            if next_token in seen_tokens:
                raise TedApiError(
                    "TED returned a repeated "
                    "iteration token"
                )

            seen_tokens.add(next_token)
            token = next_token

    def _backoff(self, attempt: int) -> None:
        delay = (
            self.backoff_seconds
            * (2**attempt)
        )

        if delay > 0:
            time.sleep(delay)
