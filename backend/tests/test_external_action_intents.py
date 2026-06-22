"""P5 external-action intents 测试 —— food_order / doctor_booking / alarm_set。

复用既有 WriteIntent 账本(propose→confirm,全 manual_confirm,不自治)。核心不变量:
- 财务硬边界:food_order confirm **绝不**下单/付款/触碰任何支付字段(可证惰性 inert)。
- 用户隔离:doctor_booking 只扫调用方自己的 ReviewSchedule(IDOR)。
- R4 守门:food_order 摘要里的量化饮食处方在落库前被 strip(red-green)。
- tier:三类全 P1,绝不 P0。manual_confirm 恒定、双确认幂等、执行失败回滚不假装成功。
"""
import uuid
from datetime import date, timedelta

import pytest

from app.models.family_health import ReviewSchedule
from app.models.smart_reminder import SmartReminder
from app.models.user import User
from app.models.write_intent import WriteIntent
from app.services import write_intent_service as svc


# ─────────────────────────── helpers ───────────────────────────

def _mk_user(db) -> User:
    u = User(
        username=f"ea_{uuid.uuid4().hex[:6]}",
        email=f"ea_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="ea",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _due_review(db, user_id: int, *, item="空腹血糖", dept="内分泌科", overdue=False, days=5):
    nd = (date.today() - timedelta(days=2)) if overdue else (date.today() + timedelta(days=days))
    rs = ReviewSchedule(
        user_id=user_id,
        item_name=item,
        category="blood",
        department=dept,
        hospital="协和医院",
        next_due_date=nd,
        status="pending",
        is_active=True,
    )
    db.add(rs)
    db.commit()
    db.refresh(rs)
    return rs


# ═══════════════════════ 1. alarm_set ═══════════════════════

def test_alarm_set_propose_confirm_creates_reminder(db):
    u = _mk_user(db)
    wi = svc.propose_external_action(
        db, u.id, kind="alarm_set", title="起床闹钟",
        description="明早 7 点起床", payload={"alarm_time": "2026-06-23T07:00:00", "label": "起床"},
    )
    assert wi is not None
    assert wi.trust_tier == "manual_confirm"
    res = svc.confirm(db, u.id, wi.id)
    assert res["status"] == "executed" and res["idempotent"] is False
    assert res["executed_ref"].startswith("smart_reminder:")
    # 后端只记录提醒(client 据此设 OS 闹钟);后端不冒充"已上闹钟"
    rems = db.query(SmartReminder).filter(SmartReminder.user_id == u.id).all()
    assert len(rems) == 1 and rems[0].title == "起床闹钟"
    assert rems[0].extra_data.get("kind") == "alarm_set"


def test_alarm_set_confirm_idempotent(db):
    u = _mk_user(db)
    wi = svc.propose_external_action(
        db, u.id, kind="alarm_set", title="吃药闹钟",
        payload={"alarm_time": "2026-06-23T20:00:00"},
    )
    svc.confirm(db, u.id, wi.id)
    again = svc.confirm(db, u.id, wi.id)
    assert again["idempotent"] is True and again["status"] == "executed"
    assert db.query(SmartReminder).filter(SmartReminder.user_id == u.id).count() == 1


# ═══════════════════════ 2. doctor_booking ═══════════════════════

def test_doctor_booking_generated_from_due_review(db):
    u = _mk_user(db)
    rs = _due_review(db, u.id)
    n = svc.generate_doctor_booking_drafts(db, u.id)
    assert n == 1
    items = [it for it in svc.list_pending(db, u.id) if it["kind"] == "doctor_booking"]
    assert len(items) == 1
    it = items[0]
    assert it["target_type"] == "review_schedule" and it["target_id"] == rs.id
    assert it["trust_tier"] == "manual_confirm"
    # R4:摘要是物流型,绝不诊断
    assert "可预约" in it["description"] and "得了" not in it["description"]


def test_doctor_booking_confirm_creates_reminder(db):
    u = _mk_user(db)
    _due_review(db, u.id, item="甲状腺功能", dept="内分泌科")
    svc.generate_doctor_booking_drafts(db, u.id)
    wi_id = [it for it in svc.list_pending(db, u.id) if it["kind"] == "doctor_booking"][0]["id"]
    res = svc.confirm(db, u.id, wi_id)
    assert res["status"] == "executed" and res["executed_ref"].startswith("smart_reminder:")
    rem = db.query(SmartReminder).filter(SmartReminder.user_id == u.id).first()
    assert rem is not None and "内分泌科" in (rem.message or "")
    # NO 真挂号:产物只是 SmartReminder,无任何订单/预约对象
    assert rem.extra_data.get("kind") == "doctor_booking"


def test_doctor_booking_cross_user_review_not_proposed(db):
    """IDOR:别人的 ReviewSchedule 绝不被本人扫到/提议。"""
    a = _mk_user(db)
    b = _mk_user(db)
    _due_review(db, b.id, item="B 的复查")  # 属于 B
    n = svc.generate_doctor_booking_drafts(db, a.id)  # A 来扫
    assert n == 0
    assert [it for it in svc.list_pending(db, a.id) if it["kind"] == "doctor_booking"] == []


def test_doctor_booking_far_future_not_proposed(db):
    u = _mk_user(db)
    _due_review(db, u.id, days=90)  # 90 天后,超 within_days=30 窗口
    assert svc.generate_doctor_booking_drafts(db, u.id) == 0


def test_doctor_booking_same_day_no_renag(db):
    u = _mk_user(db)
    _due_review(db, u.id)
    assert svc.generate_doctor_booking_drafts(db, u.id) == 1
    # 用户忽略 → 同日再扫不重复提
    for it in svc.list_pending(db, u.id):
        if it["kind"] == "doctor_booking":
            svc.dismiss(db, u.id, it["id"])
    assert svc.generate_doctor_booking_drafts(db, u.id) == 0


# ═══════════════════════ 3. food_order(DRAFT ONLY,可证惰性)═══════════════════════

# 任何疑似支付凭据的键 —— 断言它们绝不被持久化到 WriteIntent.payload。
_PAYMENT_KEYS = (
    "payment", "card", "credit_card", "cvv", "pay_token", "payment_token",
    "bank", "account_no", "alipay", "wechat_pay", "password", "credential",
)


def test_food_order_propose_confirm_is_inert_no_order_no_payment(db):
    u = _mk_user(db)
    wi = svc.propose_external_action(
        db, u.id, kind="food_order", title="午餐外卖",
        description="鸡胸肉沙拉套餐",
        payload={
            "dish": "鸡胸肉沙拉",
            "merchant": "轻食店",
            "price_summary": "¥38",
            "delivery_addr": "公司",
            "nutrition_estimate": "约 450kcal(估算来源:商家菜单)",
            "constraints": "低脂,符合代谢目标",
        },
    )
    assert wi is not None and wi.trust_tier == "manual_confirm"
    res = svc.confirm(db, u.id, wi.id)
    # confirm 是惰性 acknowledged —— 没有下单、没有 SmartReminder、没有任何外部副作用
    assert res["status"] == "executed" and res["executed_ref"] == "acknowledged"
    assert db.query(SmartReminder).filter(SmartReminder.user_id == u.id).count() == 0
    # 持久化 payload 里绝无任何支付凭据键
    persisted = db.query(WriteIntent).get(wi.id)
    keys_blob = " ".join(str(k).lower() for k in (persisted.payload or {}).keys())
    for pk in _PAYMENT_KEYS:
        assert pk not in keys_blob, f"payment key leaked into payload: {pk}"


@pytest.mark.asyncio
async def test_food_order_skill_gateway_is_inert_stub():
    """财务边界可证惰性:外卖 skill 网关恒抛 NotImplementedError(契约未就绪)。"""
    from app.services import food_order_skill_gateway

    assert issubclass(food_order_skill_gateway.FoodOrderSkillError, Exception)
    with pytest.raises(NotImplementedError):
        await food_order_skill_gateway.place_order(
            user_id=1, dish_summary="x", confirmation_token="tok",
        )


def test_food_order_payment_key_in_payload_rejected_fail_loud(db):
    """L4 硬门:任一支付凭据类 key 进 payload → 落库前 ValueError(端点 422),绝不静默落库。"""
    u = _mk_user(db)
    for bad_key in ("payment_token", "card_no", "支付密码", "alipay_credential", "bank_card"):
        with pytest.raises(ValueError):
            svc.propose_external_action(
                db, u.id, kind="food_order", title="外卖",
                payload={"dish": "面", bad_key: "leak"},
            )
    # 没有任何带支付 key 的意图落库
    assert [it for it in svc.list_pending(db, u.id) if it["kind"] == "food_order"] == []


def test_food_order_nested_payment_key_rejected_fail_loud(db):
    """L4 硬门(递归):支付凭据类 key 嵌在 payload 任意深度(dict/list 内)→ 落库前 ValueError
    (端点 422),绝不持久化。整份 payload 会落库,故必须递归扫,不能只看顶层 key。"""
    u = _mk_user(db)
    nested_payloads = [
        # 嵌套 dict
        {"dish": "面", "checkout": {"payment_token": "tok_live_123"}},
        # 更深一层
        {"dish": "面", "order": {"billing": {"card_number": "4111111111111111"}}},
        # 嵌在 list 里的 dict
        {"dish": "面", "items": [{"name": "饭"}, {"cvv": "123"}]},
        # 驼峰变体(paymentMethod)
        {"dish": "面", "meta": {"paymentMethod": "visa"}},
        # 中文支付密码嵌套
        {"dish": "面", "checkout": {"支付密码": "6789"}},
    ]
    for bad in nested_payloads:
        with pytest.raises(ValueError):
            svc.propose_external_action(
                db, u.id, kind="food_order", title="外卖", payload=bad,
            )
    # 没有任何带嵌套支付 key 的意图落库
    assert [it for it in svc.list_pending(db, u.id) if it["kind"] == "food_order"] == []


def test_food_order_gateway_has_no_payment_param():
    """contract 守门:place_order 签名里绝无任何支付凭据形参。"""
    import inspect

    from app.services import food_order_skill_gateway

    params = set(inspect.signature(food_order_skill_gateway.place_order).parameters.keys())
    for pk in _PAYMENT_KEYS + ("amount", "total", "price"):
        assert not any(pk in p for p in params), f"payment-ish param in gateway: {pk}"


# ═══════════════════════ 4. R4 guard(red-green)═══════════════════════

def test_food_order_summary_strips_quantified_diet_prescription(db):
    """R4:外卖摘要混进量化饮食处方(「必须吃X克蛋白」)→ 落库前被 guidance_validator strip。"""
    u = _mk_user(db)
    bad = "这份套餐不错,另外你今天必须吃200克蛋白质,每天吃50克坚果。"
    wi = svc.propose_external_action(
        db, u.id, kind="food_order", title="晚餐",
        payload={"user_visible_summary": bad},
    )
    assert wi is not None
    persisted = db.query(WriteIntent).get(wi.id)
    summary = persisted.payload["user_visible_summary"]
    # 量化处方被移除(redaction 占位)
    assert "必须吃200克" not in summary
    assert "每天吃50克" not in summary
    assert "[已移除非处方化建议]" in summary
    # fail-loud:违规记入 payload 审计
    assert persisted.payload.get("guidance_violations")
    assert len(persisted.payload["guidance_violations"]) >= 1


def test_food_order_observational_summary_untouched(db):
    """R4 不误伤:描述性营养估算(非命令式)原样保留。"""
    u = _mk_user(db)
    good = "这餐约 450kcal,蛋白约 35g(估算来源:商家菜单)。"
    wi = svc.propose_external_action(
        db, u.id, kind="food_order", title="午餐",
        payload={"user_visible_summary": good},
    )
    persisted = db.query(WriteIntent).get(wi.id)
    assert persisted.payload["user_visible_summary"] == good
    assert persisted.payload.get("guidance_violations") is None


# ═══════════════════════ 5. manual_confirm / 无自治写 / 回滚不假装成功 ═══════════════════════

def test_all_external_kinds_are_manual_confirm(db):
    u = _mk_user(db)
    for kind in ("alarm_set", "food_order", "doctor_booking"):
        wi = svc.propose_external_action(
            db, u.id, kind=kind, title=f"{kind} t",
            target_type="x", target_id=hash(kind) % 1000,
            payload={"alarm_time": "2026-06-23T07:00:00"} if kind == "alarm_set" else {},
        )
        assert wi is not None and wi.trust_tier == "manual_confirm"
        assert wi.status == "pending"  # 提议态,不自治执行


def test_propose_external_action_rejects_unknown_kind(db):
    u = _mk_user(db)
    with pytest.raises(ValueError):
        svc.propose_external_action(db, u.id, kind="wire_money", title="hack")


def test_external_action_double_confirm_idempotent(db):
    u = _mk_user(db)
    wi = svc.propose_external_action(
        db, u.id, kind="food_order", title="外卖", payload={"dish": "面"},
    )
    r1 = svc.confirm(db, u.id, wi.id)
    r2 = svc.confirm(db, u.id, wi.id)
    assert r1["idempotent"] is False and r2["idempotent"] is True
    assert db.query(WriteIntent).get(wi.id).status == "executed"


def test_external_action_idor_other_user_cannot_confirm(db):
    a = _mk_user(db)
    b = _mk_user(db)
    wi = svc.propose_external_action(db, a.id, kind="food_order", title="外卖", payload={})
    with pytest.raises(LookupError):
        svc.confirm(db, b.id, wi.id)
    assert db.query(WriteIntent).get(wi.id).status == "pending"


def test_external_action_failed_execute_rolls_back(db):
    """执行失败整体回滚(状态退回 pending),绝不假装成功 —— 用未知 kind 直接落库后 confirm 验证。"""
    u = _mk_user(db)
    # 绕过白名单直接落一条未知 kind(模拟 _execute 抛错路径),确保 confirm 不吞错
    wi = svc.propose(
        db, u.id, kind="alarm_set_BOGUS", title="x", description=None,
        source="test", target_type="t", target_id=1, payload={},
    )
    with pytest.raises(ValueError):
        svc.confirm(db, u.id, wi.id)
    db.expire_all()
    assert db.query(WriteIntent).get(wi.id).status == "pending"


# ═══════════════════════ 6. tier:三类全 P1,绝不 P0 ═══════════════════════

def test_external_action_kinds_are_p1_never_p0():
    from app.tasks.event_reminders import _KIND_TIER

    for kind in ("alarm_set", "food_order", "doctor_booking"):
        assert _KIND_TIER[kind] == "P1"
        assert _KIND_TIER[kind] != "P0"


# ═══════════════════════ 7. API 层:POST /write-intents 白名单 + propose→confirm ═══════════════════════

def _http_headers(db):
    from tests.conftest import create_authenticated_user
    _, token = create_authenticated_user(db)
    return {"Authorization": f"Bearer {token}"}


def test_api_propose_unknown_kind_returns_422(client, db):
    h = _http_headers(db)
    r = client.post("/api/v1/write-intents", json={"kind": "wire_money", "title": "hack"}, headers=h)
    assert r.status_code == 422


def test_api_propose_alarm_then_confirm(client, db):
    h = _http_headers(db)
    r = client.post(
        "/api/v1/write-intents",
        json={"kind": "alarm_set", "title": "起床", "payload": {"alarm_time": "2026-06-23T07:00:00"}},
        headers=h,
    )
    assert r.status_code == 200
    intent_id = r.json()["intent"]["id"]
    c = client.post(f"/api/v1/write-intents/{intent_id}/confirm", headers=h)
    assert c.status_code == 200
    assert c.json()["status"] == "executed"


def test_api_propose_food_order_strips_prescription(client, db):
    h = _http_headers(db)
    r = client.post(
        "/api/v1/write-intents",
        json={
            "kind": "food_order", "title": "晚餐",
            "payload": {"user_visible_summary": "你今天必须吃200克蛋白质。"},
        },
        headers=h,
    )
    assert r.status_code == 200
    summary = r.json()["intent"]["payload"]["user_visible_summary"]
    assert "必须吃200克" not in summary and "[已移除非处方化建议]" in summary


def test_api_propose_food_order_payment_key_returns_422(client, db):
    h = _http_headers(db)
    r = client.post(
        "/api/v1/write-intents",
        json={"kind": "food_order", "title": "外卖", "payload": {"payment_token": "leak"}},
        headers=h,
    )
    assert r.status_code == 422
