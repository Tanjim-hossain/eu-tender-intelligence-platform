from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout

from tendergraph.auth.models import (
    AuthLoginRequest,
    AuthLogoutResponse,
    AuthRegisterRequest,
    AuthStatusResponse,
)
from tendergraph.auth.repository import (
    AuthRepository,
    EmailAlreadyRegisteredError,
    LocalAccountClaimError,
)
from tendergraph.auth.security import (
    SESSION_COOKIE_NAME,
    SESSION_TTL,
    create_session_token,
    hash_password,
    session_token_hash,
    verify_password,
)
from tendergraph.product.schema import ensure_product_schema

router = APIRouter(prefix="/auth", tags=["auth"])


def auth_repository(request: Request) -> AuthRepository:
    existing = getattr(request.app.state, "auth_repository", None)
    if existing is not None:
        return cast(AuthRepository, existing)

    pool = getattr(request.app.state, "db_pool", None)
    if pool is None:
        raise HTTPException(status_code=503, detail="Application not initialized")

    typed_pool = cast(ConnectionPool, pool)
    try:
        ensure_product_schema(typed_pool)
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    repository = AuthRepository(typed_pool)
    request.app.state.auth_repository = repository
    return repository


def _set_session_cookie(
    *,
    request: Request,
    response: Response,
    token: str,
    expires_at: datetime,
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=int(SESSION_TTL.total_seconds()),
        expires=expires_at,
        path="/",
        secure=request.url.scheme == "https",
        httponly=True,
        samesite="lax",
    )


def _create_session(
    *,
    repository: AuthRepository,
    account_id: UUID,
) -> tuple[str, datetime]:
    token = create_session_token()
    expires_at = datetime.now(UTC) + SESSION_TTL
    repository.create_session(
        account_id=account_id,
        token_hash=session_token_hash(token),
        expires_at=expires_at,
    )
    return token, expires_at


@router.post("/register", response_model=AuthStatusResponse, status_code=201)
def register(
    payload: AuthRegisterRequest,
    request: Request,
    response: Response,
) -> AuthStatusResponse:
    repository = auth_repository(request)
    try:
        account = repository.register_account(
            email=payload.email,
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
            local_account_id=payload.local_account_id,
        )
        token, expires_at = _create_session(
            repository=repository,
            account_id=account.id,
        )
    except EmailAlreadyRegisteredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LocalAccountClaimError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    _set_session_cookie(
        request=request,
        response=response,
        token=token,
        expires_at=expires_at,
    )
    return AuthStatusResponse(
        authenticated=True,
        account=account,
        expires_at=expires_at,
    )


@router.post("/login", response_model=AuthStatusResponse)
def login(
    payload: AuthLoginRequest,
    request: Request,
    response: Response,
) -> AuthStatusResponse:
    repository = auth_repository(request)
    try:
        record = repository.get_login_record(payload.email)
        if record is None or not verify_password(payload.password, record.password_hash):
            raise HTTPException(status_code=401, detail="Invalid email or password")
        token, expires_at = _create_session(
            repository=repository,
            account_id=record.account.id,
        )
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    _set_session_cookie(
        request=request,
        response=response,
        token=token,
        expires_at=expires_at,
    )
    return AuthStatusResponse(
        authenticated=True,
        account=record.account,
        expires_at=expires_at,
    )


@router.get("/me", response_model=AuthStatusResponse)
def me(request: Request) -> AuthStatusResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return AuthStatusResponse(authenticated=False)

    repository = auth_repository(request)
    try:
        session = repository.get_session(session_token_hash(token))
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    if session is None:
        return AuthStatusResponse(authenticated=False)
    return AuthStatusResponse(
        authenticated=True,
        account=session.account,
        expires_at=session.expires_at,
    )


@router.post("/logout", response_model=AuthLogoutResponse)
def logout(request: Request, response: Response) -> AuthLogoutResponse:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        try:
            auth_repository(request).revoke_session(session_token_hash(token))
        except (OperationalError, PoolTimeout) as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc

    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return AuthLogoutResponse()
