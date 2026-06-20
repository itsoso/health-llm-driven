"""D1 复购检测 —— 按依从消耗 + 库存估「快用完」(P3:检测 + 提醒,**不下单**)。

数据流:
    SupplementRecord(依从打卡, 估日消耗) + SupplementInventory(剩余量)
        → days_remaining = units_remaining / daily_consumption
        → status: low(≤7 天) / ok / unknown(缺基础数据)
        → 低库存交给 write_intent「该补货了」(由 scan task / generate fn 消费)

边界(safety):本模块只算物流数字,不含价格/支付/订单/购买动作 —— 财务面是 PRD §3.D2(P5),
要过 governance Gate + 财务安全评审,本期严禁触及。措辞 hedged,非医疗建议、非处方。

纯核函数 `compute_status` 无 DB(可单测日消耗/剩余天数/阈值);DB 包装 `detect_for_user`
聚合用户活跃补剂 + 库存 + 依从窗口,产出 InventoryItem dict 列表(端点直接返回)。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

# 低库存阈值(天):剩余 ≤ 此值 → status=low → 触发复购提醒
LOW_DAYS_THRESHOLD = 7
# 日消耗估算的回看窗口(天)
CONSUMPTION_WINDOW_DAYS = 30
# 窗口内最少多少天有打卡才用打卡估;否则回退到 prescribed 默认
MIN_LOGS_FOR_ESTIMATE = 3
# prescribed 回退:本仓补剂定义无显式 frequency 字段,补剂默认每日 1 单位
DEFAULT_DAILY_UNITS = 1.0


@dataclass(frozen=True)
class ReorderStatus:
    daily_consumption: Optional[float]
    days_remaining: Optional[float]
    status: str  # "ok" | "low" | "unknown"


def estimate_daily_consumption(
    taken_days_in_window: int,
    window_days: int = CONSUMPTION_WINDOW_DAYS,
    *,
    has_active_definition: bool = True,
) -> Optional[float]:
    """从窗口内的 taken 打卡天数估日消耗(单位/天)。

    - 打卡数 ≥ MIN_LOGS_FOR_ESTIMATE → taken_days / window_days(实际依从率 × 1 单位)。
    - 打卡数不足但补剂仍 active → 回退到 prescribed 默认(每日 1 单位)。
    - 无活跃定义且无打卡 → None(无估算依据)。

    纯函数(无 DB),便于单测。window_days 必须 > 0。
    """
    if window_days <= 0:
        return None
    if taken_days_in_window >= MIN_LOGS_FOR_ESTIMATE:
        rate = taken_days_in_window / window_days
        return rate if rate > 0 else None
    if has_active_definition:
        return DEFAULT_DAILY_UNITS
    return None


def compute_status(
    units_remaining: Optional[int],
    daily_consumption: Optional[float],
) -> ReorderStatus:
    """纯核:由剩余量 + 日消耗算 days_remaining 与状态。

    - units_remaining 或 daily_consumption 缺失/非正 → status=unknown, days_remaining=None。
    - days_remaining ≤ LOW_DAYS_THRESHOLD → low,否则 ok。
    """
    if units_remaining is None or daily_consumption is None or daily_consumption <= 0:
        return ReorderStatus(
            daily_consumption=daily_consumption,
            days_remaining=None,
            status="unknown",
        )
    days_remaining = units_remaining / daily_consumption
    status = "low" if days_remaining <= LOW_DAYS_THRESHOLD else "ok"
    return ReorderStatus(
        daily_consumption=daily_consumption,
        days_remaining=days_remaining,
        status=status,
    )


def _taken_days_in_window(db: Session, user_id: int, supplement_id: int, window_days: int) -> int:
    from app.models.supplement import SupplementRecord

    start = date.today() - timedelta(days=window_days)
    return (
        db.query(SupplementRecord.id)
        .filter(
            SupplementRecord.user_id == user_id,
            SupplementRecord.supplement_id == supplement_id,
            SupplementRecord.record_date >= start,
            SupplementRecord.taken.is_(True),
        )
        .count()
    )


def detect_for_user(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """聚合用户活跃补剂 + 库存 + 依从,产出 InventoryItem dict 列表。

    一项 = 一个活跃补剂定义。缺库存行 → units_remaining=None, status=unknown。
    brand/spec 取库存行(缺省 "")。days_remaining 可能是小数。
    """
    from app.models.supplement import SupplementDefinition
    from app.models.supplement_inventory import SupplementInventory

    defs = (
        db.query(SupplementDefinition)
        .filter(
            SupplementDefinition.user_id == user_id,
            SupplementDefinition.is_active,
        )
        .order_by(SupplementDefinition.sort_order, SupplementDefinition.id)
        .all()
    )

    # 一次取齐该用户库存,内存映射(避免 N+1)
    inv_rows = (
        db.query(SupplementInventory)
        .filter(SupplementInventory.user_id == user_id)
        .all()
    )
    inv_by_supp = {r.supplement_id: r for r in inv_rows}

    items: List[Dict[str, Any]] = []
    for d in defs:
        inv = inv_by_supp.get(d.id)
        units_remaining = inv.units_remaining if inv else None
        taken_days = _taken_days_in_window(db, user_id, d.id, CONSUMPTION_WINDOW_DAYS)
        daily = estimate_daily_consumption(
            taken_days, CONSUMPTION_WINDOW_DAYS, has_active_definition=True
        )
        st = compute_status(units_remaining, daily)
        items.append(
            {
                "supplement_id": d.id,
                "name": d.name,
                "brand": (inv.brand if inv and inv.brand else ""),
                "spec": (inv.spec if inv and inv.spec else ""),
                "units_remaining": units_remaining,
                "daily_consumption": st.daily_consumption,
                "days_remaining": st.days_remaining,
                "status": st.status,
            }
        )
    return items


def low_items_for_user(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """仅返回 status=low 的项(供复购提醒扫描消费)。"""
    return [it for it in detect_for_user(db, user_id) if it["status"] == "low"]
