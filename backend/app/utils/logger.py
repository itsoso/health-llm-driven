"""
统一日志工具类
提供模块级别的日志功能，包括函数调用追踪、数据流转记录、性能监控等
"""

import logging
import functools
import time
import json
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime


class ModuleLogger:
    """模块级别的日志工具类"""

    def __init__(self, module_name: str):
        """
        初始化模块日志器

        Args:
            module_name: 模块名称，用于日志标识
        """
        self.logger = logging.getLogger(module_name)
        self.module_name = module_name

    def log_function_call(self, log_args: bool = True, log_result: bool = False):
        """
        装饰器：记录函数调用

        Args:
            log_args: 是否记录函数参数（默认 True）
            log_result: 是否记录函数返回值（默认 False，避免敏感数据泄露）

        Usage:
            @logger.log_function_call()
            def my_function(arg1, arg2):
                return result
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                return await self._execute_with_logging(
                    func, args, kwargs, log_args, log_result, is_async=True
                )

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                return self._execute_with_logging(
                    func, args, kwargs, log_args, log_result, is_async=False
                )

            # 判断是否为异步函数
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    async def _execute_with_logging(
        self,
        func: Callable,
        args: tuple,
        kwargs: dict,
        log_args: bool,
        log_result: bool,
        is_async: bool
    ) -> Any:
        """执行函数并记录日志"""
        func_name = func.__name__
        start_time = time.time()

        # 记录函数开始
        self.logger.info(f"[{func_name}] 开始执行")

        if log_args and (args or kwargs):
            # 脱敏处理参数
            safe_args = self._mask_sensitive_data(args)
            safe_kwargs = self._mask_sensitive_data(kwargs)
            self.logger.debug(
                f"[{func_name}] 参数: args={safe_args}, kwargs={safe_kwargs}"
            )

        try:
            # 执行函数
            if is_async:
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            duration = time.time() - start_time

            # 记录成功
            self.logger.info(f"[{func_name}] 执行成功，耗时 {duration:.3f}s")

            if log_result:
                safe_result = self._mask_sensitive_data(result)
                self.logger.debug(f"[{func_name}] 返回值: {safe_result}")

            # 性能警告
            if duration > 5.0:
                self.logger.warning(
                    f"[{func_name}] 性能警告：执行时间 {duration:.3f}s 超过 5s"
                )

            return result

        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(
                f"[{func_name}] 执行失败，耗时 {duration:.3f}s，"
                f"错误类型: {type(e).__name__}, 错误信息: {str(e)}",
                exc_info=True
            )
            raise

    def log_step(self, step_name: str, data: Optional[Any] = None, mask_fields: Optional[List[str]] = None):
        """
        记录处理步骤

        Args:
            step_name: 步骤名称
            data: 步骤数据（可选）
            mask_fields: 需要脱敏的字段列表（可选）

        Usage:
            logger.log_step("获取用户数据", {"user_id": 123})
            logger.log_step("调用 LLM", mask_fields=["api_key"])
        """
        if data is not None:
            safe_data = self._mask_sensitive_data(data, mask_fields)
            self.logger.info(f"[步骤] {step_name}: {safe_data}")
        else:
            self.logger.info(f"[步骤] {step_name}")

    def log_data_flow(self, step: str, data: Any, mask_fields: Optional[List[str]] = None):
        """
        记录数据流转

        Args:
            step: 流转步骤描述
            data: 数据内容
            mask_fields: 需要脱敏的字段列表

        Usage:
            logger.log_data_flow("数据库查询结果", query_result, mask_fields=["password"])
        """
        safe_data = self._mask_sensitive_data(data, mask_fields)
        self.logger.debug(f"[数据流转] {step}: {safe_data}")

    def log_external_call(self, service: str, method: str, params: Optional[Dict] = None):
        """
        记录外部服务调用

        Args:
            service: 服务名称（如 "OpenAI", "Database", "Redis"）
            method: 调用方法
            params: 调用参数

        Usage:
            logger.log_external_call("OpenAI", "chat.completions.create", {"model": "gpt-4"})
        """
        if params:
            safe_params = self._mask_sensitive_data(params)
            self.logger.info(f"[外部调用] {service}.{method}, 参数: {safe_params}")
        else:
            self.logger.info(f"[外部调用] {service}.{method}")

    def log_performance(self, operation: str, duration: float, threshold: float = 1.0):
        """
        记录性能指标

        Args:
            operation: 操作名称
            duration: 执行时长（秒）
            threshold: 警告阈值（秒），超过此值记录警告

        Usage:
            start = time.time()
            # ... 执行操作 ...
            logger.log_performance("数据库查询", time.time() - start, threshold=0.5)
        """
        if duration > threshold:
            self.logger.warning(
                f"[性能] {operation} 耗时 {duration:.3f}s (阈值: {threshold}s)"
            )
        else:
            self.logger.debug(f"[性能] {operation} 耗时 {duration:.3f}s")

    def log_cache_hit(self, cache_key: str, hit: bool):
        """
        记录缓存命中情况

        Args:
            cache_key: 缓存键
            hit: 是否命中

        Usage:
            logger.log_cache_hit("user_profile_123", True)
        """
        status = "命中" if hit else "未命中"
        self.logger.debug(f"[缓存] {cache_key}: {status}")

    def log_validation_error(self, field: str, value: Any, error: str):
        """
        记录数据验证错误

        Args:
            field: 字段名
            value: 字段值
            error: 错误信息

        Usage:
            logger.log_validation_error("email", "invalid", "邮箱格式不正确")
        """
        safe_value = self._mask_sensitive_data(value)
        self.logger.warning(f"[验证错误] 字段: {field}, 值: {safe_value}, 错误: {error}")

    def log_business_event(self, event: str, details: Optional[Dict] = None):
        """
        记录业务事件

        Args:
            event: 事件名称
            details: 事件详情

        Usage:
            logger.log_business_event("用户登录", {"user_id": 123, "ip": "1.2.3.4"})
        """
        if details:
            safe_details = self._mask_sensitive_data(details)
            self.logger.info(f"[业务事件] {event}: {safe_details}")
        else:
            self.logger.info(f"[业务事件] {event}")

    def _mask_sensitive_data(
        self,
        data: Any,
        mask_fields: Optional[List[str]] = None
    ) -> Any:
        """
        脱敏敏感数据

        Args:
            data: 原始数据
            mask_fields: 需要脱敏的字段列表

        Returns:
            脱敏后的数据
        """
        # 默认敏感字段
        default_sensitive_fields = [
            'password', 'token', 'api_key', 'secret', 'access_token',
            'refresh_token', 'authorization', 'cookie', 'session',
            'credit_card', 'ssn', 'phone', 'email', 'id_card'
        ]

        sensitive_fields = set(default_sensitive_fields)
        if mask_fields:
            sensitive_fields.update(mask_fields)

        return self._mask_recursive(data, sensitive_fields)

    def _mask_recursive(self, data: Any, sensitive_fields: set) -> Any:
        """递归脱敏数据"""
        if isinstance(data, dict):
            return {
                key: self._mask_value(key, value, sensitive_fields)
                for key, value in data.items()
            }
        elif isinstance(data, (list, tuple)):
            return [self._mask_recursive(item, sensitive_fields) for item in data]
        else:
            return data

    def _mask_value(self, key: str, value: Any, sensitive_fields: set) -> Any:
        """脱敏单个值"""
        # 检查键名是否包含敏感字段
        key_lower = key.lower()
        is_sensitive = any(field in key_lower for field in sensitive_fields)

        if is_sensitive:
            if isinstance(value, str):
                if len(value) > 4:
                    return value[:2] + "***" + value[-2:]
                else:
                    return "***"
            else:
                return "***"
        else:
            # 递归处理嵌套数据
            return self._mask_recursive(value, sensitive_fields)


# 导入 asyncio（用于异步函数判断）
import asyncio


# 便捷函数：创建模块日志器
def get_module_logger(module_name: str) -> ModuleLogger:
    """
    获取模块日志器

    Args:
        module_name: 模块名称

    Returns:
        ModuleLogger 实例

    Usage:
        logger = get_module_logger(__name__)
    """
    return ModuleLogger(module_name)
