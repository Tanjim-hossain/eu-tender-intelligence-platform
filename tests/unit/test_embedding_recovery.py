from unittest.mock import MagicMock, Mock, patch

import pytest
from psycopg.conninfo import conninfo_to_dict

from tendergraph.database.config import DatabaseSettings
from tendergraph.search.embedding_refresh import (
    EmbeddingRefreshSummary,
    pending_embedding_groups,
    reconcile_tender_embeddings,
)

MODULE = "tendergraph.search.embedding_refresh"


def test_database_uri_round_trips_reserved_characters() -> None:
    settings = DatabaseSettings(
        postgres_user="team@local", postgres_password="a@b:/?%# word",
        postgres_db="tender/graph", _env_file=None,
    )
    parsed = conninfo_to_dict(settings.connection_uri)
    assert parsed["user"] == settings.postgres_user
    assert parsed["password"] == settings.postgres_password
    assert parsed["dbname"] == settings.postgres_db
    assert settings.postgres_password not in repr(settings)


def test_pending_groups_are_bound_to_current_model() -> None:
    connection = MagicMock()
    cursor = connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [("run-1", "A"), ("run-2", "B"), ("run-2", "C")]
    cursor.fetchone.return_value = (5817,)
    with patch(f"{MODULE}.ensure_vector_schema"), patch(
        f"{MODULE}.psycopg.connect", return_value=connection,
    ):
        groups, count = pending_embedding_groups(Mock(), model_name="local-model")
    assert groups == {"run-1": ["A"], "run-2": ["B", "C"]}
    assert count == 5817
    sql, params = cursor.execute.call_args_list[0].args
    assert params == {"model_name": "local-model"}
    assert "e.publication_number IS NULL" in sql
    assert "e.ingestion_run_id IS DISTINCT FROM s.ingestion_run_id" in sql


def test_current_embeddings_do_not_load_model() -> None:
    with patch(f"{MODULE}.pending_embedding_groups", return_value=({}, 5819)), patch(
        f"{MODULE}.SentenceTransformer",
    ) as model, patch(f"{MODULE}.refresh_tender_embeddings") as refresh:
        result = reconcile_tender_embeddings(Mock())
    assert result.embedded_rows == 0
    assert result.database_rows == 5819
    model.assert_not_called()
    refresh.assert_not_called()


def test_failed_embedding_stage_can_retry_unchanged_silver_rows() -> None:
    # Silver has already committed both groups. Only successful vector writes
    # remove entries from this durable-work simulation; Silver is never reloaded.
    pending = {"old-run": ["A"], "new-run": ["B"]}
    encoded = []
    fail_b = True

    def refresh(settings, ids, **kwargs):
        nonlocal fail_b
        encoded.append(tuple(ids))
        if ids == ["B"] and fail_b:
            fail_b = False
            raise RuntimeError("encoder unavailable")
        run = next(key for key, value in pending.items() if value == ids)
        del pending[run]
        return EmbeddingRefreshSummary(1, 1, 1, 0, 5819 - len(pending), run)

    with patch(f"{MODULE}.pending_embedding_groups", side_effect=lambda _: (dict(pending), 5817)), patch(
        f"{MODULE}.refresh_tender_embeddings", side_effect=refresh,
    ), patch(f"{MODULE}.SentenceTransformer") as model:
        with pytest.raises(RuntimeError, match="encoder unavailable"):
            reconcile_tender_embeddings(Mock())
        assert pending == {"new-run": ["B"]}
        result = reconcile_tender_embeddings(Mock())
        assert result.embedded_rows == 1
        assert pending == {}
        reconcile_tender_embeddings(Mock())
    assert encoded == [("A",), ("B",), ("B",)]
    assert model.call_count == 2  # once per attempt, never on the final no-op


def test_reconciliation_rejects_invalid_batch_before_connecting() -> None:
    with (
        patch(f"{MODULE}.pending_embedding_groups") as pending,
        pytest.raises(ValueError, match="positive"),
    ):
        reconcile_tender_embeddings(Mock(), batch_size=0)
    pending.assert_not_called()
