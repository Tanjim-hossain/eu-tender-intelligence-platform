import pytest

from tendergraph.search.pooling import (
    build_query_variants,
)


def test_build_query_variants() -> None:
    variants = build_query_variants(
        "cloud data platform"
    )

    assert (
        variants.strict
        == "cloud data platform"
    )

    assert (
        variants.broad
        == "cloud OR data OR platform"
    )

    assert (
        variants.phrase
        == '"cloud data platform"'
    )


def test_query_variants_normalize_whitespace() -> None:
    variants = build_query_variants(
        "  SAP   implementation  "
    )

    assert (
        variants.strict
        == "SAP implementation"
    )

    assert (
        variants.broad
        == "SAP OR implementation"
    )


def test_query_variants_reject_blank_query() -> None:
    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        build_query_variants("   ")
