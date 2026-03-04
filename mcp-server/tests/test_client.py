"""测试 Health API Client"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

# Add parent dir to path so we can import from mcp-server root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from client import HealthAPIClient


@pytest.fixture
def client():
    return HealthAPIClient(
        base_url="http://test-api:8000/api/v1",
        token="test-token-123"
    )


@pytest.mark.asyncio
async def test_client_get_headers(client):
    headers = client._get_headers()
    assert headers["Authorization"] == "Bearer test-token-123"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_client_get_success(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": "test"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_instance

        result = await client.get("/water/records/me/date/2024-01-01")
        assert result == {"data": "test"}


@pytest.mark.asyncio
async def test_client_post_success(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": 1, "amount": 250}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_instance

        result = await client.post("/water/records/quick", params={"amount": 250})
        assert result["amount"] == 250


@pytest.mark.asyncio
async def test_client_error_handling(client):
    with patch("httpx.AsyncClient") as MockClient:
        mock_instance = AsyncMock()
        mock_instance.get.side_effect = Exception("Connection refused")
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=None)
        MockClient.return_value = mock_instance

        result = await client.get("/nonexistent")
        assert "error" in result
