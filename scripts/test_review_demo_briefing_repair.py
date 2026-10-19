"""Pure state-machine regression tests; no production entry point."""
import importlib.util
import json
from pathlib import Path

import pytest


def load():
    path = Path(__file__).with_name('review_demo_briefing_repair.py')
    spec = importlib.util.spec_from_file_location('briefing_repair_test_subject', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Adapter:
    def __init__(self, tmp_path, module):
        self.record = tmp_path / 'repair'
        self.evidence = dict(target_sha=module.TARGET, failed_operation=module.FAILED_OPERATION,
            fixture_sha256=module.FIXTURE_SHA256, acknowledgement_sha256='a' * 64,
            database_snapshot_sha256='b' * 64, production_evidence_sha256='e' * 64,
            health_snapshot_sha256='f' * 64, demo_user_id=1, action=module.ACTION)
        self.applied = 0
        self.change = False

    def inspect(self):
        return {**self.evidence, **({'database_snapshot_sha256': 'c' * 64} if self.change else {})}

    def prepare_record(self):
        self.record.mkdir(mode=0o700)

    def write(self, name, value):
        with (self.record / name).open('x') as stream:
            json.dump(value, stream)

    def apply_once(self, evidence):
        self.applied += 1
        return {'state': 'VERIFIED_BRIEFING_ONLY', 'before_sha256': evidence['database_snapshot_sha256'],
                'after_sha256': 'd' * 64}


def test_inspect_never_writes(tmp_path):
    m = load(); a = Adapter(tmp_path, m)
    assert m.repair(a)['state'] == 'INSPECTED_NOT_AUTHORIZED'
    assert not a.record.exists() and a.applied == 0


def test_authority_and_exact_evidence_required_before_intent(tmp_path):
    m = load(); a = Adapter(tmp_path, m)
    digest = m.repair(a)['evidence_sha256']
    with pytest.raises(m.RepairError):
        m.repair(a, evidence_sha256=digest)
    with pytest.raises(m.RepairError):
        m.repair(a, authorized=True, evidence_sha256='0' * 64)
    assert not a.record.exists() and a.applied == 0


def test_profile_drift_blocks_even_inspection(tmp_path):
    m = load(); a = Adapter(tmp_path, m)
    a.evidence['target_sha'] = 'f' * 40
    with pytest.raises(m.RepairError):
        m.repair(a)
    assert not a.record.exists()


def test_attempt_is_one_shot_and_never_unblocks_release(tmp_path):
    m = load(); a = Adapter(tmp_path, m)
    digest = m.repair(a)['evidence_sha256']
    out = m.repair(a, authorized=True, evidence_sha256=digest)
    assert out['release_unblocked'] is False and out['reset_authorized'] is False
    assert a.applied == 1
    with pytest.raises(m.RepairError):
        m.repair(a, authorized=True, evidence_sha256=digest)
    assert a.applied == 1


def test_unknown_outcome_preserves_intent_and_cannot_retry(tmp_path):
    m = load(); a = Adapter(tmp_path, m)
    digest = m.repair(a)['evidence_sha256']
    def unknown(_):
        a.applied += 1
        raise RuntimeError('synthetic uncertain commit')
    a.apply_once = unknown
    with pytest.raises(RuntimeError):
        m.repair(a, authorized=True, evidence_sha256=digest)
    assert (a.record / 'intent.json').exists()
    assert not (a.record / 'completed.json').exists()
    with pytest.raises(m.RepairError):
        m.repair(a, authorized=True, evidence_sha256=digest)
    assert a.applied == 1


def test_post_intent_drift_blocks_mutation(tmp_path):
    m = load(); a = Adapter(tmp_path, m)
    digest = m.repair(a)['evidence_sha256']
    write = a.write
    def drift(name, value):
        write(name, value)
        a.change = True
    a.write = drift
    with pytest.raises(m.RepairError):
        m.repair(a, authorized=True, evidence_sha256=digest)
    assert a.applied == 0 and (a.record / 'intent.json').exists()

@pytest.fixture
def pg(monkeypatch):
    import os
    import uuid
    from sqlalchemy import create_engine, text
    url = os.environ.get('REVA_REVIEW_CLOSURE_TEST_DATABASE_URL')
    if not url:
        pytest.skip('dedicated PostgreSQL integration URL required')
    engine = create_engine(url, isolation_level='SERIALIZABLE')
    assert engine.dialect.name == 'postgresql'
    schema = 'briefing_' + uuid.uuid4().hex
    m = load()
    monkeypatch.setattr(m, 'SCHEMA', schema)
    with engine.begin() as c:
        c.execute(text(f'CREATE SCHEMA {schema}'))
        c.execute(text(f'''CREATE TABLE {schema}.users (id SERIAL PRIMARY KEY, email TEXT UNIQUE,
            is_active BOOLEAN, is_approved BOOLEAN, is_admin BOOLEAN)'''))
        c.execute(text(f'''CREATE TABLE {schema}.agent_conversations (id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES {schema}.users(id), title TEXT, session_key TEXT,
            created_at TIMESTAMP, updated_at TIMESTAMP)'''))
        c.execute(text(f'''CREATE TABLE {schema}.agent_messages (id SERIAL PRIMARY KEY,
            conversation_id INTEGER REFERENCES {schema}.agent_conversations(id), role TEXT,
            content TEXT, image_url TEXT, meta JSONB, created_at TIMESTAMP)'''))
        c.execute(text(f"INSERT INTO {schema}.users VALUES (1,'review@example.invalid',true,true,false),(2,'other@example.invalid',true,true,false)"))
        c.execute(text(f"INSERT INTO {schema}.agent_conversations (user_id,title,session_key,created_at,updated_at) VALUES (1,'old','old',now()-interval '1 day',now()-interval '1 day'),(2,'other','other',now(),now())"))
        c.execute(text(f"INSERT INTO {schema}.agent_messages (conversation_id,role,content,created_at) VALUES (1,'user','old content',now()),(2,'user','other content',now())"))
    try:
        yield m, engine, schema
    finally:
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        engine.dispose()


def snapshot(m, engine):
    with engine.begin() as c:
        return m.inspect_briefing_rows(c, 'review@example.invalid', 1)


def test_postgres_create_preserves_old_rows(pg):
    from sqlalchemy import text
    m, engine, schema = pg
    before = snapshot(m, engine)
    fixture = Path(__file__).parents[1] / 'backend/fixtures/demo_user_minimal.json'
    with engine.begin() as c:
        result = m.create_briefing_rows(c, 'review@example.invalid', 1, before, fixture)
    assert result['state'] == 'VERIFIED_BRIEFING_ONLY'
    with engine.begin() as c:
        assert c.execute(text(f'SELECT count(*) FROM {schema}.agent_conversations')).scalar_one() == 3
        assert c.execute(text(f'SELECT count(*) FROM {schema}.agent_messages')).scalar_one() == 4
        assert c.execute(text(f"SELECT content FROM {schema}.agent_messages WHERE id=1")).scalar_one() == 'old content'
        assert c.execute(text(f"SELECT title FROM {schema}.agent_conversations WHERE user_id=1 ORDER BY updated_at DESC LIMIT 1")).scalar_one().startswith('每日健康简报')
    with engine.begin() as c, pytest.raises(m.RepairError):
        m.create_briefing_rows(c, 'review@example.invalid', 1, before, fixture)


def test_postgres_snapshot_drift_rejects_before_insert(pg):
    from sqlalchemy import text
    m, engine, schema = pg
    before = snapshot(m, engine)
    with engine.begin() as c:
        c.execute(text(f"UPDATE {schema}.agent_messages SET content='changed' WHERE id=1"))
    with pytest.raises(m.RepairError), engine.begin() as c:
        m.create_briefing_rows(c, 'review@example.invalid', 1, before, Path(__file__).parents[1] / 'backend/fixtures/demo_user_minimal.json')
    with engine.begin() as c:
        assert c.execute(text(f'SELECT count(*) FROM {schema}.agent_conversations')).scalar_one() == 2


def test_postgres_future_timestamp_rejected(pg):
    from sqlalchemy import text
    m, engine, schema = pg
    with engine.begin() as c:
        c.execute(text(f"UPDATE {schema}.agent_conversations SET updated_at=now()+interval '1 day' WHERE user_id=1"))
    with pytest.raises(m.RepairError):
        snapshot(m, engine)


def test_postgres_admin_account_rejected(pg):
    from sqlalchemy import text
    m, engine, schema = pg
    with engine.begin() as c:
        c.execute(text(f'UPDATE {schema}.users SET is_admin=true WHERE id=1'))
    with pytest.raises(m.RepairError):
        snapshot(m, engine)


def test_postgres_fixed_identity_not_just_email(pg):
    m, engine, _ = pg
    with pytest.raises(m.RepairError), engine.begin() as c:
        m.inspect_briefing_rows(c, 'review@example.invalid', 2)


def test_postgres_non_utc_session_and_fresh_readback(pg):
    from sqlalchemy import text
    m, engine, _ = pg
    before = snapshot(m, engine)
    fixture = Path(__file__).parents[1] / 'backend/fixtures/demo_user_minimal.json'
    with engine.begin() as c:
        c.execute(text("SET LOCAL TIME ZONE 'Asia/Shanghai'"))
        result = m.create_briefing_rows(c, 'review@example.invalid', 1, before, fixture)
    with engine.begin() as c:
        assert m.verify_created_briefing_rows(c, 'review@example.invalid', 1, result['after_sha256'], fixture)['state'] == 'VERIFIED_BRIEFING_ONLY'
    with pytest.raises(m.RepairError), engine.begin() as c:
        m.verify_created_briefing_rows(c, 'review@example.invalid', 1, '0' * 64, fixture)


def test_postgres_changed_fixture_never_inserts(pg, tmp_path):
    from sqlalchemy import text
    m, engine, schema = pg
    before = snapshot(m, engine)
    fixture = tmp_path / 'fixture.json'; fixture.write_text('{}')
    with pytest.raises(m.RepairError), engine.begin() as c:
        m.create_briefing_rows(c, 'review@example.invalid', 1, before, fixture)
    with engine.begin() as c:
        assert c.execute(text(f'SELECT count(*) FROM {schema}.agent_conversations')).scalar_one() == 2


def test_postgres_rollback_leaves_no_new_rows(pg):
    from sqlalchemy import text
    m, engine, schema = pg
    before = snapshot(m, engine)
    fixture = Path(__file__).parents[1] / 'backend/fixtures/demo_user_minimal.json'
    with pytest.raises(RuntimeError), engine.begin() as c:
        m.create_briefing_rows(c, 'review@example.invalid', 1, before, fixture)
        raise RuntimeError('synthetic pre-commit failure')
    assert snapshot(m, engine) == before


def test_postgres_row_lock_blocks_competing_mutation(pg):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    m, engine, schema = pg
    before = snapshot(m, engine)
    fixture = Path(__file__).parents[1] / 'backend/fixtures/demo_user_minimal.json'
    with engine.begin() as first:
        m.create_briefing_rows(first, 'review@example.invalid', 1, before, fixture)
        with pytest.raises(DBAPIError), engine.begin() as second:
            second.exec_driver_sql("SET LOCAL lock_timeout='50ms'")
            second.execute(text(f"UPDATE {schema}.agent_messages SET content='racing' WHERE id=1"))
