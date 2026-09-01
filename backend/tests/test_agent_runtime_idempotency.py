from app.services.agent_turn_idempotency import (
    SemanticTurnDedupeCache,
    is_semantic_read_only_candidate,
    resolve_distributed_semantic_turn,
    semantic_turn_fingerprint,
)


def _fingerprint(**overrides):
    values = {
        "user_id": 7,
        "conversation_id": 11,
        "message": " 分析我最近 7 天睡眠 ",
        "data_version": "health-v1",
        "image_hashes": (),
        "intent": "read",
    }
    values.update(overrides)
    return semantic_turn_fingerprint(**values)


def test_normalized_read_request_reuses_the_existing_turn_inside_window():
    cache = SemanticTurnDedupeCache(ttl_seconds=30)
    first = cache.resolve(
        fingerprint=_fingerprint(), proposed_client_turn_id="turn-first", now=10
    )
    duplicate = cache.resolve(
        fingerprint=_fingerprint(message="分析我最近   7 天睡眠"),
        proposed_client_turn_id="turn-second",
        now=20,
    )

    assert first.dedupe_hit is False
    assert duplicate.dedupe_hit is True
    assert duplicate.client_turn_id == "turn-first"


def test_owner_conversation_data_version_and_intent_are_part_of_the_key():
    baseline = _fingerprint()

    assert _fingerprint(user_id=8) != baseline
    assert _fingerprint(conversation_id=12) != baseline
    assert _fingerprint(data_version="health-v2") != baseline
    assert _fingerprint(intent="image_analysis", image_hashes=("abc",)) != baseline


def test_cache_expires_and_allows_a_fresh_run():
    cache = SemanticTurnDedupeCache(ttl_seconds=5)
    cache.resolve(fingerprint=_fingerprint(), proposed_client_turn_id="old", now=1)
    fresh = cache.resolve(
        fingerprint=_fingerprint(), proposed_client_turn_id="fresh", now=7
    )

    assert fresh.dedupe_hit is False
    assert fresh.client_turn_id == "fresh"


def test_write_shaped_or_uncertain_requests_are_never_semantic_candidates():
    assert is_semantic_read_only_candidate("分析我最近 7 天睡眠") is True
    assert is_semantic_read_only_candidate("记录我喝了 1200 毫升水") is False
    assert is_semantic_read_only_candidate("修改昨天的晚餐记录") is False
    assert is_semantic_read_only_candidate("delete yesterday's record") is False
    assert is_semantic_read_only_candidate("hello") is False


def test_distributed_cache_coalesces_requests_across_worker_local_caches(monkeypatch):
    values = {}

    class FakeRedis:
        def set(self, key, value, *, nx, ex):
            assert nx is True and ex > 0
            if key in values:
                return False
            values[key] = value
            return True

        def get(self, key):
            return values.get(key)

    # Earlier tests can legitimately put the module-level Redis circuit breaker
    # into its 30-second cooldown. This case replaces Redis with a healthy fake,
    # so reset that independent global state instead of depending on test order.
    monkeypatch.setattr(
        "app.services.agent_turn_idempotency._redis_retry_after",
        0.0,
    )
    monkeypatch.setattr("app.utils.redis_cache.get_redis_client", lambda: FakeRedis())
    first = resolve_distributed_semantic_turn(
        cache=SemanticTurnDedupeCache(),
        fingerprint=_fingerprint(),
        proposed_client_turn_id="worker-a",
    )
    duplicate = resolve_distributed_semantic_turn(
        cache=SemanticTurnDedupeCache(),
        fingerprint=_fingerprint(),
        proposed_client_turn_id="worker-b",
    )

    assert first.dedupe_hit is False
    assert duplicate.dedupe_hit is True
    assert duplicate.client_turn_id == "worker-a"
