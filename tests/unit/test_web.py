from unittest.mock import Mock

from fastapi.testclient import TestClient
from psycopg import OperationalError

from tendergraph.api.app import create_app
from tendergraph.rag.settings import RAGSettings


def test_ui_assets_and_security_headers():
    with TestClient(create_app(use_lifespan=False)) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert "TenderGraph" in response.text
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/assets/style.css").status_code == 200


def test_public_config_never_exposes_credentials_or_origin():
    app = create_app(use_lifespan=False)
    app.state.rag_settings = RAGSettings(
        _env_file=None, provider="ollama", model="fixture-local",
        OPENAI_API_KEY="private-test-key",
    )
    with TestClient(app) as client:
        response = client.get("/config")
    assert response.json() == {
        "answer_mode": "ollama", "generation_model": "fixture-local", "reranking": False,
    }
    assert "private-test-key" not in response.text
    assert "11434" not in response.text


def test_search_database_failure_is_sanitized():
    app = create_app(use_lifespan=False)
    app.state.search_service = Mock()
    app.state.search_service.search.side_effect = OperationalError("private connection string")
    with TestClient(app) as client:
        response = client.post("/search", json={"query": "cloud"})
    assert response.status_code == 503
    assert response.json()["detail"] == "Database unavailable"
