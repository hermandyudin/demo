import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from httpx._transports.asgi import ASGITransport
from api_service import ModelAPIService, get_current_user
from example_pb2 import Fake

api_service = ModelAPIService()
app = api_service.app


@pytest.mark.asyncio
@patch.object(api_service, "redis", new_callable=AsyncMock)
@patch.object(api_service, "rabbitmq_channel", new_callable=AsyncMock)
async def test_submit_task(mock_channel, mock_redis):
    # Register model
    api_service.models = {"test_model": {"host": "localhost", "port": 9000}}

    # Override auth
    app.dependency_overrides[get_current_user] = lambda: "testuser"

    # Patch descriptor logic to use real Protobuf descriptor
    api_service.get_descriptor = lambda model, kind: Fake.DESCRIPTOR

    # Send request
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/models/test_model/tasks",
            json={"fake": "value"},
            headers={"Content-Type": "application/json"}
        )

    # Assertions
    assert response.status_code == 200
    assert "task_id" in response.json()
