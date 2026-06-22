"""P4 锻炼链(workout chain)测试。

钉死设计不变量:
1. opt-in ON + 好恢复 → 7 条链协议(pre_check..review),带 chain_id/chain_step/role + prev/next 链接。
2. 每步经 /agenda/complete {health_protocol, id} 可完成 → HealthProtocolEvent 落库,议程 HealthEvent 翻 done。
3. readiness RED / rx.intensity=="rest" → 不建锻炼步(只拉伸),标 downgraded_from。
4. 幂等:连刷两次(模拟两次首页刷新)→ 不重建协议。
5. opt-out(flag off)→ 旧单锻炼项,无链协议(无回归)。
6. meal 步复用既有恢复餐语义(不建第二条 meal 协议)。

测试用 monkeypatch 把 workout_prescription 钉成确定性 rx(避开整次 build_twin),precisely 控强度。
"""
import pytest

from app.models.health_protocol import HealthProtocol, HealthProtocolEvent
from app.models.user_profile import UserProfile
from app.services import agenda_service, day_schedule_service


# ─────────────────────────── fixtures / helpers ───────────────────────────

def _set_profile(db, user_id, *, chain_enabled, pref="evening", target=50):
    prof = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if prof is None:
        prof = UserProfile(user_id=user_id)
        db.add(prof)
    prof.workout_pref_window = pref
    prof.workout_target_minutes = target
    prof.workout_chain_enabled = chain_enabled
    prof.usual_wake_time = "07:00"
    prof.usual_sleep_time = "23:00"
    db.commit()
    db.refresh(prof)
    return prof


@pytest.fixture
def stub_rx(monkeypatch):
    """把 workout_prescription 钉成确定性 rx(默认中等强度,好恢复)。"""
    def _apply(intensity="moderate"):
        rx = {
            "intensity": intensity,
            "type": "aerobic_z2" if intensity == "moderate" else "general",
            "guidance": "今日可正常训练" if intensity != "rest" else "今日建议恢复,不安排训练。",
        }
        if intensity in ("high", "moderate", "low"):
            rx["duration_min"] = {"high": 45, "moderate": 50, "low": 30}[intensity]
            rx["rpe"] = {"high": "7-9", "moderate": "6-7", "low": "≤5"}[intensity]
        monkeypatch.setattr(day_schedule_service, "workout_prescription",
                            lambda db, uid: dict(rx))
        # readiness 灯不门控(无 garmin 行 → None → 留默认 GRAY,锻炼正常排)。
        monkeypatch.setattr(day_schedule_service, "_latest_readiness_zone",
                            lambda db, uid: None)
    return _apply


def _chain_protocols(db, user_id):
    out = []
    for p in db.query(HealthProtocol).filter(
        HealthProtocol.user_id == user_id, HealthProtocol.status == "active"
    ).all():
        iq = p.implied_quantity or {}
        if iq.get("chain_id"):
            out.append(p)
    return out


# ─────────────────────────── 1. 链生成 ───────────────────────────

def test_chain_enabled_good_readiness_creates_7_linked_protocols(
    db, auth_user_and_headers, stub_rx
):
    user, _ = auth_user_and_headers
    _set_profile(db, user.id, chain_enabled=True)
    stub_rx("moderate")

    agenda_service.today(db, user.id)  # 触发链物化

    chain = sorted(_chain_protocols(db, user.id),
                   key=lambda p: p.implied_quantity["chain_step"])
    roles = [p.implied_quantity["chain_role"] for p in chain]
    assert roles == ["pre_check", "workout", "stretch", "shower", "massage", "meal", "review"]

    # 同一 chain_id,step 连续 0..6
    chain_ids = {p.implied_quantity["chain_id"] for p in chain}
    assert len(chain_ids) == 1
    assert [p.implied_quantity["chain_step"] for p in chain] == list(range(7))

    # prev/next 链接已串好:首无 prev、尾无 next、中间互指。
    ids = [p.id for p in chain]
    for i, p in enumerate(chain):
        iq = p.implied_quantity
        assert iq["prev_protocol_id"] == (ids[i - 1] if i > 0 else None)
        assert iq["next_protocol_id"] == (ids[i + 1] if i < len(ids) - 1 else None)

    # 链项也流入议程(都是 health_protocol),带 chain_role 透传。
    items = agenda_service.today(db, user.id)["items"]
    chain_items = [it for it in items if it.get("chain_id")]
    assert len(chain_items) == 7
    assert all(it["source"]["object_type"] == "health_protocol" for it in chain_items)
    assert {it["chain_role"] for it in chain_items} == set(roles)


# ─────────────────────────── 2. 每步可完成(闭环) ───────────────────────────

def test_each_chain_step_completable_via_agenda_complete(
    client, db, auth_user_and_headers, stub_rx
):
    user, h = auth_user_and_headers
    _set_profile(db, user.id, chain_enabled=True)
    stub_rx("moderate")
    agenda_service.today(db, user.id)

    chain = sorted(_chain_protocols(db, user.id),
                   key=lambda p: p.implied_quantity["chain_step"])
    assert len(chain) == 7

    for p in chain:
        r = client.post("/api/v1/agenda/complete", headers=h, json={
            "object_type": "health_protocol", "object_id": p.id, "status": "done",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["agenda_status"] == "done", f"step {p.implied_quantity['chain_role']}"
        # 每步独立 complete_ref → 独立 HealthEvent → 互不碰撞。
        assert body["event_id"] is not None

    # 每步都落了 HealthProtocolEvent(completed),互不串。
    done = (
        db.query(HealthProtocolEvent)
        .filter(HealthProtocolEvent.user_id == user.id,
                HealthProtocolEvent.status == "completed")
        .count()
    )
    assert done == 7, "7 步各落一条 completed 事件"

    # 议程里链项全部翻 completed。
    items = agenda_service.today(db, user.id)["items"]
    chain_items = [it for it in items if it.get("chain_id")]
    assert chain_items and all(it["status"] == "completed" for it in chain_items)


# ─────────────────────────── 3. 降级(RED / rest) ───────────────────────────

def test_rest_intensity_skips_workout_step_downgrade(
    db, auth_user_and_headers, stub_rx
):
    user, _ = auth_user_and_headers
    _set_profile(db, user.id, chain_enabled=True)
    stub_rx("rest")  # 急性/RED → rx.intensity=="rest"

    agenda_service.today(db, user.id)

    chain = sorted(_chain_protocols(db, user.id),
                   key=lambda p: p.implied_quantity["chain_step"])
    roles = [p.implied_quantity["chain_role"] for p in chain]
    assert "workout" not in roles, "rest 强度下不得创建锻炼步"
    assert "stretch" in roles
    # 降级标记:每步带 downgraded_from="workout"。
    stretch = next(p for p in chain if p.implied_quantity["chain_role"] == "stretch")
    assert stretch.implied_quantity.get("downgraded_from") == "workout"


def test_red_readiness_downgrades_to_stretch(db, auth_user_and_headers, monkeypatch):
    """readiness RED(非 rest rx)→ 锻炼被剔,降级为只拉伸(锻炼永远只降强度,从不上调)。"""
    user, _ = auth_user_and_headers
    _set_profile(db, user.id, chain_enabled=True)
    # rx 本身是 moderate,但 readiness 灯为 RED → 链生成内部降级。
    monkeypatch.setattr(day_schedule_service, "workout_prescription",
                        lambda db, uid: {"intensity": "moderate", "type": "aerobic_z2",
                                         "duration_min": 50, "guidance": "g"})
    from app.services.timing_solver import RED
    monkeypatch.setattr(day_schedule_service, "_latest_readiness_zone",
                        lambda db, uid: RED)

    agenda_service.today(db, user.id)
    chain = _chain_protocols(db, user.id)
    roles = {p.implied_quantity["chain_role"] for p in chain}
    assert "workout" not in roles, "RED 下不排锻炼步"
    assert "stretch" in roles


# ─────────────────────────── 4. 幂等 ───────────────────────────

def test_chain_generation_idempotent(db, auth_user_and_headers, stub_rx):
    user, _ = auth_user_and_headers
    _set_profile(db, user.id, chain_enabled=True)
    stub_rx("moderate")

    agenda_service.today(db, user.id)  # 刷新 1
    first = sorted(p.id for p in _chain_protocols(db, user.id))
    assert len(first) == 7

    agenda_service.today(db, user.id)  # 刷新 2(模拟再次首页刷新)
    second = sorted(p.id for p in _chain_protocols(db, user.id))
    assert second == first, "二次刷新不得重建协议(必须按 chain_id+chain_step 幂等)"


def test_chain_key_unique_index_enforced(db, auth_user_and_headers):
    """DB 级幂等 backstop:同 (user_id, chain_key) 第二条 INSERT 必撞 partial unique index。

    SQLite 单连接测不了真并发,但能直接验唯一约束确实生效(否则应用层去重一旦有竞态就裸奔)。
    """
    from sqlalchemy.exc import IntegrityError

    user, _ = auth_user_and_headers
    p1 = HealthProtocol(
        user_id=user.id, domain="exercise", name="链步A", status="active",
        cadence="event_triggered", chain_key="c1:0",
        implied_quantity={"chain_id": "c1", "chain_step": 0},
    )
    db.add(p1)
    db.commit()

    p2 = HealthProtocol(
        user_id=user.id, domain="exercise", name="链步A重复", status="active",
        cadence="event_triggered", chain_key="c1:0",  # 同 user + 同 chain_key
        implied_quantity={"chain_id": "c1", "chain_step": 0},
    )
    db.add(p2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    # NULL chain_key 的普通协议不受约束(partial WHERE NOT NULL):可建任意多条。
    for _ in range(2):
        db.add(HealthProtocol(user_id=user.id, domain="hydration", name="普通", status="active"))
    db.commit()  # 不应抛


# ─────────────────────────── 5. opt-out(无回归) ───────────────────────────

def test_chain_disabled_keeps_legacy_single_workout_no_chain(
    db, auth_user_and_headers, stub_rx
):
    user, _ = auth_user_and_headers
    _set_profile(db, user.id, chain_enabled=False)  # opt-out,但仍有 pref_window
    stub_rx("moderate")

    items = agenda_service.today(db, user.id)["items"]

    # 无任何链协议
    assert _chain_protocols(db, user.id) == []
    assert not any(it.get("chain_id") for it in items)
    # 旧单锻炼项仍在(movement 类,来自 day_schedule_workout)。
    movement = [it for it in items
                if it.get("type") == "movement"
                and (it.get("source") or {}).get("object_type") == "day_schedule_workout"]
    assert len(movement) >= 1, "opt-out 必须保留旧单锻炼项(无回归)"


# ─────────────────────────── 6. meal 步不建第二条餐 ───────────────────────────

def test_meal_role_single_protocol_no_duplicate(db, auth_user_and_headers, stub_rx):
    """meal 角色只产一条 diet 链协议;反复刷新不叠加第二条餐。"""
    user, _ = auth_user_and_headers
    _set_profile(db, user.id, chain_enabled=True)
    stub_rx("moderate")

    agenda_service.today(db, user.id)
    agenda_service.today(db, user.id)  # 再刷一次

    meal_protocols = [
        p for p in _chain_protocols(db, user.id)
        if p.implied_quantity.get("chain_role") == "meal"
    ]
    assert len(meal_protocols) == 1, "meal 步只允许一条链协议(不建第二条餐)"
    assert meal_protocols[0].domain == "diet"
    assert meal_protocols[0].source_model == "diet_records"


# ─────────────────── 7. 链物化 DB 错误必须 fail-soft(安全评审 B1)───────────────────

def test_chain_materialize_db_error_degrades_not_500(db, auth_user_and_headers, stub_rx, monkeypatch):
    """对抗(安全评审 B1):链物化里的 DB 级错误会 doom session;
    maybe_materialize_workout_chain 必须 db.rollback() 退化为无链,否则紧接着
    today_status() 的 autoflush 会再抛 PendingRollbackError → 整条 /agenda/today 500。
    去掉 wrapper 里的 db.rollback() 本测试即红(today() 抛而非正常返回)。"""
    from app.services import workout_chain_service

    user, _ = auth_user_and_headers
    _set_profile(db, user.id, chain_enabled=True)
    stub_rx("moderate")

    def _boom(db, user_id, *, chain_id, steps):
        # 模拟 DB 级错误:flush 一条缺 NOT-NULL(name/domain)的行 → IntegrityError → session 终态
        db.add(HealthProtocol(user_id=user_id))
        db.flush()

    monkeypatch.setattr(workout_chain_service, "ensure_workout_chain_protocols", _boom)

    # 不得抛(链是增强,失败应退化为无链);主议程仍可正常返回。
    result = agenda_service.today(db, user.id)
    assert "items" in result, "链物化失败时主议程仍须正常返回(不可 500)"
    # session 已被 rollback 恢复:后续查询不再抛 PendingRollbackError。
    assert db.query(HealthProtocol).filter(HealthProtocol.user_id == user.id).count() >= 0


# ─────────────────────── 7. chain_id / trigger_date 用「中国日」基准 ───────────────────────

def test_chain_id_and_trigger_date_use_china_day_basis(
    db, auth_user_and_headers, stub_rx, monkeypatch
):
    """chain_id + trigger_date 必须从 get_user_today(中国日)派生,不用进程 date.today()。

    钉住中国日基准:把 get_user_today 固定成一个确定日期,断言 chain_id 与每步 trigger_date
    都用该日 —— 防 UTC 进程下午夜边界把同一中国日拆成两套链(改回 date.today() 时,本测试
    在非该日的环境下即红)。
    """
    import datetime as _dt

    from app.utils import timezone as tz_util

    user, _ = auth_user_and_headers
    _set_profile(db, user.id, chain_enabled=True)
    stub_rx("moderate")

    fixed_day = _dt.date(2026, 6, 24)
    # 两个出口(day_schedule_service.build_workout_chain_steps 与
    # workout_chain_service.ensure_workout_chain_protocols)都懒导入 get_user_today,
    # 故直接打源模块属性,两处都走同一钉死日。
    monkeypatch.setattr(tz_util, "get_user_today", lambda db, uid: fixed_day)

    agenda_service.today(db, user.id)  # 触发链物化

    chain = _chain_protocols(db, user.id)
    assert chain, "应物化出链协议"
    # chain_id 用中国日
    chain_ids = {p.implied_quantity["chain_id"] for p in chain}
    assert chain_ids == {f"workout_chain:{user.id}:{fixed_day.isoformat()}"}
    # 每步 trigger_date 也用同一中国日(与 chain_id 同基准,不会拆两套链)
    trigger_dates = {p.implied_quantity.get("trigger_date") for p in chain}
    assert trigger_dates == {fixed_day.isoformat()}
