r"""GenUI-first 深报告数据卡 — 确定性把**数字型 specialist finding** 打成 reva-ui 卡片。

背景 (rank11 deep-report-genui milestone-1): 并行分段合成关思考 + 180 字上限让弱模型从
twin_blob **抄错数字**(说 HRV 44ms 真实 27ms)。根治 = 精确数值改由确定性卡片承载(零 LLM,
直接读 SpecialistFinding 的结构化字段), 段落只写定性结论、不复述具体数字。卡准 + 段落快。

铁律 (R4): 本模块每一个单元格都来自 finding 的**确定性字段**(summary / findings dict / raw),
**永不**来自任何 LLM 文本。数值缺失 → 跳过该行/该卡, 绝不填 0 或编造(诚实空值)。请用
`grep -n "llm\|LLM\|_call_llm" report_cards.py` 自证(无命中)。

设计:纯函数(无 DB / HTTP / LLM), 复用 `services/genui/table_builder` 的 metric_table 契约
(`_make_block` fail-open: 列 2-4、行 1-12、每格 str、任一约束不满足返回 None)。排序键复用
`parallel_synthesis.finding_severity_rank`(safety 卡恒第一, +10 floor boost), 总卡数 cap≤4。

覆盖的 specialist(只对亲自 grep 核实过字段名的 finding 形状写提取器;核实不了 → 不出卡):
  - safety_guardian        —— specialists.py SafetyGuardianSpecialist.run
  - hypertension_specialist —— agents/chronic_specialists/hypertension.py
  - recovery_coach         —— agents/recovery_coach/coach.py
  - metabolic_specialist   —— agents/chronic_specialists/metabolic.py
  - longevity_specialist   —— agents/longevity_specialist/specialist.py
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.orchestrator.parallel_synthesis import finding_severity_rank
from app.orchestrator.schema import SpecialistFinding
from app.services.genui.table_builder import _make_block, render_metric_table_block

# 总卡数上限:超出的低优先 finding 不出卡, 靠段落叙事(防刷屏)。
MAX_CARDS = 4

# 通用「指标 | 数值 | 说明」三列(多数数字卡共用)。
_METRIC_COLS: List[Tuple[str, str]] = [("指标", "指标"), ("数值", "数值"), ("说明", "说明")]


# ---------------------------------------------------------------------------
# 纯工具
# ---------------------------------------------------------------------------


def _num(value: Any) -> Optional[str]:
    """标量数值 → 展示串(整值 float 去 '.0': 350.0→'350')。None/空 → None(跳过, 不落占位)。"""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    return text or None


def _find_item(finding: SpecialistFinding, type_name: str) -> Optional[Dict[str, Any]]:
    """取 finding.findings 里第一个 type==type_name 的 dict(无 → None)。"""
    for item in getattr(finding, "findings", None) or []:
        if isinstance(item, dict) and item.get("type") == type_name:
            return item
    return None


# ---------------------------------------------------------------------------
# safety_guardian
# ---------------------------------------------------------------------------

# 只把 critical/high 级告警放进卡(medium 及以下靠段落叙事, 不占卡面)。severity_label 存
# 中文(label_zh: 紧急/警告), 同时容忍英文 label 以防上游形状变。
_SAFETY_INCLUDE = {"critical", "紧急", "high", "警告"}
# 卡内行严重优先排序的 fallback(finding item 恒带 int severity, 缺失时按 label 兜底)。
_SEVERITY_INT = {"紧急": 4, "critical": 4, "警告": 3, "high": 3, "注意": 2, "关注": 1, "提示": 0}


def _safety_sev(item: Dict[str, Any]) -> int:
    sev = item.get("severity")
    if isinstance(sev, (int, float)):
        return int(sev)
    return _SEVERITY_INT.get(str(item.get("severity_label") or "").strip(), 0)


def _safety_card(finding: SpecialistFinding) -> Optional[dict]:
    """安全提示卡:每条 critical/high 告警一行 = 告警(title) | 级别(label_zh) | 处置(action)。"""
    items = [it for it in (getattr(finding, "findings", None) or []) if isinstance(it, dict)]
    items.sort(key=_safety_sev, reverse=True)  # 严重优先(截断时 critical 存活)
    rows: List[Dict[str, str]] = []
    for it in items:
        label = str(it.get("severity_label") or it.get("severity") or "").strip()
        if label not in _SAFETY_INCLUDE:
            continue
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        rows.append({"告警": title, "级别": label, "处置": str(it.get("action") or "").strip()})
    columns = [("告警", "告警"), ("级别", "级别"), ("处置", "处置")]
    return _make_block("安全提示", columns, rows)


# ---------------------------------------------------------------------------
# hypertension_specialist
# ---------------------------------------------------------------------------

# 与 hypertension.py 的 stage_zh 对齐(单一真源在那边;此处是卡片投影)。
_BP_STAGE_ZH = {
    "normal": "正常", "elevated": "血压偏高", "stage1": "一级高血压",
    "stage2": "二级高血压", "severe": "血压严重升高", "unknown": "未测量",
}


def _hypertension_card(finding: SpecialistFinding) -> Optional[dict]:
    """血压卡:一行 = 血压 | {sys}/{dia} mmHg | stage 中文。data_gap / 无读数 → 不出卡。"""
    raw = getattr(finding, "raw", None) or {}
    if raw.get("data_gap"):
        return None
    stage = str(raw.get("stage") or "").strip()
    if stage in ("", "unknown"):
        return None
    sys_v, dia_v = raw.get("systolic"), raw.get("diastolic")
    if sys_v is None or dia_v is None:
        return None
    rows = [{"指标": "血压", "数值": f"{sys_v}/{dia_v} mmHg", "说明": _BP_STAGE_ZH.get(stage, stage)}]
    return _make_block("血压", _METRIC_COLS, rows)


# ---------------------------------------------------------------------------
# recovery_coach
# ---------------------------------------------------------------------------

# 与 coach.py 的 summary zone_zh 对齐。
_ZONE_ZH = {"hard": "状态极佳", "moderate": "状态良好", "light": "状态一般", "rest": "恢复不足"}


def _recovery_card(finding: SpecialistFinding) -> Optional[dict]:
    """恢复卡:一行 = Readiness | {score}/100 | zone 中文(+ Garmin官方)。zone=unknown → 不出卡。"""
    item = _find_item(finding, "readiness_score")  # 实际 type 是 readiness_score(非 spec 说的 readiness)
    if item is None:
        return None
    zone = str(item.get("zone") or "").strip()
    if zone in ("", "unknown"):
        return None
    score = _num(item.get("score"))
    if score is None:
        return None
    note = _ZONE_ZH.get(zone, zone)
    if str(item.get("source") or "") == "garmin":
        note += " · Garmin官方"
    rows = [{"指标": "Readiness", "数值": f"{score}/100", "说明": note}]
    return _make_block("恢复", _METRIC_COLS, rows)


# ---------------------------------------------------------------------------
# metabolic_specialist
# ---------------------------------------------------------------------------

# status → 中文(与 metabolic.py 的 _hba1c_status / _glucose_status 分级对齐)。
_HBA1C_ZH = {"diabetes": "糖尿病范围", "prediabetes": "糖尿病前期", "normal": "正常"}
_GLUCOSE_ZH = {"diabetes": "糖尿病范围", "impaired": "受损空腹血糖", "normal": "正常"}


def _metabolic_card(finding: SpecialistFinding) -> Optional[dict]:
    """代谢卡:HbA1c / 空腹血糖 / 血脂三项 / BMI / CGM TIR / 代谢综合征命中数, 逐条来自结构化字段。"""
    raw = getattr(finding, "raw", None) or {}
    if raw.get("data_gap"):
        return None
    rows: List[Dict[str, str]] = []
    for it in getattr(finding, "findings", None) or []:
        if not isinstance(it, dict):
            continue
        t = it.get("type")
        if t == "hba1c":
            v = _num(it.get("value"))
            if v:
                rows.append({"指标": "HbA1c", "数值": f"{v}%", "说明": _HBA1C_ZH.get(str(it.get("status")), "")})
        elif t == "fasting_glucose":
            v = _num(it.get("value"))
            if v:
                rows.append({"指标": "空腹血糖", "数值": f"{v} mmol/L", "说明": _GLUCOSE_ZH.get(str(it.get("status")), "")})
        elif t == "lipid_panel":
            for key, label in (("ldl", "LDL"), ("hdl", "HDL"), ("triglycerides", "甘油三酯")):
                v = _num(it.get(key))
                if v:
                    rows.append({"指标": label, "数值": f"{v} mmol/L", "说明": ""})
        elif t == "cgm_summary":
            v = _num(it.get("tir_pct"))
            if v:
                rows.append({"指标": "CGM 达标率(TIR)", "数值": f"{v}%", "说明": ""})
        elif t == "body_composition":
            v = _num(it.get("bmi"))
            if v:
                rows.append({"指标": "BMI", "数值": v, "说明": str(it.get("bmi_category") or "")})
        elif t == "metabolic_syndrome":
            hit = it.get("criteria_hit")
            if hit is not None:
                rows.append({
                    "指标": "代谢综合征",
                    "数值": f"命中 {hit}/5 项",
                    "说明": "达标(≥3项)" if it.get("is_metabolic_syndrome") else "未达标",
                })
    return _make_block("代谢指标", _METRIC_COLS, rows)


# ---------------------------------------------------------------------------
# longevity_specialist
# ---------------------------------------------------------------------------


def _longevity_card(finding: SpecialistFinding) -> Optional[dict]:
    """表型年龄卡:表型年龄 / 实际年龄 / 差值(interpretation 为确定性文案)。unavailable → 不出卡。"""
    item = _find_item(finding, "phenotypic_age")
    if item is None:
        return None
    pa = _num(item.get("phenotypic_age"))
    if pa is None:
        return None
    rows: List[Dict[str, str]] = [
        {"指标": "表型年龄", "数值": f"{pa} 岁", "说明": str(item.get("interpretation") or "")}
    ]
    chrono = _num(item.get("chronological_age"))
    if chrono is not None:
        rows.append({"指标": "实际年龄", "数值": f"{chrono} 岁", "说明": ""})
    delta = item.get("delta_years")
    dnum = _num(delta)
    if dnum is not None:
        sign = "+" if isinstance(delta, (int, float)) and delta > 0 else ""
        rows.append({"指标": "差值", "数值": f"{sign}{dnum} 岁", "说明": "正=偏老 / 负=偏年轻"})
    return _make_block("表型年龄", _METRIC_COLS, rows)


# ---------------------------------------------------------------------------
# 分发 + 聚合
# ---------------------------------------------------------------------------

_EXTRACTORS = {
    "safety_guardian": _safety_card,
    "hypertension_specialist": _hypertension_card,
    "recovery_coach": _recovery_card,
    "metabolic_specialist": _metabolic_card,
    "longevity_specialist": _longevity_card,
}


def build_report_cards(findings: List[SpecialistFinding]) -> List[dict]:
    """对数字型 specialist 各产一张 metric_table block, 按严重度排序(safety 恒第一), cap≤4。

    - 排序键 = `finding_severity_rank`(safety +10 boost), 降序; 同级保持原注册顺序(稳定)。
    - 无提取器 / 提取器返回 None(数据缺口/缺字段)→ 跳过, 不占卡面。
    """
    ranked = sorted(
        enumerate(findings or []),
        key=lambda pair: (-finding_severity_rank(pair[1]), pair[0]),
    )
    cards: List[dict] = []
    for _, finding in ranked:
        extractor = _EXTRACTORS.get((getattr(finding, "specialist_name", "") or "").strip().lower())
        if extractor is None:
            continue
        block = extractor(finding)
        if block is None:
            continue
        cards.append(block)
        if len(cards) >= MAX_CARDS:
            break
    return cards


def render_report_cards(findings: List[SpecialistFinding]) -> str:
    """build + 逐张渲染 reva-ui fenced 文本 + '\\n\\n' 拼接。无卡 → ""(调用方据此不 prepend)。"""
    blocks = build_report_cards(findings)
    if not blocks:
        return ""
    return "\n\n".join(render_metric_table_block(b) for b in blocks)
