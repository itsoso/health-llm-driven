"""测试受控 reviewed knowledge MCP 工具"""

import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tools.knowledge import (  # noqa: E402
    get_knowledge_coverage_report,
    get_knowledge_eval_report,
    lookup_reviewed_knowledge_for_twin,
    search_reviewed_knowledge,
)


@pytest.fixture
def mock_client():
    with patch("tools.knowledge.get_client") as mock_get_client:
        client = AsyncMock()
        mock_get_client.return_value = client
        yield client


@pytest.mark.asyncio
async def test_search_reviewed_knowledge_calls_serving_search(mock_client):
    mock_client.get.return_value = {"results": [{"document": {"doc_id": "claim:c_demo"}}]}

    result = await search_reviewed_knowledge("葡萄柚 用药", limit=3, doc_type="claim")
    data = json.loads(result)

    assert data["results"][0]["document"]["doc_id"] == "claim:c_demo"
    mock_client.get.assert_called_once_with(
        "/knowledge/search",
        params={"q": "葡萄柚 用药", "limit": 3, "doc_type": "claim"},
    )


@pytest.mark.asyncio
async def test_lookup_reviewed_knowledge_for_twin_posts_twin_payload(mock_client):
    twin = {"medications": [{"name": "simvastatin"}]}
    mock_client.post.return_value = {"claims": [{"doc_id": "claim:c_grapefruit"}]}

    result = await lookup_reviewed_knowledge_for_twin(twin)
    data = json.loads(result)

    assert data["claims"][0]["doc_id"] == "claim:c_grapefruit"
    mock_client.post.assert_called_once_with("/knowledge/lookup_for_twin", data=twin)


@pytest.mark.asyncio
async def test_get_knowledge_coverage_report_calls_admin_endpoint(mock_client):
    mock_client.get.return_value = {"documents": {"total": 841}}

    result = await get_knowledge_coverage_report()
    data = json.loads(result)

    assert data["documents"]["total"] == 841
    mock_client.get.assert_called_once_with("/admin/knowledge/coverage_report")


@pytest.mark.asyncio
async def test_get_knowledge_eval_report_calls_admin_eval_endpoint(mock_client):
    mock_client.get.return_value = {"total": 1, "failed": 0}

    result = await get_knowledge_eval_report(["eval:demo"])
    data = json.loads(result)

    assert data["failed"] == 0
    mock_client.get.assert_called_once_with(
        "/admin/knowledge/eval_report",
        params={"case_id": ["eval:demo"]},
    )
