"""GET /api/v1/schedule/today —— 每日时点日程(timing-solver)的客户端表面(cut 6 接活)。

把已落地但休眠的 day_schedule_service 求解结果投影给 mobile 当日时间轴 / Watch 当下时点。
只读 + 确定性求解:不写库、不生成/调剂量(R4)、不出因果裁决;rejected 是硬禁忌走告警通道。
user_id 取自 token(IDOR 安全)。见 docs/specs/active/2026-06-17-day-timing-schedule.md。
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.day_schedule_service import build_day_schedule

router = APIRouter(prefix="/schedule", tags=["schedule"])
logger = logging.getLogger(__name__)


@router.get("/today")
def get_today_schedule(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """当日时点日程:{scheduled, rejected, deferred}。

    读活跃 medications + user_profile(作息 + 上下班),按硬约束(药代/螯合/餐锚/昼夜/静默窗/
    工作窗)确定性求解。浮动项避开工作时段;锚点药/补剂/餐不受工作窗影响。

    disclaimer 随响应一起带出 hedge —— 即使将来 Watch 等别的客户端先消费本端点、还没接上
    展示层措辞,时点也不会以「处方」面目出现(safety review 建议:hedge 跟数据走)。
    """
    result = build_day_schedule(db, current_user.id)
    result["disclaimer"] = "建议时点,具体用法用量与时间请遵医嘱 / 产品说明;本表不替代医生处方。"
    return result
