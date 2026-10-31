from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout

from tendergraph.decision.models import BidNoBidDossier, DecisionReviewUpdate
from tendergraph.decision.repository import DecisionReviewRepository
from tendergraph.decision.service import (
    DecisionDossierService,
    SavedOpportunityNotFoundError,
)
from tendergraph.documents.router import _service as document_service
from tendergraph.documents.service import TenderNotFoundError as DocumentTenderNotFoundError
from tendergraph.product.router import _authorize_account, _repository
from tendergraph.product.schema import ensure_product_schema
from tendergraph.qualification.router import _service as qualification_service
from tendergraph.qualification.service import TenderNotFoundError as QualificationTenderNotFoundError

router = APIRouter(prefix="/decisions", tags=["decisions"])


def _clean_publication_number(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail="publication_number must not be blank",
        )
    return cleaned


def _review_repository(request: Request) -> DecisionReviewRepository:
    existing = getattr(request.app.state, "decision_review_repository", None)
    if existing is not None:
        return cast(DecisionReviewRepository, existing)

    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(
            status_code=503,
            detail="Application not initialized",
        )

    typed_pool = cast(ConnectionPool, pool)
    try:
        ensure_product_schema(typed_pool)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    repository = DecisionReviewRepository(typed_pool)
    request.app.state.decision_review_repository = repository
    return repository


def _service(request: Request) -> DecisionDossierService:
    existing = getattr(request.app.state, "decision_dossier_service", None)
    if existing is not None:
        return cast(DecisionDossierService, existing)

    service = DecisionDossierService(
        product_repository=_repository(request),
        review_repository=_review_repository(request),
        qualification_service=qualification_service(request),
        document_service=document_service(request),
    )
    request.app.state.decision_dossier_service = service
    return service


def _authorize(request: Request, account_id: UUID) -> None:
    repository = _repository(request)
    _authorize_account(
        request=request,
        repository=repository,
        account_id=account_id,
    )


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, SavedOpportunityNotFoundError):
        return HTTPException(
            status_code=404,
            detail="Saved opportunity not found",
        )
    if isinstance(
        exc,
        (QualificationTenderNotFoundError, DocumentTenderNotFoundError),
    ):
        return HTTPException(
            status_code=404,
            detail="Tender evidence not found",
        )
    if isinstance(exc, ValueError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, (OperationalError, PoolTimeout)):
        return HTTPException(
            status_code=503,
            detail="Database unavailable",
        )
    return HTTPException(
        status_code=500,
        detail="Decision dossier unavailable",
    )


@router.get(
    "/accounts/{account_id}/opportunities/{publication_number}",
    response_model=BidNoBidDossier,
)
def get_dossier(
    account_id: UUID,
    publication_number: str,
    request: Request,
) -> BidNoBidDossier:
    try:
        _authorize(request, account_id)
        return _service(request).dossier(
            account_id,
            _clean_publication_number(publication_number),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.put(
    "/accounts/{account_id}/opportunities/{publication_number}/review",
    response_model=BidNoBidDossier,
)
def put_dossier_review(
    account_id: UUID,
    publication_number: str,
    payload: DecisionReviewUpdate,
    request: Request,
) -> BidNoBidDossier:
    try:
        _authorize(request, account_id)
        return _service(request).update_review(
            account_id,
            _clean_publication_number(publication_number),
            payload,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate_error(exc) from exc
