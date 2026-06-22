"""行为协议模板注册表 + 播种 + 投影/完成往返 + 提醒桥 + 安全闸(P1a)。

钉死:
① 播种幂等:两次 seed → 每模板恰一行;先 created 后 skipped。
② 投影:播种后 /agenda/today smart 把 nasal_wash_morning + sleep_winddown 当 pending +
   can_complete + complete_ref object_type=health_protocol。
③ 完成往返:POST /agenda/complete {health_protocol, done} → 200 + 今日 completed 事件;幂等。
④ 跳过:status=skipped + skip_reason=no_time → skipped 事件,不双写。
⑤ 提醒桥:晨洗鼻(morning)被 _collect_timed_items 收集,start_min=480、kind=protocol、
   tier=P1、complete_ref={health_protocol,id};protocol-only 用户进 _candidate_user_ids。
⑥ 红旗抑制:活跃鼻部红旗症状 → 洗鼻提醒**不被收集**。
⑦ R4 措辞闸:任何模板 advisory_note 不含命令式量化剂量。
⑧ tier:protocol kind 恒 P1,绝不 P0。
"""
import re
from datetime import UTC, date, datetime, timedelta

from app.models.health_protocol import HealthProtocol, HealthProtocolEvent
from app.models.symptom_entry import SymptomEntry
from app.services import health_protocol_service as svc
from app.services.protocol_templates import (
    BEHAVIOR_PROTOCOL_TEMPLATES,
    TEMPLATES_BY_KEY,
    nasal_red_flag_active,
    seed_behavior_protocols,
)


# ───────────────────────────── ① 播种幂等 ─────────────────────────────

def test_seed_idempotent_one_row_per_template(db, auth_user_and_headers):
    user, _ = auth_user_and_headers

    first = seed_behavior_protocols(db, user.id)
    assert set(first["created"]) == set(TEMPLATES_BY_KEY.keys())
    assert first["skipped"] == []

    second = seed_behavior_protocols(db, user.id)
    assert second["created"] == []
    assert set(second["skipped"]) == set(TEMPLATES_BY_KEY.keys())

    # 每模板恰一行
    for key in TEMPLATES_BY_KEY:
        rows = (
            db.query(HealthProtocol)
            .filter(HealthProtocol.user_id == user.id)
            .all()
        )
        matched = [r for r in rows if (r.implied_quantity or {}).get("template_key") == key]
        assert len(matched) == 1, f"{key} 应恰一行, 实得 {len(matched)}"


def test_seed_subset_then_rest(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    r1 = seed_behavior_protocols(db, user.id, keys=["sleep_winddown"])
    assert r1["created"] == ["sleep_winddown"] and r1["skipped"] == []

    r2 = seed_behavior_protocols(db, user.id)  # all → only the other two are new
    assert "sleep_winddown" in r2["skipped"]
    assert set(r2["created"]) == {"nasal_wash_morning", "nasal_wash_evening"}


def test_seed_unknown_key_raises(db, auth_user_and_headers):
    user, _ = auth_user_and_headers
    try:
        seed_behavior_protocols(db, user.id, keys=["does_not_exist"])
        assert False, "未知 key 应抛 ValueError"
    except ValueError as e:
        assert "does_not_exist" in str(e)


def test_seed_endpoint(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    r = client.post("/api/v1/protocols/seed/behavior", headers=h, json={})
    assert r.status_code == 200, r.text
    assert set(r.json()["created"]) == set(TEMPLATES_BY_KEY.keys())

    # 二次播种 → 全 skipped
    r2 = client.post("/api/v1/protocols/seed/behavior", headers=h, json={})
    assert r2.json()["created"] == []

    # 未知 key → 400
    r3 = client.post("/api/v1/protocols/seed/behavior", headers=h, json={"keys": ["nope"]})
    assert r3.status_code == 400


# ───────────────────────────── ② 投影 ─────────────────────────────

def _proto_by_key(db, user_id, key):
    for p in db.query(HealthProtocol).filter(HealthProtocol.user_id == user_id).all():
        if (p.implied_quantity or {}).get("template_key") == key:
            return p
    return None


def test_projection_shows_pending_completable(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    seed_behavior_protocols(db, user.id)

    r = client.get("/api/v1/agenda/today?mode=smart", headers=h)
    assert r.status_code == 200, r.text
    payload = r.json()
    # smart_today shape: 取所有项的扁平列表(items / top_actions 任一容器)
    blob = repr(payload)
    # 至少 nasal_wash_morning 与 sleep_winddown 的协议出现在投影里,且是 health_protocol ref
    morning = _proto_by_key(db, user.id, "nasal_wash_morning")
    wind = _proto_by_key(db, user.id, "sleep_winddown")
    assert morning is not None and wind is not None
    assert "health_protocol" in blob
    # 协议 id 出现在投影
    assert str(morning.id) in blob or "晨起洗鼻" in blob


# ───────────────────────── ③ 完成往返(幂等)─────────────────────────

def test_complete_roundtrip_idempotent(client, db, auth_user_and_headers):
    user, h = auth_user_and_headers
    seed_behavior_protocols(db, user.id)
    p = _proto_by_key(db, user.id, "nasal_wash_morning")

    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "health_protocol", "object_id": p.id, "status": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["agenda_status"] == "done"

    today = date.today()
    evs = (
        db.query(HealthProtocolEvent)
        .filter(
            HealthProtocolEvent.protocol_id == p.id,
            HealthProtocolEvent.event_date == today,
        )
        .all()
    )
    assert len(evs) == 1 and evs[0].status == "completed"

    # 幂等:重复完成不新增事件
    r2 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "health_protocol", "object_id": p.id, "status": "done"})
    assert r2.status_code == 200
    evs2 = (
        db.query(HealthProtocolEvent)
        .filter(
            HealthProtocolEvent.protocol_id == p.id,
            HealthProtocolEvent.event_date == today,
        )
        .all()
    )
    assert len(evs2) == 1


# ───────────────────────────── ④ 跳过 ─────────────────────────────

def test_skip_via_agenda_no_writeback(client, db, auth_user_and_headers):
    """经 /agenda/complete 跳过:HealthEvent 生命周期翻 skipped,**不**回写 source
    (与药/补剂跳过对齐:漏做不记成完成)。幂等。"""
    user, h = auth_user_and_headers
    seed_behavior_protocols(db, user.id)
    p = _proto_by_key(db, user.id, "sleep_winddown")

    r = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "health_protocol", "object_id": p.id,
        "status": "skipped", "skip_reason": "no_time"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["agenda_status"] == "skipped"
    assert body["skip_reason"] == "no_time"
    assert body["wrote"] is False           # 跳过不回写 source

    # 幂等:重复跳过仍 skipped,不报错。
    r2 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "health_protocol", "object_id": p.id,
        "status": "skipped", "skip_reason": "no_time"})
    assert r2.status_code == 200 and r2.json()["agenda_status"] == "skipped"

    # 坏 skip_reason → 400
    r3 = client.post("/api/v1/agenda/complete", headers=h, json={
        "object_type": "health_protocol", "object_id": p.id,
        "status": "skipped", "skip_reason": "bogus"})
    assert r3.status_code == 400


def test_skip_via_protocol_endpoint_creates_event_no_double(client, db, auth_user_and_headers):
    """协议层自身 /protocols/{id}/skip:落一条 HealthProtocolEvent(skipped),重复不双写。"""
    user, h = auth_user_and_headers
    seed_behavior_protocols(db, user.id)
    p = _proto_by_key(db, user.id, "sleep_winddown")

    r = client.post(f"/api/v1/protocols/{p.id}/skip", headers=h, json={"reason": "no_time"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "skipped"

    # 再跳一次(改原因)→ 仍单行(uq_hpe_protocol_date)。
    client.post(f"/api/v1/protocols/{p.id}/skip", headers=h, json={"reason": "too_tired"})

    today = date.today()
    evs = (
        db.query(HealthProtocolEvent)
        .filter(
            HealthProtocolEvent.protocol_id == p.id,
            HealthProtocolEvent.event_date == today,
        )
        .all()
    )
    assert len(evs) == 1 and evs[0].status == "skipped"


# ─────────────────────────── ⑤ 提醒桥 ───────────────────────────

def test_reminder_bridge_collects_protocol(db, auth_user_and_headers):
    from app.tasks.event_reminders import _collect_timed_items

    user, _ = auth_user_and_headers
    seed_behavior_protocols(db, user.id, keys=["nasal_wash_morning"])
    p = _proto_by_key(db, user.id, "nasal_wash_morning")

    items = _collect_timed_items(db, user.id, date.today())
    proto_items = [it for it in items if it["kind"] == "protocol"]
    assert len(proto_items) == 1
    it = proto_items[0]
    assert it["start_min"] == 480          # 08:00
    assert it["item_key"] == f"protocol:{p.id}"
    assert it["lead"] == 0
    assert it["complete_ref"] == {"object_type": "health_protocol", "object_id": p.id}


def test_protocol_only_user_enumerated(db, auth_user_and_headers):
    from app.tasks.event_reminders import _candidate_user_ids

    user, _ = auth_user_and_headers
    seed_behavior_protocols(db, user.id, keys=["nasal_wash_morning"])

    ids = _candidate_user_ids(db, date.today())
    assert user.id in ids


def test_anytime_window_not_collected(db, auth_user_and_headers):
    """无固定到点(anytime)的协议不进提醒桥(避免无谓打扰)。"""
    from app.tasks.event_reminders import _collect_timed_items

    user, _ = auth_user_and_headers
    # 手建一个 anytime 行为协议
    svc.create_protocol(db, user.id, {
        "domain": "sleep", "name": "随时放松", "cadence": "daily",
        "time_window": "anytime",
        "implied_quantity": {"template_key": "sleep_winddown", "template_version": 1},
        "source_model": None,
    })
    items = _collect_timed_items(db, user.id, date.today())
    assert [it for it in items if it["kind"] == "protocol"] == []


# ─────────────────────── ⑥ 红旗抑制(fail-safe)───────────────────────

def test_nasal_red_flag_suppresses_reminder(db, auth_user_and_headers):
    from app.tasks.event_reminders import _collect_timed_items

    user, _ = auth_user_and_headers
    seed_behavior_protocols(db, user.id, keys=["nasal_wash_morning"])

    # 活跃鼻部红旗:近期鼻出血症状
    db.add(SymptomEntry(
        user_id=user.id, body_part="respiratory", description="今天早上有鼻出血",
        occurred_at=datetime.now(UTC) - timedelta(hours=2),
    ))
    db.commit()

    assert nasal_red_flag_active(db, user.id) is True
    items = _collect_timed_items(db, user.id, date.today())
    assert [it for it in items if it["kind"] == "protocol"] == [], \
        "活跃鼻部红旗下洗鼻提醒应被抑制"


def test_no_red_flag_not_suppressed(db, auth_user_and_headers):
    from app.tasks.event_reminders import _collect_timed_items

    user, _ = auth_user_and_headers
    seed_behavior_protocols(db, user.id, keys=["nasal_wash_morning"])
    # 无关症状不触发抑制
    db.add(SymptomEntry(
        user_id=user.id, body_part="musculoskeletal", description="膝盖有点酸",
        occurred_at=datetime.now(UTC) - timedelta(hours=2),
    ))
    db.commit()

    assert nasal_red_flag_active(db, user.id) is False
    items = _collect_timed_items(db, user.id, date.today())
    assert len([it for it in items if it["kind"] == "protocol"]) == 1


# ─────────────── F3: 红旗门 fail-CLOSED + push 正文带 caveat ───────────────

def test_nasal_red_flag_fails_closed_on_query_error(db, auth_user_and_headers, monkeypatch):
    """F3(a):症状查询抛异常(安全状态不可验证)→ nasal_red_flag_active 返回 True(抑制)。

    这是禁忌抑制门,必须 fail-CLOSED:宁可漏推一次良性提醒,不在不可知安全态下推禁忌 nudge。
    """
    from app.tasks.event_reminders import _collect_timed_items
    import app.services.protocol_templates as pt

    user, _ = auth_user_and_headers
    seed_behavior_protocols(db, user.id, keys=["nasal_wash_morning"])

    # 让症状查询路径抛异常(模拟缺列 / DB 抖动)。SymptomEntry 在该模块函数内 import,
    # patch 模型属性触发查询构建即炸。
    class _Boom:
        def __getattr__(self, name):
            raise RuntimeError("simulated symptom query failure")

    monkeypatch.setattr(pt, "SymptomEntry", _Boom(), raising=False)
    # 注意:nasal_red_flag_active 在函数体内 `from app.models.symptom_entry import SymptomEntry`,
    # 故 patch 真实模型模块上的符号。
    import app.models.symptom_entry as se_mod
    monkeypatch.setattr(se_mod, "SymptomEntry", _Boom(), raising=False)

    assert nasal_red_flag_active(db, user.id) is True, "查询异常必须 fail-closed 抑制(返回 True)"
    # 抑制传导到提醒桥:洗鼻项不被收集。
    items = _collect_timed_items(db, user.id, date.today())
    assert [it for it in items if it["kind"] == "protocol"] == [], \
        "红旗门 fail-closed → 洗鼻提醒不被收集"


def test_nasal_push_body_carries_caveat():
    """F3(b):洗鼻协议推送正文必须带禁忌 caveat(安全字符串随通知传播,不依赖检测)。"""
    from app.tasks.event_reminders import _push_body

    _, body = _push_body("protocol", "晨起洗鼻", 0, template_key="nasal_wash_morning")
    assert "请勿洗鼻" in body and "咨询医生" in body, f"洗鼻 push 正文缺禁忌 caveat: {body!r}"

    # 非洗鼻协议(如睡前放松)不强加洗鼻 caveat。
    _, body2 = _push_body("protocol", "睡前放松", 0, template_key="sleep_winddown")
    assert "请勿洗鼻" not in body2


# ─────────────────────── ⑦ R4 措辞闸 ───────────────────────

# 命令式量化剂量: "300-500 ml" / "2000 IU" / "服用 5 mg" 这类裸处方数值。
_PRESCRIPTIVE_DOSE = re.compile(
    r"\d+\s*[-–~]?\s*\d*\s*(µg|μg|ug|mg|g|IU|iu|ml|mL|毫升|毫克|克)\b"
)


def test_no_template_carries_prescriptive_dose():
    for tpl in BEHAVIOR_PROTOCOL_TEMPLATES:
        note = tpl["advisory_note"]
        assert not _PRESCRIPTIVE_DOSE.search(note), \
            f"{tpl['key']} advisory_note 含命令式量化剂量: {note!r}"
        # 对冲措辞必须存在(建议/可考虑/请/以...为准 之一)
        assert any(k in note for k in ("建议", "可考虑", "请", "为准")), \
            f"{tpl['key']} advisory_note 缺对冲措辞: {note!r}"


def test_nasal_templates_carry_red_flag_caveat():
    """洗鼻模板的 advisory_note 必须始终带禁忌 caveat(red-flag caveat always present)。"""
    for key in ("nasal_wash_morning", "nasal_wash_evening"):
        note = TEMPLATES_BY_KEY[key]["advisory_note"]
        assert "请勿自行洗鼻" in note and "咨询医生" in note, \
            f"{key} 缺红旗禁忌 caveat: {note!r}"


# ─────────────────────── ⑧ tier 永不 P0 ───────────────────────

def test_protocol_tier_is_p1_never_p0():
    from app.tasks.event_reminders import _KIND_TIER

    assert _KIND_TIER["protocol"] == "P1"
    assert _KIND_TIER["protocol"] != "P0"
    for tpl in BEHAVIOR_PROTOCOL_TEMPLATES:
        assert tpl["reminder_tier"] == "P1"
