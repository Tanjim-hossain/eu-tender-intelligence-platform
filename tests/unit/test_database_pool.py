import pytest

from tendergraph.database.pool import (
    validate_pool_config,
)


def test_pool_config_accepts_valid_sizes() -> None:
    validate_pool_config(
        min_size=1,
        max_size=5,
        timeout=10.0,
    )


def test_pool_config_rejects_negative_minimum() -> None:
    with pytest.raises(
        ValueError,
        match="minimum size",
    ):
        validate_pool_config(
            min_size=-1,
            max_size=5,
            timeout=10.0,
        )


def test_pool_config_rejects_zero_maximum() -> None:
    with pytest.raises(
        ValueError,
        match="maximum size",
    ):
        validate_pool_config(
            min_size=0,
            max_size=0,
            timeout=10.0,
        )


def test_pool_config_rejects_inverted_sizes() -> None:
    with pytest.raises(
        ValueError,
        match="must not exceed",
    ):
        validate_pool_config(
            min_size=6,
            max_size=5,
            timeout=10.0,
        )


def test_pool_config_rejects_invalid_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="timeout",
    ):
        validate_pool_config(
            min_size=1,
            max_size=5,
            timeout=0,
        )
