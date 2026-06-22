"""P5(D2)复购下单测试 —— 财务一等对象 ReorderIntent(SCAFFOLD,不真下单)。

核心:**财务边界可证为惰性**。
- place_order STUB 恒抛 NotImplementedError(财务硬门可证)。
- confirm → 501,意图停在 user_confirmed,**绝不** order_placed、无支付/扣款路径。
- propose 幂等去重、cancel 状态门、IDOR 404、quantity 422、月额护栏结构、list 过滤。
"""
import uuid

import pytest

from app.models.reorder_intent import ReorderIntent
from app.models.supplement import SupplementDefinition
from app.models.user import User
from app.services import kuaishou_skill_gateway
from app.services import reorder_intent_service as svc


# ─────────────────────────── fixtures / helpers ───────────────────────────

def _mk_user(db) -> User:
    u = User(
        username=f"p5_{uuid.uuid4().hex[:6]}",
        email=f"p5_{uuid.uuid4().hex[:6]}@x.com",
        hashed_password="x",
        name="p5",
        is_active=True,
        is_approved=True,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_supp(db, user_id, name="维生素D") -> SupplementDefinition:
    s = SupplementDefinition(user_id=user_id, name=name, is_active=True)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _headers(db, user) -> dict:
    from app.services.auth import auth_service
    return {"Authorization": f"Bearer {auth_service.create_access_token({'sub': str(user.id)})}"}


# ═══════════════════════ 财务硬门:place_order 永远惰性 ═══════════════════════

@pytest.mark.asyncio
async def test_place_order_stub_raises_not_implemented():
    """财务边界可证为惰性:快手 skill 网关恒抛 NotImplementedError(契约未就绪)。"""
    with pytest.raises(NotImplementedError):
        await kuaishou_skill_gateway.place_order(
            supplement_id=1,
            quantity=1,
            user_kuaishou_account_ref="acc",
            confirmation_token="tok",
        )


def test_kuaishou_skill_error_exists():
    """交接契约的错误类型存在(skill 就绪后用于 order_failed 分流)。"""
    assert issubclass(kuaishou_skill_gateway.KuaishouSkillError, Exception)


# ─────────────────────────── propose(幂等去重)───────────────────────────

def test_propose_creates_proposed(db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=2, brand="A", spec="60s")
    assert v["status"] == "proposed"
    assert v["quantity"] == 2
    assert v["kuaishou_order_id"] is None
    assert v["placed_at"] is None
    assert v["confirmed_at"] is None


def test_propose_idempotent_no_dup(db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    v1 = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=2)
    v2 = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=5)
    assert v1["id"] == v2["id"]  # 同 (user,supplement,proposed) → 返回既有
    # 库里只有一行 proposed
    n = db.query(ReorderIntent).filter(
        ReorderIntent.user_id == u.id, ReorderIntent.status == "proposed"
    ).count()
    assert n == 1


def test_propose_idor_supplement_not_owned(db):
    u = _mk_user(db)
    attacker = _mk_user(db)
    s = _mk_supp(db, u.id)
    with pytest.raises(LookupError):
        svc.propose_reorder_intent(db, attacker.id, supplement_id=s.id, quantity=1)
    # 且不建意图
    assert db.query(ReorderIntent).filter(ReorderIntent.user_id == attacker.id).count() == 0


# ─────────────────── confirm → 501,绝无 order_placed / 钱路 ───────────────────

@pytest.mark.asyncio
async def test_confirm_skill_not_ready_raises(db):
    """confirm 走到下单接缝 → ReorderSkillNotReady;意图停在 user_confirmed,绝不 order_placed。"""
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=1)
    with pytest.raises(svc.ReorderSkillNotReady):
        await svc.confirm_reorder_intent(db, u.id, v["id"])
    ri = db.get(ReorderIntent, v["id"])
    assert ri.status == "user_confirmed"          # 安全态:已确认未下单
    assert ri.confirmed_at is not None
    assert ri.status != "order_placed"            # 绝无下单
    assert ri.kuaishou_order_id is None           # 绝无订单号
    assert ri.placed_at is None                    # 绝无下单时刻


@pytest.mark.asyncio
async def test_confirm_double_is_idempotent(db):
    """第二次 confirm(已是 user_confirmed)→ 幂等返回,不重复触发下单(不再抛 501)。"""
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=1)
    with pytest.raises(svc.ReorderSkillNotReady):
        await svc.confirm_reorder_intent(db, u.id, v["id"])
    # 已是 user_confirmed → 再次 confirm 幂等返回
    res = await svc.confirm_reorder_intent(db, u.id, v["id"])
    assert res["status"] == "user_confirmed"
    assert res["idempotent"] is True


@pytest.mark.asyncio
async def test_confirm_idor_404_cross_user(db):
    u = _mk_user(db)
    attacker = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=1)
    with pytest.raises(LookupError):
        await svc.confirm_reorder_intent(db, attacker.id, v["id"])


# ─────────────────────────── cancel(状态门)───────────────────────────

def test_cancel_proposed(db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=1)
    res = svc.cancel_reorder_intent(db, u.id, v["id"])
    assert res["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_user_confirmed_allowed(db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=1)
    with pytest.raises(svc.ReorderSkillNotReady):
        await svc.confirm_reorder_intent(db, u.id, v["id"])
    res = svc.cancel_reorder_intent(db, u.id, v["id"])
    assert res["status"] == "cancelled"  # user_confirmed → cancelled 允许


def test_cancel_already_cancelled_idempotent(db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=1)
    svc.cancel_reorder_intent(db, u.id, v["id"])
    res = svc.cancel_reorder_intent(db, u.id, v["id"])  # 再取消 → 幂等,仍 cancelled
    assert res["status"] == "cancelled"


def test_cancel_idor_404(db):
    u = _mk_user(db)
    attacker = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=1)
    with pytest.raises(LookupError):
        svc.cancel_reorder_intent(db, attacker.id, v["id"])


# ─────────────────────────── 月额护栏(结构)───────────────────────────

@pytest.mark.asyncio
async def test_monthly_cap_structure_blocks_when_exceeded(db, monkeypatch):
    """常驻自动复购 + 月额上限,且本月已花满 → ReorderCapExceeded(确定性护栏,绝不静默放行)。"""
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(
        db, u.id, supplement_id=s.id, quantity=1,
        auto_reorder_enabled=True, monthly_cap_cents=1000,
    )
    # 强制本月已花满(护栏结构:真实金额来源待 skill 契约就绪)
    monkeypatch.setattr(svc, "_monthly_spent_cents", lambda _db, _uid: 1000)
    with pytest.raises(svc.ReorderCapExceeded):
        await svc.confirm_reorder_intent(db, u.id, v["id"])
    # 超限被挡 → 意图仍 proposed,未推进、未下单
    ri = db.get(ReorderIntent, v["id"])
    assert ri.status == "proposed"


@pytest.mark.asyncio
async def test_monthly_cap_not_enforced_when_disabled(db):
    """未开常驻自动复购 → 不走 cap-check;confirm 仍到财务硬门 501(不被 cap 误挡)。"""
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    v = svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=1)  # auto=False
    with pytest.raises(svc.ReorderSkillNotReady):
        await svc.confirm_reorder_intent(db, u.id, v["id"])


# ─────────────────────────── list(过滤)───────────────────────────

def test_list_filters_by_status(db):
    u = _mk_user(db)
    s1 = _mk_supp(db, u.id, "A")
    s2 = _mk_supp(db, u.id, "B")
    v1 = svc.propose_reorder_intent(db, u.id, supplement_id=s1.id, quantity=1)
    svc.propose_reorder_intent(db, u.id, supplement_id=s2.id, quantity=1)
    svc.cancel_reorder_intent(db, u.id, v1["id"])

    all_items = svc.list_reorder_intents(db, u.id)
    assert len(all_items) == 2
    proposed = svc.list_reorder_intents(db, u.id, status="proposed")
    assert len(proposed) == 1 and proposed[0]["status"] == "proposed"
    cancelled = svc.list_reorder_intents(db, u.id, status="cancelled")
    assert len(cancelled) == 1 and cancelled[0]["status"] == "cancelled"


def test_list_scoped_to_user(db):
    u = _mk_user(db)
    other = _mk_user(db)
    s = _mk_supp(db, u.id)
    svc.propose_reorder_intent(db, u.id, supplement_id=s.id, quantity=1)
    assert svc.list_reorder_intents(db, other.id) == []  # IDOR:别人看不到


# ═══════════════════════════ API 层(端到端 shape）═══════════════════════════

def test_api_propose_and_list(client, db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    h = _headers(db, u)
    r = client.post("/api/v1/reorder-intents",
                    json={"supplement_id": s.id, "quantity": 3}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "proposed" and body["quantity"] == 3

    rl = client.get("/api/v1/reorder-intents", headers=h)
    assert rl.status_code == 200
    assert len(rl.json()["items"]) == 1


def test_api_quantity_required_422(client, db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    h = _headers(db, u)
    # 缺 quantity
    r = client.post("/api/v1/reorder-intents", json={"supplement_id": s.id}, headers=h)
    assert r.status_code == 422
    # quantity <= 0
    r0 = client.post("/api/v1/reorder-intents",
                     json={"supplement_id": s.id, "quantity": 0}, headers=h)
    assert r0.status_code == 422
    rneg = client.post("/api/v1/reorder-intents",
                       json={"supplement_id": s.id, "quantity": -2}, headers=h)
    assert rneg.status_code == 422


def test_api_propose_idor_404(client, db):
    u = _mk_user(db)
    attacker = _mk_user(db)
    s = _mk_supp(db, u.id)
    r = client.post("/api/v1/reorder-intents",
                    json={"supplement_id": s.id, "quantity": 1},
                    headers=_headers(db, attacker))
    assert r.status_code == 404


def test_api_confirm_returns_501_skill_stubbed(client, db):
    """API 财务硬门:confirm → 501;库里意图停在 user_confirmed,绝无 order_placed。"""
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    h = _headers(db, u)
    pr = client.post("/api/v1/reorder-intents",
                     json={"supplement_id": s.id, "quantity": 1}, headers=h)
    intent_id = pr.json()["id"]
    r = client.post(f"/api/v1/reorder-intents/{intent_id}/confirm", headers=h)
    assert r.status_code == 501, r.text
    ri = db.get(ReorderIntent, intent_id)
    assert ri.status == "user_confirmed"
    assert ri.kuaishou_order_id is None
    # 全库无任何 order_placed 行(财务路径惰性)
    assert db.query(ReorderIntent).filter(ReorderIntent.status == "order_placed").count() == 0


def test_api_confirm_idor_404(client, db):
    u = _mk_user(db)
    attacker = _mk_user(db)
    s = _mk_supp(db, u.id)
    pr = client.post("/api/v1/reorder-intents",
                     json={"supplement_id": s.id, "quantity": 1}, headers=_headers(db, u))
    intent_id = pr.json()["id"]
    r = client.post(f"/api/v1/reorder-intents/{intent_id}/confirm",
                    headers=_headers(db, attacker))
    assert r.status_code == 404


def test_api_cancel(client, db):
    u = _mk_user(db)
    s = _mk_supp(db, u.id)
    h = _headers(db, u)
    pr = client.post("/api/v1/reorder-intents",
                     json={"supplement_id": s.id, "quantity": 1}, headers=h)
    intent_id = pr.json()["id"]
    r = client.post(f"/api/v1/reorder-intents/{intent_id}/cancel", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
