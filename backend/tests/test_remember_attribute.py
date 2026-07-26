"""remember 记录能力:无结构化类型的个人属性/事实 → MemoryFact 三元组。

补齐"档案属性"缺口 —— 此前小巴主动说"补充进档案"却无工具可写, 用户给了值也
0 工具调用 → 落进饮食味的兜底话术(founder 2026-07-17 实测:鞋码 42.5 记不下来
还被要求补早餐)。
"""
import json
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_remember_routes_to_memory_fact(db):
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 7

    captured = {}

    async def fake_post(url, headers, payload):
        captured["url"] = url
        captured["payload"] = payload
        return json.dumps({"id": 88, "subject": "用户", "predicate": "鞋码",
                           "object_value": "42.5", "tier": "semantic"})

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._exec_health_record(
            "http://t", {"Authorization": "Bearer x"},
            {"record_type": "remember", "data": {"predicate": "鞋码", "object_value": "42.5"}},
        )

    assert captured["url"].endswith("/memory-facts"), captured["url"]
    p = captured["payload"]
    assert p["predicate"] == "鞋码"
    assert p["object_value"] == "42.5"
    assert p["subject"] == "用户"       # 默认主语
    assert p["tier"] == "semantic"
    assert p["confidence"] >= 0.8        # 用户明说 → 高置信
    # 写入被识别为回执(id-based)
    assert json.loads(result).get("id") == 88


@pytest.mark.asyncio
async def test_remember_missing_value_fails_loud(db):
    """缺属性名或值 → fail-loud, 不静默写空事实。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 7

    async def fake_post(url, headers, payload):
        raise AssertionError("不该在缺值时发 POST")

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._exec_health_record(
            "http://t", {"Authorization": "Bearer x"},
            {"record_type": "remember", "data": {"predicate": "鞋码"}},  # 无 object_value
        )
    rejection = json.loads(result)
    assert rejection["status"] == "rejected"
    assert rejection["success"] is False
    assert rejection["dispatch_started"] is False
    assert rejection["error_code"] == "memory_attribute_missing"


def test_remember_is_typed_only_auto_confirm():
    """remember 是可逆、非医疗的档案属性 → typed 通道免确认(与 symptom/goal 同档)。"""
    from app.services import agent_executor as ae

    assert "remember" in ae._TYPED_ONLY_AUTO_CONFIRM_KINDS
    assert "remember" not in ae._FAST_RECORD_NEVER_AUTO_CONFIRM_KINDS
    assert ae._RESOURCE_TYPE_BY_RECORD_TYPE.get("remember") == "memory_fact"


def test_typed_only_is_subset_of_auto_confirm():
    """不变量(safety review IMPORTANT-3):typed_only ⊆ AUTO 集,否则 typed 通道恒确认 →
    fast 模式确认死循环。symptom/rhinitis/goal/remember 都必须同时在两个集合里。"""
    from app.services import agent_executor as ae

    assert ae._TYPED_ONLY_AUTO_CONFIRM_KINDS <= ae._FAST_RECORD_AUTO_CONFIRM_KINDS, (
        ae._TYPED_ONLY_AUTO_CONFIRM_KINDS - ae._FAST_RECORD_AUTO_CONFIRM_KINDS
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    {"predicate": "血压", "object_value": "150/95"},          # 血压读数
    {"predicate": "记录", "object_value": "华法林"},           # 药名(drug_lexicon)
    {"predicate": "剂量", "object_value": "二甲双胍 500mg"},   # 剂量
    {"predicate": "基因型", "object_value": "C282Y 纯合"},      # 基因变异
    {"predicate": "空腹血糖", "object_value": "7.2"},          # 化验指标
    # ── 复审证伪的 fail-open, 必须闭合 ──
    {"predicate": "读数", "object_value": "150／95"},          # 全角斜杠 U+FF0F
    {"predicate": "在用", "object_value": "Xarelto"},          # 非词表英文药名 + 给药动词
    {"predicate": "今早150/95", "object_value": "mmHg"},       # BP 落 predicate + unit(扫全 blob)
])
async def test_remember_backstop_blocks_structured_medical(db, data):
    """BLOCKING-1:结构化医疗/化验/基因/用药数据经 remember → 服务端硬闸 fail-loud redirect,
    绝不写 memory_fact(否则绕过 Safety Guardian + 加密/RLS)。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 7

    async def fake_post(url, headers, payload):
        raise AssertionError(f"结构化医疗数据不该写 memory_fact: {payload}")

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._exec_health_record(
            "http://t", {"Authorization": "Bearer x"},
            {"record_type": "remember", "data": data},
        )
    rejection = json.loads(result)
    assert rejection["status"] == "rejected", (data, result)
    assert rejection["success"] is False
    assert rejection["dispatch_started"] is False
    assert rejection["error_code"] in {
        "remember_clinical_data_redirect",
        "remember_genetic_redirect",
        "remember_medication_redirect",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("data", [
    {"predicate": "鞋码", "object_value": "42.5"},
    {"predicate": "血型", "object_value": "A型"},
    {"predicate": "忌口", "object_value": "不吃香菜"},
    {"predicate": "衣服尺码", "object_value": "L"},
    # ── 复审证伪的 over-alarm(fail-safe 但打中核心用例), 必须放行 ──
    {"predicate": "职业", "object_value": "药剂师"},           # 泛称'药'不该误判用药
    {"predicate": "职业", "object_value": "医药代表"},
    {"predicate": "习惯", "object_value": "在吃素"},           # 饮食偏好 ≠ 用药
    {"predicate": "会员卡号", "object_value": "A2024B"},       # 流水号 ≠ 基因变异
    {"predicate": "喜好", "object_value": "capsaicin"},        # ca(psa)icin ≠ PSA 化验
    {"predicate": "评分", "object_value": "*5"},               # 星号评分 ≠ 星等位
])
async def test_remember_backstop_allows_benign_attributes(db, data):
    """良性档案属性(鞋码/血型/忌口/衣码)不被硬闸误伤,照常写 memory_fact。"""
    from app.services.agent_executor import AgentExecutor

    executor = AgentExecutor(db)
    executor._current_user_id = 7
    captured = {}

    async def fake_post(url, headers, payload):
        captured["payload"] = payload
        return json.dumps({"id": 1, "predicate": data["predicate"]})

    with patch.object(executor, "_api_post", new=AsyncMock(side_effect=fake_post)):
        result = await executor._exec_health_record(
            "http://t", {"Authorization": "Bearer x"},
            {"record_type": "remember", "data": data},
        )
    assert not str(result).startswith("Error:"), (data, result)
    assert captured["payload"]["predicate"] == data["predicate"]
