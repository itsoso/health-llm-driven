"""Apple Watch Companion API(W1)。腕上摘要:状态灯 + 最重要行动 + 打点入口 + 关键推送。"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.watch_summary import build_watch_summary

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watch", tags=["Apple Watch Companion"])


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
