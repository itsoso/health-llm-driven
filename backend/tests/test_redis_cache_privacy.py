"""Cache operations must not expose genotype-bearing keys or connection secrets."""
import logging
from unittest.mock import Mock

import pytest
from app.utils import redis_cache


@pytest.mark.parametrize("operation", ["get", "set", "delete", "exists", "clear_pattern"])
def test_cache_failure_does_not_log_key_or_upstream_payload(monkeypatch, caplog, operation):
    client = Mock()
    target = "setex" if operation == "set" else "scan" if operation == "clear_pattern" else operation
    getattr(client, target).side_effect = RuntimeError("synthetic-private-upstream")
    monkeypatch.setattr(redis_cache, "get_redis_client", lambda: client)
    key = "genetic_snp_detail:v2:user=7:rsid=rs1:gt=SYNTHETIC_PRIVATE_GT"
    method = getattr(redis_cache.RedisCache, operation)
    method(key, {"synthetic": True}) if operation == "set" else method(key)
    assert key not in caplog.text
    assert "synthetic-private-upstream" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_cache_set_requires_positive_acknowledgement(monkeypatch):
    client = Mock()
    client.setex.return_value = False
    monkeypatch.setattr(redis_cache, "get_redis_client", lambda: client)
    assert redis_cache.RedisCache.set("synthetic", {}) is False


def test_connection_and_success_logs_do_not_include_secrets_or_keys(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger=redis_cache.__name__)
    monkeypatch.setattr(redis_cache, "_redis_client", None)
    monkeypatch.setattr(redis_cache.settings, "redis_url", "redis://synthetic:synthetic-private-password@localhost:1/0")
    client = Mock()
    client.setex.return_value = True
    monkeypatch.setattr(redis_cache.redis, "from_url", lambda *a, **kw: client)
    assert redis_cache.get_redis_client() is client
    redis_cache.RedisCache.set("SYNTHETIC_PRIVATE_GT", {})
    redis_cache.RedisCache.delete("SYNTHETIC_PRIVATE_GT")
    assert "synthetic-private-password" not in caplog.text
    assert "SYNTHETIC_PRIVATE_GT" not in caplog.text
