"""Redis缓存模块测试"""
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestRedisCacheClearPattern:
    """测试 RedisCache.clear_pattern 使用 SCAN 替代 KEYS"""

    def test_clear_pattern_no_redis_client(self):
        """测试 Redis 客户端不可用时返回 0"""
        with patch('app.utils.redis_cache.get_redis_client', return_value=None):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.clear_pattern("test:*")
            assert result == 0

    def test_clear_pattern_empty_result(self):
        """测试没有匹配键时返回 0"""
        mock_client = Mock()
        # SCAN 返回 cursor=0 和空键列表，表示扫描完成且无结果
        mock_client.scan.return_value = (0, [])

        with patch('app.utils.redis_cache.get_redis_client', return_value=mock_client):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.clear_pattern("nonexistent:*")

            assert result == 0
            mock_client.scan.assert_called_once_with(0, match="nonexistent:*", count=100)
            mock_client.delete.assert_not_called()

    def test_clear_pattern_single_batch(self):
        """测试单批次删除（少于100个键）"""
        mock_client = Mock()
        keys_to_delete = [b"test:1", b"test:2", b"test:3"]
        # SCAN 返回 cursor=0 表示扫描完成
        mock_client.scan.return_value = (0, keys_to_delete)
        mock_client.delete.return_value = 3

        with patch('app.utils.redis_cache.get_redis_client', return_value=mock_client):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.clear_pattern("test:*")

            assert result == 3
            mock_client.scan.assert_called_once_with(0, match="test:*", count=100)
            mock_client.delete.assert_called_once_with(*keys_to_delete)

    def test_clear_pattern_multiple_batches(self):
        """测试多批次删除（使用 SCAN 迭代）"""
        mock_client = Mock()
        batch1_keys = [b"test:1", b"test:2"]
        batch2_keys = [b"test:3", b"test:4", b"test:5"]

        # 第一次 SCAN 返回 cursor=123（非0表示还有更多数据）
        # 第二次 SCAN 返回 cursor=0（表示扫描完成）
        mock_client.scan.side_effect = [
            (123, batch1_keys),
            (0, batch2_keys)
        ]
        mock_client.delete.side_effect = [2, 3]

        with patch('app.utils.redis_cache.get_redis_client', return_value=mock_client):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.clear_pattern("test:*")

            assert result == 5  # 2 + 3
            assert mock_client.scan.call_count == 2
            assert mock_client.delete.call_count == 2

            # 验证 SCAN 调用参数
            calls = mock_client.scan.call_args_list
            assert calls[0][0] == (0,)  # 第一次从 cursor=0 开始
            assert calls[1][0] == (123,)  # 第二次从 cursor=123 继续

    def test_clear_pattern_exception_handling(self):
        """测试异常处理"""
        mock_client = Mock()
        mock_client.scan.side_effect = Exception("Redis connection error")

        with patch('app.utils.redis_cache.get_redis_client', return_value=mock_client):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.clear_pattern("test:*")

            assert result == 0

    def test_clear_pattern_partial_delete_on_exception(self):
        """测试部分删除后发生异常"""
        mock_client = Mock()
        batch1_keys = [b"test:1", b"test:2"]

        mock_client.scan.side_effect = [
            (123, batch1_keys),
            Exception("Connection lost")
        ]
        mock_client.delete.return_value = 2

        with patch('app.utils.redis_cache.get_redis_client', return_value=mock_client):
            from app.utils.redis_cache import RedisCache
            # 由于异常被捕获，应该返回 0（根据当前实现）
            result = RedisCache.clear_pattern("test:*")

            assert result == 0


class TestRedisCacheGet:
    """测试 RedisCache.get 方法"""

    def test_get_no_redis_client(self):
        """测试 Redis 客户端不可用时返回 None"""
        with patch('app.utils.redis_cache.get_redis_client', return_value=None):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.get("test_key")
            assert result is None

    def test_get_existing_key(self):
        """测试获取存在的键"""
        mock_client = Mock()
        mock_client.get.return_value = '{"data": "test"}'

        with patch('app.utils.redis_cache.get_redis_client', return_value=mock_client):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.get("test_key")

            assert result == {"data": "test"}
            mock_client.get.assert_called_once_with("test_key")

    def test_get_nonexistent_key(self):
        """测试获取不存在的键"""
        mock_client = Mock()
        mock_client.get.return_value = None

        with patch('app.utils.redis_cache.get_redis_client', return_value=None):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.get("nonexistent_key")

            assert result is None


class TestRedisCacheSet:
    """测试 RedisCache.set 方法"""

    def test_set_no_redis_client(self):
        """测试 Redis 客户端不可用时返回 False"""
        with patch('app.utils.redis_cache.get_redis_client', return_value=None):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.set("test_key", {"data": "test"})
            assert result is False

    def test_set_with_ttl(self):
        """测试设置带 TTL 的键"""
        mock_client = Mock()
        mock_client.setex.return_value = True

        with patch('app.utils.redis_cache.get_redis_client', return_value=mock_client):
            from app.utils.redis_cache import RedisCache
            result = RedisCache.set("test_key", {"data": "test"}, ttl=3600)

            assert result is True
            mock_client.setex.assert_called_once()
