"""
健康记录通用工具模块

提供健康记录 API 的通用功能，减少代码重复：
- 用户权限验证
- 日期范围查询
- 记录归属验证
- 通用 CRUD 操作
"""
from datetime import date, timedelta
from typing import Optional, Type, TypeVar, Generic, List, Callable
from fastapi import HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.user import User


# 泛型类型
T = TypeVar('T')  # 数据库模型
R = TypeVar('R')  # 响应模型


def verify_user_access(user_id: int, current_user: User) -> None:
    """
    验证用户只能访问自己的数据

    Args:
        user_id: 请求的用户ID
        current_user: 当前登录用户

    Raises:
        HTTPException: 403 如果尝试访问其他用户的数据
    """
    if user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权访问其他用户的数据")


def verify_record_ownership(record, current_user: User, action: str = "操作") -> None:
    """
    验证记录归属于当前用户

    Args:
        record: 数据库记录对象（必须有 user_id 属性）
        current_user: 当前登录用户
        action: 操作描述（用于错误消息）

    Raises:
        HTTPException: 403 如果记录不属于当前用户
    """
    if record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail=f"无权{action}其他用户的记录")


def get_record_or_404(db: Session, model: Type[T], record_id: int) -> T:
    """
    获取记录或返回 404

    Args:
        db: 数据库会话
        model: 模型类
        record_id: 记录ID

    Returns:
        数据库记录

    Raises:
        HTTPException: 404 如果记录不存在
    """
    record = db.query(model).filter(model.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    return record


def apply_date_filter(query, model, start_date: Optional[date], end_date: Optional[date]):
    """
    应用日期范围过滤

    Args:
        query: SQLAlchemy 查询对象
        model: 模型类（必须有 record_date 属性）
        start_date: 开始日期
        end_date: 结束日期

    Returns:
        过滤后的查询对象
    """
    if start_date:
        query = query.filter(model.record_date >= start_date)
    if end_date:
        query = query.filter(model.record_date <= end_date)
    return query


def get_user_records(
    db: Session,
    model: Type[T],
    user_id: int,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = 30,
    order_by_field: str = "record_date"
) -> List[T]:
    """
    获取用户的健康记录列表

    Args:
        db: 数据库会话
        model: 模型类
        user_id: 用户ID
        start_date: 开始日期
        end_date: 结束日期
        limit: 返回记录数限制
        order_by_field: 排序字段名

    Returns:
        记录列表
    """
    query = db.query(model).filter(model.user_id == user_id)
    query = apply_date_filter(query, model, start_date, end_date)

    # 按指定字段降序排序
    order_field = getattr(model, order_by_field, None)
    if order_field is not None:
        query = query.order_by(desc(order_field))

    return query.limit(limit).all()


def get_records_in_days(
    db: Session,
    model: Type[T],
    user_id: int,
    days: int = 30
) -> List[T]:
    """
    获取最近N天的记录

    Args:
        db: 数据库会话
        model: 模型类
        user_id: 用户ID
        days: 天数

    Returns:
        记录列表
    """
    start_date = date.today() - timedelta(days=days)
    return db.query(model).filter(
        model.user_id == user_id,
        model.record_date >= start_date
    ).all()


def update_record(
    db: Session,
    record,
    update_data,
    exclude_fields: Optional[List[str]] = None
) -> None:
    """
    通用记录更新

    Args:
        db: 数据库会话
        record: 数据库记录
        update_data: Pydantic 更新模型
        exclude_fields: 排除的字段列表
    """
    exclude_fields = exclude_fields or []
    update_dict = update_data.model_dump(exclude_unset=True)

    for key, value in update_dict.items():
        if key not in exclude_fields and hasattr(record, key):
            setattr(record, key, value)

    db.commit()
    db.refresh(record)


def delete_record(db: Session, record) -> dict:
    """
    删除记录

    Args:
        db: 数据库会话
        record: 数据库记录

    Returns:
        成功消息
    """
    db.delete(record)
    db.commit()
    return {"message": "记录删除成功"}


def calculate_stats(values: List[float]) -> dict:
    """
    计算统计数据

    Args:
        values: 数值列表

    Returns:
        包含 average, max, min, count 的字典
    """
    if not values:
        return {
            "average": None,
            "max": None,
            "min": None,
            "count": 0
        }

    return {
        "average": round(sum(values) / len(values), 1),
        "max": max(values),
        "min": min(values),
        "count": len(values)
    }
