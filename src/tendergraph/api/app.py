from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import (
    FastAPI,
    HTTPException,
    Request,
)
from psycopg_pool import ConnectionPool
from sentence_transformers import (
    SentenceTransformer,
)

from tendergraph.api.models import (
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
    settings = DatabaseSettings()

    pool = create_connection_pool(
        settings,
        min_size=1,
        max_size=5,
    )

    pool.open(wait=True)

    try:
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

        yield

    finally:
        pool.close()


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

    return application


app = create_app()
