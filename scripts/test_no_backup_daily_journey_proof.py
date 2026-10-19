"""Exact pre-stop journey closure: no migration execution or retry authority."""
import copy
import importlib.util
from pathlib import Path
import pytest


def load():
    path = Path(__file__).with_name('no_backup_daily_journey_proof.py')
    spec = importlib.util.spec_from_file_location('journey_closure', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_exact_log_and_mutation_rejection():
    m = load()
    raw = b'\n'.join(m.REQUIRED_LOG) + b'\n' + m.FAILURE_SUFFIX
    m.validate_failure_log(raw)
    for bad in [raw + b'after\n', raw.replace(b'operator review', b'other'), raw*2]:
        with pytest.raises(m.JourneyProofError): m.validate_failure_log(bad)
    for token in m.FORBIDDEN_LOG:
        with pytest.raises(m.JourneyProofError): m.validate_failure_log(token + b'\n' + raw)


def test_catalog_and_binding_reject_any_changed_evidence():
    m = load()
    value = {'state':'PENDING', 'target_tables':[], 'read_only':True, 'health_rows_read':False,
             'failed_sha':m.FAILED, 'production_sha':m.PRODUCTION,'database_sha256':'a'*64,'ledger_sha256':'b'*64}
    m.validate_catalog(value)
    for field, replacement in [('state','APPLIED'),('target_tables',['daily_journey_points']),
                               ('read_only',False),('health_rows_read',True),('failed_sha','f'*40)]:
        bad=copy.deepcopy(value); bad[field]=replacement
        with pytest.raises(m.JourneyProofError): m.validate_catalog(bad)
    with pytest.raises(m.JourneyProofError): m.validate_catalog({**value,'intent':False})


def test_failed_code_hashes_not_sha_only():
    m = load()
    m.validate_implementations(m.IMPLEMENTATIONS)
    for key in m.IMPLEMENTATIONS:
        bad=dict(m.IMPLEMENTATIONS);bad[key]='f'*64
        with pytest.raises(m.JourneyProofError): m.validate_implementations(bad)


def test_profile_integrated_and_historical_shape():
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import no_backup_preflight_proof as proof
    assert proof._journey.PROFILE == load().PROFILE


@pytest.mark.parametrize('moment', ['before', 'after'])
def test_intent_or_state_appearing_blocks_inspection(tmp_path, monkeypatch, moment):
    from types import SimpleNamespace
    m=load()
    calls=[]
    def missing(*paths):
        calls.append(paths)
        if len(calls) == (1 if moment == 'before' else 2):
            raise RuntimeError('state appeared')
    proof=SimpleNamespace(failed_sha=m.FAILED, production_sha=m.PRODUCTION, source=tmp_path,
        production=tmp_path, bootstrap=SimpleNamespace(STATE=tmp_path, secure=lambda p:None),
        _absent=missing, _file=lambda p: (b'', {'sha256':m.IMPLEMENTATIONS[str(p.relative_to(tmp_path))]}))
    expected={'state':'PENDING','target_tables':[],'read_only':True,'health_rows_read':False,
              'failed_sha':m.FAILED,'production_sha':m.PRODUCTION,'database_sha256':'a'*64,'ledger_sha256':'b'*64}
    import json
    ran=[]
    def child(*args, **kwargs):
        ran.append(True)
        return SimpleNamespace(returncode=0,stdout=json.dumps(expected).encode())
    monkeypatch.setattr(m.subprocess,'run',child)
    with pytest.raises(RuntimeError,match='state appeared'): m.inspect(proof,tmp_path)
    assert bool(ran) == (moment == 'after')


def test_journey_snapshot_rejects_rebound_revision_or_context():
    import sys
    sys.path.insert(0,str(Path(__file__).parent))
    import no_backup_preflight_proof as proof
    from test_no_backup_preflight_proof import complete_snapshot
    m=load();snapshot=complete_snapshot();marker=snapshot['no_backup_preflight']
    marker.update(profile=m.PROFILE,failed_sha=m.FAILED,production_sha=m.PRODUCTION,
                  failed_implementations=dict(m.IMPLEMENTATIONS),journey_context={
        'catalog':{'state':'PENDING','target_tables':[],'read_only':True,'health_rows_read':False,
                   'failed_sha':m.FAILED,'production_sha':m.PRODUCTION,'database_sha256':'a'*64,'ledger_sha256':'b'*64},
        'implementations':dict(m.IMPLEMENTATIONS),'migration_state_absent':True,'laya_candidate_absent':True})
    snapshot['stage']['runtime_state_release_transaction.py']['sha256']=m.IMPLEMENTATIONS['backend/scripts/runtime_state_release_transaction.py']
    proof.validate_snapshot(snapshot)
    marker['journey_context']['migration_state_absent']=False
    with pytest.raises(Exception):proof.validate_snapshot(snapshot)
    marker['journey_context']['migration_state_absent']=True
    marker['failed_sha']='e'*40
    with pytest.raises(Exception):proof.validate_snapshot(snapshot)


@pytest.mark.parametrize('case', ['clean','ledger','table','writable'])
def test_catalog_postgresql_fail_closed(case):
    """Explicit synthetic database only; never production config or credentials."""
    import os
    url=os.environ.get('JOURNEY_CLOSURE_TEST_DATABASE_URL')
    if not url: pytest.skip('dedicated synthetic PostgreSQL URL required')
    from sqlalchemy import create_engine,text
    from sqlalchemy.engine import make_url
    if make_url(url).database != 'journey_closure_test' or make_url(url).host not in {'127.0.0.1','localhost'}:
        pytest.fail('dedicated journey_closure_test database required')
    m=load()
    spec=importlib.util.spec_from_file_location('catalog_helper_test',Path(__file__).with_name('daily_journey_release.py'))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    engine=create_engine(url)
    with engine.begin() as conn:
        conn.execute(text('DROP TABLE IF EXISTS public.daily_journey_points'))
        conn.execute(text('DROP TABLE IF EXISTS public.schema_migrations'))
        conn.execute(text('CREATE TABLE public.schema_migrations(id text, checksum text)'))
        if case=='table':conn.execute(text('CREATE TABLE public.daily_journey_points(id int)'))
        if case=='ledger':conn.execute(text('INSERT INTO public.schema_migrations VALUES(:id,:checksum)'),{'id':helper.MIGRATION,'checksum':helper.SQL_HASH})
    # Metadata role checks use the dedicated PG fixture role; no elevated
    # production role is accepted by the real role_identity function.
    helper.role_identity=lambda conn:{'db':'journey_closure_test','role':'synthetic','host':'127.0.0.1','port':55439}
    try:
        with engine.connect() as conn:
            if case!='writable':conn.execute(text('SET TRANSACTION READ ONLY'))
            if case=='clean':assert m.read_catalog(helper,conn,{helper.MIGRATION:helper.SQL_HASH})['state']=='PENDING'
            else:
                with pytest.raises((m.JourneyProofError,helper.ReleaseBlocked)):
                    m.read_catalog(helper,conn,{helper.MIGRATION:helper.SQL_HASH})
    finally:
        engine.dispose()


@pytest.mark.parametrize('damage',['order','duplicate','wrong_terminal','extra_timing','missing_env'])
def test_preparation_chronology_rejects_drift(damage):
    m=load();parts=list(m.REQUIRED_LOG)
    if damage=='order':parts[1],parts[2]=parts[2],parts[1]
    elif damage=='duplicate':parts.append(parts[5])
    elif damage=='wrong_terminal':parts[5]=parts[5].replace(m.PRODUCTION.encode(),b'f'*40)
    elif damage=='extra_timing':parts.append(b'REVA_RELEASE_TIMING phase=other ')
    else:parts.pop(2)
    with pytest.raises(m.JourneyProofError):m.validate_failure_log(b'\n'.join(parts)+b'\n'+m.FAILURE_SUFFIX)


@pytest.mark.parametrize('key',['database_sha256','ledger_sha256'])
def test_closed_snapshot_change_is_not_silently_ignored(key, monkeypatch):
    m=load()
    first={'state':'PENDING','target_tables':[],'read_only':True,'health_rows_read':False,
           'failed_sha':m.FAILED,'production_sha':m.PRODUCTION,'database_sha256':'a'*64,'ledger_sha256':'b'*64}
    second=dict(first);second[key]='c'*64
    m.validate_catalog(first);m.validate_catalog(second)
    import no_backup_preflight_proof as proof
    instance=proof.NoBackupPreflightProof.__new__(proof.NoBackupPreflightProof)
    instance._original_lease={}
    instance._closed=False
    instance._workspace=lambda _: {'original':True}
    instance.snapshot=lambda: {'workspace':{'original':True},'catalog':second}
    monkeypatch.setattr(proof,'validate_snapshot',lambda _:None)
    with pytest.raises(proof.ProofError,match='evidence changed'):
        proof.verify_closed(instance,{'workspace':{'original':True},'catalog':first})


@pytest.mark.parametrize('kind',['leaf','parent'])
def test_source_chain_rejects_symlink_before_execution(tmp_path, monkeypatch, kind):
    from types import SimpleNamespace
    m=load();real=tmp_path/'real';real.mkdir();(real/'code.py').write_text('pass')
    link=tmp_path/'link'
    link.symlink_to(real if kind=='parent' else real/'code.py')
    target=link/'code.py' if kind=='parent' else link
    original=Path.lstat
    def metadata(path):
        info=original(path)
        # Preserve actual symlink/kind metadata; synthetic root ownership.
        return SimpleNamespace(st_uid=0,st_mode=info.st_mode & ~0o022,st_nlink=info.st_nlink)
    monkeypatch.setattr(Path,'lstat',metadata)
    with pytest.raises(m.JourneyProofError,match='unsafe'):m.secure_chain(target)


def test_existing_migration_parent_must_be_secure_before_absence_claim(monkeypatch):
    from types import SimpleNamespace
    m=load();called=[]
    monkeypatch.setattr(m.os.path,'lexists',lambda _:True)
    def reject(path):
        called.append(path)
        raise RuntimeError('unsafe migration parent')
    proof=SimpleNamespace(_directory=reject,_absent=lambda *a:pytest.fail('must not trust unsafe parent'))
    with pytest.raises(RuntimeError,match='unsafe migration parent'):m.absent(proof)
    assert called==[Path('/var/lib/reva-release/daily-journey-migrations')]
