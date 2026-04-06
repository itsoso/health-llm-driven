"""慢病风险评估 API"""
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_required
from app.database import get_db
from app.models.user import User
from app.services.chronic_risk_service import chronic_risk_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health/chronic-risk", tags=["慢病风险"])


@router.get("")
async def get_comprehensive_risk(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """慢病风险综合评估（心血管 + 代谢综合征 + 90天趋势）"""
    logger.info(f"[ChronicRisk] 用户 {current_user.id} 请求综合风险评估")
    return chronic_risk_service.assess_comprehensive_risk(db=db, user_id=current_user.id)


@router.get("/cardiovascular")
async def get_cardiovascular_risk(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """心血管风险评估（改良 Framingham）"""
    logger.info(f"[ChronicRisk] 用户 {current_user.id} 请求心血管风险评估")
    return chronic_risk_service.assess_cardiovascular_risk(db=db, user_id=current_user.id)


@router.get("/metabolic")
async def get_metabolic_syndrome(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """代谢综合征评估（IDF 标准）"""
    logger.info(f"[ChronicRisk] 用户 {current_user.id} 请求代谢综合征评估")
    return chronic_risk_service.assess_metabolic_syndrome(db=db, user_id=current_user.id)
