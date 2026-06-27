# -*- coding: utf-8 -*-
"""因果记忆(RFC 方向二)回归 —— 含**诚实地板**护栏。

钉:事件后指标变化要穿过 [样本门 + 匹配对照(DiD) + 回归均值折减 + 个体内噪声带 + 实用显著]
才出记忆条;方向(改善/走低)按**净效应**;文案严格 observational;端点鉴权。

核心护栏 = KILL-TEST:1 天 vs 1 天的纯噪声**绝不**出"改善/走低"条。地板缺失则此测必红。
"""
from app.services.causal_memory import notes_from_impact


def _imp(before, after, *, nb=20, na=None, noise=None, baseline=None,
         title="补充维D", window=30):
    """构造 get_event_impact 形状的 impact 字典(把 samples 注进 before/after)。"""
    na = nb if na is None else na
    b = dict(before)
    b["samples"] = nb
    a = dict(after)
    a["samples"] = na
    return {
        "title": title, "window_days": window,
        "before": b, "after": a,
        "noise": noise or {}, "baseline": baseline or {},
    }


# ── 方向语义 ──────────────────────────────────────────────────────────────────
def test_net_effect_note_direction():
    # HRV 升(越高越好)→ 改善;RHR 升(越低越好)→ 走低。低噪声 + 无事件前趋势 → 穿过地板。
    notes = notes_from_impact(_imp(
        before={"hrv": 40, "rhr": 60}, after={"hrv": 52, "rhr": 70},
        noise={"hrv": 3.0, "rhr": 2.0}, baseline={"hrv": 40, "rhr": 60}))
    by = {n["metric"]: n for n in notes}
    assert by["hrv"]["direction"] == "改善"
    assert by["rhr"]["direction"] == "走低"
    assert "相关非因果" in by["hrv"]["text"] and "补充维D" in by["hrv"]["text"]
    assert by["hrv"]["evidence_tier"] == "observational"


# ── KILL-TEST:纯噪声 1 天 vs 1 天必须静默 ─────────────────────────────────────
def test_kill_single_day_pure_noise_emits_nothing():
    """地板存在性测试:每侧只有 1 天,无论摆动多大、给不给 noise/baseline,都不出条。"""
    notes = notes_from_impact(_imp(
        before={"hrv": 45, "rhr": 60, "sleep_score": 70, "deep_sleep_min": 90, "steps": 8000},
        after={"hrv": 70, "rhr": 45, "sleep_score": 95, "deep_sleep_min": 130, "steps": 14000},
        nb=1, na=1,
        noise={"hrv": 1.0, "rhr": 1.0, "sleep_score": 1.0, "deep_sleep_min": 1.0, "steps": 1.0},
        baseline={"hrv": 45, "rhr": 60, "sleep_score": 70, "deep_sleep_min": 90, "steps": 8000}))
    assert notes == []


def test_kill_holds_without_noise_or_baseline_keys():
    # 即便 impact 完全没带 noise/baseline,1天vs1天仍被样本门拦下(fail-closed)。
    impact = {"title": "聚餐", "window_days": 30,
              "before": {"hrv": 40, "samples": 1}, "after": {"hrv": 80, "samples": 1}}
    assert notes_from_impact(impact) == []


# ── 匹配对照窗口:扣除事件前既有趋势(difference-in-differences) ─────────────────
def test_control_window_removes_pre_existing_trend():
    """HRV 在事件后 50→60(+20%),但事件前对照窗 40→50 已同速上升 → 净效应≈0 → 不出条。"""
    notes = notes_from_impact(_imp(
        before={"hrv": 50}, after={"hrv": 60},
        noise={"hrv": 2.0}, baseline={"hrv": 40}))
    assert notes == []


# ── 个体内噪声带:变化须超过个体内变异 ─────────────────────────────────────────
def test_noise_band_suppresses_change_within_variability():
    # 同样 +12% 的 HRV 变化:高日间 SD(=12)→ 落在噪声带内 → 不出条。
    notes = notes_from_impact(_imp(
        before={"hrv": 50}, after={"hrv": 56},
        noise={"hrv": 12.0}, baseline={"hrv": 50}))
    assert notes == []


def test_same_change_surfaces_when_variability_low():
    # 对照:同 +12% 变化,低 SD(=3)→ 超过噪声带 → 出条(噪声带是真正的判别量)。
    notes = notes_from_impact(_imp(
        before={"hrv": 50}, after={"hrv": 56},
        noise={"hrv": 3.0}, baseline={"hrv": 50}))
    assert len(notes) == 1 and notes[0]["metric"] == "hrv" and notes[0]["direction"] == "改善"


# ── 实用显著地板:统计上能过但相对变化太小 → 不出条 ────────────────────────────
def test_practical_significance_floor():
    # 步数 8000→8100(+1.25%),低噪声足以统计显著,但 <5% 实用门 → 不出条。
    notes = notes_from_impact(_imp(
        before={"steps": 8000}, after={"steps": 8100}, nb=30, na=30,
        noise={"steps": 10.0}, baseline={"steps": 8000}))
    assert notes == []


# ── 正常合法效应:穿过全部地板 → 出条,文案 observational ───────────────────────
def test_legit_effect_survives_floor():
    notes = notes_from_impact(_imp(
        before={"hrv": 50}, after={"hrv": 62}, nb=25, na=25,
        noise={"hrv": 3.0}, baseline={"hrv": 50}))
    assert len(notes) == 1
    n = notes[0]
    assert n["metric"] == "hrv" and n["direction"] == "改善"
    assert n["evidence_tier"] == "observational"
    assert "相关非因果" in n["text"] and "数据不足以判断因果" in n["text"]


# ── 噪声带兜底:无日间 SD 时退回人群 RCV%(保守) ──────────────────────────────
def test_rcv_fallback_when_sd_absent():
    """某指标窗口内 <2 天有数据 → sd=None;退回 RCV% 兜底带(对 wearable 是保守通用值)。"""
    # 40→60(+50% 原始):净效应 16 > RCV 带(≈0.277×40≈11.1)→ 出条。
    big = notes_from_impact(_imp(
        before={"hrv": 40}, after={"hrv": 60},
        noise={"hrv": None}, baseline={"hrv": 40}))
    assert len(big) == 1 and big[0]["direction"] == "改善"
    # 40→48(+20% 原始):净效应 6.4 < RCV 带 → 兜底比 SD 带更保守, 不出条。
    small = notes_from_impact(_imp(
        before={"hrv": 40}, after={"hrv": 48},
        noise={"hrv": None}, baseline={"hrv": 40}))
    assert small == []


# ── 缺值/零基线短路(地板之前) ───────────────────────────────────────────────
def test_missing_or_zero_skipped():
    assert notes_from_impact(_imp(before={"hrv": None}, after={"hrv": 50})) == []
    assert notes_from_impact(_imp(before={"hrv": 0}, after={"hrv": 50})) == []
    assert notes_from_impact(_imp(before={}, after={})) == []


# ── 处方/激素门控:与两个 N-of-1 估计器共用同一 clinician-gate 单一事实源 ──────────
def test_clinician_gated_metric_never_attributed(monkeypatch):
    """临时把一个处方指标(LDL)塞进 metric 表 —— 即便数据足以穿过其它地板,也绝不出方向条。

    复用 intervention_priors.is_clinician_gated_metric(单一事实源,防与估计器漂移)。
    """
    from app.services import causal_memory
    monkeypatch.setitem(causal_memory._METRIC_META, "ldl", ("LDL", False))
    notes = notes_from_impact(_imp(
        before={"hrv": 50, "ldl": 120}, after={"hrv": 62, "ldl": 100},
        noise={"hrv": 3.0, "ldl": 2.0}, baseline={"hrv": 50, "ldl": 120}))
    metrics = {n["metric"] for n in notes}
    assert "ldl" not in metrics      # 处方指标被门控掉
    assert "hrv" in metrics          # 非处方指标正常穿过(对照)


def test_clinician_gate_classifies_our_metrics():
    """文档化:5 个 wearable 指标均非处方/激素 → 门控对现存指标是 no-op(未来加才生效)。"""
    from app.services.personal_models.intervention_priors import is_clinician_gated_metric
    for m in ("hrv", "rhr", "sleep_score", "deep_sleep_min", "steps"):
        assert is_clinician_gated_metric(m) is False
    assert is_clinician_gated_metric("ldl") is True


# ── derive + 端点 ─────────────────────────────────────────────────────────────
def test_derive_empty_when_no_events(db):
    from app.services.causal_memory import derive_causal_notes
    out = derive_causal_notes(db, user_id=99999)
    assert out["notes"] == [] and out["evidence_tier"] == "observational"


def test_endpoint_requires_auth(client):
    r = client.get("/api/v1/personal-outcome/me/causal-notes")
    assert r.status_code in (401, 403)
