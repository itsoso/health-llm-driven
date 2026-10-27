"""Synthetic local roles/database only: fixed DDL, append grants and serial proof."""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
ROOT=Path(__file__).resolve().parents[1]
URL=os.getenv('EXAM_ATTEMPTS_RELEASE_TEST_URL')

@pytest.fixture
def pg(tmp_path,monkeypatch):
    if not URL:pytest.skip('explicit local synthetic PostgreSQL required')
    url=make_url(URL)
    if url.host not in ('127.0.0.1','localhost') or not url.database.endswith('_test'):
        pytest.fail('local dedicated test cluster required')
    spec=importlib.util.spec_from_file_location('exam_release_pg_test',ROOT/'scripts/exam_attempts_release.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    monkeypatch.setattr(m,'protected_read',lambda p,**kw:p.read_bytes())
    suffix=uuid4().hex[:12]
    database,migrator,role='ex_release_'+suffix,'ex_m_'+suffix,'ex_r_'+suffix
    password=uuid4().hex
    admin=create_engine(url,isolation_level='AUTOCOMMIT');migration=runtime=None
    try:
        with admin.connect() as c:
            c.execute(text(f'CREATE ROLE {migrator} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :password'),{'password':password})
            c.execute(text(f'CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :password'),{'password':password})
            c.execute(text(f'CREATE DATABASE {database} OWNER {migrator}'))
        migration=create_engine(url.set(username=migrator,password=password,database=database))
        runtime=create_engine(url.set(username=role,password=password,database=database))
        with migration.begin() as c:
            c.execute(text('CREATE TABLE users(id INTEGER PRIMARY KEY)'))
            c.execute(text('CREATE TABLE schema_migrations(id VARCHAR(200) PRIMARY KEY,checksum VARCHAR(64) NOT NULL,applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'))
            c.execute(text("INSERT INTO schema_migrations(id,checksum) VALUES('old','a')"))
            c.execute(text(f'GRANT SELECT,DELETE ON users TO {role}'))
            c.execute(text('INSERT INTO users VALUES(1)'))
        plan={'old':'a'*40,'candidate':'b'*40,'checksum':m.SQL_HASH}
        expected={'old':'a',m.MIGRATION:m.SQL_HASH}
        yield m,migration,runtime,role,plan,expected,tmp_path
    finally:
        if migration:migration.dispose()
        if runtime:runtime.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS {database} WITH (FORCE)'))
            c.execute(text(f'DROP ROLE IF EXISTS {role}'))
            c.execute(text(f'DROP ROLE IF EXISTS {migrator}'))
        admin.dispose()


def apply(pg):
    m,migration,runtime,role,plan,expected,record=pg
    m.write_once(record/'intent.json',plan)
    with migration.begin() as c:m.apply_exact(c,ROOT,plan,role)


def test_atomic_append_runtime_serial_usage_account_cascade_and_readback(pg):
    m,migration,runtime,role,plan,expected,record=pg
    with migration.connect() as c:
        assert m.database_state(c,expected)=='PENDING'
        assert m.role_identity(c)['role']!=role
    apply(pg)
    assert m.reentry_state(record,plan,'APPLIED')=='READBACK'
    with migration.connect() as c:
        assert m.database_state(c,expected)=='APPLIED'
        proof=m.committed_proof(c,plan,record,role)
        evidence=m.schema_evidence(c,role)
        assert set(evidence)=={'tables','sequences'}
    m.write_once(record/'completed.json',proof)
    with runtime.begin() as c:
        c.execute(text("INSERT INTO life_exam_attempts(id,user_id,request_id,question_id,question_version,choice_index,correct_index,correct,elapsed_seconds,study_date,answered_at,question_snapshot) VALUES(:id,1,:request,'e101',1,0,1,false,10,CURRENT_DATE,now(),:snapshot)"),{'id':str(uuid4()),'request':str(uuid4()),'snapshot':'{"prompt":"synthetic"}'})
        assert c.execute(text('SELECT count(*) FROM life_exam_attempts')).scalar_one()==1
    for command in ['UPDATE life_exam_attempts SET correct=true','DELETE FROM life_exam_attempts',"SELECT setval('life_exam_attempts_sequence_seq',1)",'SELECT last_value FROM life_exam_attempts_sequence_seq']:
        with pytest.raises(DBAPIError):
            with runtime.begin() as c:c.execute(text(command))
    with runtime.begin() as c:
        c.execute(text('DELETE FROM users WHERE id=1'))
        assert c.execute(text('SELECT count(*) FROM life_exam_attempts')).scalar_one()==0
    with migration.connect() as c:assert m.committed_proof(c,plan,record,role)==proof


def test_failed_transaction_preserves_intent_and_blocks_repeat(pg,monkeypatch):
    m,migration,runtime,role,plan,expected,record=pg
    m.write_once(record/'intent.json',plan)
    def fail(*args):raise m.ReleaseBlocked('synthetic proof failure')
    monkeypatch.setattr(m,'schema_evidence',fail)
    with pytest.raises(m.ReleaseBlocked):
        with migration.begin() as c:m.apply_exact(c,ROOT,plan,role)
    with migration.connect() as c:assert m.database_state(c,expected)=='PENDING'
    with pytest.raises(m.ReleaseBlocked):m.reentry_state(record,plan,'PENDING')
    assert not (record/'completed.json').exists()


@pytest.mark.parametrize('ddl',[
    'ALTER TABLE life_exam_attempts ADD COLUMN unexpected TEXT',
    'ALTER TABLE life_exam_attempts ALTER COLUMN sequence SET DEFAULT 5',
    'GRANT SELECT(question_snapshot) ON life_exam_attempts TO PUBLIC',
    'GRANT UPDATE(choice_index) ON life_exam_attempts TO {role}',
    'GRANT USAGE ON SEQUENCE life_exam_attempts_sequence_seq TO {role} WITH GRANT OPTION',
    'GRANT SELECT ON life_exam_attempts TO {role} WITH GRANT OPTION',
    'ALTER SEQUENCE life_exam_attempts_sequence_seq INCREMENT BY 2',
    'ALTER SEQUENCE life_exam_attempts_sequence_seq OWNED BY NONE',
    'GRANT USAGE ON SEQUENCE life_exam_attempts_sequence_seq TO PUBLIC',
    'GRANT SELECT ON life_exam_attempts TO PUBLIC',
    'GRANT SELECT ON SEQUENCE life_exam_attempts_sequence_seq TO {role}',
    'GRANT UPDATE ON SEQUENCE life_exam_attempts_sequence_seq TO {role}',
    'REVOKE USAGE ON SEQUENCE life_exam_attempts_sequence_seq FROM {role}',
    'GRANT UPDATE ON life_exam_attempts TO {role}',
    'REVOKE INSERT ON life_exam_attempts FROM {role}',
])
def test_readback_rejects_schema_serial_and_privilege_drift(pg,ddl):
    m,migration,runtime,role,plan,expected,record=pg;apply(pg)
    with migration.begin() as c:c.execute(text(ddl.format(role=role)))
    with migration.connect() as c:
        with pytest.raises(m.ReleaseBlocked):m.committed_proof(c,plan,record,role)


def test_preexisting_sequence_and_other_pending_migration_are_rejected(pg):
    m,migration,runtime,role,plan,expected,record=pg
    with migration.connect() as c:
        with pytest.raises(m.ReleaseBlocked):m.database_state(c,{**expected,'other':'extra'})
    with migration.begin() as c:c.execute(text('CREATE SEQUENCE life_exam_attempts_sequence_seq'))
    with migration.connect() as c:
        with pytest.raises(m.ReleaseBlocked):m.database_state(c,expected)


def test_privileged_role_and_index_collision_block(pg):
    m,migration,runtime,role,plan,expected,record=pg
    admin=create_engine(make_url(URL).set(database=migration.url.database))
    try:
        with admin.connect() as c:
            with pytest.raises(m.ReleaseBlocked):m.role_identity(c)
    finally:admin.dispose()
    with migration.begin() as c:c.execute(text('CREATE INDEX ix_life_exam_owner_date_sequence ON users(id)'))
    with pytest.raises(m.ReleaseBlocked):
        with migration.begin() as c:m.apply_exact(c,ROOT,plan,role)
    with migration.connect() as c:assert m.database_state(c,expected)=='PENDING'
