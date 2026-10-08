"""Public registry text can be reused; authority and mutable schemas cannot."""
from copy import deepcopy
import hashlib
import importlib.util
from itertools import combinations
from pathlib import Path

import pytest

from app.services import agent_tool_prompt_projection as projection
from app.services.agent_kernel.read_task_scope import OwnedReadScope


@pytest.fixture(autouse=True)
def empty_caches():
    def clear():
        for helper in (projection._query_description, projection._batch_description):
            if hasattr(helper, "cache_clear"):
                helper.cache_clear()
    clear()
    yield
    clear()


def tools():
    return deepcopy(projection.HEALTH_TOOLS[:2])


def scope(*dimensions, days=7):
    return OwnedReadScope(tuple({"dimension": dimension, "days": days} for dimension in dimensions))


def test_all_dimension_subsets_match_frozen_provider_bytes_cold_and_warm():
    path = Path(__file__).parent / "fixtures/tool_projection_7d934b3.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "054fd897fd4c3964dbe1154f5ae0c6fb8ee813a220f755b741e63f4be6df43d1"
    spec = importlib.util.spec_from_file_location("frozen_tool_projection", path)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    dimensions = ["sleep", "spo2", "diet", "workout", "supplements"]
    for size in range(1, len(dimensions) + 1):
        for subset in combinations(dimensions, size):
            for authorized in (tools(), tools()[:1], tools()[1:], []):
                original = deepcopy(authorized)
                bound = scope(*subset)
                expected = baseline.project_owned_read_tool_descriptions(authorized, bound)
                for _ in range(2):
                    assert projection.project_owned_read_tool_descriptions(authorized, bound) == expected
                    assert authorized == original


def test_repeated_public_guide_parses_once_across_date_ranges(monkeypatch):
    class CountedPattern:
        def __init__(self, pattern):
            self.pattern, self.calls = pattern, 0

        def finditer(self, text):
            self.calls += 1
            return self.pattern.finditer(text)

    counted = CountedPattern(projection._SECTION)
    monkeypatch.setattr(projection, "_SECTION", counted)
    original = tools()
    expected = projection.project_owned_read_tool_descriptions(original, scope("sleep", "diet"))
    for days in (1, 7, 31, 7):
        assert projection.project_owned_read_tool_descriptions(original, scope("diet", "sleep", days=days)) == expected
    assert counted.calls == 1


@pytest.mark.parametrize("tool_index", [0, 1])
def test_registry_edits_invalidate_warm_text_immediately(monkeypatch, tool_index):
    bound = scope("sleep", "spo2")
    projection.project_owned_read_tool_descriptions(tools(), bound)
    changed = deepcopy(projection.HEALTH_TOOLS)
    changed[tool_index]["function"]["description"] += "\n新增合成安全限制，必须保留。"
    monkeypatch.setattr(projection, "HEALTH_TOOLS", changed)
    result = projection.project_owned_read_tool_descriptions(tools(), bound)
    assert "新增合成安全限制" in result[tool_index]["function"]["description"]
    # Incompatible format after a warm hit must use its complete new text.
    changed[tool_index]["function"]["description"] = "新版格式：保持完整说明"
    authorized = tools()
    assert projection.project_owned_read_tool_descriptions(authorized, bound)[tool_index] is authorized[tool_index]


def test_warm_text_cannot_restore_tools_or_reuse_mutated_schema():
    bound = scope("sleep")
    first = projection.project_owned_read_tool_descriptions(tools(), bound)
    first[0]["function"]["parameters"]["required"].append("provider_mutation")
    first[0]["function"]["description"] = "provider_mutation"
    authorized = tools()
    second = projection.project_owned_read_tool_descriptions(authorized, bound)
    assert "provider_mutation" not in second[0]["function"]["parameters"]["required"]
    assert second[0]["function"]["description"] != "provider_mutation"
    assert projection.project_owned_read_tool_descriptions([], bound) == []
    batch_only = projection.project_owned_read_tool_descriptions(authorized[1:], bound)
    assert [tool["function"]["name"] for tool in batch_only] == ["health_query_batch"]
    authorized[0]["function"]["parameters"]["properties"]["dimension"]["enum"] = ["sleep"]
    assert projection.project_owned_read_tool_descriptions(authorized, bound)[0] is authorized[0]


def test_public_metadata_cache_has_a_fixed_capacity():
    query = projection.HEALTH_TOOLS[0]["function"]["description"]
    batch = projection.HEALTH_TOOLS[1]["function"]["description"]
    for version in range(96):
        guidance = projection._query_description(query + f"\nregistry_version={version}", frozenset({"sleep"}))
        projection._batch_description(batch, guidance)
    assert projection._query_description.cache_info().maxsize == 64
    assert projection._query_description.cache_info().currsize == 64
    assert projection._batch_description.cache_info().maxsize == 64
    assert projection._batch_description.cache_info().currsize == 64


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_warm_cache_preserves_provider_payload_and_rechecks_owner(db, auth_user_and_headers, monkeypatch, stream):
    from app.services import agent_executor as ae
    from tests.test_agent_prompt_budget_execution import CaptureProvider

    user, _ = auth_user_and_headers
    executor = ae.AgentExecutor(db)
    text = "分析我最近7天的睡眠和饮食记录。"
    executor._current_user_id = user.id
    executor._current_turn_user_message = text
    executor._start_agent_kernel_turn(user_id=user.id, message=text, channel="typed")
    monkeypatch.setattr(ae.settings, "domain_prompt_optimization", True)
    monkeypatch.setattr(ae.settings, "agent_base_url", None)
    monkeypatch.setattr(ae.settings, "agent_api_key", None)
    provider = CaptureProvider()
    monkeypatch.setattr(executor, "_resolve_chat_provider", lambda authorized: (provider, authorized))
    authorized = tools()
    messages = [{"role": "user", "content": text}]
    for _ in range(2):
        if stream:
            _ = [event async for event in executor._call_llm_stream(messages, authorized)]
        else:
            await executor._call_llm(messages, authorized)
    assert provider.calls[0] == provider.calls[1]
    assert projection._query_description.cache_info().hits >= 1
    # A cache hit cannot bypass the owner match preceding the projection.
    executor._current_user_id = user.id + 1
    assert executor._model_tools_for_turn(authorized) == authorized
