"""Opt-in public ingress safeguards; local development remains unchanged."""
from __future__ import annotations

from collections import deque
from collections.abc import Awaitable, Callable
from time import monotonic
from urllib.parse import urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from psycopg import OperationalError
from psycopg_pool import PoolTimeout
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint

from tendergraph.auth.router import auth_repository
from tendergraph.auth.security import SESSION_COOKIE_NAME, session_token_hash

PUBLIC_PATHS = {"/", "/health", "/config", "/auth/me", "/auth/login",
                "/auth/register", "/auth/logout"}
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def validate_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https" or not parsed.hostname or parsed.username
        or parsed.password or parsed.path or parsed.query or parsed.fragment
        or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("TENDERGRAPH_PUBLIC_ORIGIN must be an HTTPS origin without a path")
    return value


class RequestBudget:
    """Bounded single-process request budget; deploy behind an ingress limiter too."""

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self.clock = clock
        self.general: deque[float] = deque()
        self.authentication: deque[float] = deque()

    def allow(self, authentication: bool) -> bool:
        now = self.clock()
        while self.general and self.general[0] <= now - 60:
            self.general.popleft()
        while self.authentication and self.authentication[0] <= now - 60:
            self.authentication.popleft()
        if len(self.general) >= 240 or (authentication and len(self.authentication) >= 20):
            return False
        self.general.append(now)
        if authentication:
            self.authentication.append(now)
        return True


def _signed_in(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return False
    session = auth_repository(request).get_session(session_token_hash(token))
    return session is not None and session.account.account_type == "registered"


def install_public_guard(origin: str) -> Callable[[Request, RequestResponseEndpoint], Awaitable[Response]]:
    expected_host = urlsplit(origin).netloc.lower()
    budget = RequestBudget()

    async def guard(request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        host = request.headers.get("host", "").lower()
        internal_health = path == "/health" and host in {"127.0.0.1:8000", "localhost:8000"}
        if host != expected_host and not internal_health:
            return JSONResponse({"detail": "Invalid host"}, status_code=400)
        if path.startswith("/assets/") or internal_health:
            return await call_next(request)
        if not budget.allow(path in {"/auth/login", "/auth/register"}):
            return JSONResponse({"detail": "Request limit reached"}, status_code=429,
                                headers={"Retry-After": "60"})
        if request.method in UNSAFE:
            if request.headers.get("origin") != origin:
                return JSONResponse({"detail": "Invalid request origin"}, status_code=403)
            length = request.headers.get("content-length")
            if request.headers.get("transfer-encoding"):
                return JSONResponse({"detail": "Chunked request bodies are not accepted"}, status_code=411)
            if request.method != "DELETE" and length is None:
                return JSONResponse({"detail": "Content-Length required"}, status_code=411)
            if length is not None:
                if not length.isascii() or not length.isdecimal() or len(length) > 10:
                    return JSONResponse({"detail": "Invalid Content-Length"}, status_code=400)
                if int(length) > 1_048_576:
                    return JSONResponse({"detail": "Request too large"}, status_code=413)
        if path == "/product/accounts" and request.method == "POST":
            return JSONResponse({"detail": "Register or sign in first"}, status_code=403)
        if path.startswith("/documents/") and path.endswith("/ingest"):
            return JSONResponse({"detail": "Public document fetching is disabled pending network isolation; use indexed evidence."}, status_code=403)
        if path not in PUBLIC_PATHS:
            try:
                if not await run_in_threadpool(_signed_in, request):
                    return JSONResponse({"detail": "Authentication required"}, status_code=401)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
            except (OperationalError, PoolTimeout):
                return JSONResponse({"detail": "Database unavailable"}, status_code=503)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    return guard
