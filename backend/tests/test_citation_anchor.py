"""
test_citation_anchor — P1 数字锚定核验(shadow)单测。

覆盖:
  - build_fact_index: 拍平结构化 twin(含嵌套逐夜序列/异常项),排除 schema 默认常量
  - extract_personal_numeric_claims: 个人语境正例 / 通用知识负例 / 泛化数值不误抓 /
    日期不当数值 / 单位必需
  - anchor_report: 正例(数值在 twin → anchored)/ 负例(不在 → unanchored)/
    空 twin 安全 / total=0 → ratio=1.0
  - shadow 接线 helper: 异常吞点计数暴露(不静默),开关关时跳过

fixtures 用对比评测(evals/comparative)里**真实小巴回答**的 verbatim 片段,
确保抽取逻辑对真实产出稳健(而非只对合成文本)。
"""

from datetime import datetime

from app.services.citation_anchor import (
    anchor_report,
    build_fact_index,
    extract_personal_numeric_claims,
)
from app.twin.schema import HealthTwin, TwinMeta


# ─────────────────────────── 真实小巴回答片段(verbatim) ────────────────

# state_sleep_hrv_readout(个人恢复状态,大量个人日读数,markdown 表)。
XIAOBA_SLEEP_HRV = """## 恢复状态评估：近两天明显下滑 ⚠️

综合你最近 8 天的睡眠、HRV、身体电量和静息心率数据，整体恢复状态**从 7/3 起持续走低**，昨晚（7/5）达到最低点。

### 📊 HRV 趋势（7 日均值 ~47ms）

| 日期 | HRV | 信号 |
|------|-----|------|
| 6/29 | 49.7ms | 正常 |
| 7/4 | **33.3ms** | 🔴 骤降 |
| 7/5 | **42.0ms** | 🟡 仍偏低 |

昨晚（7/5）只睡了 3.3 小时。7/5 血氧均值 92.0% 已触及低氧阈值。
REM 仅 13 分钟（正常应 90-120min），认知恢复严重不足。"""

# safety_mthfr_folate_dose(个人化验 + 参考范围混排)。末句刻意保留个人叙述里带单位的
# HCY 8.0 µmol/L(强个人指代「你的」压过同句「参考范围」),验证 strong-personal override。
XIAOBA_MTHFR = """理解你想要一个直接数字，但我必须先把你的实际数据摆出来：

## 你当前的化验结果（2026-06-11）

| 指标 | 数值 | 参考范围 | 状态 |
|------|------|----------|------|
| 同型半胱氨酸 (HCY) | **8.0** µmol/L | 参考范围 0-15 | ✅ 正常 |
| 叶酸 | **26.9** ng/mL | 参考 3.1-20.5 | ⚠️ 已超标 |

你的 HCY 8.0 µmol/L 完全正常（参考范围 0-15），MTHFR TT 型已被当前方案管住。"""

# fact_gastric_ulcer_stages(纯通用知识,零个人指代 → 零断言)。
XIAOBA_GENERIC = """## 胃溃疡内镜分期（Sakita-Miwa 分期法）

胃溃疡在内镜下分为 3 个阶段、6 个亚期：

| 亚期 | 内镜特征 | 典型愈合周期 |
|------|---------|-------------|
| A1（急性期） | 溃疡边缘明显水肿 | 规范治疗 2-4 周 → 进入 H 期 |

参考范围内 pH 4.0-4.5 属正常胃酸。"""


def _twin() -> HealthTwin:
    return HealthTwin(meta=TwinMeta(user_id=1, generated_at=datetime.now()))


# ─────────────────────────── build_fact_index ──────────────────────────


def test_fact_index_flattens_scalar_partitions():
    t = _twin()
    t.physiological.hrv_latest = 42.0
    t.physiological.resting_hr = 52
    t.physiological.spo2_avg = 92.0
    t.body_composition.weight_kg = 73.1
    idx = build_fact_index(t)
    assert 42.0 in idx
    assert 52.0 in idx
    assert 92.0 in idx
    assert 73.1 in idx
    # 类目标签跟到位
    cats = {c for triples in idx.values() for (c, _k, _d) in triples}
    assert "生理" in cats
    assert "身体成分" in cats


def test_fact_index_walks_nested_series_with_dates():
    t = _twin()
    t.physiological.hrv_nightly_series = [
        {"date": "2026-07-04", "hrv_avg": 33.3, "count": 74},
        {"date": "2026-07-05", "hrv_avg": 42.0, "count": 39},
    ]
    idx = build_fact_index(t)
    assert 33.3 in idx
    assert 42.0 in idx
    # count 是噪音键,不进索引
    assert 74.0 not in idx
    assert 39.0 not in idx
    # 逐夜 hrv_avg 回填了每条自带的 date
    dates = {d for (_c, _k, d) in idx[33.3]}
    assert "2026-07-04" in dates


def test_fact_index_walks_flagged_abnormal():
    t = _twin()
    t.labs.flagged_abnormal = [
        {"item_name": "叶酸", "value": 26.9, "unit": "ng/mL", "exam_date": "2026-06-11"},
    ]
    idx = build_fact_index(t)
    assert 26.9 in idx


def test_fact_index_excludes_schema_default_constants():
    """water_goal_ml / taking_window_days 是 schema 默认常量,不是采集数据,
    不该进索引(否则答案「建议每天 2000ml」误锚定)。"""
    t = _twin()
    # 全默认:water_goal_ml=2000, taking_window_days=14
    idx = build_fact_index(t)
    assert 2000.0 not in idx
    assert 14.0 not in idx


def test_fact_index_empty_twin_safe():
    idx = build_fact_index(_twin())
    # 空 twin 不报错;可能只剩 0.0 之类默认零值
    assert isinstance(idx, dict)


# ─────────────────── extract_personal_numeric_claims ────────────────────


def test_extract_personal_readout_real_answer():
    claims = extract_personal_numeric_claims(XIAOBA_SLEEP_HRV)
    values = {c["value"] for c in claims}
    # 个人日读数被抓(含 92% 血氧 —— "已触及低氧阈值" 里的「阈值」不当泛化词误杀)
    assert 42.0 in values
    assert 33.3 in values
    assert 3.3 in values
    assert 92.0 in values
    assert 49.7 in values
    # 泛化对照值(REM 正常应 90-120min)不抓
    assert 90.0 not in values
    assert 120.0 not in values


def test_extract_ignores_generic_knowledge_answer():
    """纯通用知识回答(零个人指代)→ 零个人数值断言。"""
    claims = extract_personal_numeric_claims(XIAOBA_GENERIC)
    assert claims == []


def test_extract_excludes_reference_ranges_but_keeps_personal():
    """同一数值 8.0:参考范围单元格里排除,个人叙述句里保留。"""
    claims = extract_personal_numeric_claims(XIAOBA_MTHFR)
    values = [c["value"] for c in claims]
    # 「你的 HCY 8.0」这句是个人叙述 → 8.0 至少出现一次
    assert 8.0 in values
    # 26.9 在「参考范围」同格里(泛化词命中,无强个人指代)→ 不抓
    # (注:µmol/L 单位识别正常,排除来自泛化而非漏识别)
    assert 26.9 not in values


def test_extract_dates_not_treated_as_numeric_claims():
    text = "你 7/5 的 HRV 42.0ms 偏低,2026-06-11 的化验正常。"
    claims = extract_personal_numeric_claims(text)
    values = {c["value"] for c in claims}
    assert 42.0 in values
    # 日期碎片不当断言
    assert 7.0 not in values
    assert 5.0 not in values
    assert 6.0 not in values
    assert 11.0 not in values
    assert 2026.0 not in values


def test_extract_requires_unit():
    """裸数字(无健康单位)shadow 阶段不抓(避免误报)。"""
    text = "你的睡眠分 42,身体电量 7。"  # 无单位
    claims = extract_personal_numeric_claims(text)
    assert claims == []
    # 有单位则抓
    text2 = "你的 HRV 42ms。"
    assert extract_personal_numeric_claims(text2)


def test_extract_micro_sign_and_greek_mu_both_match():
    """µ(MICRO SIGN) 与 μ(GREEK MU) 两个 codepoint 都要能匹配 µmol/L。"""
    assert extract_personal_numeric_claims("你的尿酸 420 µmol/L")  # micro sign
    assert extract_personal_numeric_claims("你的尿酸 420 μmol/L")  # greek mu


def test_extract_empty_text_safe():
    assert extract_personal_numeric_claims("") == []
    assert extract_personal_numeric_claims(None) == []  # type: ignore[arg-type]


def test_extract_over_alarm_generic_values_never_counted():
    """对抗(过杀方向): 通用知识/建议量/参考范围数值绝不被当个人断言,
    否则 shadow 会把满是通用数字的答案误报成低锚定。"""
    for g in (
        "每天建议摄入维C 100mg,钙 1000mg。",       # 建议量
        "成人正常心率 60-100bpm,血氧 95-100%。",   # 正常(范围)
        "维D 参考范围 30-100 ng/mL。",             # 参考范围
        "BMI 18.5-24 属正常范围。",                # 正常范围
        "一天喝水 2000ml 左右比较合适。",           # 无个人指代
    ):
        assert extract_personal_numeric_claims(g) == [], g


# ─────────────────────────── anchor_report ─────────────────────────────


def test_anchor_report_positive_value_in_twin():
    t = _twin()
    t.physiological.hrv_latest = 42.0
    t.physiological.spo2_avg = 92.0
    t.physiological.sleep_duration_h_latest = 3.3
    text = "你今天 HRV 42.0ms,血氧 92.0%,睡眠 3.3 小时。"
    rep = anchor_report(text, t)
    assert rep["total"] == 3
    assert rep["anchored"] == 3
    assert rep["unanchored"] == []
    assert rep["anchored_ratio"] == 1.0


def test_anchor_report_negative_value_not_in_twin():
    t = _twin()
    t.physiological.hrv_latest = 42.0
    # 答案里编造一个 twin 里不存在的 HRV
    text = "你今天 HRV 42.0ms,昨天 HRV 88.8ms。"
    rep = anchor_report(text, t)
    assert rep["total"] == 2
    assert rep["anchored"] == 1
    assert len(rep["unanchored"]) == 1
    assert rep["unanchored"][0]["value"] == 88.8
    assert rep["anchored_ratio"] == 0.5


def test_anchor_report_tolerance_relative_and_absolute():
    t = _twin()
    t.body_composition.weight_kg = 73.069  # twin 存原始精度
    t.physiological.sleep_duration_h_latest = 3.3
    # 答案四舍五入:73.1kg(相对 1% 内),3.3h(末位)
    rep = anchor_report("你体重 73.1kg,睡眠 3.3 小时。", t)
    assert rep["anchored"] == 2
    assert rep["anchored_ratio"] == 1.0


def test_anchor_report_empty_twin_all_unanchored():
    t = _twin()
    text = "你今天 HRV 42.0ms,血氧 92.0%。"
    rep = anchor_report(text, t)
    assert rep["total"] == 2
    assert rep["anchored"] == 0
    assert len(rep["unanchored"]) == 2
    assert rep["anchored_ratio"] == 0.0


def test_anchor_report_under_alarm_fabrication_surfaces():
    """对抗(漏杀方向): twin 里没有的个人数值(编造/未记录)必须落到 unanchored,
    否则 fabrication 被静默放过 —— 这正是盲评裁判纠结的点。"""
    t = _twin()
    t.physiological.hrv_latest = 42.0
    t.physiological.spo2_avg = 92.0
    # 编造一个昨天 HRV + 一个 twin 里根本没有的血糖
    rep = anchor_report("你今天 HRV 42.0ms,昨天 HRV 61.5ms,血糖 7.8mmol/L。", t)
    unv = {u["value"] for u in rep["unanchored"]}
    assert 61.5 in unv
    assert 7.8 in unv
    assert 42.0 not in unv  # 真值仍锚定
    assert rep["anchored"] == 1


def test_anchor_report_no_personal_claims_ratio_one():
    """没有可核验的个人断言 → ratio=1.0(无断言=不扣分),不是 0/0 崩。"""
    t = _twin()
    rep = anchor_report(XIAOBA_GENERIC, t)
    assert rep["total"] == 0
    assert rep["anchored"] == 0
    assert rep["anchored_ratio"] == 1.0


def test_anchor_report_real_answer_against_matching_twin():
    """真实小巴回答 + 对得上的 twin → 大部分个人读数 anchored。"""
    t = _twin()
    p = t.physiological
    p.hrv_latest = 42.0
    p.spo2_avg = 92.0
    p.sleep_duration_h_latest = 3.3
    p.hrv_nightly_series = [
        {"date": "2026-06-29", "hrv_avg": 49.7, "count": 90},
        {"date": "2026-07-04", "hrv_avg": 33.3, "count": 74},
        {"date": "2026-07-05", "hrv_avg": 42.0, "count": 39},
    ]
    rep = anchor_report(XIAOBA_SLEEP_HRV, t)
    assert rep["total"] > 0
    # 42.0 / 33.3 / 49.7 / 92.0 / 3.3 都在 twin → anchored 应占多数
    assert rep["anchored"] >= 5
    assert rep["anchored_ratio"] > 0.5


# ─────────────────────── shadow 接线 helper ────────────────────────────


def test_shadow_helper_disabled_returns_none(monkeypatch):
    from app.services import agent_executor as ae
    from app.config import settings

    monkeypatch.setattr(settings, "citation_anchor_shadow", False, raising=False)
    assert ae._citation_anchor_shadow_meta(None, 1, "你的 HRV 42ms") is None


def test_shadow_helper_empty_answer_returns_none(monkeypatch):
    from app.services import agent_executor as ae
    from app.config import settings

    monkeypatch.setattr(settings, "citation_anchor_shadow", True, raising=False)
    assert ae._citation_anchor_shadow_meta(None, 1, "") is None
    assert ae._citation_anchor_shadow_meta(None, 1, "   ") is None


def test_shadow_helper_swallows_exception_and_counts(monkeypatch):
    """观测层绝不打死回合:build_twin 抛异常时吞掉,但 failed_count 暴露(非静默)。"""
    from app.services import agent_executor as ae
    from app.config import settings

    monkeypatch.setattr(settings, "citation_anchor_shadow", True, raising=False)

    def _boom(*a, **k):
        raise RuntimeError("twin build blew up")

    monkeypatch.setattr("app.twin.builder.build_twin", _boom)
    out = ae._citation_anchor_shadow_meta(object(), 1, "你的 HRV 42ms")
    assert out is not None
    assert out["failed_count"] == 1
    assert out["anchored_ratio"] is None
    assert out["total"] == 0


def test_shadow_helper_happy_path(monkeypatch):
    """开关开 + twin 可锚定 → 返回 additive 摘要,failed_count=0。"""
    from app.services import agent_executor as ae
    from app.config import settings

    monkeypatch.setattr(settings, "citation_anchor_shadow", True, raising=False)

    t = _twin()
    t.physiological.hrv_latest = 42.0
    monkeypatch.setattr("app.twin.builder.build_twin", lambda *a, **k: t)

    out = ae._citation_anchor_shadow_meta(object(), 1, "你今天 HRV 42.0ms 偏低。")
    assert out is not None
    assert out["failed_count"] == 0
    assert out["total"] == 1
    assert out["anchored"] == 1
    assert out["anchored_ratio"] == 1.0
    assert out["unanchored_count"] == 0
