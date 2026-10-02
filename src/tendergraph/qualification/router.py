from __future__ import annotations

from typing import cast

from fastapi import APIRouter, HTTPException, Request
from psycopg import OperationalError
from psycopg_pool import ConnectionPool, PoolTimeout

from tendergraph.qualification.models import (
    TenderQualification,
)
from tendergraph.qualification.service import (
    QualificationService,
    TenderNotFoundError,
)
from tendergraph.rag.evidence import (
    TenderEvidenceRepository,
)

router = APIRouter(
    prefix="/qualification",
    tags=["qualification"],
)


def _service(
    request: Request,
) -> QualificationService:
    existing = getattr(
        request.app.state,
        "qualification_service",
        None,
    )
    if existing is not None:
        return cast(
            QualificationService,
            existing,
        )

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

    service = QualificationService(
        TenderEvidenceRepository(
            cast(ConnectionPool, pool)
        )
    )
    request.app.state.qualification_service = (
        service
    )
    return service


@router.get(
    "/{publication_number}",
    response_model=TenderQualification,
)
def get_qualification(
    publication_number: str,
    request: Request,
) -> TenderQualification:
    cleaned = publication_number.strip()
    if not cleaned:
        raise HTTPException(
            status_code=422,
            detail=(
                "publication_number must not be blank"
            ),
        )

    try:
        return _service(request).qualify(
            cleaned
        )
    except TenderNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Tender not found",
        ) from exc
    except (OperationalError, PoolTimeout) as exc:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc
