"""测试 Chat Tools Schema 定义"""
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from app.services.chat_tools import HEALTH_TOOLS, get_tool_by_name, execute_tool


def test_health_tools_format():
    """所有工具都符合 OpenAI function calling 格式"""
    assert len(HEALTH_TOOLS) >= 5
    for tool in HEALTH_TOOLS:
        assert tool["type"] == "function"
        func = tool["function"]
        assert "name" in func
        assert "description" in func
        assert "parameters" in func
        assert func["parameters"]["type"] == "object"


def test_get_tool_by_name():
    """能通过名称查找工具"""
    tool = get_tool_by_name("record_water")
    assert tool is not None
    assert tool["function"]["name"] == "record_water"


def test_get_tool_by_name_not_found():
    """查找不存在的工具返回 None"""
    tool = get_tool_by_name("nonexistent_tool")
    assert tool is None


def test_tool_names_unique():
    """工具名称唯一"""
    names = [t["function"]["name"] for t in HEALTH_TOOLS]
    assert len(names) == len(set(names))


# ---- Tool Executor Tests ----

@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.id = 1
    return user


@pytest.mark.asyncio
async def test_execute_record_water(mock_db, mock_user):
    """测试执行饮水记录工具"""
    with patch("app.services.chat_tools._record_water") as mock_fn:
        mock_fn.return_value = {"success": True, "amount": 250}
        result = await execute_tool("record_water", {"amount_ml": 250}, mock_db, mock_user)
        assert result["success"] is True
        assert result["amount"] == 250


@pytest.mark.asyncio
async def test_execute_record_weight(mock_db, mock_user):
    """测试执行体重记录工具"""
    with patch("app.services.chat_tools._record_weight") as mock_fn:
        mock_fn.return_value = {"success": True, "weight": 72.5}
        result = await execute_tool("record_weight", {"weight_kg": 72.5}, mock_db, mock_user)
        assert result["success"] is True


@pytest.mark.asyncio
async def test_execute_unknown_tool(mock_db, mock_user):
    """测试执行未知工具返回错误"""
    result = await execute_tool("unknown_tool", {}, mock_db, mock_user)
    assert result.get("error") is not None
