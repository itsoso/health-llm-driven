"""Redis 缓存工具"""
import redis
import json
import logging
from typing import Optional, Any
from datetime import timedelta
from app.config import settings

logger = logging.getLogger(__name__)

# Redis 客户端（延迟初始化）
_redis_client: Optional[redis.Redis] = None


def get_redis_client() -> Optional[redis.Redis]:
    """获取 Redis 客户端（单例模式）"""
    global _redis_client
    
    if _redis_client is None:
        try:
            _redis_client = redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True
            )
            # 测试连接
            _redis_client.ping()
            logger.info(f"✅ Redis 连接成功: {settings.redis_url}")
        except Exception as e:
            logger.warning(f"⚠️  Redis 连接失败: {e}，将不使用缓存")
            _redis_client = None
    
    return _redis_client


class RedisCache:
    """Redis 缓存封装类"""
    
    @staticmethod
    def get(key: str) -> Optional[Any]:
        """从 Redis 获取缓存
        
        Args:
            key: 缓存键
            
        Returns:
            缓存的值（自动 JSON 解析），如果不存在或出错则返回 None
        """
        client = get_redis_client()
        if not client:
            return None
        
        try:
            value = client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis GET 失败 (key={key}): {e}")
            return None
    
    @staticmethod
    def set(key: str, value: Any, ttl: int = 3600) -> bool:
        """设置 Redis 缓存
        
        Args:
            key: 缓存键
            value: 缓存值（会自动 JSON 序列化）
            ttl: 过期时间（秒），默认 1 小时
            
        Returns:
            是否设置成功
        """
        client = get_redis_client()
        if not client:
            return False
        
        try:
            serialized = json.dumps(value, ensure_ascii=False)
            client.setex(key, ttl, serialized)
            logger.debug(f"Redis SET 成功 (key={key}, ttl={ttl}s)")
            return True
        except Exception as e:
            logger.error(f"Redis SET 失败 (key={key}): {e}")
            return False
    
    @staticmethod
    def delete(key: str) -> bool:
        """删除 Redis 缓存
        
        Args:
            key: 缓存键
            
        Returns:
            是否删除成功
        """
        client = get_redis_client()
        if not client:
            return False
        
        try:
            client.delete(key)
            logger.debug(f"Redis DELETE 成功 (key={key})")
            return True
        except Exception as e:
            logger.error(f"Redis DELETE 失败 (key={key}): {e}")
            return False
    
    @staticmethod
    def exists(key: str) -> bool:
        """检查缓存是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在
        """
        client = get_redis_client()
        if not client:
            return False
        
        try:
            return bool(client.exists(key))
        except Exception as e:
            logger.error(f"Redis EXISTS 失败 (key={key}): {e}")
            return False
    
    @staticmethod
    def clear_pattern(pattern: str) -> int:
        """清除匹配模式的所有键
        
        Args:
            pattern: 键的模式，如 "user:123:*"
            
        Returns:
            删除的键数量
        """
        client = get_redis_client()
        if not client:
            return 0
        
        try:
            keys = client.keys(pattern)
            if keys:
                return client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis CLEAR_PATTERN 失败 (pattern={pattern}): {e}")
            return 0


# 便捷函数
def cache_daily_recommendation(user_id: int, date: str, recommendation: dict, ttl: int = 3600):
    """缓存每日推荐
    
    Args:
        user_id: 用户 ID
        date: 日期（YYYY-MM-DD）
        recommendation: 推荐内容
        ttl: 过期时间（秒），默认 1 小时
    """
    key = f"daily_rec:{user_id}:{date}"
    RedisCache.set(key, recommendation, ttl)


def get_cached_daily_recommendation(user_id: int, date: str) -> Optional[dict]:
    """获取缓存的每日推荐
    
    Args:
        user_id: 用户 ID
        date: 日期（YYYY-MM-DD）
        
    Returns:
        缓存的推荐内容，如果不存在则返回 None
    """
    key = f"daily_rec:{user_id}:{date}"
    return RedisCache.get(key)


def invalidate_user_cache(user_id: int):
    """清除用户的所有缓存
    
    Args:
        user_id: 用户 ID
    """
    pattern = f"*:{user_id}:*"
    count = RedisCache.clear_pattern(pattern)
    logger.info(f"清除用户 {user_id} 的缓存，共 {count} 个键")
