"""
性能监控数据模型
记录前端页面和 API 的性能指标
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Index, Enum as SQLEnum
from sqlalchemy.sql import func
from datetime import datetime
import enum

from app.database import Base


class PlatformType(str, enum.Enum):
    """平台类型"""
    MINI_PROGRAM = "mini_program"  # 小程序
    WEB = "web"  # Web 端
    H5 = "h5"  # H5 页面
    APP = "app"  # 原生 APP


class MetricType(str, enum.Enum):
    """指标类型"""
    PAGE_LOAD = "page_load"  # 页面加载
    API_CALL = "api_call"  # API 调用
    RENDER = "render"  # 渲染性能
    INTERACTION = "interaction"  # 交互性能
    ERROR = "error"  # 错误


class PerformanceMetric(Base):
    """性能指标记录"""
    __tablename__ = "performance_metrics"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 基本信息
    user_id = Column(Integer, nullable=True, index=True)  # 用户 ID（可选）
    session_id = Column(String(100), nullable=False, index=True)  # 会话 ID
    platform = Column(SQLEnum(PlatformType), nullable=False, index=True)  # 平台类型
    
    # 指标信息
    metric_type = Column(SQLEnum(MetricType), nullable=False, index=True)  # 指标类型
    metric_name = Column(String(200), nullable=False, index=True)  # 指标名称（如页面路径、API 端点）
    
    # 性能数据
    duration = Column(Float, nullable=False)  # 耗时（毫秒）
    start_time = Column(DateTime, nullable=False)  # 开始时间
    end_time = Column(DateTime, nullable=False)  # 结束时间
    
    # 详细信息
    details = Column(JSON, nullable=True)  # 详细信息（如分批加载时间、缓存命中等）
    metadata = Column(JSON, nullable=True)  # 元数据（如设备信息、网络状态等）
    
    # 状态
    success = Column(Integer, default=1)  # 是否成功（1=成功，0=失败）
    error_message = Column(String(500), nullable=True)  # 错误信息
    
    # 时间戳
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)
    
    # 索引
    __table_args__ = (
        Index('idx_platform_metric_created', 'platform', 'metric_type', 'created_at'),
        Index('idx_metric_name_created', 'metric_name', 'created_at'),
        Index('idx_user_created', 'user_id', 'created_at'),
    )


class PerformanceAlert(Base):
    """性能告警记录"""
    __tablename__ = "performance_alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 告警信息
    alert_type = Column(String(50), nullable=False, index=True)  # 告警类型（slow_page, slow_api, high_error_rate）
    severity = Column(String(20), nullable=False)  # 严重程度（critical, warning, info）
    
    # 相关指标
    platform = Column(SQLEnum(PlatformType), nullable=False)
    metric_name = Column(String(200), nullable=False)
    metric_value = Column(Float, nullable=False)  # 指标值
    threshold = Column(Float, nullable=False)  # 阈值
    
    # 详细信息
    description = Column(String(500), nullable=False)  # 描述
    details = Column(JSON, nullable=True)  # 详细信息
    
    # 状态
    status = Column(String(20), default='open', index=True)  # 状态（open, acknowledged, resolved）
    resolved_at = Column(DateTime, nullable=True)  # 解决时间
    
    # 时间戳
    created_at = Column(DateTime, default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())


class PerformanceSummary(Base):
    """性能摘要（按小时/天聚合）"""
    __tablename__ = "performance_summaries"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 聚合维度
    platform = Column(SQLEnum(PlatformType), nullable=False, index=True)
    metric_type = Column(SQLEnum(MetricType), nullable=False)
    metric_name = Column(String(200), nullable=False, index=True)
    
    # 时间维度
    period_type = Column(String(20), nullable=False)  # hour, day
    period_start = Column(DateTime, nullable=False, index=True)
    period_end = Column(DateTime, nullable=False)
    
    # 统计数据
    total_count = Column(Integer, default=0)  # 总次数
    success_count = Column(Integer, default=0)  # 成功次数
    error_count = Column(Integer, default=0)  # 错误次数
    
    avg_duration = Column(Float, default=0)  # 平均耗时
    min_duration = Column(Float, default=0)  # 最小耗时
    max_duration = Column(Float, default=0)  # 最大耗时
    p50_duration = Column(Float, default=0)  # P50 耗时
    p90_duration = Column(Float, default=0)  # P90 耗时
    p95_duration = Column(Float, default=0)  # P95 耗时
    p99_duration = Column(Float, default=0)  # P99 耗时
    
    # 时间戳
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    
    # 索引
    __table_args__ = (
        Index('idx_platform_period', 'platform', 'period_type', 'period_start'),
        Index('idx_metric_period', 'metric_name', 'period_start'),
    )
