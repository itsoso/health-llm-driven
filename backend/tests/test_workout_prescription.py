"""cut A:锻炼处方化 —— movement_coach 处方接进调度块 + 三端透传契约。"""
from app.services.day_schedule_service import (
    _maybe_workout_item, schedule_from_medications, workout_prescription, _day_context,
)


class _Profile:
    def __init__(self, **kw):
        self.workout_pref_window = kw.get("workout_pref_window", "evening")
        self.workout_target_minutes = kw.get("workout_target_minutes")
        self.usual_wake_time = "07:00"
        self.usual_sleep_time = "22:30"
        self.work_start_time = "09:00"
        self.work_end_time = "18:00"


RX_MOD = {"intensity": "moderate", "type": "aerobic_z2", "duration_min": 50,
          "rpe": "6-7", "guidance": "Z2-Z3 有氧 45-60min", "gene_note": "ACTN3 XX:增加 Z2"}
RX_REST = {"intensity": "rest", "type": "recovery", "guidance": "过载,强制休息 2-3 天"}


def test_block_carries_prescription_and_label():
    ctx = _day_context(_Profile())
    it = _maybe_workout_item(_Profile(), ctx, RX_MOD)
    assert it is not None and it.id == "workout:today"
    assert it.prescription == RX_MOD
    assert "Z2 有氧" in it.title          # 处方简短串
    assert it.fixed_time                   # 排上了具体时点


def test_rest_prescription_rejected_as_recovery():
    ctx = _day_context(_Profile())
    it = _maybe_workout_item(_Profile(), ctx, RX_REST)
    assert it is not None and it.hard_forbidden is True   # 走拒排通道 → 「今日恢复」
    assert it.forbidden_reason == RX_REST["guidance"]
    assert it.prescription == RX_REST


def test_no_pref_no_block():
    ctx = _day_context(_Profile(workout_pref_window=None))
    assert _maybe_workout_item(_Profile(workout_pref_window=None), ctx, RX_MOD) is None


def test_prescription_flows_into_scheduled_dict():
    out = schedule_from_medications([], profile=_Profile(), workout_rx=RX_MOD)
    w = next((s for s in out["scheduled"] if s["id"] == "workout:today"), None)
    assert w is not None
    assert w["prescription"]["intensity"] == "moderate"
    assert w["prescription"]["rpe"] == "6-7"


def test_no_rx_falls_back_to_generic_block():
    # workout_rx=None(处方取数失败的降级)→ 仍排通用块,不炸
    out = schedule_from_medications([], profile=_Profile(workout_target_minutes=40), workout_rx=None)
    w = next((s for s in out["scheduled"] if s["id"] == "workout:today"), None)
    assert w is not None
    assert "锻炼" in w["title"]
    assert "prescription" not in w        # 无处方字段


def test_workout_prescription_fail_soft(monkeypatch):
    # build_twin 抛错 → workout_prescription 返 None(降级),不抛
    import app.services.day_schedule_service as svc
    monkeypatch.setattr("app.twin.builder.build_twin",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert svc.workout_prescription(db=None, user_id=3) is None


# ── cut A 安全复评修复:急性休息门控 + gene_note 真实路径 ──────────────
from types import SimpleNamespace
import app.services.day_schedule_service as _svc


def _patch_rx(monkeypatch, *, acute_rest, guardrail=None, status="optimal", zone="moderate",
              intensity="moderate", guidance="Z2-Z3 有氧", gene_tip="ACTN3 XX:增加长距离 Z2 比例"):
    twin = SimpleNamespace(acute=SimpleNamespace(should_rest_from_training=acute_rest,
                                                 training_guardrail=guardrail))
    monkeypatch.setattr("app.twin.builder.build_twin", lambda *a, **k: twin)
    monkeypatch.setattr("app.agents.recovery_coach.compute_readiness",
                        lambda t: SimpleNamespace(zone=zone))
    import app.agents.movement_coach.coach as mc
    monkeypatch.setattr(mc, "_resolve_training_status", lambda t: (status, "computed"))
    monkeypatch.setattr(mc, "_today_intensity", lambda s, z: (intensity, guidance))
    monkeypatch.setattr(mc, "_gene_bias", lambda t: {"tip": gene_tip} if gene_tip else None)


def test_acute_illness_forces_rest_even_if_matrix_says_train(monkeypatch):
    # 急性不适 + 矩阵本会给 moderate → 必须被强制 rest(不给急性病人排训练)
    _patch_rx(monkeypatch, acute_rest=True, guardrail="发烧期间,今天休息", intensity="moderate")
    rx = _svc.workout_prescription(db=None, user_id=3)
    assert rx["intensity"] == "rest"
    assert rx["guidance"] == "发烧期间,今天休息"
    assert "duration_min" not in rx          # rest 不带时长


def test_gene_note_populates_from_real_tip_key(monkeypatch):
    # 非急性 → 矩阵 moderate + ACTN3 tip 真实落到 gene_note(修 tip/tips 键 bug)
    _patch_rx(monkeypatch, acute_rest=False)
    rx = _svc.workout_prescription(db=None, user_id=3)
    assert rx["intensity"] == "moderate"
    assert rx["gene_note"] == "ACTN3 XX:增加长距离 Z2 比例"
    assert rx["rpe"] == "6-7"
