"""目标管理API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import date
from pydantic import BaseModel
from app.database import get_db
from app.schemas.goal import GoalCreate, GoalResponse, GoalProgressCreate
from app.models.goal import Goal, GoalProgress, GoalStatus, GoalType, GoalPeriod
from app.models.user import User
from app.services.goal_management import GoalManagementService
from app.services.goal_guidance import goal_guidance_service
from app.api.deps import get_current_user_required

router = APIRouter()


# ========== 新增：目标引导请求模型 ==========

class GoalGuidanceRequest(BaseModel):
    """目标引导请求"""
    goal_type: str  # 接受字符串，如 RUNNING, WEIGHT_LOSS, CARDIO 等
    goal_description: Optional[str] = ""
    target_value: Optional[float] = None


@router.post("/", response_model=GoalResponse)
def create_goal(
    goal: GoalCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """创建目标（需要登录）"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"[创建目标] 用户 {current_user.id} 请求创建目标，数据: {goal.model_dump()}")
        
        # 强制使用当前用户ID
        goal_data = goal.model_dump()
        goal_data["user_id"] = current_user.id
        from app.schemas.goal import GoalCreate as GC
        goal = GC(**goal_data)
        service = GoalManagementService()
        result = service.create_goal(db, goal)
        
        logger.info(f"[创建目标] 目标创建成功，ID: {result.id}")
        return result
    except Exception as e:
        logger.error(f"[创建目标] 创建失败: {e}", exc_info=True)
        raise


# ========== /me 端点必须在 /user/{user_id} 之前定义 ==========

@router.get("/me", response_model=List[GoalResponse])
def get_my_goals(
    status: Optional[str] = None,
    goal_type: Optional[str] = None,
    goal_period: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取当前用户目标（需要登录）"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # 转换字符串参数为枚举类型
        status_enum = GoalStatus(status) if status else None
        goal_type_enum = GoalType(goal_type) if goal_type else None
        goal_period_enum = GoalPeriod(goal_period) if goal_period else None
        
        logger.info(f"[获取我的目标] 用户 {current_user.id}, status={status_enum}, type={goal_type_enum}, period={goal_period_enum}")
        
        service = GoalManagementService()
        goals = service.get_user_goals(db, current_user.id, status_enum, goal_type_enum, goal_period_enum)
        
        logger.info(f"[获取我的目标] 找到 {len(goals)} 个目标")
        return goals
    except ValueError as e:
        logger.error(f"[获取我的目标] 参数错误: {e}")
        raise HTTPException(status_code=400, detail=f"无效的参数: {str(e)}")
    except Exception as e:
        logger.error(f"[获取我的目标] 查询失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.get("/user/{user_id}", response_model=List[GoalResponse])
def get_user_goals(
    user_id: int,
    status: Optional[str] = None,
    goal_type: Optional[str] = None,
    goal_period: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """获取用户目标（需要登录，只能查看自己的）"""
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")
    
    try:
        # 转换字符串参数为枚举类型
        status_enum = GoalStatus(status) if status else None
        goal_type_enum = GoalType(goal_type) if goal_type else None
        goal_period_enum = GoalPeriod(goal_period) if goal_period else None
        
        service = GoalManagementService()
        return service.get_user_goals(db, current_user.id, status_enum, goal_type_enum, goal_period_enum)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"无效的参数: {str(e)}")


@router.post("/{goal_id}/progress", response_model=dict)
def update_goal_progress(
    goal_id: int,
    progress_date: date,
    progress_value: Optional[float] = None,
    db: Session = Depends(get_db)
):
    """更新目标进展"""
    service = GoalManagementService()
    progress = service.update_goal_progress(db, goal_id, progress_date, progress_value)
    return {"message": "更新成功", "progress_id": progress.id}


@router.get("/{goal_id}/progress", response_model=List[dict])
def get_goal_progress(
    goal_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """获取目标进展记录"""
    service = GoalManagementService()
    progress_list = service.get_goal_progress(db, goal_id, start_date, end_date)
    return [
        {
            "id": p.id,
            "progress_date": p.progress_date.isoformat(),
            "progress_value": p.progress_value,
            "completion_percentage": p.completion_percentage,
        }
        for p in progress_list
    ]


@router.post("/generate-from-analysis/{user_id}", response_model=List[GoalResponse])
def generate_goals_from_analysis(
    user_id: int,
    db: Session = Depends(get_db)
):
    """基于健康分析结果自动生成目标"""
    service = GoalManagementService()
    goals = service.generate_goals_from_analysis(db, user_id)
    return goals


@router.post("/me/generate-from-analysis", response_model=List[GoalResponse])
def generate_my_goals_from_analysis(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """基于当前用户的健康分析结果自动生成目标（需要登录）"""
    service = GoalManagementService()
    goals = service.generate_goals_from_analysis(db, current_user.id)
    return goals


@router.post("/guidance", response_model=Dict[str, Any])
def get_goal_guidance(
    request: GoalGuidanceRequest,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
):
    """
    获取目标智能引导
    
    基于张展晖课程知识库和用户数据，生成个性化的训练建议：
    - 心率区间计算（基于年龄和静息心率）
    - 训练计划建议（频率、时长、强度分配）
    - 课程知识要点
    - 个性化建议
    
    需要登录
    """
    guidance = goal_guidance_service.generate_goal_guidance(
        db=db,
        user_id=current_user.id,
        goal_type=request.goal_type,
        goal_description=request.goal_description,
        target_value=request.target_value
    )
    
    if not guidance.get("success"):
        raise HTTPException(
            status_code=500,
            detail=guidance.get("message", "生成引导失败")
        )
    
    return guidance


@router.get("/{goal_id}/completion", response_model=dict)
def check_goal_completion(
    goal_id: int,
    check_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """检查目标完成情况"""
    service = GoalManagementService()
    return service.check_goal_completion(db, goal_id, check_date)

