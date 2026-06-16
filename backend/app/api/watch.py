"""Apple Watch Companion API(W1)。腕上摘要:状态灯 + 最重要行动 + 打点入口 + 关键推送。

W1.5(本刀):到点项一键完成 + 服药/补剂依从回写。腕上不持 user_id,经 iPhone 中继携 token,
后端从 token 取 user_id(绝不信任客户端 user_id)。详见 docs/design-watch-action-complete.md。
"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services import agenda_service
from app.services import health_protocol_service as proto_svc
from app.services.watch_summary import build_watch_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watch", tags=["Apple Watch Companion"])

# action_id 编码: agenda-{object_type}-{object_id}(与 client_events meta 零翻译)
_ACTION_ID_RE = re.compile(r"^agenda-(?P<ot>[a-z_]+)-(?P<oid>\d+)$")

# source_model → 回写表的 written 标签(响应给 watch,稳定不随幂等变化)
_WRITTEN_BY_SOURCE_MODEL = {
    "medication_logs": "medication_log",
    "supplement_records": "supplement_record",
    "diet_records": "diet_record",
    "water_records": "water_record",
}


@router.get("/summary")
async def watch_summary(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """腕上摘要(只读投影 agenda.today → watch 优化视图)。

    watch 冷启动 / complication 刷新拉这个:一眼看到今日状态灯 + 最该做的事 +
    打点入口 + 该推到手腕的关键信息(运动/补剂/睡眠/复查)。
    """
    return build_watch_summary(db, current_user.id)


@router.post("/actions/{action_id}/complete")
async def complete_action(
    action_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """腕上「一键已做」→ 完成到点项,完成事实落真实业务表(用药/补剂依从)。

    - user_id 取自 token(绝不信任客户端)。
    - action_id 解析失败 / 非 health_protocol 源 → 400(fail loud)。
    - 协议不存在或非本人(IDOR)→ 404。
    - 幂等:首次「非完成→完成」才落领域记录;重复 POST 不重复写。
    - 请求内禁 build_twin(本端点只操作协议/领域表)。
    """
    m = _ACTION_ID_RE.match(action_id)
    if not m:
        raise HTTPException(status_code=400, detail="action_id 格式非法")
    object_type = m.group("ot")
    object_id = int(m.group("oid"))

    if object_type != "health_protocol":
        raise HTTPException(status_code=400, detail="该来源不支持腕上完成")

    try:
        result = agenda_service.complete_item(
            db, current_user.id, object_type, object_id, track="protocol", value=None
        )
    except ValueError:
        # 仅 health_protocol 走到这里 → 唯一 ValueError 是「协议不存在/非本人」(含 IDOR)
        raise HTTPException(status_code=404, detail="协议不存在")

    # written 标签由协议 source_model 推导(user 过滤,IDOR 安全;不进 build_twin)
    p = proto_svc.get_protocol(db, object_id, current_user.id)
    written = _WRITTEN_BY_SOURCE_MODEL.get(p.source_model, "none") if p else "none"

    return {
        "action_id": action_id,
        "object_type": result["object_type"],
        "object_id": result["object_id"],
        "status": "completed",
        "written": written,
    }
