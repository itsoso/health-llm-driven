import hashlib
from pathlib import Path
import sqlite3


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS validator_snapshots(
  id INTEGER PRIMARY KEY, sampled_at TEXT NOT NULL UNIQUE, validator_index INTEGER NOT NULL,
  balance_gwei INTEGER NOT NULL, status TEXT NOT NULL, slashed INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS proposed_blocks(id INTEGER PRIMARY KEY, slot INTEGER UNIQUE, execution_block INTEGER);
CREATE TABLE IF NOT EXISTS execution_rewards(id INTEGER PRIMARY KEY, block_number INTEGER UNIQUE, priority_wei TEXT, mev_wei TEXT, complete INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS exchange_rates(id INTEGER PRIMARY KEY, fetched_at TEXT NOT NULL, provider TEXT NOT NULL, eth_cny TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS daily_reports(report_date TEXT PRIMARY KEY, payload_json TEXT NOT NULL, complete INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS deliveries(delivery_key TEXT PRIMARY KEY, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY, alert_key TEXT NOT NULL, level TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS api_tokens(id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, scope TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS api_audit(id INTEGER PRIMARY KEY, token_id TEXT, path TEXT NOT NULL, status_code INTEGER NOT NULL, created_at TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    def claim_delivery(self, delivery_key: str) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("INSERT INTO deliveries(delivery_key) VALUES (?)", (delivery_key,))
            return True
        except sqlite3.IntegrityError:
            return False

    def save_token(self, token_id: str, plaintext: str, scope: str) -> None:
        token_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO api_tokens(id, token_hash, scope) VALUES (?, ?, ?)",
                (token_id, token_hash, scope),
            )
