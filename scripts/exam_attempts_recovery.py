"""Database-only recovery for the single failed exam release.

No CLI, credentials, service starts, lease retirement or automatic DDL retry.
The canonical outer operator supplies verified engines and rechecks its signed
source/CI/incident authority through assert_authorized at every write boundary.
"""
import hashlib
import json
import os
import re
import subprocess

FAILED_SHA = 'a8cd1e7635eb697c0f0bc528382c98b3602893c3'
OLD_SHA = '83876750fcbb404255b7439482688fee82a490d4'


def assert_writers_stopped():
    for unit in ('health-backend.socket','health-backend','celery-worker','celery-beat'):
        state=subprocess.run(['/usr/bin/systemctl','show',unit,'-p','ActiveState','--value'],env={'PATH':'/usr/bin:/bin','HOME':'/nonexistent'},capture_output=True,check=True,text=True,timeout=15).stdout.strip()
        if state!='inactive':
            raise RuntimeError('all writers must be stopped')


def _context(h,migration,runtime,source,record,publisher,token,authorize):
    authorize()
    if re.fullmatch('[a-f0-9]{40}',publisher) is None or publisher in (FAILED_SHA,OLD_SHA):
        raise h.ReleaseBlocked('reviewed recovery publisher required')
    if h.git(source,'rev-parse','HEAD').decode().strip()!=publisher or h.git(source,'status','--porcelain','--untracked-files=all'):
        raise h.ReleaseBlocked('recovery source not exact and clean')
    if not h.source_admission(source,OLD_SHA,publisher):
        raise h.ReleaseBlocked('recovery schema source differs')
    if h.git(h.LIVE,'rev-parse','HEAD').decode().strip()!=FAILED_SHA or h.git(h.LIVE,'status','--porcelain','--untracked-files=no'):
        raise h.ReleaseBlocked('failed candidate no longer live')
    lease=h.lease_check(token)
    original=h.STATE/FAILED_SHA
    h.secure(original,directory=True,private=True)
    if {p.name for p in original.iterdir()}!={'intent.json'}:
        raise h.ReleaseBlocked('original migration artifacts differ')
    raw=h.protected_read(original/'intent.json',private=True)
    if migration.dialect.name!='postgresql' or runtime.dialect.name!='postgresql':
        raise h.ReleaseBlocked('PostgreSQL required')
    with runtime.connect() as conn:
        runtime_identity=h.role_identity(conn)
    with migration.connect() as conn:
        h.sql(conn,'SET TRANSACTION READ ONLY')
        identity=h.role_identity(conn)
        if identity['role']==runtime_identity['role'] or any(identity[k]!=runtime_identity[k] for k in ('db','host','port')):
            raise h.ReleaseBlocked('database role identity differs')
        if h.sql(conn,"SELECT pg_has_role(:runtime,current_user,'MEMBER') OR has_schema_privilege(:runtime,'public','CREATE')",runtime=runtime_identity['role']).scalar_one():
            raise h.ReleaseBlocked('runtime inherits elevated authority')
    plan={'old':OLD_SHA,'candidate':FAILED_SHA,'checksum':h.SQL_HASH,'lease_sha256':hashlib.sha256(token.encode()).hexdigest(),'database_sha256':hashlib.sha256(json.dumps([identity,runtime_identity],sort_keys=True).encode()).hexdigest()}
    if json.loads(raw)!=plan:
        raise h.ReleaseBlocked('original intent binding differs')
    binding={'publisher_sha':publisher,'original_intent_sha256':hashlib.sha256(raw).hexdigest(),'binding':plan}
    if record==original or original in record.parents:
        raise h.ReleaseBlocked('recovery must preserve original evidence')
    h.secure(record.parent,directory=True,private=True)
    if os.path.lexists(record):
        h.secure(record,directory=True,private=True)
        if {p.name for p in record.iterdir()}-{'intent.json','completed.json'}:
            raise h.ReleaseBlocked('unknown recovery artifact')
        for p in record.iterdir():h.protected_read(p,private=True)
    expected=h.expected_migrations(source)
    return plan,binding,lease,runtime_identity['role'],expected


def inspect(h,migration,runtime,source,record,publisher,token,assert_authorized):
    plan,binding,lease,role,expected=_context(h,migration,runtime,source,record,publisher,token,assert_authorized)
    intent=record/'intent.json';completed=record/'completed.json'
    has_intent=os.path.lexists(intent)
    if has_intent and json.loads(h.protected_read(intent,private=True))!=binding:
        raise h.ReleaseBlocked('recovery intent binding differs')
    with migration.connect() as conn:
        h.sql(conn,'SET TRANSACTION READ ONLY')
        state=h.database_state(conn,expected)
        proof=h.committed_proof(conn,plan,h.STATE/FAILED_SHA,role) if state=='APPLIED' else None
    if state=='APPLIED' and not has_intent:
        raise h.ReleaseBlocked('committed recovery lacks intent')
    result={**binding,'database_state':state,'proof':proof}
    if os.path.lexists(completed):
        if not has_intent or state!='APPLIED' or json.loads(h.protected_read(completed,private=True))!=result:
            raise h.ReleaseBlocked('recovery receipt differs')
    if h.lease_check(token)!=lease:raise h.ReleaseBlocked('lease changed')
    return result


def recover(h,migration,runtime,source,record,publisher,token,assert_authorized):
    result=inspect(h,migration,runtime,source,record,publisher,token,assert_authorized)
    if result['database_state']=='APPLIED':
        # A prior commit can only be read back, never replayed or relabelled.
        if not os.path.lexists(record/'completed.json'):
            assert_authorized();h.write_once(record/'completed.json',result)
        return result
    if os.path.lexists(record/'intent.json'):
        raise h.ReleaseBlocked('pending recovery intent; operator inspection only')
    plan,binding,lease,role,expected=_context(h,migration,runtime,source,record,publisher,token,assert_authorized)
    assert_writers_stopped()
    record.mkdir(mode=0o700);h.sync_directory(record.parent)
    h.write_once(record/'intent.json',binding)
    with migration.begin() as conn:
        h.sql(conn,"SET LOCAL lock_timeout='5s'")
        h.sql(conn,"SET LOCAL statement_timeout='30s'")
        if not h.sql(conn,'SELECT pg_try_advisory_xact_lock(730228120000)').scalar_one():
            raise h.ReleaseBlocked('migration transaction already running')
        assert_authorized();assert_writers_stopped()
        if h.lease_check(token)!=lease or h.database_state(conn,expected)!='PENDING':
            raise h.ReleaseBlocked('recovery state changed before DDL')
        h.apply_exact(conn,source,plan,role)
        assert_authorized();assert_writers_stopped()
        if h.lease_check(token)!=lease:raise h.ReleaseBlocked('lease changed before commit')
    result=inspect(h,migration,runtime,source,record,publisher,token,assert_authorized)
    if result['database_state']!='APPLIED':raise h.ReleaseBlocked('recovery commit unproved')
    h.write_once(record/'completed.json',result)
    return result
