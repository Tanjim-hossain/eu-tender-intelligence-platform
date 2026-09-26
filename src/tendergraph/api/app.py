from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import ExitStack, asynccontextmanager
from typing import cast

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
)
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout
from sentence_transformers import (
    SentenceTransformer,
)

from tendergraph.api.models import (
    AnswerSource,
    AskRequest,
    AskResponse,
    HealthResponse,
    SearchRequest,
    SearchResponse,
    SearchResult,
)
from tendergraph.database.config import (
    DatabaseSettings,
)
from tendergraph.database.pool import (
    create_connection_pool,
)
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
        app.state.answer_service = build_answer_service(
            service, TenderEvidenceRepository(pool), rag_settings, resources
        )

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

        results = service.search(
            payload.query,
            limit=payload.limit,
            retrieval_depth=(
                payload.retrieval_depth
            ),
        )

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
