from fastapi.testclient import TestClient

from tendergraph.api.app import create_app
from tendergraph.api.public_guard import RequestBudget

ORIGIN = "https://tendergraph.example"


def test_public_guard_requires_origin_session_and_registered_workspace() -> None:
    client = TestClient(create_app(use_lifespan=False, public_origin=ORIGIN), base_url=ORIGIN)
    assert client.get("/").status_code == 200
    assert client.get("/", headers={"host": "evil.example"}).status_code == 400
    assert client.post("/search", json={"query": "data"}).status_code == 403
    assert client.post("/search", headers={"origin": ORIGIN}, json={"query": "data"}).status_code == 401
    assert client.post("/product/accounts", headers={"origin": ORIGIN}, content="").status_code == 403
    assert client.post("/documents/123-2026/ingest", headers={"origin": ORIGIN}, json={}).status_code == 403
    assert client.post("/search", headers={"origin": ORIGIN, "content-length": "2000000"}, content="").status_code == 413


def test_budget_is_bounded_and_recovers() -> None:
    now = [0.0]
    budget = RequestBudget(clock=lambda: now[0])
    assert all(budget.allow(True) for _ in range(20))
    assert not budget.allow(True)
    assert budget.allow(False)
    now[0] = 61.0
    assert budget.allow(True)
