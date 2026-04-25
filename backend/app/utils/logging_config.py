"""日志配置工具 - 统一使用北京时间，支持动态级别控制"""
import os
import logging
from datetime import datetime
from typing import Optional, Dict
from app.utils.timezone import CHINA_TIMEZONE


class BeijingTimeFormatter(logging.Formatter):
    """自定义日志格式化器，使用北京时间"""
    def formatTime(self, record, datefmt=None):
        ct = datetime.now(CHINA_TIMEZONE)
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            t = ct.strftime("%Y-%m-%d %H:%M:%S")
            s = "%s" % t
        return s


# 全局日志管理器
class LogManager:
    """日志管理器 - 支持动态日志级别控制"""

    _instance: Optional['LogManager'] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not LogManager._initialized:
            self._loggers: Dict[str, logging.Logger] = {}
            self._default_level = logging.INFO
            self._debug_mode = os.getenv('DEBUG', 'false').lower() == 'true'
            LogManager._initialized = True

    def get_logger(self, name: str) -> logging.Logger:
        """获取或创建日志记录器"""
        if name not in self._loggers:
            logger = logging.getLogger(name)
            logger.setLevel(self._default_level if not self._debug_mode else logging.DEBUG)
            self._loggers[name] = logger
        return self._loggers[name]

    def set_level(self, level: int, logger_name: Optional[str] = None):
        """设置日志级别"""
        if logger_name:
            if logger_name in self._loggers:
                self._loggers[logger_name].setLevel(level)
        else:
            self._default_level = level
            for logger in self._loggers.values():
                logger.setLevel(level)
            logging.getLogger().setLevel(level)

    def enable_debug(self):
        """启用调试模式"""
        self._debug_mode = True
        self.set_level(logging.DEBUG)

    def disable_debug(self):
        """禁用调试模式"""
        self._debug_mode = False
        self.set_level(logging.INFO)

    def get_status(self) -> Dict:
        """获取日志管理器状态"""
        return {
            'debug_mode': self._debug_mode,
            'default_level': logging.getLevelName(self._default_level),
            'loggers': {
                name: logging.getLevelName(logger.level)
                for name, logger in self._loggers.items()
            }
        }


# 单例实例
log_manager = LogManager()


def setup_beijing_logging(level=logging.INFO, format_string=None):
    """设置使用北京时间的日志配置"""
    env_level = os.getenv('LOG_LEVEL', '').upper()
    if env_level:
        level_map = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'ERROR': logging.ERROR,
            'CRITICAL': logging.CRITICAL,
        }
        level = level_map.get(env_level, level)

    if format_string is None:
        format_string = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handler = logging.StreamHandler()
    handler.setFormatter(BeijingTimeFormatter(format_string))

    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True
    )

    log_manager.set_level(level)


def get_logger(name: str) -> logging.Logger:
    """便捷函数：获取日志记录器"""
    return log_manager.get_logger(name)
