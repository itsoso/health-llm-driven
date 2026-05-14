"""Personal Health Trajectory Agent API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.health_trajectory import build_health_trajectory_snapshot

router = APIRouter(prefix="/trajectory", tags=["trajectory"])


@router.get("/me")
def get_my_health_trajectory(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """获取当前用户疾病上游健康轨迹快照."""
    return build_health_trajectory_snapshot(db, current_user.id)
