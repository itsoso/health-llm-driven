"""Token 优化第一批(2026-07-11)契约测试。

#2 fast 回合工具白名单子集:固定 big-3, 不随消息变(保前缀缓存);
#3 orchestrator 结果投影:二次合成只吃 synthesis+精简 findings, 契约字段(perf)保留。
"""
import json

import pytest

from app.services.tool_schema_registry import (
    ANALYSIS_TURN_TOOL_NAMES,
    DIET_TURN_TOOL_NAMES,
    KNOWLEDGE_TURN_TOOL_NAMES,
    RECOVERY_TURN_TOOL_NAMES,
    FAST_READ_TURN_TOOL_NAMES,
    FAST_TURN_TOOL_NAMES,
    HEALTH_TOOLS,
    get_health_tools,
)
from app.services.agent_executor import (
    _fast_turn_tool_names_for_message,
    _history_limit_for_turn,
    _is_analysis_only_turn,
    _project_orchestrator_result,
    _tool_subset_withheld_upgrade,
    _tool_names_for_turn,
)


def test_domain_history_window_trims_only_standalone_scoped_reads():
    assert _history_limit_for_turn(
        "昨晚睡得怎样，今天是否适合锻炼？",
        domain_optimization=True,
        has_attachments=False,
    ) == 6
    assert _history_limit_for_turn(
        "刚才那个睡眠结果继续分析",
        domain_optimization=True,
        has_attachments=False,
    ) == 15
    assert _history_limit_for_turn(
        "删除刚才的两餐",
        domain_optimization=True,
        has_attachments=False,
    ) == 15
    assert _history_limit_for_turn(
        "综合分析睡眠和肝功能趋势",
        domain_optimization=True,
        has_attachments=False,
    ) == 15


@pytest.mark.parametrize(
    "message",
    (
        "上次的用药方案再发我一下",
        "昨天说的用药怎么吃",
        "请回顾上周说的训练建议",
        "同前，今天还能运动吗",
        "照旧分析今天的睡眠",
        "按照你的建议继续训练",
        "和之前相比睡眠怎样",
        "按你说的今天练多少",
        "你之前建议的运动强度是多少",
        "基于前述睡眠结果今天能跑吗",
        "per your advice, how hard should I train today",
        "照你说的今天运动多少",
        "基于你说的睡眠结果今天能跑吗",
        "as you suggested, can I exercise",
        "根据你的建议今天运动多少",
    ),
)
def test_domain_history_window_fails_open_for_conversation_references(message):
    assert _history_limit_for_turn(
        message,
        domain_optimization=True,
        has_attachments=False,
    ) == 15


def test_domain_history_window_fails_open_when_disabled_or_with_attachment():
    assert _history_limit_for_turn(
        "昨晚睡得怎样？",
        domain_optimization=False,
        has_attachments=False,
    ) == 15
    assert _history_limit_for_turn(
        "解读这份睡眠截图",
        domain_optimization=True,
        has_attachments=True,
    ) == 15


def test_fast_subset_returns_exactly_big3_in_stable_order():
    subset = get_health_tools(subset=list(FAST_TURN_TOOL_NAMES))
    names = [t["function"]["name"] for t in subset]
    assert set(names) == {"health_record", "health_query", "health_manage"}
    # 顺序=HEALTH_TOOLS 定义序(字节稳定 → 前缀缓存友好), 两次调用完全一致
    assert names == [t["function"]["name"] for t in get_health_tools(subset=list(FAST_TURN_TOOL_NAMES))]


def test_fast_read_turn_omits_write_tool():
    names = _fast_turn_tool_names_for_message("今天我的饮食的记录，帮我列个表格出来。")

    assert names == FAST_READ_TURN_TOOL_NAMES
    assert "health_record" not in names
    assert "health_query_batch" in names


def test_fast_write_turn_keeps_record_tool():
    names = _fast_turn_tool_names_for_message("记录午餐吃了牛肉面")

    assert names == FAST_TURN_TOOL_NAMES
    assert "health_record" in names


def test_full_toolset_unchanged_by_subset_param():
    assert get_health_tools() == HEALTH_TOOLS
    assert len(get_health_tools()) == len(HEALTH_TOOLS)


def test_subset_saves_majority_of_schema_bytes():
    full = len(json.dumps(get_health_tools(), ensure_ascii=False))
    small = len(json.dumps(get_health_tools(subset=list(FAST_TURN_TOOL_NAMES)), ensure_ascii=False))
    assert small < full * 0.55  # 实测 ~37%, 松断言防 schema 演化误红


# ── R5 分析轮只读工具子集 ──────────────────────────────────────────

def test_analysis_subset_is_read_only():
    """分析子集绝不含写/上传/管理工具(否则纯分析轮可能静默写)。"""
    WRITE = {"health_record", "health_manage", "upload_genetic_txt",
             "upload_medical_exam_text", "manage_plan", "intervention_cycle"}
    assert not (set(ANALYSIS_TURN_TOOL_NAMES) & WRITE)


def test_analysis_subset_all_exist_and_trim():
    full = {t["function"]["name"] for t in get_health_tools()}
    assert set(ANALYSIS_TURN_TOOL_NAMES) <= full  # 子集工具都真实存在
    sub = get_health_tools(subset=list(ANALYSIS_TURN_TOOL_NAMES))
    assert len(sub) < len(full)  # 真裁剪
    # 顺序稳定(前缀缓存友好):两次调用完全一致
    sub2 = get_health_tools(subset=list(ANALYSIS_TURN_TOOL_NAMES))
    assert [t["function"]["name"] for t in sub] == [t["function"]["name"] for t in sub2]


def test_analysis_subset_saves_schema_bytes():
    full = len(json.dumps(get_health_tools(), ensure_ascii=False))
    small = len(json.dumps(get_health_tools(subset=list(ANALYSIS_TURN_TOOL_NAMES)), ensure_ascii=False))
    assert small < full  # 分析子集省下 record/manage/upload/plan schema


def test_domain_recovery_turn_uses_stable_small_read_only_bundle():
    names = _tool_names_for_turn(
        "综合分析我最近的睡眠趋势",
        fast_route=False,
        analysis_subset=False,
        domain_subset=True,
        has_attachments=False,
    )
    assert names == RECOVERY_TURN_TOOL_NAMES
    assert "health_record" not in names
    assert "health_manage" not in names
    full_bytes = len(json.dumps(get_health_tools(), ensure_ascii=False))
    scoped_bytes = len(json.dumps(
        get_health_tools(subset=list(names)), ensure_ascii=False
    ))
    assert scoped_bytes < full_bytes * 0.4
    # New domain lanes supersede the older broad analysis lane when both
    # rollout flags are enabled.
    assert _tool_names_for_turn(
        "综合分析我最近的睡眠趋势",
        fast_route=False,
        analysis_subset=True,
        domain_subset=True,
        has_attachments=False,
    ) == RECOVERY_TURN_TOOL_NAMES


def test_every_domain_lane_maps_to_existing_read_only_tools():
    expected = {
        "分析我今天饮食营养": DIET_TURN_TOOL_NAMES,
        "循证医学是什么": KNOWLEDGE_TURN_TOOL_NAMES,
    }
    full_names = {tool["function"]["name"] for tool in get_health_tools()}
    write_names = {
        "health_record",
        "health_manage",
        "upload_genetic_txt",
        "upload_medical_exam_text",
        "manage_plan",
        "intervention_cycle",
        "record_doctor_feedback",
        "draft_aigc_media",
    }
    for query, expected_names in expected.items():
        actual = _tool_names_for_turn(
            query,
            fast_route=False,
            analysis_subset=False,
            domain_subset=True,
            has_attachments=False,
        )
        assert actual == expected_names
        assert set(actual) <= full_names
        assert not (set(actual) & write_names)


@pytest.mark.parametrize(
    "query",
    (
        "这个药是否适合我",
        "解读我的肝功能化验",
        "肝功能异常会不会和补剂有关",
    ),
)
def test_high_stakes_domain_tools_keep_cross_domain_safety_dependencies(query):
    actual = _tool_names_for_turn(
        query,
        fast_route=False,
        analysis_subset=False,
        domain_subset=True,
        has_attachments=False,
    )
    assert actual == ANALYSIS_TURN_TOOL_NAMES
    assert "query_lab_indicators" in actual
    assert "supplement_guide" in actual


def test_domain_tool_bundle_fails_open_for_write_or_attachment():
    assert _tool_names_for_turn(
        "删除刚才的两餐",
        fast_route=False,
        analysis_subset=False,
        domain_subset=True,
        has_attachments=False,
    ) is None
    assert _tool_names_for_turn(
        "解读这份报告",
        fast_route=False,
        analysis_subset=False,
        domain_subset=True,
        has_attachments=True,
    ) is None


@pytest.mark.parametrize(
    "message",
    (
        "记录我现在胸痛",
        "记录我服了维生素D",
        "删除刚才错误的用药记录",
    ),
)
def test_high_stakes_write_keeps_write_capable_full_toolset(message):
    assert _tool_names_for_turn(
        message,
        fast_route=False,
        analysis_subset=False,
        domain_subset=True,
        has_attachments=False,
    ) is None


def test_domain_tool_bundle_is_off_by_default():
    assert _tool_names_for_turn(
        "昨晚睡得怎样，今天是否适合锻炼？",
        fast_route=False,
        analysis_subset=False,
    ) is None


def test_is_analysis_only_turn_detection():
    f = _is_analysis_only_turn
    # 纯分析/建议 → True
    assert f("综合分析我最近的睡眠趋势", has_images=False, has_file=False)
    assert f("解读一下我的化验报告", has_images=False, has_file=False)
    assert f("为什么最近血压偏高?该怎么调整", has_images=False, has_file=False)
    # 记录/破坏性意图 → False(可能要写,不裁)
    assert not f("记录我今天血压120/80", has_images=False, has_file=False)
    assert not f("分析后帮我删除重复早餐", has_images=False, has_file=False)
    assert not f("喝了300ml水", has_images=False, has_file=False)
    # 多模态 → False
    assert not f("分析我的睡眠", has_images=True, has_file=False)
    assert not f("解读报告", has_images=False, has_file=True)


def test_ships_off_by_default():
    from app.config import Settings
    assert Settings.model_fields["analysis_turn_tool_subset"].default is False
    assert Settings.model_fields["domain_prompt_optimization"].default is False


# ── R5 withheld-upgrade 护栏(fast + analysis 共用)──────────────────

def _tc(name):  # 造一个 tool_call
    return {"function": {"name": name, "arguments": "{}"}}


def test_upgrade_none_when_requested_tool_in_subset():
    sub = get_health_tools(subset=list(ANALYSIS_TURN_TOOL_NAMES))
    withheld, action = _tool_subset_withheld_upgrade(
        [_tc("health_query")], sub, live_text_already_sent=False)
    assert action == "none" and withheld == []


def test_upgrade_rerun_when_withheld_write_tool_and_no_live_text():
    """分析轮请求被扣下的写工具 + 本轮未 live 正文 → rerun(升级回全集重跑,拿对 schema)。"""
    sub = get_health_tools(subset=list(ANALYSIS_TURN_TOOL_NAMES))
    withheld, action = _tool_subset_withheld_upgrade(
        [_tc("health_record")], sub, live_text_already_sent=False)
    assert action == "rerun" and withheld == ["health_record"]


def test_upgrade_fallthrough_when_live_text_already_sent():
    """已 live 流式正文 + 请求被扣工具 → fallthrough(不重跑避免双发,被扣工具按 name 执行)。"""
    sub = get_health_tools(subset=list(ANALYSIS_TURN_TOOL_NAMES))
    withheld, action = _tool_subset_withheld_upgrade(
        [_tc("health_manage")], sub, live_text_already_sent=True)
    assert action == "fallthrough" and withheld == ["health_manage"]


def test_upgrade_ignores_hallucinated_tool_not_in_full_set():
    """幻觉工具名(全集也没有)不算 withheld → none(走原未知工具路径,升级救不了它)。"""
    sub = get_health_tools(subset=list(ANALYSIS_TURN_TOOL_NAMES))
    withheld, action = _tool_subset_withheld_upgrade(
        [_tc("totally_made_up_tool")], sub, live_text_already_sent=False)
    assert action == "none" and withheld == []


def test_upgrade_works_for_fast_big3_subset_too():
    """同一护栏对 fast big-3 子集也成立(请求 health_analysis 被扣 → rerun)。"""
    sub = get_health_tools(subset=list(FAST_TURN_TOOL_NAMES))
    withheld, action = _tool_subset_withheld_upgrade(
        [_tc("health_analysis")], sub, live_text_already_sent=False)
    assert action == "rerun" and "health_analysis" in withheld


def _fake_orchestrator_json() -> str:
    return json.dumps({
        "intent": "recovery",
        "synthesis": "今晚早睡半小时, 明天以恢复性运动为主。",
        "used_specialists": ["recovery_coach", "safety_guardian"],
        "perf": {"llm_ttft_ms": 1200},
        "findings": [
            {
                "specialist_name": "recovery_coach",
                "category": "recovery",
                "summary": "HRV 低于 7 日均值, 建议降负荷。",
                "findings": [
                    {"severity": "medium", "title": "HRV 下降", "action": "恢复走路 20 分钟", "raw_series": [1, 2, 3]},
                ],
                "raw": {"huge": "x" * 5000},
                "ms_elapsed": 812,
            },
        ],
    }, ensure_ascii=False)


def test_projection_keeps_contract_fields_and_drops_raw():
    raw = _fake_orchestrator_json()
    projected = json.loads(_project_orchestrator_result(raw))

    assert projected["synthesis"] == "今晚早睡半小时, 明天以恢复性运动为主。"
    assert projected["perf"] == {"llm_ttft_ms": 1200}          # round loop 透传契约
    assert projected["used_specialists"] == ["recovery_coach", "safety_guardian"]
    f = projected["findings"][0]
    assert f["specialist"] == "recovery_coach" and f["summary"].startswith("HRV")
    assert f["items"][0]["severity"] == "medium"
    assert "raw" not in json.dumps(projected)                   # 大头被丢
    assert len(_project_orchestrator_result(raw)) < len(raw) * 0.4


def test_projection_fails_open_on_non_orchestrator_payloads():
    # 非 JSON / 无 synthesis 的 JSON → 原样返回, 绝不丢内容
    assert _project_orchestrator_result("Error: 上游超时") == "Error: 上游超时"
    other = json.dumps({"items": [1, 2, 3]})
    assert _project_orchestrator_result(other) == other


def test_intent_block_gating_menu_and_gene():
    """#5 意图门控:命中才发;None fail-open 全发(多模型路径未传 intent)。"""
    from app.services.agent_executor import (
        _wants_gene_rules_block,
        _wants_menu_share_block,
    )

    # menu:餐食类命中, 记录/查询类不发
    assert _wants_menu_share_block("今晚吃啥好")
    assert _wants_menu_share_block("给我个晚餐建议")
    assert not _wants_menu_share_block("记录我喝了500ml水")
    assert not _wants_menu_share_block("最近血压怎么样")
    # gene:基因/补剂相邻流命中(FADS1 优势基因误判风险在补剂建议里)
    assert _wants_gene_rules_block("从基因角度看我该怎么调整")
    assert _wants_gene_rules_block("我的补剂方案合理吗")
    assert _wants_gene_rules_block("鱼油还要不要吃")
    assert not _wants_gene_rules_block("今天步数多少")
    # fail-open:未传 intent → 全发, 行为与旧版一致
    assert _wants_menu_share_block(None) and _wants_gene_rules_block(None)


def test_intent_blocks_preserve_exact_text_when_included():
    """门控块内容与旧内联文本一致的关键锚点(防抽取时改字)。"""
    from app.services.agent_executor import (
        _GENE_RULES_PROMPT_BLOCK,
        _MENU_SHARE_PROMPT_BLOCK,
    )

    assert _GENE_RULES_PROMPT_BLOCK[0] == "## 基因解读规则（必须遵守）"
    assert any("FADS1 TT" in line for line in _GENE_RULES_PROMPT_BLOCK)
    assert any("SLCO1B1" in line for line in _GENE_RULES_PROMPT_BLOCK)
    assert _MENU_SHARE_PROMPT_BLOCK[0] == "## 菜单输出 (可分享卡片)"
    assert any("```menu_share" in line for line in _MENU_SHARE_PROMPT_BLOCK)
    assert _GENE_RULES_PROMPT_BLOCK[-1] == "" and _MENU_SHARE_PROMPT_BLOCK[-1] == ""
