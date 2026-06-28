"""确定性数值合理性闸测试 — scan_implausible + annotate_if_implausible。

覆盖动机: SpO2 53% 录入错误被当作 🔴立即行动 依据的生产事故。
安全评审修正铁律: 被标记的值在两个方向都安全 ——
  错误→提示核实; 属实→危急→建议就医。**永不**等于"忽略"。
危险区(WBC 0.4 / PLT 4 / SpO2 65 / Hgb 60 g/L 这类真实可生存的危急值)
必须标为 suspect 走安全语义, 绝不被 R4 prompt 教模型忽略。
"""
import json

from app.services.lab_plausibility import (
    scan_implausible,
    annotate_if_implausible,
    TIER_IMPOSSIBLE,
    TIER_SUSPECT,
)


def _flagged_names(flags):
    return {str(f["name"]) for f in flags}


def _tiers_by_metric(flags):
    return {str(f["name"]): f["tier"] for f in flags}


# ── 危险区: 真实但极端 → 必须标 suspect, 安全语义 ────────────────
# 这些是真实可生存的危急值; 原 SpO2-53 bug 的根因就在这里。
# 它们必须被标记(去核实), 且 reason 绝不含"勿作为依据"/"忽略"式压制措辞。

_SUPPRESSION_WORDS = ["勿作为依据", "忽略", "不要作为依据", "请勿作为", "不予理会"]


def _assert_safe_suspect(flags, name_substr):
    """断言: 至少一条 flag 命中该指标, tier=suspect, reason 安全(不压制 + 提就医)。"""
    matched = [f for f in flags if name_substr.lower() in str(f["name"]).lower()]
    assert matched, f"expected a flag for {name_substr}, got {flags}"
    for f in matched:
        assert f["tier"] == TIER_SUSPECT, f"{name_substr} should be suspect, got {f['tier']}"
        reason = f["reason"]
        for w in _SUPPRESSION_WORDS:
            assert w not in reason, f"reason must not suppress action: {reason!r}"
        assert "就医" in reason, f"suspect reason must advise 就医: {reason!r}"


def test_spo2_60_suspect_safe():
    flags = scan_implausible([{"name": "SpO2", "value": 60, "unit": "%"}])
    _assert_safe_suspect(flags, "spo2")


def test_spo2_53_suspect_safe():
    # 原生产事故值 —— 现在必须是 suspect(去核实), 不是被忽略
    flags = scan_implausible([{"name": "SpO2", "value": 53, "unit": "%"}])
    _assert_safe_suspect(flags, "spo2")


def test_wbc_03_suspect_safe():
    flags = scan_implausible([{"name": "白细胞", "value": 0.3, "unit": "×10^9/L"}])
    _assert_safe_suspect(flags, "白细胞")


def test_wbc_04_suspect_safe():
    flags = scan_implausible([{"name": "WBC", "value": 0.4, "unit": "×10^9/L"}])
    _assert_safe_suspect(flags, "wbc")


def test_plt_3_suspect_safe():
    flags = scan_implausible([{"name": "血小板", "value": 3, "unit": "×10^9/L"}])
    _assert_safe_suspect(flags, "血小板")


def test_plt_4_suspect_safe():
    flags = scan_implausible([{"name": "PLT", "value": 4, "unit": "×10^9/L"}])
    _assert_safe_suspect(flags, "plt")


def test_hgb_45_gl_suspect_safe():
    flags = scan_implausible([{"name": "血红蛋白", "value": 45, "unit": "g/L"}])
    _assert_safe_suspect(flags, "血红蛋白")


def test_spo2_65_suspect_safe():
    flags = scan_implausible([{"name": "血氧", "value": 65, "unit": "%"}])
    _assert_safe_suspect(flags, "血氧")


# ── impossible 档: 活体绝不可能 → 几乎必为录入错误 ───────────────

def test_spo2_130_impossible():
    flags = scan_implausible([{"name": "SpO2", "value": 130, "unit": "%"}])
    assert _tiers_by_metric(flags).get("SpO2") == TIER_IMPOSSIBLE


def test_temp_50_impossible():
    flags = scan_implausible([{"name": "体温", "value": 50, "unit": "°C"}])
    assert flags
    assert all(f["tier"] == TIER_IMPOSSIBLE for f in flags)


def test_hr_400_impossible():
    flags = scan_implausible([{"name": "心率", "value": 400, "unit": "bpm"}])
    assert flags
    assert all(f["tier"] == TIER_IMPOSSIBLE for f in flags)


def test_hgb_5_gdl_impossible():
    # 5 < 30 → 视作 g/dL; 5 < ... 不, 5 > 1 且 < 26 → 在 g/dL impossible 内? 不。
    # 题目要求 "Hgb 5 g/L" impossible: 5 g/L = 0.5 g/dL < 1 → impossible。
    flags = scan_implausible([{"name": "血红蛋白", "value": 5, "unit": "g/L"}])
    assert flags
    assert all(f["tier"] == TIER_IMPOSSIBLE for f in flags)


# ── 正常-异常 → 绝不标记 ────────────────────────────────────────

def test_spo2_88_not_flagged():
    # 88% 真低氧血症, 异常但生理可能 → 不标记
    flags = scan_implausible([{"name": "spo2", "value": 88, "unit": "%"}])
    assert flags == []


def test_wbc_32_not_flagged():
    flags = scan_implausible([{"name": "白细胞", "value": 3.2, "unit": "×10^9/L"}])
    assert flags == []


def test_plt_90_not_flagged():
    flags = scan_implausible([{"name": "血小板", "value": 90, "unit": "×10^9/L"}])
    assert flags == []


def test_hgb_110_gl_not_flagged():
    flags = scan_implausible([{"name": "血红蛋白", "value": 110, "unit": "g/L"}])
    assert flags == []


def test_hct_54_not_flagged():
    flags = scan_implausible([{"name": "红细胞压积", "value": 54, "unit": "%"}])
    assert flags == []


def test_hgb_173_gl_not_flagged():
    flags = scan_implausible([{"name": "血红蛋白", "value": 173, "unit": "g/L"}])
    assert flags == []


def test_hr_60_not_flagged():
    flags = scan_implausible([{"name": "heart rate", "value": 60, "unit": "bpm"}])
    assert flags == []


def test_spo2_96_not_flagged():
    flags = scan_implausible([{"name": "血氧饱和度", "value": 96, "unit": "%"}])
    assert flags == []


# ── 词边界: 短 token 同义词必须整 token 相等(无子串误配) ──────────

def test_word_boundary_no_false_positives():
    text = json.dumps(
        {"thr_value": 5, "attempts": 50, "reference_low": 0.5, "count": 53},
        ensure_ascii=False,
    )
    out = annotate_if_implausible(text)
    # 不应注入任何告警 → 输出 json-equal 于输入
    assert json.loads(out) == json.loads(text)
    assert "_data_plausibility_warning" not in out


def test_thr_value_not_matched_as_hr():
    flags = scan_implausible([{"name": "thr_value", "value": 5, "unit": None}])
    assert flags == []


def test_attempts_not_matched_as_temp():
    flags = scan_implausible([{"name": "attempts", "value": 50, "unit": None}])
    assert flags == []


# ── 下划线键(常见 shape): hr 短同义词不命中, 靠长同义词补 ──────────

def test_heart_rate_underscore_key_impossible():
    # heart_rate: hr 短同义词被 'thr' 边界挡住, 必须靠长同义词 heart_rate 命中
    flags = scan_implausible([{"name": "heart_rate", "value": 400, "unit": "bpm"}])
    assert flags
    assert all(f["tier"] == TIER_IMPOSSIBLE for f in flags)


def test_heart_rate_underscore_key_normal_not_flagged():
    flags = scan_implausible([{"name": "heart_rate", "value": 72, "unit": "bpm"}])
    assert flags == []


def test_reference_low_denylisted():
    # 即便值落在某指标可疑区, reference_low 也被 DENYLIST 掉, 不扫
    text = json.dumps({"reference_low": 0.5}, ensure_ascii=False)
    out = annotate_if_implausible(text)
    assert "_data_plausibility_warning" not in out


# ── 解析鲁棒性 ──────────────────────────────────────────────

def test_arrow_and_string_value_parsed():
    flags = scan_implausible([{"name": "SpO2", "value": "53↓", "unit": "%"}])
    assert flags
    assert flags[0]["tier"] == TIER_SUSPECT


def test_non_numeric_value_skipped_no_crash():
    flags = scan_implausible([{"name": "SpO2", "value": "正常", "unit": "%"}])
    assert flags == []


def test_empty_list():
    assert scan_implausible([]) == []


# ── annotate_if_implausible: JSON 有效性 ────────────────────────

def test_annotate_json_object_stays_valid_with_warning_key():
    text = json.dumps({"name": "血氧", "value": 130, "unit": "%"}, ensure_ascii=False)
    out = annotate_if_implausible(text)
    parsed = json.loads(out)  # 必须仍是合法 JSON
    assert "_data_plausibility_warning" in parsed
    warns = parsed["_data_plausibility_warning"]
    assert isinstance(warns, list) and warns
    assert warns[0]["tier"] == TIER_IMPOSSIBLE
    # 原数据不被修改
    assert parsed["value"] == 130
    assert parsed["name"] == "血氧"


def test_annotate_json_array_wrapped():
    text = json.dumps(
        [{"name": "SpO2", "value": 53, "unit": "%"}], ensure_ascii=False
    )
    out = annotate_if_implausible(text)
    parsed = json.loads(out)
    assert isinstance(parsed, dict)
    assert "data" in parsed and isinstance(parsed["data"], list)
    assert "_data_plausibility_warning" in parsed
    assert parsed["_data_plausibility_warning"][0]["tier"] == TIER_SUSPECT


def test_annotate_clean_json_json_equal_no_warning():
    text = json.dumps({"spo2": 96, "heart_rate": 60}, ensure_ascii=False)
    out = annotate_if_implausible(text)
    assert json.loads(out) == json.loads(text)
    assert "_data_plausibility_warning" not in out


def test_annotate_non_json_string_unchanged():
    text = "用户最近睡眠良好, 血氧正常。"
    assert annotate_if_implausible(text) == text


def test_annotate_malformed_no_crash():
    text = '{"spo2": 53, "unit": '  # 截断的 JSON
    assert annotate_if_implausible(text) == text


def test_annotate_empty_string_unchanged():
    assert annotate_if_implausible("") == ""


def test_annotate_nested_record_flagged_stays_valid():
    text = json.dumps(
        {"latest": {"name": "血氧", "value": 53, "unit": "%"}}, ensure_ascii=False
    )
    out = annotate_if_implausible(text)
    parsed = json.loads(out)
    assert "_data_plausibility_warning" in parsed
    assert parsed["_data_plausibility_warning"][0]["tier"] == TIER_SUSPECT
    # 原嵌套结构完好
    assert parsed["latest"]["value"] == 53


def test_annotate_warning_reason_is_safe():
    # 注入到 JSON 的 reason 同样必须是安全语义(suspect → 提就医, 不压制)
    text = json.dumps({"name": "WBC", "value": 0.4, "unit": "×10^9/L"}, ensure_ascii=False)
    parsed = json.loads(annotate_if_implausible(text))
    reason = parsed["_data_plausibility_warning"][0]["reason"]
    assert "就医" in reason
    for w in _SUPPRESSION_WORDS:
        assert w not in reason


# ── 工具/提示集成(轻量, 无需 DB fixture) ──────────────────

def test_registry_includes_knowledge_search():
    from app.services.tool_schema_registry import get_tool_names, HEALTH_TOOLS

    assert "knowledge_search" in get_tool_names()
    tool = next(t for t in HEALTH_TOOLS if t["function"]["name"] == "knowledge_search")
    props = tool["function"]["parameters"]["properties"]
    assert "query" in props
    assert "n_results" in props
    assert tool["function"]["parameters"]["required"] == ["query"]


def test_system_prompt_contains_r4_block(db):
    from app.services.agent_executor import AgentExecutor

    prompt = AgentExecutor(db)._build_system_prompt(
        user_id=1, conv_id=1, user_auth_token=None
    )
    # R4 markers — 因果边界 + 数据合理性闸联动 + knowledge_search 接地
    assert "相关性,非因果" in prompt
    assert "数据合理性提示" in prompt
    assert "knowledge_search" in prompt
    # R4 必须**不**含"绝不忽略"被反转的旧压制措辞
    assert "绝不**用它做任何判断或行动建议" not in prompt
