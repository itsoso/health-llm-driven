"""
性能监控中间件
自动追踪所有 API 请求的性能指标
"""

import time
import logging
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.utils.performance_monitor import log_api_metrics

logger = logging.getLogger(__name__)


class PerformanceMiddleware(BaseHTTPMiddleware):
    """
    性能监控中间件
    自动记录每个 API 请求的响应时间
    """
    
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.slow_threshold = 1.0  # 慢请求阈值（秒）
        self.warning_threshold = 0.5  # 警告阈值（秒）
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 记录开始时间
        start_time = time.time()
        
        # 获取请求信息
        method = request.method
        path = request.url.path
        
        # 尝试获取用户 ID（如果有）
        user_id = None
        if hasattr(request.state, 'user'):
            user_id = getattr(request.state.user, 'id', None)
        
        # 执行请求
        try:
            response = await call_next(request)
            
            # 计算耗时
            duration = time.time() - start_time
            
            # 记录性能指标
            log_api_metrics(
                endpoint=path,
                method=method,
                status_code=response.status_code,
                duration=duration,
                user_id=user_id
            )
            
            # 添加性能头
            response.headers["X-Response-Time"] = f"{duration*1000:.2f}ms"
            
            return response
            
        except Exception as e:
            # 计算耗时
            duration = time.time() - start_time
            
            # 记录错误
            logger.error(
                f"[API错误] {method} {path} | "
                f"耗时: {duration*1000:.2f}ms | "
                f"错误: {str(e)}"
            )
            
            raise


class DetailedPerformanceMiddleware(BaseHTTPMiddleware):
    """
    详细性能监控中间件
    记录更详细的性能指标，包括请求体大小、响应体大小等
    """
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        
        # 获取请求信息
        method = request.method
        path = request.url.path
        query_params = dict(request.query_params)
        
        # 获取请求体大小（如果有）
        request_size = 0
        if request.headers.get("content-length"):
            request_size = int(request.headers["content-length"])
        
        # 执行请求
        response = await call_next(request)
        
        # 计算耗时
        duration = time.time() - start_time
        duration_ms = duration * 1000
        
        # 获取响应体大小
        response_size = 0
        if "content-length" in response.headers:
            response_size = int(response.headers["content-length"])
        
        # 构建详细日志
        log_data = {
            "method": method,
            "path": path,
            "status": response.status_code,
            "duration_ms": f"{duration_ms:.2f}",
            "request_size": request_size,
            "response_size": response_size
        }
        
        if query_params:
            log_data["query_params"] = query_params
        
        # 根据耗时和状态码选择日志级别
        if response.status_code >= 500:
            logger.error(f"[API详情] {log_data}")
        elif response.status_code >= 400:
            logger.warning(f"[API详情] {log_data}")
        elif duration >= 1.0:
            logger.warning(f"[API详情-慢] {log_data}")
        else:
            logger.debug(f"[API详情] {log_data}")
        
        # 添加详细性能头
        response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
        response.headers["X-Request-Size"] = str(request_size)
        response.headers["X-Response-Size"] = str(response_size)
        
        return response
