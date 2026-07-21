"""统一健康议程 API(R1)。只读投影:今日该做什么,一处可见、跨端一致。"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from app.database import get_db
from app.models.user import User
from app.api.deps import get_current_user_required
from app.services import agenda_service
from app.services import health_protocol_service as proto_svc
from app.models.health_protocol import SKIP_REASONS
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agenda", tags=["统一健康议程"])


@router.get("/today")
async def agenda_today(
    followup_within_days: int = Query(default=14, le=120),
    mode: str = Query(default="regular", description="regular | smart | runtime"),
    max_items: int = Query(default=3, ge=1, le=10, description="smart mode top item limit"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """今日统一议程:默认普通投影;mode=smart/runtime 时返回可执行智能议程/运行时投影。"""
    if mode == "smart":
        return agenda_service.smart_today(db, current_user.id, followup_within_days, max_items=max_items)
    if mode == "runtime":
        return agenda_service.runtime_range_view(db, current_user.id, days=1, max_items_per_day=max_items)
    if mode != "regular":
        raise HTTPException(status_code=422, detail="mode 仅支持 regular、smart 或 runtime")
    return agenda_service.today(db, current_user.id, followup_within_days)


@router.get("/range")
async def agenda_range(
    days: int = Query(default=7, le=120),
    mode: str = Query(default="regular", description="regular | runtime"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """区间视图:常驻每日协议 + 窗口内按到期日排布的复查。"""
    if mode == "runtime":
        return agenda_service.runtime_range_view(db, current_user.id, days)
    if mode != "regular":
        raise HTTPException(status_code=422, detail="mode 仅支持 regular 或 runtime")
    return agenda_service.range_view(db, current_user.id, days)


class AgendaComplete(BaseModel):
    object_type: str            # health_protocol / medication / supplement
    object_id: int
    track: str = "protocol"     # protocol / manual(仅 health_protocol 用;med/supp 忽略)
    value: Optional[Dict[str, Any]] = None
    status: str = "done"        # done | skipped
    skip_reason: Optional[str] = None  # status=skipped 时必带,枚举见 SKIP_REASONS
    # F5b 多剂闭环:剂量槽 "HH:MM"。仅真多剂(med 的 reminder_times ≥2 个时点)由 push/spine
    # 项透传该剂的 slot —— 同药不同槽各闭环一条依从,BID 两剂不被同日幂等折成一次。
    # 单剂/每日一次:不传(None)→ complete_ref 不含 slot 键、行为与改前逐字节相同。
    slot: Optional[str] = None


class AgendaActionRef(BaseModel):
    object_type: str
    object_id: int


class AgendaSnooze(AgendaActionRef):
    minutes: int = Field(default=30, ge=5, le=240)


def _require_protocol_source(object_type: str) -> None:
    if object_type != "health_protocol":
        raise HTTPException(status_code=400, detail="该来源不支持稍后")


@router.post("/snooze")
async def agenda_snooze(
    data: AgendaSnooze,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """持久化今日协议的稍后状态；不写领域完成记录。"""
    _require_protocol_source(data.object_type)
    try:
        event = proto_svc.snooze_protocol(
            db,
            data.object_id,
            current_user.id,
            minutes=data.minutes,
            day=get_user_today(db, current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if event is None:
        raise HTTPException(status_code=404, detail="协议不存在")
    value = event.value or {}
    return {
        "object_type": data.object_type,
        "object_id": data.object_id,
        "status": event.status,
        "minutes": value.get("minutes", data.minutes),
        "snoozed_until": value.get("snoozed_until"),
    }


@router.post("/resume")
async def agenda_resume(
    data: AgendaActionRef,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """恢复今日被稍后的协议；重复请求返回同一 pending 状态。"""
    _require_protocol_source(data.object_type)
    try:
        result = proto_svc.resume_protocol(
            db,
            data.object_id,
            current_user.id,
            day=get_user_today(db, current_user.id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="稍后记录不存在")
    event, idempotent = result
    return {
        "object_type": data.object_type,
        "object_id": data.object_id,
        "status": event.status,
        "idempotent": idempotent,
    }


@router.post("/complete")
async def agenda_complete(
    data: AgendaComplete,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """统一完成路由:经议程脊柱闭环完成(翻 HealthEvent 生命周期 + 双轨回写真实 source)。

    懒物化:complete_by_ref 按 {object_type, object_id} 找/建议程 HealthEvent 再完成,
    所以本端点既写真实记录、又熄灭首页脊柱项,且支持 skipped(带 skip_reason)。
    幂等(双击一次效果)。强制 user_id 隔离(跨用户 / 不存在 → 404)。
    回写失败 → 422(不假装成功)。
    """
    from app.services import timeline_agenda_service as tas

    if data.status not in ("done", "skipped"):
        raise HTTPException(status_code=400, detail="status 仅支持 done 或 skipped")
    if data.status == "skipped" and not data.skip_reason:
        raise HTTPException(status_code=400, detail="status=skipped 时必须提供 skip_reason")
    if data.status == "skipped" and data.skip_reason is not None and data.skip_reason not in SKIP_REASONS:
        raise HTTPException(
            status_code=400, detail=f"未知 skip_reason(应为 {list(SKIP_REASONS)})")

    try:
        result = tas.complete_by_ref(
            db, current_user.id, data.object_type, data.object_id,
            status=data.status, skip_reason=data.skip_reason,
            track=data.track, value=data.value, slot=data.slot,
            day=get_user_today(db, current_user.id),
        )
    except LookupError:
        # 真实 source 不存在 / 非本人 → 404(不跨用户写、不假装成功)。
        raise HTTPException(status_code=404, detail="完成来源不存在")
    except tas.AgendaEventNotFound:
        raise HTTPException(status_code=404, detail="议程事件不存在")
    except tas.AgendaCompleteError as e:
        # 真实 source 回写失败 → 让客户端感知(不静默吞、不假装完成)。
        raise HTTPException(status_code=422, detail=f"完成回写失败: {e}")
    except ValueError as e:
        # 不支持的 object_type / 非法 status / skip_reason → 400(显式失败,不静默)。
        raise HTTPException(status_code=400, detail=str(e))

    # 响应为旧 shape 的超集:保留 object_type/object_id,叠加生命周期 + 回写事实,
    # 让只「成功即失效缓存」的存量 mobile 调用方不破。
    # wrote=本次是否真做了「完成/服用」领域写:done 回写真实记录 → True;skipped 现在也写
    # 源行(漏服事实/HealthProtocolEvent skipped),但它**不是依从完成** → wrote=False
    # (源行各分支自报 wrote);幂等终态短路(无 source_write)→ False(不二次回写,守去重)。
    source_write = result.get("source_write")
    wrote = bool(source_write and source_write.get("wrote"))
    return {
        "object_type": data.object_type,
        "object_id": data.object_id,
        "event_id": result.get("event_id"),
        "agenda_status": result.get("agenda_status"),
        "skip_reason": result.get("skip_reason"),
        "wrote": wrote,
        "idempotent": bool(result.get("idempotent")),
        "source_write": source_write,
    }
