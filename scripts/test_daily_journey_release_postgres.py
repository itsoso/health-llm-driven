"""Real isolated PostgreSQL proof for the bounded no-backup migration path.

Requires an explicitly supplied local synthetic admin DSN; never uses app env.
"""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv('DAILY_JOURNEY_RELEASE_TEST_URL')


@pytest.fixture
def pg(tmp_path, monkeypatch):
    if not URL:
        pytest.skip('explicit local synthetic PostgreSQL required')
    url = make_url(URL)
    if url.host not in ('127.0.0.1', 'localhost') or not url.database.endswith('_test'):
        pytest.fail('local dedicated test cluster required')
    spec = importlib.util.spec_from_file_location('daily_release_pg_test', ROOT / 'scripts/daily_journey_release.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, 'protected_read', lambda p, **kw: p.read_bytes())
    suffix = uuid4().hex[:12]
    database, migrator, runtime_role = 'dj_release_' + suffix, 'dj_m_' + suffix, 'dj_r_' + suffix
    password = uuid4().hex  # synthetic per-test roles, never an application credential
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    migration = runtime = None
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE ROLE {migrator} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :password'), {'password': password})
            c.execute(text(f'CREATE ROLE {runtime_role} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :password'), {'password': password})
            c.execute(text(f'CREATE DATABASE {database} OWNER {migrator}'))
        migration = create_engine(url.set(username=migrator, password=password, database=database))
        runtime = create_engine(url.set(username=runtime_role, password=password, database=database))
        with migration.begin() as c:
            c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY)'))
            c.execute(text('CREATE TABLE schema_migrations(id VARCHAR(200) PRIMARY KEY,checksum VARCHAR(64) NOT NULL,applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'))
            c.execute(text("INSERT INTO schema_migrations(id,checksum) VALUES('old','a')"))
            c.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON users TO {runtime_role}'))
            c.execute(text('INSERT INTO users VALUES(1)'))
        plan = {'old': 'a' * 40, 'candidate': 'b' * 40, 'checksum': m.SQL_HASH}
        expected = {'old': 'a', m.MIGRATION: m.SQL_HASH}
        yield m, migration, runtime, runtime_role, plan, expected, tmp_path
    finally:
        if migration:
            migration.dispose()
        if runtime:
            runtime.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS {database} WITH (FORCE)'))
            c.execute(text(f'DROP ROLE IF EXISTS {runtime_role}'))
            c.execute(text(f'DROP ROLE IF EXISTS {migrator}'))
        admin.dispose()


def test_atomic_addition_runtime_crud_account_cascade_and_readback(pg):
    m, migration, runtime, role, plan, expected, record = pg
    with migration.connect() as c:
        assert m.database_state(c, expected) == 'PENDING'
        before = c.execute(text("SELECT column_name,data_type FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position")).all()
        assert m.role_identity(c)['role'] != 'postgres'
    m.write_once(record / 'intent.json', plan)
    with migration.begin() as c:
        m.apply_exact(c, ROOT, plan, role)
    # Simulated loss after COMMIT and before completion receipt: only readback.
    assert m.reentry_state(record, plan, 'APPLIED') == 'READBACK'
    with migration.connect() as c:
        assert m.database_state(c, expected) == 'APPLIED'
        proof = m.committed_proof(c, plan, record, role)
        assert before == c.execute(text("SELECT column_name,data_type FROM information_schema.columns WHERE table_name='users' ORDER BY ordinal_position")).all()
    m.write_once(record / 'completed.json', proof)
    with runtime.begin() as c:
        assert m.role_identity(c)['role'] == role
        c.execute(text("INSERT INTO daily_journey_requests VALUES(1,'request','session')"))
        c.execute(text("INSERT INTO daily_journey_sessions(id,user_id,client_id,local_date,timezone,status,version,segment,started_at,segment_started_at,deadline_at,expires_at,retention_days,point_count,annotations) VALUES('session',1,'client',CURRENT_DATE,'UTC','active',1,1,now(),now(),now()+interval '1 day',now()+interval '7 days',7,0,'ciphertext')"))
        c.execute(text("INSERT INTO daily_journey_points VALUES('session','point',1,'ciphertext')"))
        c.execute(text("UPDATE daily_journey_sessions SET status='ended' WHERE id='session'"))
        assert c.execute(text('SELECT count(*) FROM daily_journey_points')).scalar_one() == 1
        c.execute(text('DELETE FROM users WHERE id=1'))
        for name in m.TABLES:
            assert c.execute(text(f'SELECT count(*) FROM {name}')).scalar_one() == 0
    with migration.connect() as c:
        assert m.committed_proof(c, plan, record, role) == proof


def test_rolled_back_ddl_preserves_intent_and_refuses_replay(pg, monkeypatch):
    m, migration, runtime, role, plan, expected, record = pg
    m.write_once(record / 'intent.json', plan)
    def fail(*args):
        raise m.ReleaseBlocked('synthetic failure before ledger')
    monkeypatch.setattr(m, 'schema_evidence', fail)
    with pytest.raises(m.ReleaseBlocked):
        with migration.begin() as c:
            m.apply_exact(c, ROOT, plan, role)
    with migration.connect() as c:
        assert m.database_state(c, expected) == 'PENDING'
    with pytest.raises(m.ReleaseBlocked):
        m.reentry_state(record, plan, 'PENDING')
    assert not (record / 'completed.json').exists()


def test_readback_rejects_schema_drift_and_missing_crud(pg):
    m, migration, runtime, role, plan, expected, record = pg
    m.write_once(record / 'intent.json', plan)
    with migration.begin() as c:
        m.apply_exact(c, ROOT, plan, role)
    with migration.begin() as c:
        c.execute(text('ALTER TABLE daily_journey_points ADD COLUMN unexpected TEXT'))
    with migration.connect() as c:
        with pytest.raises(m.ReleaseBlocked):
            m.committed_proof(c, plan, record, role)
    with migration.begin() as c:
        c.execute(text('ALTER TABLE daily_journey_points DROP COLUMN unexpected'))
        c.execute(text(f'REVOKE DELETE ON daily_journey_sessions FROM {role}'))
    with migration.connect() as c:
        with pytest.raises(m.ReleaseBlocked):
            m.committed_proof(c, plan, record, role)


def test_preexisting_target_and_other_pending_migration_are_rejected(pg):
    m, migration, runtime, role, plan, expected, record = pg
    with migration.connect() as c:
        with pytest.raises(m.ReleaseBlocked):
            m.database_state(c, {**expected, 'other': 'extra'})
    with migration.begin() as c:
        c.execute(text('CREATE TABLE daily_journey_points(unrelated TEXT)'))
    with migration.connect() as c:
        with pytest.raises(m.ReleaseBlocked):
            m.database_state(c, expected)


def test_unsafe_role_and_public_grants_are_rejected(pg):
    m, migration, runtime, role, plan, expected, record = pg
    admin = create_engine(make_url(URL).set(database=migration.url.database))
    try:
        with admin.connect() as c:
            with pytest.raises(m.ReleaseBlocked):
                m.role_identity(c)
    finally:
        admin.dispose()
    with migration.begin() as c:
        m.apply_exact(c, ROOT, plan, role)
    with migration.begin() as c:
        c.execute(text('GRANT SELECT ON daily_journey_points TO PUBLIC'))
    with migration.connect() as c:
        with pytest.raises(m.ReleaseBlocked):
            m.schema_evidence(c, role)


def test_global_index_name_collision_rolls_back_instead_of_accepting_partial_schema(pg):
    m, migration, runtime, role, plan, expected, record = pg
    with migration.begin() as c:
        c.execute(text('CREATE INDEX ix_daily_journey_expiry ON users(id)'))
    with pytest.raises(m.ReleaseBlocked):
        with migration.begin() as c:
            m.apply_exact(c, ROOT, plan, role)
    with migration.connect() as c:
        assert m.database_state(c, expected) == 'PENDING'
