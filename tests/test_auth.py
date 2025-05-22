import pytest
from httpx import AsyncClient, ASGITransport
from api_service import ModelAPIService

api_service = ModelAPIService()
app = api_service.app

@pytest.mark.asyncio
async def test_register_and_login():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post("/register", json={"username": "testuser", "password": "test"})
        assert response.status_code == 200
