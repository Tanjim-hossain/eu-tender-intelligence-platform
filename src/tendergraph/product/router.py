from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout

from tendergraph.auth.router import auth_repository
from tendergraph.auth.security import SESSION_COOKIE_NAME, session_token_hash
from tendergraph.matching.models import CompanyProfile
from tendergraph.product.models import (
    OpportunityStateUpdate,
    ProductAccount,
    ProductState,
    StoredOpportunityState,
)
from tendergraph.product.repository import ProductRepository
from tendergraph.product.schema import ensure_product_schema

router = APIRouter(prefix="/product", tags=["product"])


def _repository(request: Request) -> ProductRepository:
    existing = getattr(
        request.app.state,
        "product_repository",
        None,
    )
    if existing is not None:
        return cast(ProductRepository, existing)

    pool = getattr(
        request.app.state,
        "db_pool",
        None,
    )
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

    repository = ProductRepository(typed_pool)
    request.app.state.product_repository = repository
    return repository


def _authorize_account(
    *,
    request: Request,
    repository: ProductRepository,
    account_id: UUID,
) -> ProductAccount:
    account = repository.get_account(account_id)
    if account is None:
        raise HTTPException(
            status_code=404,
            detail="Product account not found",
        )
    if account.account_type == "local":
        return account

    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )
    session = auth_repository(request).get_session(session_token_hash(token))
    if session is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )
    if session.account.id != account_id:
        raise HTTPException(
            status_code=403,
            detail="Account access denied",
        )
    return account


@router.post(
    "/accounts",
    response_model=ProductAccount,
    status_code=201,
)
def create_account(
    request: Request,
) -> ProductAccount:
    try:
        return _repository(
            request
        ).create_local_account()
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc


@router.get(
    "/accounts/{account_id}/state",
    response_model=ProductState,
)
def get_state(
    account_id: UUID,
    request: Request,
) -> ProductState:
    repository = _repository(request)
    try:
        _authorize_account(
            request=request,
            repository=repository,
            account_id=account_id,
        )
        state = repository.get_state(
            account_id
        )
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    if state is None:
        raise HTTPException(
            status_code=404,
            detail="Product account not found",
        )

    return state


@router.put(
    "/accounts/{account_id}/profile",
    response_model=CompanyProfile,
)
def put_profile(
    account_id: UUID,
    profile: CompanyProfile,
    request: Request,
) -> CompanyProfile:
    repository = _repository(request)
    try:
        _authorize_account(
            request=request,
            repository=repository,
            account_id=account_id,
        )
        return repository.upsert_profile(
            account_id,
            profile,
        )
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc


@router.delete(
    "/accounts/{account_id}/profile",
)
def delete_profile(
    account_id: UUID,
    request: Request,
) -> dict[str, str]:
    repository = _repository(request)
    try:
        _authorize_account(
            request=request,
            repository=repository,
            account_id=account_id,
        )
        repository.delete_profile(account_id)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    return {"status": "deleted"}


@router.put(
    (
        "/accounts/{account_id}/opportunities/"
        "{publication_number}"
    ),
    response_model=StoredOpportunityState,
)
def put_opportunity(
    account_id: UUID,
    publication_number: str,
    update: OpportunityStateUpdate,
    request: Request,
) -> StoredOpportunityState:
    cleaned_number = publication_number.strip()
    if not cleaned_number:
        raise HTTPException(
            status_code=422,
            detail="publication_number must not be blank",
        )

    repository = _repository(request)
    try:
        _authorize_account(
            request=request,
            repository=repository,
            account_id=account_id,
        )
        return repository.upsert_opportunity(
            account_id,
            cleaned_number,
            update,
        )
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc


@router.delete(
    (
        "/accounts/{account_id}/opportunities/"
        "{publication_number}"
    ),
)
def delete_opportunity(
    account_id: UUID,
    publication_number: str,
    request: Request,
) -> dict[str, str]:
    cleaned_number = publication_number.strip()
    if not cleaned_number:
        raise HTTPException(
            status_code=422,
            detail="publication_number must not be blank",
        )

    repository = _repository(request)
    try:
        _authorize_account(
            request=request,
            repository=repository,
            account_id=account_id,
        )
        repository.delete_opportunity(
            account_id,
            cleaned_number,
        )
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    return {"status": "deleted"}
