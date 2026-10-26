"""A failed preclaim can close once, never become a publish/retry permission."""
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    spec = importlib.util.spec_from_file_location('unclaimed_retirement_test',
        Path(__file__).with_name('trusted_ota_unclaimed_retirement.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_requires_exact_failed_profile_and_no_mutation_on_changed_inspection(tmp_path):
    m = load()
    record = tmp_path / 'audit' / m.FAILED_SHA
    adapter = SimpleNamespace(record=record, check_record_parent=lambda: None,
        inspect=lambda: {'failed_sha': m.FAILED_SHA}, check_locks=lambda: None)
    inspected = m.close_transaction(adapter)
    assert inspected['state'] == 'INSPECTED_UNPUBLISHED_CLAIM'
    assert not record.exists()
    with pytest.raises(m.ClosureError):
        m.close_transaction(adapter, '0' * 64)
    assert not record.exists()


@pytest.mark.parametrize('failed_sha', ['da91b5de303313f1fb014bbe045e8f1597d15229',
                                      '151f26b0dd6c1c976e6d26cd6e21ab247a6fdb90',
                                      'f2022e10027bcf35c4225bf1cc898a9001161ecc',
                                      'c29d2a60f3fa8e49b87c183af3d7cfba72b9dfaf'])
def test_artifact_rejects_vendor_receipt_or_wrong_phase(monkeypatch, failed_sha):
    m = load()
    m.select_profile(failed_sha)
    entries = {
        'ota-diagnostic.json': {'sha': m.FAILED_SHA, 'state': 'BLOCKED',
                                'phase': 'claim-ota', 'reason': 'command_failed'},
        'ota-claim.json': {'sha': m.FAILED_SHA},
        'ota-preflight.json': {'sha': m.FAILED_SHA},
    }
    for fault in ('vendor', 'phase', 'duplicate'):
        altered = dict(entries)
        if fault == 'vendor':
            altered['ota-receipt.json'] = {'state': 'SUCCEEDED'}
        if fault == 'phase':
            altered['ota-diagnostic.json'] = {**entries['ota-diagnostic.json'], 'phase': 'vendor-publish'}
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            for name, value in altered.items():
                archive.writestr(name, json.dumps(value))
            if fault == 'duplicate':
                archive.writestr('ota-claim.json', '{}')
        raw = stream.getvalue()
        monkeypatch.setattr(m, 'ARTIFACT_ZIP_SHA256', hashlib.sha256(raw).hexdigest())
        with pytest.raises(m.ClosureError):
            m.validate_artifact(raw)


def test_terminal_is_never_ota_success():
    m = load()
    assert m.TERMINAL == 'CLOSED_UNPUBLISHED_CLAIM'
    assert m.FAILED_SHA == 'da91b5de303313f1fb014bbe045e8f1597d15229'


def metadata(m):
    run = {'id': m.RUN_ID, 'run_attempt': 1, 'workflow_id': m.WORKFLOW_ID,
        'path': '.github/workflows/trusted-ota.yml', 'head_sha': m.FAILED_SHA,
        'head_branch': 'main', 'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': 'failure',
        'repository': {'full_name': m.REPOSITORY}, 'head_repository': {'full_name': m.REPOSITORY}}
    jobs = {'total_count': 1, 'jobs': [{'id': m.JOB_ID, 'name': 'ota', 'status': 'completed',
        'conclusion': 'failure', 'steps': [{'name': name, 'status': 'completed', 'conclusion': result}
            for name, result in m.REQUIRED_STEPS.items()]}]}
    artifact = {'id': m.ARTIFACT_ID, 'name': f'trusted-ota-{m.FAILED_SHA}-{m.RUN_ID}-1',
        'digest': 'sha256:' + m.ARTIFACT_ZIP_SHA256, 'size_in_bytes': m.ARTIFACT_SIZE, 'expired': False,
        'workflow_run': {'id': m.RUN_ID, 'repository_id': 1127096388, 'head_repository_id': 1127096388,
                          'head_branch': 'main', 'head_sha': m.FAILED_SHA}}
    return run, jobs, artifact


@pytest.mark.parametrize('fault', ['attempt', 'running', 'wrong_sha', 'success', 'extra_job',
                                  'wrong_job', 'step', 'expired', 'digest', 'artifact_run'])
@pytest.mark.parametrize('failed_sha', ['da91b5de303313f1fb014bbe045e8f1597d15229',
                                      '151f26b0dd6c1c976e6d26cd6e21ab247a6fdb90',
                                      'f2022e10027bcf35c4225bf1cc898a9001161ecc',
                                      'c29d2a60f3fa8e49b87c183af3d7cfba72b9dfaf'])
def test_official_metadata_failures_are_closed(fault, failed_sha):
    m = load(); m.select_profile(failed_sha)
    run, jobs, artifact = metadata(m)
    if fault == 'attempt': run['run_attempt'] = 2
    elif fault == 'running': run['status'] = 'in_progress'
    elif fault == 'wrong_sha': run['head_sha'] = 'a' * 40
    elif fault == 'success': run['conclusion'] = 'success'
    elif fault == 'extra_job': jobs['total_count'] = 2
    elif fault == 'wrong_job': jobs['jobs'][0]['id'] += 1
    elif fault == 'step': jobs['jobs'][0]['steps'][2]['conclusion'] = 'success'
    elif fault == 'expired': artifact['expired'] = True
    elif fault == 'digest': artifact['digest'] = 'sha256:' + 'f' * 64
    elif fault == 'artifact_run': artifact['workflow_run']['id'] += 1
    with pytest.raises(m.ClosureError):
        m.validate_official_metadata(run, jobs, artifact)


@pytest.fixture(params=('da91b5de303313f1fb014bbe045e8f1597d15229',
                        '151f26b0dd6c1c976e6d26cd6e21ab247a6fdb90',
                        'f2022e10027bcf35c4225bf1cc898a9001161ecc',
                        'c29d2a60f3fa8e49b87c183af3d7cfba72b9dfaf'))
def transaction(tmp_path, monkeypatch, request):
    m = load()
    m.select_profile(request.param)
    monkeypatch.setattr(sys, 'dont_write_bytecode', True)
    root = tmp_path / 'state'
    root.mkdir(mode=0o700)
    for path in (root/'ota', root/m.FAILED_SHA, root/'run'):
        path.mkdir(mode=0o700)
    operation = root/'ota'/m.FAILED_SHA
    operation.mkdir(mode=0o700)
    business = root/'run'/'business-lease'
    business.mkdir(mode=0o700)
    closing = 'c' * 40
    def private(path, raw):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream: stream.write(raw)
    def secure(path, *, directory=False, private=False):
        assert not path.is_symlink()
        info = path.lstat()
        assert stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if private: assert stat.S_IMODE(info.st_mode) == 0o600
    server = SimpleNamespace(STATE=root, BUSINESS_LEASE=business, secure_path=secure,
        validate_metadata=lambda *a, **kw: None, _testflight_lease_parent=lambda: None,
        _sync_directory=lambda path: None, _sync_business_lease_parent=lambda: None,
        _write_private=private, _read_private=lambda path:path.read_bytes(), _json=m.parsed)
    lease = {'token':'e'*64, 'started_at':'1234567890'}
    contents = {'token':lease['token'], 'label':'testflight-check',
                'stage':str(root/m.FAILED_SHA), 'started_at':lease['started_at']}
    for name, value in contents.items(): private(business/name, (value+'\n').encode())
    lease['identity'] = [v for p in (business, business/'token')
                         for v in (p.stat().st_dev, p.stat().st_ino)]
    claim = {'sha':m.FAILED_SHA, 'synthetic_only':True}
    private(operation/'intent.json', json.dumps(claim).encode())
    private(operation/'lease.json', json.dumps(lease).encode())
    private(root/'launcher.lock', b'')
    private(root/m.FAILED_SHA/'build.lock', b'')
    monkeypatch.setitem(m.ENTRY_DIGESTS, 'ota-claim.json', m.digest(claim))
    source = root/'bootstrap'/closing/'source'
    oldsource = root/'bootstrap'/m.FAILED_SHA/'source'
    for directory in (source/'scripts', oldsource/'scripts', oldsource/'.github/workflows'):
        directory.mkdir(parents=True)
    oldfiles = {}
    for name in m.SOURCE_HASHES:
        raw = b'byte-bound synthetic source '+name.encode()
        (oldsource/name).write_bytes(raw)
        oldfiles[name] = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(m, 'SOURCE_HASHES', oldfiles)
    bootstrap_raw = f"from pathlib import Path\ndef canonical_source(sha):\n return Path({str(root)!r})/'bootstrap'/sha/'source'\n".encode()
    (source/'scripts/bootstrap_trusted_release.py').write_bytes(bootstrap_raw)
    operator_raw=b'byte-bound synthetic closure source'
    (source/'scripts/trusted_ota_unclaimed_retirement.py').write_bytes(operator_raw)
    proof = m.validate_official_metadata(*metadata(m))
    calls=[]
    bootstrap = SimpleNamespace(canonical_source=lambda sha:root/'bootstrap'/sha/'source',
        _assert_backend_terminated_or_unstarted=lambda sha:calls.append('backend'),
        _recovery_process_proof=lambda:calls.append('process'),
        _recovery_production_proof=lambda *a:calls.append('health'))
    server._assert_testflight_lease=lambda value, stage:m.lease_snapshot(server,business,value)
    monkeypatch.setattr(m, 'official_evidence', lambda token:(proof,{'ota-claim.json':claim}))
    monkeypatch.setattr(m, 'production_health', lambda server: {
        'sha':m.FAILED_SHA, 'terminal':'SUCCEEDED',
        'units':['health-backend','celery-worker','celery-beat','reva-laya'],
        'loopback':'healthy','public':'healthy'})
    monkeypatch.setattr(m.subprocess, 'run', lambda args, **kw:SimpleNamespace(
        stdout=operator_raw if args[-1].endswith('trusted_ota_unclaimed_retirement.py') else bootstrap_raw))
    adapter=m.Adapter(bootstrap,server,source,closing,'synthetic-read-only-token',lambda:calls.append('locks'))
    return m,adapter,operation,lease,calls


def test_real_transaction_keeps_original_files_and_consumes_lease_once(transaction):
    m,a,op,_lease,calls=transaction
    originals={p.name:(p.stat().st_ino,p.read_bytes()) for p in op.iterdir()}
    original_inode=a.server.BUSINESS_LEASE.stat().st_ino
    inspect=m.close_transaction(a)
    assert a.server.BUSINESS_LEASE.exists() and not a.record.exists()
    result=m.close_transaction(a,inspect['evidence_sha256'])
    assert result['state']==m.TERMINAL
    assert not a.server.BUSINESS_LEASE.exists()
    assert m.retired_path(a.server).stat().st_ino==original_inode
    assert {p.name:(p.stat().st_ino,p.read_bytes()) for p in op.iterdir()}==originals
    assert {p.name for p in a.record.iterdir()}=={'intent.json','completed.json'}
    assert m.validate_closed_history(a.server,op)['state']==m.TERMINAL
    with pytest.raises(m.ClosureError,match='retry forbidden'):
        m.close_transaction(a,inspect['evidence_sha256'])
    # Volatile /run retirement can disappear across reboot, not its durable audit.
    shutil.rmtree(m.retired_path(a.server))
    assert m.validate_closed_history(a.server,op)['state']==m.TERMINAL
    assert 'health' in calls and 'process' in calls


@pytest.mark.parametrize('name',['claimed.json','verified.json','completed.json','ota-receipt.json'])
def test_any_publication_or_unknown_partial_evidence_blocks_before_writes(transaction,name):
    m,a,op,_lease,_calls=transaction
    (op/name).write_text('{}')
    with pytest.raises(m.ClosureError):m.close_transaction(a)
    assert not a.record.exists() and a.server.BUSINESS_LEASE.exists()


@pytest.mark.parametrize('fault',['replace_lease','replace_token','claim','locks','official','source','process'])
def test_inspection_drift_and_unavailable_proofs_never_retire(transaction,monkeypatch,fault):
    m,a,op,_lease,_calls=transaction
    old=m.close_transaction(a)
    if fault=='replace_lease':
        original=a.server.BUSINESS_LEASE
        original.rename(original.with_name('other'))
        shutil.copytree(original.with_name('other'),original)
    elif fault=='replace_token':
        token=a.server.BUSINESS_LEASE/'token';raw=token.read_bytes();token.unlink();token.write_bytes(raw);token.chmod(0o600)
    elif fault=='claim':(op/'intent.json').write_text('{}')
    elif fault=='locks':(a.server.STATE/'launcher.lock').write_text('changed')
    elif fault=='official':monkeypatch.setattr(m,'official_evidence',lambda token:(_ for _ in ()).throw(m.ClosureError('unavailable')))
    elif fault=='source':(a.b.canonical_source(m.FAILED_SHA)/'scripts/trusted_ota_publish.py').write_text('different')
    elif fault=='process':a.b._recovery_process_proof=lambda:(_ for _ in ()).throw(m.ClosureError('active'))
    with pytest.raises((m.ClosureError,AssertionError)):
        m.close_transaction(a,old['evidence_sha256'])
    assert not a.record.exists() and a.server.BUSINESS_LEASE.exists()


def test_interrupted_close_intent_is_consumed_and_history_blocked(transaction,monkeypatch):
    m,a,op,_lease,_calls=transaction
    inspect=m.close_transaction(a)
    monkeypatch.setattr(a,'retire_lease',lambda evidence:(_ for _ in ()).throw(m.ClosureError('injected fault')))
    with pytest.raises(m.ClosureError):m.close_transaction(a,inspect['evidence_sha256'])
    assert a.server.BUSINESS_LEASE.exists()
    assert {p.name for p in a.record.iterdir()}=={'intent.json'}
    with pytest.raises(m.ClosureError):m.validate_closed_history(a.server,op)
    with pytest.raises(m.ClosureError):m.close_transaction(a,inspect['evidence_sha256'])


def test_rename_then_durability_failure_still_blocks_and_cannot_retry(transaction,monkeypatch):
    m,a,op,_lease,_calls=transaction
    inspect=m.close_transaction(a)
    a.server._sync_business_lease_parent=lambda:(_ for _ in ()).throw(m.ClosureError('fsync failure'))
    with pytest.raises(m.ClosureError):m.close_transaction(a,inspect['evidence_sha256'])
    assert not a.server.BUSINESS_LEASE.exists() and m.retired_path(a.server).exists()
    with pytest.raises(m.ClosureError):m.validate_closed_history(a.server,op)
    with pytest.raises(m.ClosureError):m.close_transaction(a,inspect['evidence_sha256'])


def test_nonroot_checkout_context_never_runs_network_or_mutations(monkeypatch):
    m=load()
    monkeypatch.setattr(m.os,'geteuid',lambda:501)
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:pytest.fail('untrusted process'))
    with pytest.raises(m.ClosureError):m.context('c'*40, 'synthetic-token')


@pytest.mark.parametrize('fault', ['none', 'completion', 'audit', 'original', 'revive', 'lock'])
def test_producer_to_actual_server_history_consumer(transaction, monkeypatch, fault):
    m,a,op,_lease,_calls=transaction
    inspected=m.close_transaction(a)
    m.close_transaction(a,inspected['evidence_sha256'])
    if fault=='completion':(a.record/'completed.json').unlink()
    elif fault=='audit':
        intent=json.loads((a.record/'intent.json').read_text());intent['closing_sha']='f'*40
        (a.record/'intent.json').write_text(json.dumps(intent))
    elif fault=='original':(op/'lease.json').write_text('{}')
    elif fault=='revive':m.retired_path(a.server).rename(a.server.BUSINESS_LEASE)
    elif fault=='lock':(a.server.STATE/'launcher.lock').write_text('changed')
    spec=importlib.util.spec_from_file_location('real_history_server',Path(__file__).with_name('trusted_release_server.py'))
    server=importlib.util.module_from_spec(spec);spec.loader.exec_module(server)
    monkeypatch.setattr(server,'STATE',a.server.STATE)
    monkeypatch.setattr(server,'BUSINESS_LEASE',a.server.BUSINESS_LEASE)
    # Only canonical-loader and OS ownership/sticky-parent dependencies are
    # replaced. The transaction, closure validator, and history consumer run.
    monkeypatch.setattr(server,'secure_path',a.server.secure_path)
    monkeypatch.setattr(server,'validate_metadata',a.server.validate_metadata)
    monkeypatch.setattr(server,'_testflight_lease_parent',lambda:None)
    monkeypatch.setattr(server,'_load_ota_unclaimed_retirement',lambda:m)
    if fault=='none':server.assert_ota_history()
    else:
        with pytest.raises((m.ClosureError, server.LaunchError)):server.assert_ota_history()


@pytest.mark.parametrize('fault', ['none','backend','unit','loopback','public'])
def test_actual_production_health_boundary(monkeypatch,fault):
    m=load()
    server=SimpleNamespace(STATE=Path('/var/lib/reva-release'),read_status=lambda *a:{
        'sha':m.FAILED_SHA,'state':'SUCCEEDED' if fault!='backend' else 'NEEDS_OPERATOR'})
    outputs=[]
    def run(args,**kwargs):
        outputs.append(args)
        return SimpleNamespace(stdout=(b'ActiveState=active\nSubState=running\nMainPID=321\n'
            if fault!='unit' else b'ActiveState=inactive\nSubState=dead\nMainPID=0\n'))
    monkeypatch.setattr(m.subprocess,'run',run)
    class Response:
        status=200
        def __init__(self,url):self.url=url
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,bound):
            unhealthy=(fault=='loopback' and '127.0.0.1' in self.url) or (fault=='public' and 'executor.life' in self.url)
            return json.dumps({'status':'unhealthy' if unhealthy else 'healthy',
                'services':{'api':'running','database':'connected','redis':'connected','celery':'connected'}}).encode()
    monkeypatch.setattr(m,'opener',lambda:SimpleNamespace(open=lambda request,**kw:Response(request.full_url)))
    if fault=='none':
        assert m.production_health(server)['public']=='healthy'
        assert len(outputs)==4
    else:
        with pytest.raises(m.ClosureError):m.production_health(server)


def test_network_failure_cannot_create_close_intent(transaction,monkeypatch):
    m,a,_op,_lease,_calls=transaction
    monkeypatch.setattr(m,'official_evidence',lambda token:(_ for _ in ()).throw(m.ClosureError('quota unavailable')))
    with pytest.raises(m.ClosureError):m.close_transaction(a)
    assert a.server.BUSINESS_LEASE.exists() and not a.record.exists()


@pytest.mark.parametrize('fault',['official_attempt','artifact_hash','lock_manifest','lease_snapshot',
                                  'completion_hash','operator_source'])
def test_history_components_fail_even_with_recomputed_audit_digests(transaction,fault):
    m,a,op,_lease,_calls=transaction
    inspected=m.close_transaction(a)
    m.close_transaction(a,inspected['evidence_sha256'])
    intent=json.loads((a.record/'intent.json').read_text())
    if fault=='official_attempt':intent['official']['run']['run_attempt']=2
    elif fault=='artifact_hash':intent['official']['artifact']['digest']='sha256:'+'f'*64
    elif fault=='lock_manifest':intent['locks']['launcher']['inode']+=1
    elif fault=='lease_snapshot':intent['lease']['files']['label']['sha256']='f'*64
    elif fault=='operator_source':
        (a.source/'scripts/trusted_ota_unclaimed_retirement.py').write_bytes(b'changed operator')
    intent['evidence_sha256']=m.digest({k:v for k,v in intent.items() if k not in {'state','evidence_sha256'}})
    completed={'state':m.TERMINAL,'failed_sha':m.FAILED_SHA,'intent_sha256':m.digest(intent)}
    if fault=='completion_hash':completed['intent_sha256']='f'*64
    (a.record/'intent.json').write_text(json.dumps(intent))
    (a.record/'completed.json').write_text(json.dumps(completed))
    with pytest.raises(m.ClosureError):m.validate_closed_history(a.server,op)


def test_history_allows_different_current_lease_but_not_original_inode(transaction):
    m,a,op,_lease,_calls=transaction
    inspected=m.close_transaction(a)
    m.close_transaction(a,inspected['evidence_sha256'])
    a.server.BUSINESS_LEASE.mkdir(mode=0o700)
    assert m.validate_closed_history(a.server,op)['state']==m.TERMINAL
    a.server.BUSINESS_LEASE.rmdir()
    m.retired_path(a.server).rename(a.server.BUSINESS_LEASE)
    with pytest.raises(m.ClosureError):m.validate_closed_history(a.server,op)


NEW_FAILED_SHA = '151f26b0dd6c1c976e6d26cd6e21ab247a6fdb90'


def test_fixed_profile_selection_preserves_legacy_and_is_one_shot():
    old = load()
    old.select_profile(old.FAILED_SHA)
    assert old.RUN_ID == 38509318595 and old.ARTIFACT_SIZE == 2533
    new = load()
    new.select_profile(NEW_FAILED_SHA)
    assert new.FAILED_SHA == NEW_FAILED_SHA and new.RUN_ID == 39539354647
    assert new.JOB_ID == 119023297148 and new.ARTIFACT_ID == 12318856926
    assert new.ARTIFACT_SIZE == 2531
    with pytest.raises(new.ClosureError): new.select_profile(old.FAILED_SHA)
    new.select_profile(NEW_FAILED_SHA)  # Same fixed profile is idempotent.
    unknown = load()
    with pytest.raises(unknown.ClosureError): unknown.select_profile('f' * 40)


def test_mixed_profile_metadata_cannot_authorize_new_closure():
    old = load(); old_values = metadata(old)
    new = load(); new.select_profile(NEW_FAILED_SHA)
    with pytest.raises(new.ClosureError): new.validate_official_metadata(*old_values)
    run, jobs, artifact = metadata(new); artifact['size_in_bytes'] = new.ARTIFACT_SIZE
    assert new.validate_official_metadata(run, jobs, artifact)['run']['head_sha'] == NEW_FAILED_SHA
    for field in ('id', 'digest', 'size_in_bytes'):
        changed = dict(artifact); changed[field] = old_values[2][field]
        with pytest.raises(new.ClosureError): new.validate_official_metadata(run, jobs, changed)


def test_history_selects_only_fixed_directory_before_reading_evidence(tmp_path):
    m = load()
    with pytest.raises(m.ClosureError):
        m.validate_closed_history(SimpleNamespace(), tmp_path / ('f' * 40))
    assert m._SELECTED_PROFILE is None


def test_fresh_history_modules_do_not_share_profile_state():
    old, new = load(), load()
    old.select_profile(old.LEGACY_FAILED_SHA)
    new.select_profile(new.CURRENT_FAILED_SHA)
    old.select_profile(old.LEGACY_FAILED_SHA)
    assert old.RUN_ID == 38509318595 and new.RUN_ID == 39539354647
    assert old.SOURCE_HASHES != new.SOURCE_HASHES
    assert old.ENTRY_DIGESTS != new.ENTRY_DIGESTS


F202_FAILED_SHA = 'f2022e10027bcf35c4225bf1cc898a9001161ecc'


def test_f202_fixed_official_profile():
    m = load(); m.select_profile(F202_FAILED_SHA)
    assert (m.RUN_ID, m.RUN_ATTEMPT, m.WORKFLOW_ID, m.JOB_ID, m.ARTIFACT_ID, m.ARTIFACT_SIZE) == (
        39546553940, 1, 370218159, 119045918716, 12321694024, 2533)
    assert m.ARTIFACT_ZIP_SHA256 == '49c2f461f7c089ae770c86c50a77359887fd7090a1bb1fdd412915b2b411a92e'
    assert m.ENTRY_DIGESTS == {
        'ota-diagnostic.json': 'e52078e7c9f6cc04e99d752add662df2ca4c1822b1972432f46767b11f0aaae4',
        'ota-claim.json': '95e20f0dd109e1298dbecd9b167b118c7fe4420f70b81e9542ca3714e038a63e',
        'ota-preflight.json': '4a46b4731606e591fe3fb53706b7dd1d954ab3a48fc1e4fedc1c7a1bebffc6e9'}
    assert m.validate_official_metadata(*metadata(m))['run']['head_sha'] == F202_FAILED_SHA


@pytest.mark.parametrize('foreign_sha', ['da91b5de303313f1fb014bbe045e8f1597d15229', NEW_FAILED_SHA])
def test_f202_rejects_foreign_profile_and_preserves_loaded_history(foreign_sha):
    import copy
    old = load(); old.select_profile(foreign_sha)
    old_values = copy.deepcopy(metadata(old)); old_entries = copy.deepcopy(old.ENTRY_DIGESTS)
    new = load(); new.select_profile(F202_FAILED_SHA)
    for index in range(3):
        mixed = list(metadata(new)); mixed[index] = old_values[index]
        with pytest.raises(new.ClosureError): new.validate_official_metadata(*mixed)
    before = copy.deepcopy(metadata(new)); before_entries = copy.deepcopy(new.ENTRY_DIGESTS)
    with pytest.raises(new.ClosureError): new.select_profile(foreign_sha)
    new.select_profile(F202_FAILED_SHA)
    assert metadata(new) == before and new.ENTRY_DIGESTS == before_entries
    assert metadata(old) == old_values and old.ENTRY_DIGESTS == old_entries
    with pytest.raises(old.ClosureError): old.select_profile(F202_FAILED_SHA)
    assert metadata(old) == old_values and old.ENTRY_DIGESTS == old_entries


C29D_FAILED_SHA = 'c29d2a60f3fa8e49b87c183af3d7cfba72b9dfaf'


def test_c29d_fixed_official_profile():
    m = load(); m.select_profile(C29D_FAILED_SHA)
    assert (m.RUN_ID,m.RUN_ATTEMPT,m.WORKFLOW_ID,m.JOB_ID,m.ARTIFACT_ID,m.ARTIFACT_SIZE) == (
        40281092624,1,370218159,121434341485,12633145149,2532)
    assert m.ARTIFACT_ZIP_SHA256 == 'cdd4b16985fd2a7672b8ad270f2e22a21018e390f698d70e90d55a15cb5cdfe4'
    assert m.ENTRY_DIGESTS == {
        'ota-diagnostic.json': '41397c0f02c972d269e894961b5d3a53add5298f23acee85e1099c9c042bd2b4',
        'ota-claim.json': '10cbfd6a886285891762d5dbbd6edf8f3ffda58c08ea040f1fef28f5bda36776',
        'ota-preflight.json': '842135a82961b73bcfda724ebab1b1432abe3642efb5e8fca612798e89fcd468'}
    assert m.validate_official_metadata(*metadata(m))['run']['head_sha'] == C29D_FAILED_SHA


@pytest.mark.parametrize('raw', [b'', b'{}', b'{"github_token":""}', b'{"github_token":1}',
    b'{"github_token":"bad token"}', b'{"github_token":"bad\\nvalue"}',
    b'{"github_token":"bad\\u0000value"}', b'{"github_token":"bad/value"}',
    b'{"github_token":"one","github_token":"two"}',
    b'{"github_token":"good","extra":"field"}',
    json.dumps({'github_token':'a'*4097}).encode(), b' '*8193])
def test_private_credentials_invalid_never_reach_context_or_fallback(monkeypatch,raw):
    m=load()
    monkeypatch.setattr(m.sys,'argv',['closure','--sha','c'*40])
    monkeypatch.setattr(m.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(raw)))
    monkeypatch.setenv('GH_TOKEN','must-not-fallback')
    monkeypatch.setattr(m,'context',lambda *a:pytest.fail('invalid stdin reached trusted context'))
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:pytest.fail('invalid stdin reached process'))
    with pytest.raises(m.ClosureError):m.main()


def test_same_private_stdin_token_reaches_context_before_any_gate(monkeypatch):
    m=load();token='ghs_synthetic-token.not-secret'
    monkeypatch.setattr(m.sys,'argv',['closure','--sha','c'*40])
    monkeypatch.setattr(m.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(json.dumps({'github_token':token}).encode())))
    class Inspected(Exception):pass
    def context(sha, github_token):
        assert sha=='c'*40 and github_token==token
        raise Inspected
    monkeypatch.setattr(m,'context',context)
    with pytest.raises(Inspected):m.main()


def test_closing_ci_token_is_stdin_only_and_explicit_full_gate(monkeypatch):
    m=load();token='ghs_synthetic-token.not-secret';calls=[]
    monkeypatch.setenv('GH_TOKEN','must-not-fallback')
    def run(args,**kw):
        calls.append((args,kw))
        assert '--token-stdin' in args
        assert args[args.index('--target')+1]=='full'
        assert token not in ' '.join(args) and token not in str(kw['env'])
        assert kw['input']==token.encode() and 'stdin' not in kw
        assert kw['stdout']==m.subprocess.DEVNULL and kw['stderr']==m.subprocess.DEVNULL
        assert kw['check'] is True
    monkeypatch.setattr(m.subprocess,'run',run)
    m.verify_closing_ci(Path('/canonical'), 'c'*40, token)
    assert len(calls)==1


def test_closing_ci_failure_does_not_retry_another_credential(monkeypatch):
    m=load();calls=[]
    def run(*args,**kw):
        calls.append(args)
        raise m.subprocess.CalledProcessError(1,args[0])
    monkeypatch.setattr(m.subprocess,'run',run)
    with pytest.raises(m.subprocess.CalledProcessError):
        m.verify_closing_ci(Path('/canonical'),'c'*40,'ghs_fixture')
    assert len(calls)==1


@pytest.mark.parametrize('foreign_sha', [
    'da91b5de303313f1fb014bbe045e8f1597d15229', NEW_FAILED_SHA, F202_FAILED_SHA])
def test_c29d_does_not_change_or_accept_historical_profiles(foreign_sha):
    import copy
    old=load();old.select_profile(foreign_sha)
    old_metadata=copy.deepcopy(metadata(old));old_entries=copy.deepcopy(old.ENTRY_DIGESTS)
    new=load();new.select_profile(C29D_FAILED_SHA)
    for index in range(3):
        mixed=list(metadata(new));mixed[index]=old_metadata[index]
        with pytest.raises(new.ClosureError):new.validate_official_metadata(*mixed)
    with pytest.raises(new.ClosureError):new.select_profile(foreign_sha)
    with pytest.raises(old.ClosureError):old.select_profile(C29D_FAILED_SHA)
    assert metadata(old)==old_metadata and old.ENTRY_DIGESTS==old_entries
    assert new.FAILED_SHA==C29D_FAILED_SHA


@pytest.mark.parametrize('token', ['', None, 'bad token', 'bad\x00value', 'nonascii-你好', 'a'*4097])
def test_direct_ci_credential_rejection_never_spawns_or_falls_back(monkeypatch,token):
    m=load()
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:pytest.fail('invalid credential reached gate process'))
    with pytest.raises(m.ClosureError):m.verify_closing_ci(Path('/canonical'),'c'*40,token)


def test_c29d_original_source_hashes_are_fixed():
    m=load();m.select_profile(C29D_FAILED_SHA)
    assert m.SOURCE_HASHES == {
        '.github/workflows/trusted-ota.yml': 'd35f63792dfc753e43775454785de75279dba55ad6ba375e3686c6469172e74c',
        'scripts/trusted_ota_publish.py': 'd8a509e114fae2509fd93d157d713ed61b61c97b97aa358ea61f3a3ce566f63d',
        'scripts/trusted_ota_server.py': 'd61b0b19d9fb8804f8238ba6a641f391742559d56b8ff310327b873edc6166d5',
        'scripts/trusted_ota.py': '2e0c9c20f779e9fb09afb8a2c8625710d1d05265a4886b8a2a43602ac1dd2d56'}
