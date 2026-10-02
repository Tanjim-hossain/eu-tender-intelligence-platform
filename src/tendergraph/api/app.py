from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout
from sentence_transformers import (
    SentenceTransformer,
)

from tendergraph.api.models import (
    AnswerSource,
    AskRequest,
    AskResponse,
    CompanyMatchRequest,
    HealthResponse,
    OperationsStatusResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from tendergraph.auth.router import router as auth_router
from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.database.pool import (
    create_connection_pool,
)
from tendergraph.documents.router import router as documents_router
from tendergraph.matching.models import CompanyMatchResult
from tendergraph.matching.service import CompanyMatchingService
from tendergraph.pipeline.status import (
    read_operational_status,
)
from tendergraph.product.router import router as product_router
from tendergraph.qualification.router import router as qualification_router
from tendergraph.rag.errors import GenerationUnavailable, InvalidGeneratedAnswer
from tendergraph.rag.evidence import TenderEvidenceRepository
from tendergraph.rag.factory import build_answer_service
from tendergraph.rag.pipeline import TenderAnswerService
from tendergraph.rag.settings import RAGSettings
from tendergraph.search.semantic import (
    MODEL_NAME,
)
from tendergraph.search.service import (
    HybridSearchService,
)


@asynccontextmanager
async def lifespan(
    app: FastAPI,
) -> AsyncIterator[None]:
    rag_settings = RAGSettings()
    settings = DatabaseSettings()

    pool = create_connection_pool(
        settings,
        min_size=1,
        max_size=5,
    )

    with ExitStack() as resources:
        resources.callback(pool.close)
        pool.open(wait=True)
        model = SentenceTransformer(
            MODEL_NAME
        )

        service = HybridSearchService(
            settings,
            pool=pool,
            model=model,
        )

        app.state.db_pool = pool
        app.state.search_service = service
        app.state.matching_service = CompanyMatchingService(
            service
        )
        app.state.answer_service = build_answer_service(
            service, TenderEvidenceRepository(pool), rag_settings, resources
        )
        app.state.rag_settings = rag_settings

        yield


def create_app(
    *,
    use_lifespan: bool = True,
) -> FastAPI:
    application = FastAPI(
        title="EU TenderGraph API",
        description=(
            "Hybrid lexical and semantic "
            "retrieval over European public "
            "procurement notices."
        ),
        version="0.1.0",
        lifespan=(
            lifespan
            if use_lifespan
            else None
        ),
    )

    application.include_router(auth_router)
    application.include_router(product_router)
    application.include_router(qualification_router)
    application.include_router(documents_router)

    web_dir = Path(__file__).parent / "web"
    application.mount("/assets", StaticFiles(directory=web_dir), name="assets")

    @application.get("/", include_in_schema=False)
    def home() -> FileResponse:
        return FileResponse(web_dir / "index.html", headers={
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'"
            ),
            "X-Content-Type-Options": "nosniff",
        })

    @application.get("/config")
    def public_config(request: Request) -> dict[str, object]:
        config = getattr(request.app.state, "rag_settings", None)
        if config is None:
            raise HTTPException(status_code=503, detail="Application not initialized")
        return {
            "answer_mode": config.provider,
            "generation_model": config.model if config.provider != "evidence" else None,
            "reranking": config.rerank,
        }

    @application.get(
        "/health",
        response_model=HealthResponse,
    )
    def health(
        request: Request,
    ) -> HealthResponse:
        pool = cast(
            ConnectionPool,
            request.app.state.db_pool,
        )

        try:
            with (
                pool.connection() as connection,
                connection.cursor() as cursor,
            ):
                cursor.execute(
                    "SELECT 1;"
                )

                row = cursor.fetchone()

            if row is None or row[0] != 1:
                raise RuntimeError(
                    "Unexpected database "
                    "health response"
                )

        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Database unavailable",
            ) from exc

        return HealthResponse(
            status="ok",
            database="ok",
            model=MODEL_NAME,
        )

    @application.get(
        "/operations/status",
        response_model=OperationsStatusResponse,
    )
    def operations_status() -> OperationsStatusResponse:
        try:
            status = read_operational_status()
        except (
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Operational status unavailable"
                ),
            ) from exc

        return OperationsStatusResponse.model_validate(
            status
        )

    @application.post(
        "/search",
        response_model=SearchResponse,
    )
    def search(
        payload: SearchRequest,
        request: Request,
    ) -> SearchResponse:
        service = cast(
            HybridSearchService,
            request.app.state.search_service,
        )

        try:
            results = service.search(
                payload.query, limit=payload.limit,
                retrieval_depth=payload.retrieval_depth,
            )
        except (OperationalError, PoolTimeout) as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc

        return SearchResponse(
            query=payload.query,
            count=len(results),
            results=[
                SearchResult.model_validate(
                    result
                )
                for result in results
            ],
        )

    @application.post(
        "/matches",
        response_model=CompanyMatchResult,
    )
    def matches(
        payload: CompanyMatchRequest,
        request: Request,
    ) -> CompanyMatchResult:
        service = cast(
            CompanyMatchingService,
            request.app.state.matching_service,
        )
        try:
            return service.match(
                payload.profile,
                limit=payload.limit,
                retrieval_depth=payload.retrieval_depth,
            )
        except (OperationalError, PoolTimeout) as exc:
            raise HTTPException(
                status_code=503,
                detail="Database unavailable",
            ) from exc

    @application.post("/ask", response_model=AskResponse)
    def ask(payload: AskRequest, request: Request) -> AskResponse:
        service = cast(TenderAnswerService, request.app.state.answer_service)
        try:
            result = service.answer(
                question=payload.question,
                query=payload.query,
                evidence_limit=payload.evidence_limit,
                retrieval_depth=payload.retrieval_depth,
            )
        except GenerationUnavailable as exc:
            raise HTTPException(
                status_code=503, detail="Answer provider unavailable; check server configuration"
            ) from exc
        except InvalidGeneratedAnswer as exc:
            raise HTTPException(
                status_code=502, detail="Answer failed validation; inspect sources using /search"
            ) from exc
        except (OperationalError, PoolTimeout) as exc:
            raise HTTPException(status_code=503, detail="Database unavailable") from exc
        return AskResponse(
            question=result.question, mode=result.mode, status=result.status,
            answer=result.text, citations=list(result.citations),
            sources=[AnswerSource.model_validate(item) for item in result.evidence],
            context_truncated=result.context_truncated,
        )

    return application


app = create_app()
