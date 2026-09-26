from __future__ import annotations

from psycopg_pool import ConnectionPool

from tendergraph.database.config import (
    DatabaseSettings,
)

DEFAULT_POOL_MIN_SIZE = 1
DEFAULT_POOL_MAX_SIZE = 5
DEFAULT_POOL_TIMEOUT = 10.0


def validate_pool_config(
    *,
    min_size: int,
    max_size: int,
    timeout: float,
) -> None:
    if min_size < 0:
        raise ValueError(
            "Pool minimum size must not be negative"
        )

    if max_size <= 0:
        raise ValueError(
            "Pool maximum size must be positive"
        )

    if min_size > max_size:
        raise ValueError(
            "Pool minimum size must not exceed "
            "maximum size"
        )

    if timeout <= 0:
        raise ValueError(
            "Pool timeout must be positive"
        )


def create_connection_pool(
    settings: DatabaseSettings,
    *,
    min_size: int = DEFAULT_POOL_MIN_SIZE,
    max_size: int = DEFAULT_POOL_MAX_SIZE,
    timeout: float = DEFAULT_POOL_TIMEOUT,
) -> ConnectionPool:
    """Create a PostgreSQL pool without opening it."""

    validate_pool_config(
        min_size=min_size,
        max_size=max_size,
        timeout=timeout,
    )

    return ConnectionPool(
        conninfo=settings.connection_uri,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout,
        open=False,
        name="tendergraph-db",
    )
