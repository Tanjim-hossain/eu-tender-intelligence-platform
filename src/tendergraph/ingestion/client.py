from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx
from pydantic import ValidationError

from tendergraph.ingestion.models import (
    TedSearchRequest,
    TedSearchResponse,
)

TED_SEARCH_URL = "https://api.ted.europa.eu/v3/notices/search"

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
    """Raised when TED returns a response that violates our contract."""


@dataclass(frozen=True, slots=True)
class TedSearchResult:
    """Raw and validated representations of one TED response."""

    raw: dict[str, Any]
    parsed: TedSearchResponse


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
        """Execute and validate one TED search request."""

        with httpx.Client(
            timeout=self.timeout_seconds,
            transport=self.transport,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        ) as client:
            for attempt in range(self.max_retries + 1):
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
                        "TED response must be a JSON object"
                    )

                try:
                    parsed = TedSearchResponse.model_validate(
                        payload
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

        raise RuntimeError("Unreachable TED client state")

    def _backoff(self, attempt: int) -> None:
        delay = self.backoff_seconds * (2**attempt)

        if delay > 0:
            time.sleep(delay)
