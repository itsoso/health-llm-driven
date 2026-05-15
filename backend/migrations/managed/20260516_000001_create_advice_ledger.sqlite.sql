CREATE TABLE IF NOT EXISTS advice_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    advice_key VARCHAR(64) NOT NULL,
    source VARCHAR(50) NOT NULL,
    source_id VARCHAR(120) NOT NULL,
    domain VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    metric_key VARCHAR(80),
    target_value VARCHAR(120),
    evidence_tier VARCHAR(50) NOT NULL,
    confidence VARCHAR(20) NOT NULL,
    claim_boundary TEXT NOT NULL,
    decision VARCHAR(20) NOT NULL DEFAULT 'allowed',
    reason VARCHAR(50) NOT NULL DEFAULT 'allowed',
    conflicts_with_id INTEGER,
    valid_for_date DATE,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_advice_ledger_user_key
    ON advice_ledger(user_id, advice_key);
CREATE INDEX IF NOT EXISTS idx_advice_ledger_user_domain
    ON advice_ledger(user_id, domain, status);
CREATE INDEX IF NOT EXISTS idx_advice_ledger_valid_for_date
    ON advice_ledger(valid_for_date);
