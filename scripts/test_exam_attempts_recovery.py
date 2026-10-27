import hashlib
import importlib.util
import json
from pathlib import Path
import pytest
from sqlalchemy import text
from test_exam_attempts_release_postgres import pg, ROOT

@pytest.fixture
def recovery(pg,monkeypatch):
    spec=importlib.util.spec_from_file_location('exam_recovery_test',ROOT/'scripts/exam_attempts_recovery.py')
    core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
    h,migration,runtime,role,_,expected,tmp=pg
    original=tmp/'original';original.mkdir();record=tmp/'recovery'
    token='synthetic-original-lease';publisher='c'*40
    with migration.connect() as c:identity=h.role_identity(c)
    with runtime.connect() as c:runtime_identity=h.role_identity(c)
    plan={'old':core.OLD_SHA,'candidate':core.FAILED_SHA,'checksum':h.SQL_HASH,'lease_sha256':hashlib.sha256(token.encode()).hexdigest(),'database_sha256':hashlib.sha256(json.dumps([identity,runtime_identity],sort_keys=True).encode()).hexdigest()}
    h.write_once(original/'intent.json',plan)
    monkeypatch.setattr(h,'STATE',tmp)
    original.rename(tmp/core.FAILED_SHA);original=tmp/core.FAILED_SHA
    monkeypatch.setattr(h,'secure',lambda *a,**k:None)
    monkeypatch.setattr(h,'lease_check',lambda t:('same',) if t==token else (_ for _ in ()).throw(h.ReleaseBlocked('lease')))
    monkeypatch.setattr(h,'git',lambda root,*args: (publisher if root==ROOT else core.FAILED_SHA).encode()+b'\n' if args==('rev-parse','HEAD') else b'')
    monkeypatch.setattr(h,'source_admission',lambda *a:True)
    monkeypatch.setattr(h,'expected_migrations',lambda *a:expected)
    monkeypatch.setattr(core,'assert_writers_stopped',lambda:None)
    args=(h,migration,runtime,ROOT,record,publisher,token,lambda:None)
    return core,args,original,pg

def test_recovery_default_acl_commits_once_preserves_original_and_readback(recovery,monkeypatch):
    c,args,original,pg=recovery;h,migration,runtime,role,_,expected,tmp=pg
    before=(original/'intent.json').read_bytes()
    with migration.begin() as conn:
        conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO {role}'))
        conn.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,USAGE ON SEQUENCES TO {role}'))
    assert c.inspect(*args)['database_state']=='PENDING'
    assert not args[4].exists()
    result=c.recover(*args)
    assert result['database_state']=='APPLIED'
    assert (original/'intent.json').read_bytes()==before
    assert not (original/'completed.json').exists()
    monkeypatch.setattr(h,'apply_exact',lambda *a:pytest.fail('DDL replay'))
    assert c.recover(*args)==result

def test_recovery_failed_transaction_intent_never_replays(recovery,monkeypatch):
    c,args,original,pg=recovery;h,migration,*_=pg
    monkeypatch.setattr(h,'apply_exact',lambda *a:(_ for _ in ()).throw(h.ReleaseBlocked('proof failure')))
    with pytest.raises(h.ReleaseBlocked):c.recover(*args)
    with pytest.raises(h.ReleaseBlocked,match='pending recovery intent'):c.recover(*args)

def test_recovery_requires_authority_and_matching_original(recovery):
    c,args,original,pg=recovery;h=pg[0]
    with pytest.raises(h.ReleaseBlocked):c.recover(*args[:-1],lambda:(_ for _ in ()).throw(h.ReleaseBlocked('authority')))
    assert not args[4].exists()
    d=json.loads((original/'intent.json').read_text());d['old']='f'*40;(original/'intent.json').write_text(json.dumps(d))
    with pytest.raises(h.ReleaseBlocked,match='original intent'):c.recover(*args)

def test_commit_without_receipt_recovers_only_by_readback(recovery,monkeypatch):
    c,args,original,pg=recovery;h=pg[0];write=h.write_once
    def fail_receipt(path,value):
        if path.name=='completed.json':raise OSError('synthetic fsync failure')
        return write(path,value)
    monkeypatch.setattr(h,'write_once',fail_receipt)
    with pytest.raises(OSError):c.recover(*args)
    assert c.inspect(*args)['database_state']=='APPLIED'
    assert not (args[4]/'completed.json').exists()
    monkeypatch.setattr(h,'write_once',write)
    monkeypatch.setattr(h,'apply_exact',lambda *a:pytest.fail('DDL replay'))
    assert c.recover(*args)['database_state']=='APPLIED'
    assert (args[4]/'completed.json').exists()

def test_lease_change_after_ddl_rolls_back_and_never_replays(recovery,monkeypatch):
    c,args,original,pg=recovery;h,migration,_,_,_,expected,_=pg;apply=h.apply_exact
    def changed(*a):
        apply(*a)
        monkeypatch.setattr(h,'lease_check',lambda *a:('changed',))
    monkeypatch.setattr(h,'apply_exact',changed)
    with pytest.raises(h.ReleaseBlocked,match='lease changed before commit'):c.recover(*args)
    with migration.connect() as conn:assert h.database_state(conn,expected)=='PENDING'
    monkeypatch.setattr(h,'lease_check',lambda *a:('same',))
    with pytest.raises(h.ReleaseBlocked,match='pending recovery intent'):c.recover(*args)

def test_active_writer_prevents_recovery_intent(recovery,monkeypatch):
    c,args,original,pg=recovery
    monkeypatch.setattr(c,'assert_writers_stopped',lambda:(_ for _ in ()).throw(RuntimeError('writers active')))
    with pytest.raises(RuntimeError,match='writers active'):c.recover(*args)
    assert not args[4].exists()

def test_unexpected_public_default_acl_is_not_silently_repaired(recovery):
    c,args,original,pg=recovery;h,migration,_,_,_,expected,_=pg
    with migration.begin() as conn:conn.execute(text('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO PUBLIC'))
    with pytest.raises(h.ReleaseBlocked,match='additional roles'):c.recover(*args)
    with migration.connect() as conn:assert h.database_state(conn,expected)=='PENDING'
    with pytest.raises(h.ReleaseBlocked,match='pending recovery intent'):c.recover(*args)

@pytest.mark.parametrize('deny_at',[3,4])
def test_authorization_revocation_at_write_boundaries_rolls_back(recovery,deny_at):
    c,args,original,pg=recovery;h,migration,_,_,_,expected,_=pg
    calls=0
    def authorize():
        nonlocal calls
        calls+=1
        if calls==deny_at:raise h.ReleaseBlocked('authority revoked')
    with pytest.raises(h.ReleaseBlocked,match='authority revoked'):c.recover(*args[:-1],authorize)
    with migration.connect() as conn:assert h.database_state(conn,expected)=='PENDING'
    assert (args[4]/'intent.json').exists()
    with pytest.raises(h.ReleaseBlocked,match='pending recovery intent'):c.recover(*args)
