import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient
from api_service import ModelAPIService

api_service = ModelAPIService()
app = api_service.app


@pytest.mark.asyncio
@patch("api_component.get_current_user", return_value="testuser")
@patch.object(api_service, "redis", new_callable=AsyncMock)
@patch.object(api_service, "rabbitmq_channel", new_callable=AsyncMock)
async def test_submit_task(mock_channel, mock_redis, mock_user):
    api_service.models = {"test_model": {"host": "localhost", "port": 9000}}

    # Return a fake descriptor
    descriptor = AsyncMock()
    api_service.get_descriptor = lambda model, kind: descriptor
    message_class = AsyncMock()
    message_instance = AsyncMock()
    message_class.return_value = message_instance
    message_instance.SerializeToString.return_value = b"protobuf_bytes"

    with patch("api_component.make_message_class", return_value=message_class):
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/models/test_model/tasks",
                json={},
                headers={"Authorization": "Bearer faketoken"}
            )
            assert response.status_code == 200
            assert "task_id" in response.json()
