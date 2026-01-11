"""日志配置工具 - 统一使用北京时间"""
import logging
from datetime import datetime
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


def setup_beijing_logging(level=logging.INFO, format_string=None):
    """
    设置使用北京时间的日志配置
    
    Args:
        level: 日志级别，默认INFO
        format_string: 日志格式字符串，默认使用标准格式
    """
    if format_string is None:
        format_string = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    
    handler = logging.StreamHandler()
    handler.setFormatter(BeijingTimeFormatter(format_string))
    
    logging.basicConfig(
        level=level,
        handlers=[handler],
        force=True  # 强制重新配置
    )
