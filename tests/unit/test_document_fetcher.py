import pytest

from tendergraph.documents.fetcher import (
    UnsafeDocumentUrlError,
    validate_public_http_url,
)


def test_document_fetcher_blocks_loopback() -> None:
    with pytest.raises(UnsafeDocumentUrlError):
        validate_public_http_url("http://127.0.0.1/internal")


def test_document_fetcher_blocks_non_http_scheme() -> None:
    with pytest.raises(UnsafeDocumentUrlError):
        validate_public_http_url("file:///etc/passwd")


def test_document_fetcher_blocks_embedded_credentials() -> None:
    with pytest.raises(UnsafeDocumentUrlError):
        validate_public_http_url("https://user:secret@example.com/spec.pdf")
