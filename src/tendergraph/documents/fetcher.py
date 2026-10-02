from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urljoin, urlsplit

import httpx

DEFAULT_MAX_BYTES = 20_000_000
MAX_REDIRECTS = 5


class UnsafeDocumentUrlError(ValueError):
    """Raised when a URL could reach a local/private network target."""


class DocumentFetchError(RuntimeError):
    """Raised when a remote procurement resource cannot be safely fetched."""


@dataclass(frozen=True, slots=True)
class RawFetch:
    source_url: str
    final_url: str
    content_type: str | None
    content: bytes
    sha256: str
    byte_count: int
    status_code: int


def _is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_public_http_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeDocumentUrlError("Only http/https document URLs are allowed")
    if not parsed.hostname:
        raise UnsafeDocumentUrlError("Document URL has no hostname")
    if parsed.username or parsed.password:
        raise UnsafeDocumentUrlError("Document URLs with embedded credentials are blocked")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeDocumentUrlError("Document URL contains an invalid port") from exc

    try:
        addresses = socket.getaddrinfo(parsed.hostname, port)
    except socket.gaierror as exc:
        raise DocumentFetchError("Document hostname could not be resolved") from exc

    if not addresses:
        raise DocumentFetchError("Document hostname resolved to no addresses")

    for address in addresses:
        ip_value = address[4][0]
        if not _is_public_ip(ip_value):
            raise UnsafeDocumentUrlError("Document URL resolves to a non-public address")


class SafeDocumentFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float = 20.0,
        user_agent: str = "TenderGraph/0.1 procurement-document-fetcher",
    ) -> None:
        self._timeout = timeout_seconds
        self._headers = {"User-Agent": user_agent}

    def fetch(
        self,
        url: str,
        *,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> RawFetch:
        current = url
        with httpx.Client(
            timeout=self._timeout,
            headers=self._headers,
            follow_redirects=False,
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                validate_public_http_url(current)
                try:
                    with client.stream("GET", current) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            location = response.headers.get("location")
                            if not location:
                                raise DocumentFetchError("Redirect response omitted Location")
                            current = urljoin(current, location)
                            continue
                        if response.status_code in {401, 403}:
                            raise DocumentFetchError(
                                f"Remote document access denied ({response.status_code})"
                            )
                        if response.status_code >= 400:
                            raise DocumentFetchError(
                                f"Remote document request failed ({response.status_code})"
                            )

                        declared = response.headers.get("content-length")
                        if declared is not None:
                            try:
                                if int(declared) > max_bytes:
                                    raise DocumentFetchError("Remote document exceeds size limit")
                            except ValueError:
                                pass

                        chunks: list[bytes] = []
                        total = 0
                        for chunk in response.iter_bytes():
                            total += len(chunk)
                            if total > max_bytes:
                                raise DocumentFetchError("Remote document exceeds size limit")
                            chunks.append(chunk)
                        content = b"".join(chunks)
                        return RawFetch(
                            source_url=url,
                            final_url=str(response.url),
                            content_type=response.headers.get("content-type"),
                            content=content,
                            sha256=sha256(content).hexdigest(),
                            byte_count=len(content),
                            status_code=response.status_code,
                        )
                except httpx.HTTPError as exc:
                    raise DocumentFetchError("Remote document request failed") from exc

        raise DocumentFetchError("Remote document exceeded redirect limit")
