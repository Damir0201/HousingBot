import httpx
import pytest

from app.main import create_app


@pytest.fixture
def app():
    return create_app()


async def test_health_endpoint(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_api_key_protection(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/properties")
    assert resp.status_code == 403
    assert resp.json()["i18n_key"] == "errors.permission_denied"


async def test_webhook_secret_protection(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/webhook/telegram", json={"update_id": 1})
    assert resp.status_code == 403
