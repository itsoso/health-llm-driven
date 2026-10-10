"""Replay authority migration against the previous audit table, preserving IDs."""
from pathlib import Path
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

BASE = Path(__file__).resolve().parents[1] / 'migrations' / 'managed'


def test_operator_migration_preserves_old_audit(db):
    dialect = db.get_bind().dialect.name
    old = (BASE / f'20260720_120000_agent_runtime_rollout.{dialect}.sql').read_text()
    start = old.index('CREATE TABLE IF NOT EXISTS agent_runtime_rollout_events')
    end = old.index('CREATE INDEX IF NOT EXISTS ix_agent_runs_finished_status')
    old = old[start:end]
    migration = (BASE / f'20261010_230000_runtime_operator_recovery.{dialect}.sql').read_text()
    db.execute(text('DROP TABLE agent_runtime_rollout_events'))
    # Managed files contain no SQL string with semicolons in these DDLs.
    for statement in old.split(';'):
        if statement.strip():
            db.execute(text(statement))
    db.execute(text("INSERT INTO agent_runtime_rollout_events (id,action,actor_kind,reason_code) VALUES (42,'pause','system','reconciliation_detected')"))
    for statement in migration.split(';'):
        if statement.strip():
            db.execute(text(statement))
    db.commit()
    assert db.execute(text('SELECT id, actor_kind, operator_review FROM agent_runtime_rollout_events')).all() == [(42, 'system', None)]
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO agent_runtime_rollout_events (action,actor_kind,reason_code) VALUES ('resume','operator','manual_resume')"))
        db.commit()
    db.rollback()
    db.execute(text("INSERT INTO agent_runtime_rollout_events (action,actor_kind,reason_code,operator_review) VALUES ('resume','operator','manual_resume','{}')"))
    db.commit()
    assert db.execute(text('SELECT count(*) FROM agent_runtime_rollout_events')).scalar() == 2
