from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout

from tendergraph.alerts.models import (
    AlertDigest,
    AlertPreferences,
    AlertPreferencesUpdate,
    AlertRefreshResult,
    AlertSeenResponse,
)
from tendergraph.alerts.repository import AlertRepository
from tendergraph.alerts.service import AlertService, MissingCompanyProfileError
from tendergraph.matching.service import CompanyMatchingService
from tendergraph.product.router import _authorize_account, _repository
from tendergraph.product.schema import ensure_product_schema

router = APIRouter(prefix="/alerts", tags=["alerts"])


def _alert_repository(request: Request) -> AlertRepository:
    existing = getattr(request.app.state, "alert_repository", None)
    if existing is not None:
        return cast(AlertRepository, existing)

    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Application not initialized")

    typed_pool = cast(ConnectionPool, pool)
    try:
        ensure_product_schema(typed_pool)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    repository = AlertRepository(typed_pool)
    request.app.state.alert_repository = repository
    return repository


def _matching_service(request: Request) -> CompanyMatchingService:
    service = getattr(request.app.state, "matching_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Application not initialized")
    return cast(CompanyMatchingService, service)


def _authorize(request: Request, account_id: UUID) -> None:
    repository = _repository(request)
    _authorize_account(
        request=request,
        repository=repository,
        account_id=account_id,
    )


def _service(request: Request) -> AlertService:
    return AlertService(
        product_repository=_repository(request),
        alert_repository=_alert_repository(request),
        matching_service=_matching_service(request),
    )


@router.get(
    "/accounts/{account_id}/preferences",
    response_model=AlertPreferences,
)
def get_preferences(account_id: UUID, request: Request) -> AlertPreferences:
    try:
        _authorize(request, account_id)
        return _alert_repository(request).get_preferences(account_id)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@router.put(
    "/accounts/{account_id}/preferences",
    response_model=AlertPreferences,
)
def put_preferences(
    account_id: UUID,
    payload: AlertPreferencesUpdate,
    request: Request,
) -> AlertPreferences:
    try:
        _authorize(request, account_id)
        return _alert_repository(request).upsert_preferences(account_id, payload)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@router.get(
    "/accounts/{account_id}/digest",
    response_model=AlertDigest,
)
def get_digest(account_id: UUID, request: Request) -> AlertDigest:
    try:
        _authorize(request, account_id)
        return _service(request).get_digest(account_id)
    except MissingCompanyProfileError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@router.post(
    "/accounts/{account_id}/refresh",
    response_model=AlertRefreshResult,
)
def refresh_alerts(account_id: UUID, request: Request) -> AlertRefreshResult:
    try:
        _authorize(request, account_id)
        return _service(request).refresh(account_id)
    except MissingCompanyProfileError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc


@router.post(
    "/accounts/{account_id}/items/{publication_number}/seen",
    response_model=AlertSeenResponse,
)
def mark_seen(
    account_id: UUID,
    publication_number: str,
    request: Request,
) -> AlertSeenResponse:
    cleaned = publication_number.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="publication_number must not be blank")
    try:
        _authorize(request, account_id)
        service = _service(request)
        service.mark_seen(account_id, cleaned)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return AlertSeenResponse()


@router.post(
    "/accounts/{account_id}/seen-all",
    response_model=AlertSeenResponse,
)
def mark_all_seen(account_id: UUID, request: Request) -> AlertSeenResponse:
    try:
        _authorize(request, account_id)
        _service(request).mark_all_seen(account_id)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return AlertSeenResponse()
