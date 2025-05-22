import pytest
from httpx import AsyncClient
from api_service import ModelAPIService

api_service = ModelAPIService()
app = api_service.app


@pytest.mark.asyncio
async def test_list_models():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/models")
        assert response.status_code == 200
        assert "models" in response.json()
