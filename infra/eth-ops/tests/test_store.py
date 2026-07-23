from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from staking_report.store import Store  # noqa: E402


def test_schema_creation_is_idempotent(tmp_path: Path) -> None:
    store = Store(tmp_path / "staking.db")
    store.initialize()
    store.initialize()
    with sqlite3.connect(store.path) as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"validator_snapshots", "daily_reports", "deliveries", "api_tokens"} <= tables


def test_delivery_key_is_unique(tmp_path: Path) -> None:
    store = Store(tmp_path / "staking.db")
    store.initialize()
    assert store.claim_delivery("telegram:daily:2026-07-22:abc") is True
    assert store.claim_delivery("telegram:daily:2026-07-22:abc") is False


def test_api_tokens_store_hash_not_plaintext(tmp_path: Path) -> None:
    store = Store(tmp_path / "staking.db")
    store.initialize()
    store.save_token("id1", "secret-token", "reports:read")
    with sqlite3.connect(store.path) as conn:
        row = conn.execute("SELECT token_hash FROM api_tokens WHERE id='id1'").fetchone()
    assert row and row[0] != "secret-token"
