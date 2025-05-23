import pytest
from httpx import AsyncClient, ASGITransport
from api_service import ModelAPIService

api_service = ModelAPIService()
app = api_service.app

@pytest.mark.asyncio
async def test_register_and_login():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        reg_resp = await ac.post("/register", json={"username": "testuser", "password": "test"})
        print("Register status:", reg_resp.status_code, reg_resp.text)

        login_resp = await ac.post("/login", json={"username": "testuser", "password": "test"})
        print("Login status:", login_resp.status_code, login_resp.text)
        assert login_resp.status_code == 200
