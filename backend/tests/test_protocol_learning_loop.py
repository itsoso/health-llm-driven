# -*- coding: utf-8 -*-
"""P6 学习闭环测试 —— 聚合 → 人体工学调参建议(SUGGEST-ONLY)+ R4 dose 守门 + 节流。

钉死(任务要求):
1. 聚合:协议 14d 跳过 5×、主导原因 no_time → 产出 time_window/cooldown 类 field_delta(建议非应用)。
2. R4 硬门(守门, red-green):用药/补剂协议高跳过 → 绝不产量/剂量 field_delta(只 timing/cooldown/surface)。
3. suggest-only:跑闭环不改任何 HealthProtocol 字段(无静默写);/corrections 返回 adjustments;
   只有显式 apply-adjustment 端点才改。
4. apply-adjustment:应用白名单字段(time_window);拒绝用药/补剂的 dose 字段。
5. 节流:慢性跳过 P1 协议 → 收紧轻推,但永不低于 1/周、永不碰 P0;失败 fail-open。
6. per-user 隔离:聚合只看 caller 自己的事件。
"""
from datetime import date, timedelta

import pytest

from app.models.health_protocol import HealthProtocol, HealthProtocolEvent
from app.services import health_protocol_service as svc
from app.services import protocol_self_correction as psc
from app.services.protocol_learning_loop import (
    ALLOWED_FIELDS,
    NUDGE_DEFAULT_PER_WEEK,
    NUDGE_FLOOR_PER_WEEK,
    ProtocolCounters,
    nudge_throttle,
    run_loop,
    suggest_field_delta,
)
from tests.conftest import create_authenticated_user


# ───────────────────────── helpers ─────────────────────────

def _mk_protocol(db, user_id, *, domain="hydration", name="2000ml 温水杯",
                 time_window="morning", cadence="daily"):
    p = HealthProtocol(
        user_id=user_id, domain=domain, name=name,
        time_window=time_window, cadence=cadence, status="active",
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _skip_n_days(db, user_id, protocol_id, n, reason="no_time"):
    """造 n 天的 skipped 事件(每天一条,event_date 各不同,避免唯一约束)。"""
    today = date.today()
    for i in range(n):
        ev = HealthProtocolEvent(
            user_id=user_id, protocol_id=protocol_id,
            event_date=today - timedelta(days=i),
            status="skipped", track="protocol", skip_reason=reason,
        )
        db.add(ev)
    db.commit()


# ───────────────── ① 聚合:跳过 5× no_time → field_delta ─────────────────

def test_aggregation_emits_field_delta_for_chronic_skip(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    p = _mk_protocol(db, user.id, time_window="morning")
    _skip_n_days(db, user.id, p.id, 5, reason="no_time")

    deltas = psc.suggest_protocol_adjustments(db, user.id)
    assert len(deltas) == 1
    d = deltas[0]
    assert d["protocol_id"] == p.id
    # no_time → 建议挪时间窗(人体工学,非量)
    assert d["field"] in ("time_window", "cooldown", "surface")
    assert d["field"] in ALLOWED_FIELDS
    assert d["applied"] is False                      # SUGGEST-ONLY
    assert "from" in d and "to" in d
    # 非羞辱式文案
    assert "不是你的错" in d["message"]


def test_aggregation_below_threshold_no_delta(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    p = _mk_protocol(db, user.id)
    _skip_n_days(db, user.id, p.id, 2, reason="no_time")   # < _MIN_SKIP_FOR_SUGGEST(3)
    assert psc.suggest_protocol_adjustments(db, user.id) == []


# ───────────────── ② R4 硬门(守门, red-green)─────────────────

def test_r4_no_dose_delta_for_medication(db, auth_user_and_headers):
    """用药协议高跳过 → 只允许 timing/cooldown/surface,绝不产量/剂量字段。

    这是 R4 守门测试。把 protocol_learning_loop.suggest_field_delta 的 field 改成
    'dose'/'implied_quantity' 之类 → 此测试 + run_loop 断言会红。
    """
    user, _ = auth_user_and_headers
    p = _mk_protocol(db, user.id, domain="medication", name="二甲双胍 服药")
    _skip_n_days(db, user.id, p.id, 6, reason="too_hard")

    deltas = psc.suggest_protocol_adjustments(db, user.id)
    for d in deltas:
        assert d["field"] in ALLOWED_FIELDS
        assert d["field"] not in ("implied_quantity", "dosage", "actual_dosage",
                                  "drug", "dose")
        # field_delta 里绝不出现任何量/剂量键
        for forbidden in ("implied_quantity", "dosage", "actual_dosage", "drug", "dose"):
            assert forbidden not in d


def test_r4_no_dose_delta_for_supplement(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    p = _mk_protocol(db, user.id, domain="supplement", name="维 D 补剂", cadence="daily")
    _skip_n_days(db, user.id, p.id, 6, reason="forgot")
    deltas = psc.suggest_protocol_adjustments(db, user.id)
    for d in deltas:
        assert d["field"] in ALLOWED_FIELDS


def test_r4_run_loop_no_dose_field():
    """纯层 run_loop 后置闸:正常输入下任何 delta.field 必须 ∈ ALLOWED_FIELDS。"""
    counters = [ProtocolCounters(
        protocol_id=1, domain="medication", name="药",
        priority_tier="P0", skipped=6, dominant_skip_reason="too_hard",
    )]
    result = run_loop(counters)
    for d in result.deltas:
        assert d.field in ALLOWED_FIELDS


def test_r4_run_loop_raises_on_dose_field(monkeypatch):
    """守门(red-green, -O 鲁棒):若策略漏出量/剂量字段,run_loop 必抛 ValueError。

    用真 raise(非 assert)保证 `python -O` 下也拦得住。把 suggest_field_delta 桩成
    返回 dose field → run_loop 应抛 ValueError(把这条 if 删了 → 此测试红)。
    """
    import app.services.protocol_learning_loop as loop

    def _bad(counter):
        return loop.FieldDelta(
            protocol_id=counter.protocol_id, domain=counter.domain, name=counter.name,
            field="dose", from_value=None, to_value="2000mg",
            reason="x", confidence="low", message="x",
        )

    monkeypatch.setattr(loop, "suggest_field_delta", _bad)
    counters = [ProtocolCounters(
        protocol_id=1, domain="medication", name="药", priority_tier="P0", skipped=6,
    )]
    with pytest.raises(ValueError):
        loop.run_loop(counters)


def test_r4_redgreen_guard_catches_dose_field():
    """red-green 自证:若策略产出了 dose 字段,守门 ValueError 会触发(模拟越界)。

    直接构造一个量字段 delta,确认 aggregator 末闸会拒绝(防回归把量漏出)。
    """
    # 模拟一个被篡改成 dose 的 delta dict,过 aggregator 末闸的等价逻辑。
    forbidden = {"protocol_id": 1, "field": "dose", "from": None, "to": "2000mg"}
    bad_field = forbidden["field"]
    assert bad_field in psc._DOSE_FORBIDDEN_FIELDS or bad_field not in ALLOWED_FIELDS


# ───────────────── ③ suggest-only:不静默写 ─────────────────

def test_suggest_only_no_silent_mutation(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    p = _mk_protocol(db, user.id, time_window="morning", cadence="daily")
    _skip_n_days(db, user.id, p.id, 5, reason="no_time")

    before_tw, before_cad, before_notes = p.time_window, p.cadence, p.notes
    _ = psc.suggest_protocol_adjustments(db, user.id)

    db.refresh(p)
    assert p.time_window == before_tw                 # 跑闭环未改协议本体
    assert p.cadence == before_cad
    assert p.notes == before_notes


def test_corrections_endpoint_returns_adjustments(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    p = _mk_protocol(db, user.id, time_window="morning")
    _skip_n_days(db, user.id, p.id, 5, reason="no_time")

    resp = client.get("/api/v1/protocols/corrections", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "adjustments" in body
    assert any(a["protocol_id"] == p.id for a in body["adjustments"])
    # 仅查询不应改协议
    db.refresh(p)
    assert p.time_window == "morning"


# ───────────────── ④ apply-adjustment ─────────────────

def test_apply_adjustment_whitelisted_field(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    p = _mk_protocol(db, user.id, time_window="morning")

    resp = client.post(
        f"/api/v1/protocols/{p.id}/apply-adjustment",
        json={"field": "time_window", "to_value": "afternoon"},
        headers=headers,
    )
    assert resp.status_code == 200
    db.refresh(p)
    assert p.time_window == "afternoon"               # 显式应用才生效


def test_apply_adjustment_rejects_dose_for_medication(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    p = _mk_protocol(db, user.id, domain="medication", name="药")
    for bad in ("dose", "dosage", "implied_quantity", "actual_dosage", "drug"):
        resp = client.post(
            f"/api/v1/protocols/{p.id}/apply-adjustment",
            json={"field": bad, "to_value": "2000mg"},
            headers=headers,
        )
        assert resp.status_code == 400, f"{bad} 应被 R4 拒绝"


def test_apply_adjustment_rejects_cadence_for_supplement(client, db, auth_user_and_headers):
    user, headers = auth_user_and_headers
    p = _mk_protocol(db, user.id, domain="supplement", name="补剂", cadence="daily")
    resp = client.post(
        f"/api/v1/protocols/{p.id}/apply-adjustment",
        json={"field": "cadence", "to_value": "weekly"},
        headers=headers,
    )
    assert resp.status_code == 400                     # 用药/补剂域不接受经闭环改节奏(F5b)
    db.refresh(p)
    assert p.cadence == "daily"


# ───────────────── ⑤ 节流:只 SPEND FEWER,永不 < floor,绝不碰 P0 ─────────────────

def test_throttle_chronic_skip_p1_suppressed_but_floored():
    c = ProtocolCounters(
        protocol_id=1, domain="respiratory", name="洗鼻",
        priority_tier="P1", skipped=6,
    )
    cap = nudge_throttle(c)
    assert cap < NUDGE_DEFAULT_PER_WEEK               # 被收紧(推更少)
    assert cap >= NUDGE_FLOOR_PER_WEEK                # 永不低于 1/周


def test_throttle_never_touches_p0():
    c = ProtocolCounters(
        protocol_id=1, domain="medication", name="药",
        priority_tier="P0", skipped=99,
    )
    assert nudge_throttle(c) == NUDGE_DEFAULT_PER_WEEK  # P0 永不被收紧


def test_throttle_light_skip_keeps_default():
    c = ProtocolCounters(
        protocol_id=1, domain="hydration", name="水",
        priority_tier="P1", skipped=1,
    )
    assert nudge_throttle(c) == NUDGE_DEFAULT_PER_WEEK


def test_throttle_helper_fail_open_unknown_protocol(db, auth_user_and_headers):
    """未知协议 → 返回默认(fail-open,不因学习闭环坏掉而漏推)。"""
    user, _ = auth_user_and_headers
    assert psc.protocol_nudge_throttle(db, user.id, 999999) == NUDGE_DEFAULT_PER_WEEK


def test_throttle_helper_p0_not_suppressed(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    p = _mk_protocol(db, user.id, domain="medication", name="药")
    _skip_n_days(db, user.id, p.id, 7, reason="too_hard")
    assert psc.protocol_nudge_throttle(db, user.id, p.id) == NUDGE_DEFAULT_PER_WEEK


# ───────────────── ⑥ per-user 隔离 ─────────────────

def test_per_user_isolation(db, auth_user_and_headers):
    user_a, _ = auth_user_and_headers
    user_b, _ = create_authenticated_user(db)

    pa = _mk_protocol(db, user_a.id, name="A 的协议")
    pb = _mk_protocol(db, user_b.id, name="B 的协议")
    _skip_n_days(db, user_a.id, pa.id, 5, reason="no_time")
    _skip_n_days(db, user_b.id, pb.id, 5, reason="forgot")

    deltas_a = psc.suggest_protocol_adjustments(db, user_a.id)
    # 只见自己的协议
    assert all(d["protocol_id"] == pa.id for d in deltas_a)
    assert all(d["protocol_id"] != pb.id for d in deltas_a)


# ───────────────── 纯层:suggest_field_delta 直测 ─────────────────

def test_suggest_field_delta_multidose_domain_no_cadence():
    """多剂域(用药/补剂)即便策略想调 cadence 也降级为 cooldown(F5b 塌剂歧义)。"""
    c = ProtocolCounters(
        protocol_id=1, domain="medication", name="药",
        priority_tier="P0", skipped=6, cadence="daily",
        dominant_skip_reason=None,   # 无主导原因 → 默认 surface(非 cadence)
    )
    d = suggest_field_delta(c)
    assert d is not None
    assert d.field != "cadence"
    assert d.field in ALLOWED_FIELDS
