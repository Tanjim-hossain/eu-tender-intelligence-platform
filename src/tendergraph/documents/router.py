from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout

from tendergraph.documents.fetcher import DocumentFetchError, UnsafeDocumentUrlError
from tendergraph.documents.models import (
    DocumentIngestRequest,
    DocumentPackageIntelligence,
    TenderDocumentPackage,
)
from tendergraph.documents.repository import DocumentRepository
from tendergraph.documents.schema import ensure_documents_schema
from tendergraph.documents.service import (
    DocumentService,
    TenderDocumentSourceUnavailable,
    TenderNotFoundError,
)

router = APIRouter(prefix="/documents", tags=["documents"])


def _service(request: Request) -> DocumentService:
    existing = getattr(request.app.state, "document_service", None)
    if existing is not None:
        return cast(DocumentService, existing)

    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Application not initialized")

    typed_pool = cast(ConnectionPool, pool)
    try:
        ensure_documents_schema(typed_pool)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    service = DocumentService(DocumentRepository(typed_pool))
    request.app.state.document_service = service
    return service


def _clean_publication_number(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="publication_number must not be blank")
    return cleaned


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, TenderNotFoundError):
        return HTTPException(status_code=404, detail="Tender not found")
    if isinstance(exc, TenderDocumentSourceUnavailable):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, UnsafeDocumentUrlError):
        return HTTPException(status_code=422, detail="TED document URL failed network safety validation")
    if isinstance(exc, DocumentFetchError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, (OperationalError, PoolTimeout)):
        return HTTPException(status_code=503, detail="Database unavailable")
    return HTTPException(status_code=500, detail="Document processing failed")


@router.get("/{publication_number}", response_model=TenderDocumentPackage)
def get_document_package(publication_number: str, request: Request) -> TenderDocumentPackage:
    try:
        return _service(request).package(_clean_publication_number(publication_number))
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/{publication_number}/ingest", response_model=TenderDocumentPackage)
def ingest_document_package(
    publication_number: str,
    payload: DocumentIngestRequest,
    request: Request,
) -> TenderDocumentPackage:
    try:
        return _service(request).ingest(
            _clean_publication_number(publication_number),
            fetch_documents=payload.fetch_documents,
            force=payload.force,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get(
    "/{publication_number}/intelligence",
    response_model=DocumentPackageIntelligence,
)
def get_document_intelligence(
    publication_number: str,
    request: Request,
) -> DocumentPackageIntelligence:
    try:
        return _service(request).intelligence(
            _clean_publication_number(publication_number)
        )
    except Exception as exc:
        raise _translate_error(exc) from exc
