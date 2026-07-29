"""Twin mutations must invalidate both Twin and derived Safety caches."""

from app.twin.cache import invalidate_twin as real_invalidate_twin


class _FakeRedis:
    def __init__(self):
        self.keys = {
            "twin:v2:42": "twin",
            "safety:v3:42:s2:l8:d1": "safety",
            "safety:v3:42:s0:l50:d0": "safety",
            "safety:v3:99:s2:l8:d1": "other-user",
        }

    def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self.keys:
                deleted += 1
                del self.keys[key]
        return deleted

    def scan(self, cursor, match=None, count=None):
        prefix = (match or "").removesuffix("*")
        return 0, [key for key in self.keys if key.startswith(prefix)]


def test_invalidate_twin_also_invalidates_derived_safety_cache(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(
        "app.utils.redis_cache.get_redis_client",
        lambda: fake,
    )
    monkeypatch.setattr(
        "app.services.starter_pregen.invalidate_pregen",
        lambda _user_id: None,
    )

    real_invalidate_twin(42)

    assert "twin:v2:42" not in fake.keys
    assert not any(key.startswith("safety:v3:42:") for key in fake.keys)
    assert "safety:v3:99:s2:l8:d1" in fake.keys
