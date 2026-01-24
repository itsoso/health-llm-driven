"""
后端性能监控工具
用于追踪 API 响应时间和数据库查询性能
"""

import time
import logging
from typing import Optional, Dict, Any, Callable
from functools import wraps
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self):
        self.enabled = True
        self.slow_threshold = 1.0  # 慢操作阈值（秒）
        self.warning_threshold = 0.5  # 警告阈值（秒）
    
    @contextmanager
    def track(self, operation: str, metadata: Optional[Dict[str, Any]] = None):
        """
        上下文管理器：追踪操作性能
        
        Usage:
            with performance_monitor.track("数据库查询"):
                result = db.query(...)
        """
        if not self.enabled:
            yield
            return
        
        start_time = time.time()
        logger.debug(f"[性能] {operation} 开始")
        
        try:
            yield
        finally:
            duration = time.time() - start_time
            self._log_performance(operation, duration, metadata)
    
    def _log_performance(self, operation: str, duration: float, metadata: Optional[Dict[str, Any]] = None):
        """记录性能日志"""
        duration_ms = duration * 1000
        
        # 构建日志消息
        msg = f"[性能] {operation} 耗时 {duration_ms:.2f}ms"
        if metadata:
            msg += f" | {metadata}"
        
        # 根据耗时选择日志级别
        if duration >= self.slow_threshold:
            logger.error(f"{msg} ⚠️ 慢操作")
        elif duration >= self.warning_threshold:
            logger.warning(msg)
        else:
            logger.info(msg)
    
    def track_function(self, operation_name: Optional[str] = None):
        """
        装饰器：追踪函数执行性能
        
        Usage:
            @performance_monitor.track_function("用户登录")
            def login(username, password):
                ...
        """
        def decorator(func: Callable) -> Callable:
            op_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                with self.track(op_name):
                    return await func(*args, **kwargs)
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                with self.track(op_name):
                    return func(*args, **kwargs)
            
            # 判断是否为异步函数
            import asyncio
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
        
        return decorator


# 全局单例
performance_monitor = PerformanceMonitor()


def track_api_performance(endpoint: str):
    """
    装饰器：追踪 API 端点性能
    
    Usage:
        @track_api_performance("/api/v1/users")
        async def get_users():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                
                logger.info(
                    f"[API性能] {endpoint} 成功 | "
                    f"耗时 {duration*1000:.2f}ms"
                )
                
                return result
                
            except Exception as e:
                duration = time.time() - start_time
                
                logger.error(
                    f"[API性能] {endpoint} 失败 | "
                    f"耗时 {duration*1000:.2f}ms | "
                    f"错误: {str(e)}"
                )
                
                raise
        
        return wrapper
    
    return decorator


def track_database_query(query_name: str):
    """
    装饰器：追踪数据库查询性能
    
    Usage:
        @track_database_query("查询用户列表")
        def get_users(db):
            return db.query(User).all()
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            with performance_monitor.track(f"DB-{query_name}"):
                return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


# 便捷函数
def log_slow_operation(operation: str, duration: float, threshold: float = 1.0):
    """
    记录慢操作
    
    Args:
        operation: 操作名称
        duration: 执行时长（秒）
        threshold: 慢操作阈值（秒）
    """
    if duration >= threshold:
        logger.warning(
            f"[慢操作] {operation} 耗时 {duration*1000:.2f}ms "
            f"(阈值: {threshold*1000:.0f}ms)"
        )


def log_api_metrics(
    endpoint: str,
    method: str,
    status_code: int,
    duration: float,
    user_id: Optional[int] = None
):
    """
    记录 API 指标
    
    Args:
        endpoint: API 端点
        method: HTTP 方法
        status_code: 状态码
        duration: 执行时长（秒）
        user_id: 用户 ID（可选）
    """
    duration_ms = duration * 1000
    
    log_msg = (
        f"[API指标] {method} {endpoint} | "
        f"状态码: {status_code} | "
        f"耗时: {duration_ms:.2f}ms"
    )
    
    if user_id:
        log_msg += f" | 用户: {user_id}"
    
    # 根据状态码和耗时选择日志级别
    if status_code >= 500:
        logger.error(log_msg)
    elif status_code >= 400:
        logger.warning(log_msg)
    elif duration >= 1.0:
        logger.warning(log_msg + " ⚠️ 慢请求")
    else:
        logger.info(log_msg)
