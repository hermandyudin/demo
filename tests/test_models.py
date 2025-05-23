import pytest
from httpx import AsyncClient, ASGITransport
from api_service import ModelAPIService

api_service = ModelAPIService()
app = api_service.app


@pytest.mark.asyncio
async def test_list_models():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/models")  # Adjust to your actual route
        assert response.status_code == 200
