"""目标管理服务"""
from typing import List, Dict, Any, Optional
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.goal import Goal, GoalProgress, GoalType, GoalPeriod, GoalStatus
from app.schemas.goal import GoalCreate, GoalProgressCreate
from app.services.health_analysis import HealthAnalysisService


class GoalManagementService:
    """目标管理服务"""
    
    def __init__(self):
        self.health_analysis = HealthAnalysisService()
    
    def create_goal(
        self,
        db: Session,
        goal_create: GoalCreate
    ) -> Goal:
        """创建目标"""
        db_goal = Goal(**goal_create.model_dump())
        db.add(db_goal)
        db.commit()
        db.refresh(db_goal)
        return db_goal
    
    def get_user_goals(
        self,
        db: Session,
        user_id: int,
        status: Optional[GoalStatus] = None,
        goal_type: Optional[GoalType] = None,
        goal_period: Optional[GoalPeriod] = None
    ) -> List[Goal]:
        """获取用户目标"""
        query = db.query(Goal).filter(Goal.user_id == user_id)
        
        if status:
            query = query.filter(Goal.status == status)
        if goal_type:
            query = query.filter(Goal.goal_type == goal_type)
        if goal_period:
            query = query.filter(Goal.goal_period == goal_period)
        
        return query.order_by(Goal.priority.desc(), Goal.created_at.desc()).all()
    
    def update_goal_progress(
        self,
        db: Session,
        goal_id: int,
        progress_date: date,
        progress_value: Optional[float] = None
    ) -> GoalProgress:
        """更新目标进展"""
        goal = db.query(Goal).filter(Goal.id == goal_id).first()
        if not goal:
            raise ValueError("目标不存在")
        
        # 计算完成百分比
        completion_percentage = None
        if goal.target_value and progress_value is not None:
            completion_percentage = (progress_value / goal.target_value) * 100
        
        # 检查是否已存在该日期的进展记录
        existing = db.query(GoalProgress).filter(
            GoalProgress.goal_id == goal_id,
            GoalProgress.progress_date == progress_date
        ).first()
        
        if existing:
            existing.progress_value = progress_value
            existing.completion_percentage = completion_percentage
            db.commit()
            db.refresh(existing)
            return existing
        else:
            progress = GoalProgress(
                goal_id=goal_id,
                progress_date=progress_date,
                progress_value=progress_value,
                completion_percentage=completion_percentage
            )
            db.add(progress)
            db.commit()
            db.refresh(progress)
            
            # 更新目标的当前值
            if goal.goal_period == GoalPeriod.DAILY:
                goal.current_value = progress_value
            elif goal.goal_period == GoalPeriod.WEEKLY:
                # 计算本周的总值
                week_start = progress_date - timedelta(days=progress_date.weekday())
                week_progress = db.query(GoalProgress).filter(
                    GoalProgress.goal_id == goal_id,
                    GoalProgress.progress_date >= week_start,
                    GoalProgress.progress_date <= progress_date
                ).all()
                goal.current_value = sum(p.progress_value or 0 for p in week_progress)
            elif goal.goal_period == GoalPeriod.MONTHLY:
                # 计算本月的总值
                month_start = date(progress_date.year, progress_date.month, 1)
                month_progress = db.query(GoalProgress).filter(
                    GoalProgress.goal_id == goal_id,
                    GoalProgress.progress_date >= month_start,
                    GoalProgress.progress_date <= progress_date
                ).all()
                goal.current_value = sum(p.progress_value or 0 for p in month_progress)
            
            db.commit()
            db.refresh(goal)
            
            return progress
    
    def get_goal_progress(
        self,
        db: Session,
        goal_id: int,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[GoalProgress]:
        """获取目标进展记录"""
        query = db.query(GoalProgress).filter(GoalProgress.goal_id == goal_id)
        
        if start_date:
            query = query.filter(GoalProgress.progress_date >= start_date)
        if end_date:
            query = query.filter(GoalProgress.progress_date <= end_date)
        
        return query.order_by(GoalProgress.progress_date.desc()).all()
    
    def generate_goals_from_analysis(
        self,
        db: Session,
        user_id: int
    ) -> List[Goal]:
        """
        基于健康分析结果自动生成目标
        
        这个方法会：
        1. 分析用户的健康问题
        2. 根据问题生成相应的目标
        3. 返回生成的目标列表
        """
        analysis = self.health_analysis.analyze_health_issues(db, user_id)
        
        goals = []
        today = date.today()
        
        # 基于分析结果生成目标（这里简化实现，实际可以更智能）
        issues = analysis.get("issues", [])
        recommendations = analysis.get("recommendations", [])
        
        # 示例：如果睡眠质量有问题，生成睡眠目标
        if any("睡眠" in issue for issue in issues):
            sleep_goal = Goal(
                user_id=user_id,
                goal_type=GoalType.SLEEP,
                goal_period=GoalPeriod.DAILY,
                title="改善睡眠质量",
                description="提高每日睡眠分数和深度睡眠时长",
                target_value=80,
                target_unit="睡眠分数",
                start_date=today,
                implementation_steps="1. 保持规律作息\n2. 睡前1小时避免使用电子设备\n3. 保持卧室环境舒适",
                status=GoalStatus.ACTIVE,
                priority=8
            )
            goals.append(sleep_goal)
        
        # 示例：如果运动不足，生成运动目标
        if any("运动" in rec or "锻炼" in rec for rec in recommendations):
            exercise_goal = Goal(
                user_id=user_id,
                goal_type=GoalType.EXERCISE,
                goal_period=GoalPeriod.DAILY,
                title="每日运动",
                description="保持每日适量运动",
                target_value=30,
                target_unit="分钟",
                start_date=today,
                implementation_steps="1. 每天至少30分钟中等强度运动\n2. 可以分多次完成\n3. 选择喜欢的运动方式",
                status=GoalStatus.ACTIVE,
                priority=7
            )
            goals.append(exercise_goal)
        
        # 保存生成的目标
        for goal in goals:
            db.add(goal)
        db.commit()
        
        return goals
    
    def check_goal_completion(
        self,
        db: Session,
        goal_id: int,
        check_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """检查目标完成情况"""
        if check_date is None:
            check_date = date.today()
        
        goal = db.query(Goal).filter(Goal.id == goal_id).first()
        if not goal:
            return {"error": "目标不存在"}
        
        # 根据目标周期获取相应的进展
        if goal.goal_period == GoalPeriod.DAILY:
            progress = db.query(GoalProgress).filter(
                GoalProgress.goal_id == goal_id,
                GoalProgress.progress_date == check_date
            ).first()
        elif goal.goal_period == GoalPeriod.WEEKLY:
            week_start = check_date - timedelta(days=check_date.weekday())
            progress_list = db.query(GoalProgress).filter(
                GoalProgress.goal_id == goal_id,
                GoalProgress.progress_date >= week_start,
                GoalProgress.progress_date <= check_date
            ).all()
            total_progress = sum(p.progress_value or 0 for p in progress_list)
            progress = type('obj', (object,), {'progress_value': total_progress})()
        elif goal.goal_period == GoalPeriod.MONTHLY:
            month_start = date(check_date.year, check_date.month, 1)
            progress_list = db.query(GoalProgress).filter(
                GoalProgress.goal_id == goal_id,
                GoalProgress.progress_date >= month_start,
                GoalProgress.progress_date <= check_date
            ).all()
            total_progress = sum(p.progress_value or 0 for p in progress_list)
            progress = type('obj', (object,), {'progress_value': total_progress})()
        else:
            progress = None
        
        current_value = progress.progress_value if progress and hasattr(progress, 'progress_value') else 0
        target_value = goal.target_value or 0
        
        is_completed = current_value >= target_value if target_value > 0 else False
        completion_percentage = (current_value / target_value * 100) if target_value > 0 else 0
        
        return {
            "goal_id": goal_id,
            "goal_title": goal.title,
            "current_value": current_value,
            "target_value": target_value,
            "completion_percentage": completion_percentage,
            "is_completed": is_completed,
            "check_date": check_date.isoformat()
        }

