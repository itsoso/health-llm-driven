"""Deletion cache verification never guesses ownership from numeric substrings."""
import json

import pytest

from app.models.user import User
from app.services import account_deletion


class KeyOnlyRedis:
    def __init__(self, keys=(), pages=None):
        self.keys = list(keys)
        self.pages = pages
        self.calls = 0

    def scan(self, cursor=0, *, match, count):
        assert match == "*"
        assert count == 100
        self.calls += 1
        if self.pages is not None:
            return self.pages[self.calls - 1]
        return 0, self.keys

    def scan_iter(self, match):
        # Exercise the old implementation in the RED run, including its bug.
        from fnmatch import fnmatchcase
        return (key for key in self.keys if fnmatchcase(str(key), match))

    def get(self, *args):
        raise AssertionError("Must not read cached health content")

    def delete(self, *args):
        raise AssertionError("Verification must not delete another user's data")


OWNED_KEYS = [
    "daily_rec:12:2026-09-07", "supplement_rec:12:2026-09-07",
    "rec_gen_lock:12:2026-09-07", "dim_analysis:12:2026-09-07:sleep",
    "twin:v2:12", "twin_env:12", "safety:v3:12:s0:l100:d1",
    "starter_polish:v2:12:abcdef", "starter_pregen:v2:12:abcdef",
    "starter_pregen:inflight:v2:12:abcdef", "starter_pregen:idx:v2:12",
    "agent_loop:push_count:12:20260907",
    "genetic_report:agent_summary:v1:u12:p42",
    "genetic_snp_detail:v2:user=12:rsid=rs1:gt=AA",
    "observability:dashboard:d=7:u=12:j=0",
]


def _report(monkeypatch, keys=(), *, client=None):
    client = client if client is not None else KeyOnlyRedis(keys)
    monkeypatch.setattr(account_deletion, "get_redis_client", lambda: client)
    return account_deletion._cache_report(12)


@pytest.mark.parametrize("key", OWNED_KEYS)
def test_exact_owner_slots_detect_owned_keys(monkeypatch, key):
    result = _report(monkeypatch, [key])
    assert result["status"] == "checked"
    assert result["keys"] == 1
    assert result["unresolved_keys"] == 0
    assert key not in json.dumps(result)


@pytest.mark.parametrize("key", [key.replace("12", "312") for key in OWNED_KEYS])
def test_other_owners_are_not_counted(monkeypatch, key):
    result = _report(monkeypatch, [key])
    assert result["status"] == "checked"
    assert result["keys"] == 0


def test_dates_and_hashes_are_not_owner_ids(monkeypatch):
    result = _report(monkeypatch, ["daily_rec:31:2026-12-12", "starter_polish:v2:31:a12bc"])
    assert result["keys"] == 0
    assert result["status"] == "checked"


@pytest.mark.parametrize("key", [
    "orch:v1:abcdef", "agent:semantic-turn:v1:abcdef",
    "history_fold:v2:policy:43", "future_health_cache:abcdef",
    "observability:dashboard:d=7:u=all:j=0", "celery-task-meta-abcdef",
    "twin:v999:31", "genetic_snp_detail:v2:user=not-an-owner:rsid=rs1:gt=AA",
    b"\xffprivate-key", "twin:v2:012",
])
def test_unprovable_ownership_blocks_without_payload_reads(monkeypatch, key):
    result = _report(monkeypatch, [key])
    assert result["status"] == "partial"
    assert result["keys"] == 0
    assert result["unresolved_keys"] == 1


def test_duplicates_and_byte_keys_count_once(monkeypatch):
    client = KeyOnlyRedis(pages=[(1, [b"twin:v2:12"]), (0, ["twin:v2:12"])])
    result = _report(monkeypatch, client=client)
    assert result["keys"] == 1
    assert result["scanned_keys"] == 1
    assert result["status"] == "checked"


def test_page_limit_including_empty_pages_is_fail_closed(monkeypatch):
    monkeypatch.setattr(account_deletion, "_CACHE_SCAN_MAX_PAGES", 2)
    result = _report(monkeypatch, client=KeyOnlyRedis(pages=[(1, []), (2, [])]))
    assert result["status"] == "partial"
    assert result["scan_complete"] is False


def test_key_limit_is_fail_closed(monkeypatch):
    monkeypatch.setattr(account_deletion, "_CACHE_SCAN_MAX_KEYS", 1)
    result = _report(monkeypatch, ["twin:v2:31", "twin:v2:32"])
    assert result["status"] == "partial"
    assert result["scan_complete"] is False


def test_duplicate_keys_cannot_bypass_scan_work_limit(monkeypatch):
    monkeypatch.setattr(account_deletion, "_CACHE_SCAN_MAX_KEYS", 1)
    result = _report(monkeypatch, ["twin:v2:31", "twin:v2:31"])
    assert result["status"] == "partial"
    assert result["scan_complete"] is False


def test_oversized_key_is_not_silently_skipped(monkeypatch):
    monkeypatch.setattr(account_deletion, "_CACHE_KEY_MAX_BYTES", 4)
    result = _report(monkeypatch, ["private-health-cache-key"])
    assert result["status"] == "partial"
    assert result["scan_complete"] is False


def test_mid_scan_error_cannot_return_a_checked_zero(monkeypatch, caplog):
    class FailingRedis(KeyOnlyRedis):
        def scan(self, cursor=0, *, match, count):
            if cursor == 0:
                return 1, ["twin:v2:31"]
            raise RuntimeError("secret-cache-key")
    result = _report(monkeypatch, client=FailingRedis())
    assert result["status"] == "error"
    assert result["keys"] is None
    assert "secret-cache-key" not in caplog.text + json.dumps(result)


def test_cache_errors_are_redacted_and_fail_closed(monkeypatch, caplog):
    def fail():
        raise RuntimeError("secret-health-payload")
    monkeypatch.setattr(account_deletion, "get_redis_client", fail)
    result = account_deletion._cache_report(12)
    assert result["status"] == "error"
    assert result["keys"] is None
    assert "secret-health-payload" not in caplog.text + json.dumps(result)


def test_unavailable_cache_never_reports_zero(monkeypatch):
    monkeypatch.setattr(account_deletion, "get_redis_client", lambda: None)
    result = account_deletion._cache_report(12)
    assert result["status"] == "unavailable"
    assert result["keys"] is None


@pytest.mark.parametrize("keys,expected", [([], True), (["orch:v1:abcdef"], False), (["new_cache:abcdef"], False)])
def test_real_report_requires_complete_cache_verification(
    db, auth_user_and_headers, monkeypatch, tmp_path, keys, expected
):
    user, _ = auth_user_and_headers
    user_id = user.id
    db.delete(db.query(User).filter(User.id == user_id).one())
    db.commit()
    monkeypatch.setattr(account_deletion, "_UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(account_deletion, "get_redis_client", lambda: KeyOnlyRedis(keys))
    result = account_deletion.build_deletion_verification_report(db, user_id)
    assert result["user_exists"] is False
    assert result["blocking_rows"] == 0
    assert result["can_finalize"] is expected
