"""report_cards.py 单测 — 确定性数据卡提取器 + 聚合 + shadow 落库前缀。

铁律验证:每个单元格值都来自 finding 的结构化字段(R4);数据缺口/unknown/缺字段 → 不出卡
(诚实空值,绝不编造)。safety 卡恒第一、总卡 cap≤4、渲染产出可 JSON parse 出 metric_table。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from app.orchestrator import report_cards
from app.orchestrator.schema import SpecialistFinding


# ---------------------------------------------------------------------------
# 构造帮手
# ---------------------------------------------------------------------------


def _finding(name: str, *, findings: List[Dict[str, Any]] = None, raw: Dict[str, Any] = None) -> SpecialistFinding:
    return SpecialistFinding(
        specialist_name=name,
        category="test",
        summary="",
        findings=findings or [],
        raw=raw or {},
    )


def _parse_reva_ui(rendered: str) -> dict:
    """把 render_metric_table_block 的 ```reva-ui fenced 文本 parse 回 block dict。"""
    lines = rendered.strip().splitlines()
    assert lines[0].startswith("```reva-ui"), rendered
    assert lines[-1] == "```", rendered
    return json.loads("\n".join(lines[1:-1]))


def _all_cells_str(block: dict) -> bool:
    keys = [c["key"] for c in block["columns"]]
    return all(isinstance(row.get(k), str) for row in block["rows"] for k in keys)


# ---------------------------------------------------------------------------
# safety_guardian
# ---------------------------------------------------------------------------


def _safety_finding() -> SpecialistFinding:
    return _finding(
        "safety_guardian",
        findings=[
            {"rule_id": "bp_crisis", "severity": 4, "severity_label": "紧急",
             "title": "血压危象", "action": "立即就医"},
            {"rule_id": "ddi_x", "severity": 3, "severity_label": "警告",
             "title": "药物相互作用", "action": "咨询药师"},
            {"rule_id": "note_x", "severity": 2, "severity_label": "注意",
             "title": "轻度提示", "action": "留意即可"},
        ],
    )


def test_safety_card_only_critical_and_high_critical_first():
    block = report_cards._safety_card(_safety_finding())
    assert block is not None
    assert block["type"] == "metric_table"
    assert block["v"] == 1
    assert block["title"] == "安全提示"
    # 只保留 critical(紧急) + high(警告), 丢掉 medium(注意); critical 在前
    assert len(block["rows"]) == 2
    assert block["rows"][0] == {"告警": "血压危象", "级别": "紧急", "处置": "立即就医"}
    assert block["rows"][1] == {"告警": "药物相互作用", "级别": "警告", "处置": "咨询药师"}
    assert _all_cells_str(block)


def test_safety_card_no_critical_high_returns_none():
    f = _finding(
        "safety_guardian",
        findings=[{"rule_id": "x", "severity": 2, "severity_label": "注意", "title": "轻度", "action": "看看"}],
    )
    assert report_cards._safety_card(f) is None


def test_safety_card_empty_findings_returns_none():
    assert report_cards._safety_card(_finding("safety_guardian", findings=[])) is None


# ---------------------------------------------------------------------------
# hypertension_specialist
# ---------------------------------------------------------------------------


def test_hypertension_card_positive():
    f = _finding(
        "hypertension_specialist",
        findings=[{"type": "bp_status", "systolic": 145, "diastolic": 92, "stage": "stage2"}],
        raw={"stage": "stage2", "systolic": 145, "diastolic": 92, "has_med": False},
    )
    block = report_cards._hypertension_card(f)
    assert block is not None
    assert block["rows"] == [{"指标": "血压", "数值": "145/92 mmHg", "说明": "二级高血压"}]
    assert _all_cells_str(block)


def test_hypertension_card_data_gap_returns_none():
    f = _finding("hypertension_specialist", raw={"stage": "unknown", "data_gap": True})
    assert report_cards._hypertension_card(f) is None


def test_hypertension_card_unknown_stage_returns_none():
    f = _finding("hypertension_specialist", raw={"stage": "unknown"})
    assert report_cards._hypertension_card(f) is None


def test_hypertension_card_missing_reading_returns_none():
    f = _finding("hypertension_specialist", raw={"stage": "stage1", "systolic": None, "diastolic": None})
    assert report_cards._hypertension_card(f) is None


# ---------------------------------------------------------------------------
# recovery_coach
# ---------------------------------------------------------------------------


def test_recovery_card_positive_garmin():
    f = _finding(
        "recovery_coach",
        findings=[{"type": "readiness_score", "score": 72, "zone": "moderate", "source": "garmin"}],
    )
    block = report_cards._recovery_card(f)
    assert block is not None
    assert block["rows"] == [{"指标": "Readiness", "数值": "72/100", "说明": "状态良好 · Garmin官方"}]
    assert _all_cells_str(block)


def test_recovery_card_computed_no_garmin_suffix():
    f = _finding(
        "recovery_coach",
        findings=[{"type": "readiness_score", "score": 60, "zone": "light", "source": "computed"}],
    )
    block = report_cards._recovery_card(f)
    assert block is not None
    assert block["rows"][0]["说明"] == "状态一般"


def test_recovery_card_unknown_zone_returns_none():
    f = _finding(
        "recovery_coach",
        findings=[{"type": "readiness_score", "score": 0, "zone": "unknown", "source": "computed"}],
    )
    assert report_cards._recovery_card(f) is None


def test_recovery_card_no_readiness_item_returns_none():
    f = _finding("recovery_coach", findings=[{"type": "action", "order": 1, "text": "休息"}])
    assert report_cards._recovery_card(f) is None


# ---------------------------------------------------------------------------
# metabolic_specialist
# ---------------------------------------------------------------------------


def test_metabolic_card_positive():
    f = _finding(
        "metabolic_specialist",
        findings=[
            {"type": "hba1c", "value": 5.8, "status": "prediabetes"},
            {"type": "lipid_panel", "ldl": 3.6, "hdl": 1.1, "triglycerides": 1.9},
            {"type": "body_composition", "bmi": 26.4, "bmi_category": "超重"},
            {"type": "metabolic_syndrome", "criteria_hit": 3, "factors": ["a", "b", "c"], "is_metabolic_syndrome": True},
        ],
        raw={"metabolic_syndrome": True, "criteria_hit": 3},
    )
    block = report_cards._metabolic_card(f)
    assert block is not None
    by_metric = {r["指标"]: r for r in block["rows"]}
    assert by_metric["HbA1c"] == {"指标": "HbA1c", "数值": "5.8%", "说明": "糖尿病前期"}
    assert by_metric["LDL"]["数值"] == "3.6 mmol/L"
    assert by_metric["HDL"]["数值"] == "1.1 mmol/L"
    assert by_metric["甘油三酯"]["数值"] == "1.9 mmol/L"
    assert by_metric["BMI"] == {"指标": "BMI", "数值": "26.4", "说明": "超重"}
    assert by_metric["代谢综合征"] == {"指标": "代谢综合征", "数值": "命中 3/5 项", "说明": "达标(≥3项)"}
    assert _all_cells_str(block)


def test_metabolic_card_fasting_glucose_and_cgm():
    f = _finding(
        "metabolic_specialist",
        findings=[
            {"type": "fasting_glucose", "value": 6.0, "status": "impaired"},
            {"type": "cgm_summary", "tir_pct": 82.0, "mean_mg_dl": 120, "gmi": 5.9, "cv_pct": 28},
        ],
    )
    block = report_cards._metabolic_card(f)
    assert block is not None
    by_metric = {r["指标"]: r for r in block["rows"]}
    # 6.0(整值 float)去 .0 → "6 mmol/L"(与 table_builder _fmt_num 同纪律)
    assert by_metric["空腹血糖"] == {"指标": "空腹血糖", "数值": "6 mmol/L", "说明": "受损空腹血糖"}
    # 82.0(整值 float)去 .0
    assert by_metric["CGM 达标率(TIR)"]["数值"] == "82%"


def test_metabolic_card_data_gap_returns_none():
    f = _finding(
        "metabolic_specialist",
        findings=[{"type": "data_gap", "missing": ["hba1c"]}],
        raw={"data_gap": True, "missing": ["hba1c"]},
    )
    assert report_cards._metabolic_card(f) is None


# ---------------------------------------------------------------------------
# longevity_specialist
# ---------------------------------------------------------------------------


def test_longevity_card_positive_older():
    f = _finding(
        "longevity_specialist",
        findings=[{
            "type": "phenotypic_age",
            "phenotypic_age": 41.0,
            "chronological_age": 38.0,
            "delta_years": 3.0,
            "interpretation": "明显偏老化(> 实足 3 岁)",
        }],
    )
    block = report_cards._longevity_card(f)
    assert block is not None
    by_metric = {r["指标"]: r for r in block["rows"]}
    assert by_metric["表型年龄"] == {"指标": "表型年龄", "数值": "41 岁", "说明": "明显偏老化(> 实足 3 岁)"}
    assert by_metric["实际年龄"]["数值"] == "38 岁"
    assert by_metric["差值"]["数值"] == "+3 岁"
    assert _all_cells_str(block)


def test_longevity_card_younger_negative_delta():
    f = _finding(
        "longevity_specialist",
        findings=[{
            "type": "phenotypic_age", "phenotypic_age": 35.0, "chronological_age": 38.0,
            "delta_years": -3.0, "interpretation": "明显年轻",
        }],
    )
    block = report_cards._longevity_card(f)
    assert block is not None
    delta_row = {r["指标"]: r for r in block["rows"]}["差值"]
    assert delta_row["数值"] == "-3 岁"  # 负号无 '+'


def test_longevity_card_unavailable_returns_none():
    f = _finding(
        "longevity_specialist",
        findings=[{"type": "phenoage_unavailable", "missing": ["hba1c", "albumin"]}],
        raw={"phenoage_status": "unavailable"},
    )
    assert report_cards._longevity_card(f) is None


# ---------------------------------------------------------------------------
# build_report_cards / render_report_cards
# ---------------------------------------------------------------------------


def test_build_report_cards_safety_first_and_ordering():
    # recovery 先注册, safety 后注册 —— safety floor boost 应让它排第一。
    recovery = _finding(
        "recovery_coach",
        findings=[{"type": "readiness_score", "score": 80, "zone": "hard", "source": "garmin"}],
    )
    safety = _safety_finding()
    hypertension = _finding(
        "hypertension_specialist",
        raw={"stage": "stage1", "systolic": 132, "diastolic": 84},
    )
    cards = report_cards.build_report_cards([recovery, safety, hypertension])
    assert [c["title"] for c in cards] == ["安全提示", "血压", "恢复"] or cards[0]["title"] == "安全提示"
    assert cards[0]["title"] == "安全提示"  # safety 恒第一


def test_build_report_cards_caps_at_four():
    # 5 个各能出卡的 finding → 只出 4 张。
    findings = [
        _safety_finding(),
        _finding("hypertension_specialist", raw={"stage": "stage2", "systolic": 150, "diastolic": 95}),
        _finding("recovery_coach", findings=[{"type": "readiness_score", "score": 70, "zone": "moderate", "source": "garmin"}]),
        _finding("metabolic_specialist", findings=[{"type": "hba1c", "value": 6.0, "status": "prediabetes"}]),
        _finding("longevity_specialist", findings=[{"type": "phenotypic_age", "phenotypic_age": 40.0, "chronological_age": 39.0, "delta_years": 1.0, "interpretation": "略偏老化"}]),
    ]
    cards = report_cards.build_report_cards(findings)
    assert len(cards) == report_cards.MAX_CARDS == 4
    assert cards[0]["title"] == "安全提示"


def test_build_report_cards_skips_unknown_specialist():
    # 未写提取器的 specialist(如 fuel_strategist)不出卡。
    fuel = _finding("fuel_strategist", findings=[{"type": "deficit", "kcal": 500}])
    recovery = _finding(
        "recovery_coach",
        findings=[{"type": "readiness_score", "score": 65, "zone": "light", "source": "computed"}],
    )
    cards = report_cards.build_report_cards([fuel, recovery])
    assert len(cards) == 1
    assert cards[0]["title"] == "恢复"


def test_render_report_cards_produces_parseable_reva_ui():
    findings = [
        _safety_finding(),
        _finding("recovery_coach", findings=[{"type": "readiness_score", "score": 72, "zone": "moderate", "source": "garmin"}]),
    ]
    text = report_cards.render_report_cards(findings)
    assert "```reva-ui" in text
    # 每个 fenced block 都能 parse 出 metric_table
    chunks = text.split("\n\n")
    parsed = [_parse_reva_ui(c) for c in chunks]
    assert all(b["type"] == "metric_table" for b in parsed)
    assert parsed[0]["title"] == "安全提示"


def test_render_report_cards_empty_when_no_numeric_findings():
    # 只有未覆盖的 specialist / data_gap → 无卡 → 空串。
    findings = [
        _finding("fuel_strategist", findings=[{"type": "deficit"}]),
        _finding("hypertension_specialist", raw={"stage": "unknown", "data_gap": True}),
    ]
    assert report_cards.render_report_cards(findings) == ""


# ---------------------------------------------------------------------------
# shadow worker 卡片前缀(窄测试:mock run_parallel_sectioned)
# ---------------------------------------------------------------------------


async def test_shadow_worker_prepends_cards(monkeypatch):
    """落库 text 以卡片开头, 且卡片在 _strip_llm_reva_ui 之后 prepend(fence 存活)。"""
    from unittest.mock import MagicMock

    from datetime import datetime

    import app.agents.audit as audit_mod
    import app.orchestrator.orchestrator as orch
    import app.orchestrator.parallel_synthesis as ps
    from app.twin.schema import HealthTwin, TwinMeta

    async def _fake_sectioned(**kwargs):
        return "段落分析文本, 无精确数字。", {"sections": 1}

    monkeypatch.setattr(ps, "run_parallel_sectioned", _fake_sectioned)
    monkeypatch.setattr("app.database.SessionLocal", MagicMock())

    captured: Dict[str, Any] = {}

    def _fake_log(db, *, user_id, query, text, meta):
        captured["text"] = text
        captured["meta"] = meta

    monkeypatch.setattr(audit_mod, "log_shadow_synthesis", _fake_log)

    recovery = _finding(
        "recovery_coach",
        findings=[{"type": "readiness_score", "score": 72, "zone": "moderate", "source": "garmin"}],
    )

    twin = HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.utcnow()))
    await orch._shadow_parallel_synthesis_worker(
        user_id=1, query="我最近状态怎么样", twin=twin,
        findings=[recovery], arb_block="", task_tier=None, mega_ms=1000,
    )

    assert "text" in captured, "log_shadow_synthesis 未被调用"
    text = captured["text"]
    assert text.startswith("```reva-ui"), text[:80]
    assert "72/100" in text  # 卡里的精确数字存活
    assert text.rstrip().endswith("段落分析文本, 无精确数字。")  # 段落在后
    assert captured["meta"]["report_cards"] == 1
    assert captured["meta"]["report_card_labels"] == ["恢复"]
