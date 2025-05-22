import pytest
from httpx import AsyncClient
from api_service import ModelAPIService

api_service = ModelAPIService()
app = api_service.app


@pytest.mark.asyncio
async def test_register_and_login():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Register a user
        response = await ac.post("/register", json={"username": "testuser", "password": "testpass"})
        assert response.status_code == 200 or response.status_code == 400  # Allow already exists

        # Login with correct credentials
        response = await ac.post("/login", json={"username": "testuser", "password": "testpass"})
        assert response.status_code == 200
        assert "access_token" in response.json()
