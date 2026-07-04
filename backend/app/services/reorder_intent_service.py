"""P5(D2)复购下单服务 —— 财务一等对象 `ReorderIntent` 的状态机(SCAFFOLD,不真下单)。

见 docs/specs/active/2026-06-22-p5-reorder-ordering.md(一等对象准入 Gate)、
docs/prd/2026-06-19-proactive-planning-prd.md §3.D2 + §5。

⚠️ 财务硬边界(本期 = SCAFFOLD,过财务安全评审):
- confirm 走到「调快手电商 Agent action 下单」时,`kuaishou_skill_gateway.place_order` 抛
  NotImplementedError → 本 service 抛 `ReorderSkillNotReady`(API 转 501),意图退回
  **安全态 user_confirmed**(已确认但未下单),**绝不**标 order_placed。
- 后端永不处理支付凭据、永不扣款、永不无逐笔确认下单。
- `auto_reorder_enabled` + `monthly_cap_cents` 仅落「常驻自动复购」的月额护栏结构
  (确定性 cap-check);本期无真单触发它,cap-check 仅作结构 + 测试守门。

不变量:
- user_id 一律由端点从 token 传入,所有查询按 user_id 过滤(IDOR 安全)。
- propose 幂等:同 (user, supplement, status=proposed) 已有 → 返回既有,不重复建。
- confirm 原子门:仅 (id,user,status=proposed) → user_confirmed,rowcount==1 守 + confirmed_at;
  双击下第二次 update 命中 0 行 → 幂等返回,不重复触发下单。
- cancel 仅 proposed/user_confirmed → cancelled。
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.agents import audit
from app.models.reorder_intent import ReorderIntent
from app.models.supplement import SupplementDefinition
from app.services import kuaishou_skill_gateway


class ReorderSkillNotReady(Exception):
    """快手电商 skill 契约未就绪(本期财务硬门)。端点据此返回 HTTP 501。

    与下单业务失败(→ order_failed)区分:这是「本期就到此为止」的边界,不是错误。
    意图保持在安全态 user_confirmed(已确认未下单),绝不进 order_placed。
    """


class ReorderCapExceeded(Exception):
    """常驻自动复购触碰月额上限(确定性护栏)。端点据此返回 409。

    本期无真单触发,仅结构 + 测试守门。
    """


def _view(ri: ReorderIntent) -> Dict[str, Any]:
    return {
        "id": ri.id,
        "supplement_id": ri.supplement_id,
        "quantity": ri.quantity,
        "brand": ri.brand,
        "spec": ri.spec,
        "status": ri.status,
        "kuaishou_order_id": ri.kuaishou_order_id,
        "auto_reorder_enabled": ri.auto_reorder_enabled,
        "monthly_cap_cents": ri.monthly_cap_cents,
        "notes": ri.notes,
        "created_at": ri.created_at.isoformat() if ri.created_at else None,
        "confirmed_at": ri.confirmed_at.isoformat() if ri.confirmed_at else None,
        "placed_at": ri.placed_at.isoformat() if ri.placed_at else None,
    }


def _assert_owned_supplement(db: Session, user_id: int, supplement_id: int) -> None:
    """IDOR 防护:supplement_id 必须属调用方,否则 LookupError(端点 → 404,且不建意图)。"""
    owned = (
        db.query(SupplementDefinition.id)
        .filter(
            SupplementDefinition.id == supplement_id,
            SupplementDefinition.user_id == user_id,
        )
        .first()
    )
    if owned is None:
        raise LookupError("supplement not found for user")


def list_reorder_intents(
    db: Session, user_id: int, status: Optional[str] = None
) -> List[Dict[str, Any]]:
    """列出用户的复购意图(按 user_id 过滤,IDOR 安全);可选按 status 过滤。"""
    q = db.query(ReorderIntent).filter(ReorderIntent.user_id == user_id)
    if status:
        q = q.filter(ReorderIntent.status == status)
    rows = q.order_by(ReorderIntent.created_at.desc()).all()
    return [_view(r) for r in rows]


def propose_reorder_intent(
    db: Session,
    user_id: int,
    *,
    supplement_id: int,
    quantity: int,
    brand: Optional[str] = None,
    spec: Optional[str] = None,
    auto_reorder_enabled: bool = False,
    monthly_cap_cents: Optional[int] = None,
) -> Dict[str, Any]:
    """提一个复购意图(proposed)。同 (user, supplement, status=proposed) 已有 → 返回既有(幂等)。

    IDOR:supplement_id 非调用方 → LookupError(端点 404)。quantity ≤0 由端点 422 兜住。
    """
    _assert_owned_supplement(db, user_id, supplement_id)

    existing = (
        db.query(ReorderIntent)
        .filter(
            ReorderIntent.user_id == user_id,
            ReorderIntent.supplement_id == supplement_id,
            ReorderIntent.status == "proposed",
        )
        .first()
    )
    if existing is not None:
        return _view(existing)  # 幂等:不重复建

    ri = ReorderIntent(
        user_id=user_id,
        supplement_id=supplement_id,
        quantity=quantity,
        brand=brand,
        spec=spec,
        status="proposed",
        auto_reorder_enabled=auto_reorder_enabled,
        monthly_cap_cents=monthly_cap_cents,
    )
    db.add(ri)
    db.commit()
    db.refresh(ri)
    return _view(ri)


def _monthly_spent_cents(db: Session, user_id: int) -> int:
    """本月已下单(order_placed)的金额合计(分)。

    本期无价格列(后端不存价格/支付),故合计恒 0 —— cap-check 结构在,真实金额来源待
    skill 契约就绪(回参带成交价)后接入。保留为确定性护栏的接缝。
    """
    return 0


def _check_monthly_cap(db: Session, ri: ReorderIntent) -> None:
    """常驻自动复购的月额上限护栏(确定性)。超限 → ReorderCapExceeded(端点 409)。

    仅当 auto_reorder_enabled 且 monthly_cap_cents 设定时校验。本期无真单 → 不会触发,
    但结构与测试到位:cap 一旦被真实金额填满即阻断,绝不静默放行。
    """
    if not ri.auto_reorder_enabled or ri.monthly_cap_cents is None:
        return
    spent = _monthly_spent_cents(db, ri.user_id)
    if spent >= ri.monthly_cap_cents:
        raise ReorderCapExceeded(
            f"monthly cap reached: spent={spent} cap={ri.monthly_cap_cents}"
        )


async def confirm_reorder_intent(
    db: Session, user_id: int, intent_id: int
) -> Dict[str, Any]:
    """用户逐笔强确认 → 调快手电商 skill 下单(本期 skill 未就绪 → ReorderSkillNotReady/501)。

    原子门:仅 (id,user,status=proposed) → user_confirmed(rowcount==1 守 + confirmed_at);
    双击下第二次命中 0 行 → 幂等返回,不重复触发下单。

    skill 调用结果分流:
      - NotImplementedError(本期硬门)→ 保持 user_confirmed(已确认未下单),抛
        ReorderSkillNotReady(端点 501)。**绝不** order_placed。
      - KuaishouSkillError / 业务 failed → order_failed + notes(fail loud,不假装成功)。
      - 成功 → order_placed + kuaishou_order_id + placed_at。
    """
    ri = (
        db.query(ReorderIntent)
        .filter(ReorderIntent.id == intent_id, ReorderIntent.user_id == user_id)
        .first()
    )
    if ri is None:
        raise LookupError("reorder_intent not found")  # 端点 → 404(含 IDOR)

    # 幂等:已确认/已下单/已失败/已取消 → 不重复推进(双确认安全)
    if ri.status != "proposed":
        return {**_view(ri), "idempotent": True}

    # 常驻自动复购月额护栏(确定性;本期无真单 → 不触发)
    _check_monthly_cap(db, ri)

    # 原子推进 proposed → user_confirmed(rowcount 守防并发双击)
    affected = (
        db.query(ReorderIntent)
        .filter(
            ReorderIntent.id == intent_id,
            ReorderIntent.user_id == user_id,
            ReorderIntent.status == "proposed",
        )
        .update(
            {"status": "user_confirmed", "confirmed_at": datetime.now(timezone.utc)},
            synchronize_session=False,
        )
    )
    if affected != 1:
        # 并发双击:别人先 claim 了 → 不重复下单
        db.rollback()
        db.refresh(ri)
        return {**_view(ri), "idempotent": True}
    db.commit()
    db.refresh(ri)

    # ── 财务接缝:调快手电商 skill 下单 ──
    # 本期 skill 契约未就绪 → place_order 抛 NotImplementedError。
    # 此处不传任何支付凭据;account_ref/confirmation_token 是 skill 契约就绪后接入的占位。
    try:
        result = await kuaishou_skill_gateway.place_order(
            supplement_id=ri.supplement_id,
            quantity=ri.quantity,
            user_kuaishou_account_ref="",   # 契约就绪后由账号绑定层提供(非支付凭据)
            confirmation_token="",          # 契约就绪后由服务端签发的一次性确认 token
            brand=ri.brand,
            spec=ri.spec,
        )
    except NotImplementedError:
        # 财务硬门:意图停在安全态 user_confirmed(已确认未下单),绝不 order_placed。
        audit.log_reorder_intent(
            db, user_id, intent_id=ri.id, supplement_id=ri.supplement_id,
            quantity=ri.quantity, outcome="skill_not_ready",
        )
        raise ReorderSkillNotReady(
            "快手电商 skill 契约未就绪:已记录你的逐笔确认,但本期不会下单(财务面待 skill "
            "就绪 + 安全评审)。"
        )
    except kuaishou_skill_gateway.KuaishouSkillError as e:
        # 网关/契约层不可恢复错误 → order_failed(fail loud,不假装成功)
        ri.status = "order_failed"
        ri.notes = f"skill_error: {e}"[:500]
        db.commit()
        db.refresh(ri)
        audit.log_reorder_intent(
            db, user_id, intent_id=ri.id, supplement_id=ri.supplement_id,
            quantity=ri.quantity, outcome="order_failed",
        )
        return _view(ri)

    # 契约就绪后的成功/业务失败分流(本期不可达 —— place_order 恒抛 NotImplementedError)
    if result.get("status") == "placed" and result.get("order_id"):
        ri.status = "order_placed"
        ri.kuaishou_order_id = str(result["order_id"])[:120]
        ri.placed_at = datetime.now(timezone.utc)
        ri.notes = None
        db.commit()
        db.refresh(ri)
        audit.log_reorder_intent(
            db, user_id, intent_id=ri.id, supplement_id=ri.supplement_id,
            quantity=ri.quantity, outcome="order_placed",
            kuaishou_order_id=ri.kuaishou_order_id,
        )
        return _view(ri)

    # 业务下单失败(库存/价格变动等)→ order_failed
    ri.status = "order_failed"
    ri.notes = (f"order_failed: {result.get('error')}" or "order_failed")[:500]
    db.commit()
    db.refresh(ri)
    audit.log_reorder_intent(
        db, user_id, intent_id=ri.id, supplement_id=ri.supplement_id,
        quantity=ri.quantity, outcome="order_failed",
    )
    return _view(ri)


def cancel_reorder_intent(db: Session, user_id: int, intent_id: int) -> Dict[str, Any]:
    """取消复购意图。仅 proposed / user_confirmed → cancelled;其它状态 → 幂等返回。"""
    ri = (
        db.query(ReorderIntent)
        .filter(ReorderIntent.id == intent_id, ReorderIntent.user_id == user_id)
        .first()
    )
    if ri is None:
        raise LookupError("reorder_intent not found")
    if ri.status in ("proposed", "user_confirmed"):
        ri.status = "cancelled"
        db.commit()
        db.refresh(ri)
    return _view(ri)
