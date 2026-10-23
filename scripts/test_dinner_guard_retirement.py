"""Offline lifecycle checks; never invoke SSH, systemctl, or GitHub."""
import importlib.util
import hashlib
import json
from pathlib import Path
import pytest


def load():
    path = Path(__file__).with_name('dinner_guard_retirement.py')
    spec = importlib.util.spec_from_file_location('dinner_closure_test', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Adapter:
    def __init__(self, root):
        self.record = root / 'closure'
        self.evidence = {'old_sha': 'a' * 40}
        self.events = []
    def inspect(self):
        self.events.append('inspect')
        return dict(self.evidence)
    def retire(self, evidence):
        assert (self.record / 'intent.json').is_file()
        self.events.append('retire')
    def verify_closed(self, evidence):
        self.events.append('verify')
        return {'installation': {'unchanged': True}}


def test_inspection_no_mutation(tmp_path):
    m, a = load(), Adapter(tmp_path)
    assert m.close_transaction(a)['state'] == 'INSPECTED_DINNER_GUARD_RELEASE'
    assert not a.record.exists()
    assert a.events == ['inspect']


def test_receipt_only_after_postconditions_and_no_backup(tmp_path):
    m, a = load(), Adapter(tmp_path)
    digest = m.close_transaction(a)['evidence_sha256']
    result = m.close_transaction(a, digest)
    assert result['state'] == m.TERMINAL
    assert set(p.name for p in a.record.iterdir()) == {'intent.json', 'completed.json'}
    intent = json.loads((a.record / 'intent.json').read_text())
    assert intent['receipt_sha256'] == hashlib.sha256(result['receipt'].encode()).hexdigest()
    assert result['receipt'] not in (a.record / 'intent.json').read_text()
    assert a.events[-2:] == ['retire', 'verify']
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, digest)


def test_changed_evidence_and_interruption_fail_closed(tmp_path):
    m, a = load(), Adapter(tmp_path)
    digest = m.close_transaction(a)['evidence_sha256']
    a.evidence['drift'] = True
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, digest)
    assert not a.record.exists()
    a.evidence.pop('drift')
    def fail(evidence):
        raise RuntimeError('postcondition failed')
    a.verify_closed = fail
    with pytest.raises(RuntimeError):
        m.close_transaction(a, digest)
    assert (a.record / 'intent.json').is_file()
    assert not (a.record / 'completed.json').exists()
    with pytest.raises(m.ClosureError):
        m.close_transaction(a, digest)


def test_rotation_input_is_exclusive_and_bounded():
    m = load()
    v = {'receipt': 'a' * 64, 'github_token': 'ghs_test'}
    assert m.rotation_input(json.dumps(v).encode()) == v
    for value in ({**v, 'extra': 1}, {'receipt': 'x', 'github_token': 'a'}, {'receipt': 'a'*64, 'github_token': 'bad\n'}):
        with pytest.raises(m.ClosureError):
            m.rotation_input(json.dumps(value).encode())
    with pytest.raises(m.ClosureError):
        m.rotation_input(b'{"receipt":"'+b'a'*64+b'","github_token":"a","github_token":"b"}')


def test_historical_consumption_preserves_receipt_and_no_live_dependency(tmp_path, monkeypatch):
    from types import SimpleNamespace
    m = load()
    root = tmp_path / m.ROOT_NAME / m.FAILED
    root.mkdir(parents=True, mode=0o700)
    closing, recovery, receipt = '1'*40, '2'*40, '3'*64
    snapshot, audit, services, work = {k: {} for k in m.SNAPSHOT_FIELDS}, {'complete': True}, {'stable': True}, {'original': True}
    intent = {'old_sha': m.FAILED, 'closing_sha': closing, 'production_sha': m.PRODUCTION,
              'restoration': audit, 'snapshot': snapshot, 'workspace': work,
              'lease_directory': {}, 'config': {'loopback.key': {}, 'public': {}},
              'library': {}, 'authorized': {}, 'services': services, 'launcher': {}, 'build': None}
    intent['evidence_sha256'] = m.digest(intent)
    intent['receipt_sha256'] = hashlib.sha256(receipt.encode()).hexdigest()
    done = {'old_sha': m.FAILED, 'state': m.TERMINAL, 'intent_sha256': m.digest(intent),
            'installation': {'config': {'public': {}}, 'library': {}}}
    (root / 'intent.json').write_text(json.dumps(intent))
    (root / 'completed.json').write_text(json.dumps(done))
    def forbidden(*args, **kwargs):
        raise AssertionError('historical proof must not read removed installation/live state')
    b = SimpleNamespace(STATE=tmp_path, CONFIG=tmp_path/'removed', INSTALLED=tmp_path/'removed/module.py',
                        secure=lambda *a, **k: None, _inventory=lambda *a: None,
                        _read_json=lambda p: json.loads(p.read_text()), canonical_source=lambda s: tmp_path/s,
                        _recovery_file_identity=lambda p: {}, _installation_evidence=forbidden)
    monkeypatch.setattr(m, 'restoration', lambda *a: ({'snapshot': {**snapshot, 'prior_consumed_intent': {}, 'prior_recovery_sha': m.PRIOR_RECOVERY, 'prior_evidence_sha256': m.PRIOR_EVIDENCE}, 'recovery_sha': recovery}, {'stable_services': services}, audit))
    monkeypatch.setattr(m, 'workspace', lambda *a: work)
    assert m.closed_evidence(b, m.FAILED, receipt, historical=True)['state'] == m.TERMINAL
    with pytest.raises(AssertionError):
        m.closed_evidence(b, m.FAILED, receipt, historical=False)
    with pytest.raises(m.ClosureError):
        m.closed_evidence(b, m.FAILED, '4'*64, historical=True)
    done['state'] = 'SUCCEEDED'
    (root / 'completed.json').write_text(json.dumps(done))
    with pytest.raises(m.ClosureError):
        m.closed_evidence(b, m.FAILED, receipt, historical=True)


def test_conflicting_old_closure_is_rejected(tmp_path):
    from types import SimpleNamespace
    m = load()
    for name in m.CONFLICTS:
        path = tmp_path/name/m.FAILED
        path.mkdir(parents=True)
        with pytest.raises(m.ClosureError):
            m.no_conflicts(SimpleNamespace(STATE=tmp_path), m.FAILED)
        path.rmdir()


def bootstrap():
    import sys
    path = Path(__file__).with_name('bootstrap_trusted_release.py')
    spec = importlib.util.spec_from_file_location('dinner_bootstrap_test', path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def test_bootstrap_dispatches_historical_dinner_profile_and_rejects_conflicts(tmp_path, monkeypatch):
    from types import SimpleNamespace
    m, b = load(), bootstrap()
    (tmp_path/m.ROOT_NAME/m.FAILED).mkdir(parents=True)
    monkeypatch.setattr(b, 'STATE', tmp_path)
    seen = []
    def consume(_b, sha, receipt, *, historical):
        seen.append((sha, receipt, historical))
        return {'state': m.TERMINAL}
    monkeypatch.setattr(b, '_dinner_guard_module', lambda: SimpleNamespace(closed_evidence=consume))
    assert b._workspace_evidence(m.FAILED, recovery_receipt='3'*64, historical=True) == {'state': m.TERMINAL}
    assert seen == [(m.FAILED, '3'*64, True)]
    (tmp_path/'contained-release-closures'/m.FAILED).mkdir(parents=True)
    with pytest.raises(b.BootstrapError):
        b._workspace_evidence(m.FAILED, recovery_receipt='3'*64, historical=True)


def test_ephemeral_rotation_cannot_mix_authorities(monkeypatch):
    from types import SimpleNamespace
    m, b = load(), bootstrap()
    monkeypatch.setattr(b, 'validate_install', lambda *a, **k: None)
    monkeypatch.setattr(b, '_dinner_guard_module', lambda: SimpleNamespace(FAILED=m.FAILED))
    def forbidden(*a, **k):
        raise AssertionError('must reject before source or external access')
    monkeypatch.setattr(b, 'reviewed_source', forbidden)
    for extra in ({}, {'recovery_receipt': 'a'*64, 'backend_ci': True},
                  {'recovery_receipt': 'a'*64, 'review_release_github_token': 'other'},
                  {'recovery_receipt': 'a'*64, 'finalized_production_sha': m.PRODUCTION}):
        with pytest.raises(b.BootstrapError):
            b.rotate(m.FAILED, '1'*40, 0, 'unused', dinner_guard_github_token='ghs_test', **extra)


@pytest.fixture
def dinner_workspace(tmp_path):
    from types import SimpleNamespace
    m = load()
    root = tmp_path / m.FAILED
    root.mkdir(mode=0o700)
    canonical = tmp_path / 'canonical'
    (canonical / 'scripts').mkdir(parents=True)
    code = canonical / 'scripts/trusted_release_server.py'
    code.write_text('fixed executor bytes\n')
    executor = hashlib.sha256(code.read_bytes()).hexdigest()
    states = {'started.json': 'STARTED', 'preparation-started.json': 'PREPARING',
              'prepared.json': 'PREPARED', 'deployment-started.json': 'DEPLOYING',
              'completed.json': 'NEEDS_OPERATOR'}
    for name, state in states.items():
        value = {'sha': m.FAILED, 'state': state}
        if name == 'preparation-started.json':
            value['executor_sha256'] = executor
        (root / name).write_text(json.dumps(value))
    for name in ('preparation.log', 'deployment.log'):
        (root / name).write_text('original audit\n')
    for name in ('bin', 'source', 'home'):
        (root / name).mkdir(mode=0o700)
    calls = []
    def manifest(path):
        assert path == root
        calls.append(path)
        return {'complete_tree': 'bound'}
    b = SimpleNamespace(STATE=tmp_path, secure=lambda *a, **k: None,
                        canonical_source=lambda sha: canonical if sha == m.FAILED else None,
                        _read_json=lambda p: json.loads(p.read_text()), _preparation_manifest=manifest)
    return m, b, canonical, root, executor, calls


def test_fixed_ten_item_workspace_binds_complete_tree(dinner_workspace):
    m, b, source, root, executor, calls = dinner_workspace
    assert len(list(root.iterdir())) == 10
    assert m.workspace(b, source) == {'executor_sha256': executor, 'manifest': {'complete_tree': 'bound'}}
    assert calls == [root]


@pytest.mark.parametrize('name', ['deployment.env', 'unexpected.json', 'build.lock', 'clone-attempts'])
def test_workspace_rejects_any_extra_including_env(dinner_workspace, name):
    m, b, source, root, _, calls = dinner_workspace
    (root / name).write_text('unexpected')
    with pytest.raises(m.ClosureError):
        m.workspace(b, source)
    assert calls == []


@pytest.mark.parametrize('name', ['started.json', 'deployment.log', 'bin'])
def test_workspace_rejects_missing_items(dinner_workspace, name):
    m, b, source, root, _, calls = dinner_workspace
    path = root/name
    path.rmdir() if path.is_dir() else path.unlink()
    with pytest.raises(m.ClosureError):
        m.workspace(b, source)
    assert calls == []


@pytest.mark.parametrize('name', ['started.json', 'preparation-started.json', 'prepared.json', 'deployment-started.json', 'completed.json'])
def test_workspace_rejects_phase_drift(dinner_workspace, name):
    m, b, source, root, _, calls = dinner_workspace
    value = json.loads((root/name).read_text())
    value['state'] = 'SUCCEEDED'
    (root/name).write_text(json.dumps(value))
    with pytest.raises(m.ClosureError):
        m.workspace(b, source)
    assert calls == []


def test_workspace_rejects_wrong_executor_digest(dinner_workspace):
    m, b, source, root, _, calls = dinner_workspace
    path = root/'preparation-started.json'
    value = json.loads(path.read_text())
    value['executor_sha256'] = '0'*64
    path.write_text(json.dumps(value))
    with pytest.raises(m.ClosureError):
        m.workspace(b, source)
    assert calls == []


@pytest.fixture
def continuation_receipts(monkeypatch):
    import copy
    from types import SimpleNamespace
    m = load()
    path=Path(__file__).with_name('dinner_guard_recovery_continuation.py')
    spec=importlib.util.spec_from_file_location('dinner_bridge_fixture',path)
    bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
    base=SimpleNamespace(LEASE_PINS={'token':'a'*64},LOG_PIN='b'*64,COMPLETED_PIN='c'*64,
                         TERMINAL_PIN='d'*64,FILE_PINS={'/synthetic':'e'*64},
                         UNIT_CONFIG_PINS={'unit':'f'*64},UNIT_STATIC_CONFIG_PINS={'unit':'0'*64})
    old={'lease':{'token':{'sha256':'a'*64}},'log':{'sha256':'b'*64},'completed':{'sha256':'c'*64},
         'terminal':{'sha256':'d'*64},'files':{'/synthetic':{'sha256':'e'*64}},
         'units':{'unit':{'effective_sha256':'f'*64,'files':{'unchanged':True}}},
         'dependencies':{'unchanged':'original'}}
    prior={'recovery_sha':m.PRIOR_RECOVERY,'failed_sha':m.FAILED,'production_sha':m.PRODUCTION,'snapshot':old}
    prior['evidence_sha256']=m.digest(prior)
    monkeypatch.setattr(m,'PRIOR_EVIDENCE',prior['evidence_sha256'])
    identity={'sha256':m.PRIOR_INTENT_PIN}
    current=copy.deepcopy(old);current['units']['unit']['effective_sha256']='0'*64
    current.update(prior_consumed_intent=identity,prior_recovery_sha=m.RESTORED_FROM,
                   prior_evidence_sha256=prior['evidence_sha256'])
    # The metadata points to the consumed original recovery, never to itself.
    current['prior_recovery_sha']=m.PRIOR_RECOVERY
    intent={'recovery_sha':m.RESTORED_FROM,'failed_sha':m.FAILED,'production_sha':m.PRODUCTION,'snapshot':current}
    intent['evidence_sha256']=m.digest(intent)
    monkeypatch.setattr(m,'CONTINUATION_EVIDENCE',intent['evidence_sha256'])
    done={k:intent[k] for k in ('recovery_sha','failed_sha','production_sha','evidence_sha256')}
    done.update(state='RESTORED_PREVIOUS_SERVICES',stable_services={'stable':'same'},original_release_and_lease_preserved=True)
    return m,prior,identity,intent,done,base,bridge


def test_fixed_continuation_strips_only_exact_prior_metadata(continuation_receipts):
    m,prior,identity,intent,done,base,bridge=continuation_receipts
    m.validate_restoration(prior,identity,intent,done,base,bridge)
    result=m.semantic_snapshot(intent['snapshot'])
    assert set(result)==set(prior['snapshot'])
    assert result['units']['unit']['effective_sha256']=='0'*64
    assert result['dependencies']==prior['snapshot']['dependencies']


@pytest.mark.parametrize('field',['dependencies','files','lease','log','completed','terminal'])
def test_continuation_cannot_ignore_other_snapshot_drift(continuation_receipts,monkeypatch,field):
    m,prior,identity,intent,done,base,bridge=continuation_receipts
    intent['snapshot'][field]['unexpected']='drift'
    intent['evidence_sha256']=m.digest({k:v for k,v in intent.items() if k!='evidence_sha256'})
    done['evidence_sha256']=intent['evidence_sha256']
    monkeypatch.setattr(m,'CONTINUATION_EVIDENCE',intent['evidence_sha256'])
    with pytest.raises(RuntimeError):m.validate_restoration(prior,identity,intent,done,base,bridge)


@pytest.mark.parametrize('where,field,value',[
    ('prior','recovery_sha','1'*40),('intent','recovery_sha','1'*40),
    ('done','original_release_and_lease_preserved',False),('done','state','SUCCEEDED'),
    ('done','evidence_sha256','1'*64),('prior','evidence_sha256','1'*64)])
def test_continuation_revision_and_completion_must_match(continuation_receipts,where,field,value):
    m,prior,identity,intent,done,base,bridge=continuation_receipts
    {'prior':prior,'intent':intent,'done':done}[where][field]=value
    with pytest.raises(m.ClosureError):m.validate_restoration(prior,identity,intent,done,base,bridge)


def test_continuation_does_not_drop_arbitrary_snapshot_keys(continuation_receipts):
    m,prior,identity,intent,done,base,bridge=continuation_receipts
    intent['snapshot']['ignored_new_field']=True
    with pytest.raises(m.ClosureError):m.semantic_snapshot(intent['snapshot'])


def test_continuation_prior_file_identity_is_bound(continuation_receipts):
    m,prior,identity,intent,done,base,bridge=continuation_receipts
    with pytest.raises(m.ClosureError):m.validate_restoration(prior,{'sha256':'0'*64},intent,done,base,bridge)


@pytest.fixture
def restoration_tree(continuation_receipts,tmp_path,monkeypatch):
    from types import SimpleNamespace
    m,prior,identity,intent,done,base,bridge=continuation_receipts
    root=tmp_path/'contained-service-recoveries'/m.FAILED
    child=root/m.CONTINUATION
    child.mkdir(parents=True,mode=0o700)
    root.chmod(0o700)
    raw=json.dumps(prior).encode()
    (root/'intent.json').write_bytes(raw)
    pin=hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(m,'PRIOR_INTENT_PIN',pin)
    monkeypatch.setattr(bridge,'INTENT_PIN',pin)
    monkeypatch.setattr(bridge,'PRIOR_DIGEST',m.PRIOR_EVIDENCE)
    identity['sha256']=pin
    intent['evidence_sha256']=m.digest({k:v for k,v in intent.items() if k!='evidence_sha256'})
    monkeypatch.setattr(m,'CONTINUATION_EVIDENCE',intent['evidence_sha256'])
    done['evidence_sha256']=intent['evidence_sha256']
    for name,value,constant in (('intent.json',intent,'CONTINUATION_INTENT_PIN'),('completed.json',done,'CONTINUATION_COMPLETED_PIN')):
        raw=json.dumps(value).encode();(child/name).write_bytes(raw)
        monkeypatch.setattr(m,constant,hashlib.sha256(raw).hexdigest())
    prior_source=tmp_path/'canonical'/m.PRIOR_RECOVERY
    (prior_source/'scripts').mkdir(parents=True)
    (prior_source/'scripts/dinner_guard_recovery.py').write_text('UNIT_CONFIG_PINS = '+repr(base.UNIT_CONFIG_PINS))
    def read(path,*,pin=None):
        raw=Path(path).read_bytes();actual=hashlib.sha256(raw).hexdigest()
        m.need(pin is None or actual==pin)
        return {'sha256':actual},raw
    base.identity=read
    monkeypatch.setattr(m,'load',lambda b,path,name: base if path.name=='dinner_guard_recovery.py' else bridge)
    b=SimpleNamespace(STATE=tmp_path,secure=lambda *a,**k:None,
                      canonical_source=lambda sha: tmp_path/'canonical'/sha)
    return m,b,root,child


def test_restoration_reads_only_fixed_successful_continuation(restoration_tree):
    m,b,root,child=restoration_tree
    prior=(root/'intent.json').read_bytes()
    intent,done,audit=m.restoration(b,Path('/unused'))
    assert done['state']=='RESTORED_PREVIOUS_SERVICES'
    assert intent['recovery_sha']==m.RESTORED_FROM
    assert set(audit)=={'prior_intent','continuation_intent','continuation_completed','root','continuation'}
    assert (root/'intent.json').read_bytes()==prior
    assert not (root/'completed.json').exists()


@pytest.mark.parametrize('target',['prior','child_intent','child_completed'])
def test_restoration_rejects_even_semantically_identical_changed_bytes(restoration_tree,target):
    m,b,root,child=restoration_tree
    path={'prior':root/'intent.json','child_intent':child/'intent.json','child_completed':child/'completed.json'}[target]
    path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(m.ClosureError):m.restoration(b,Path('/unused'))


@pytest.mark.parametrize('parent,name',[('root','completed.json'),('root','other-continuation'),('child','failure.json'),('child','unexpected')])
def test_restoration_inventory_is_exact(restoration_tree,parent,name):
    m,b,root,child=restoration_tree
    ((root if parent=='root' else child)/name).write_text('{}')
    with pytest.raises(m.ClosureError):m.restoration(b,Path('/unused'))


def test_restoration_incomplete_continuation_rejected(restoration_tree):
    m,b,root,child=restoration_tree
    (child/'completed.json').unlink()
    with pytest.raises(m.ClosureError):m.restoration(b,Path('/unused'))


@pytest.fixture
def root_owned_metadata(monkeypatch, tmp_path):
    """Real filesystem objects with only host-dependent ownership normalized."""
    import os
    original = Path.lstat
    ancestors = set(tmp_path.parents)
    def lstat(path, *args, **kwargs):
        value = original(path, *args, **kwargs)
        from types import SimpleNamespace
        fields = {name: getattr(value, name) for name in dir(value) if name.startswith('st_')}
        fields['st_uid'] = fields['st_gid'] = 0
        if path in ancestors:
            fields['st_mode'] &= ~0o022
        return SimpleNamespace(**fields)
    monkeypatch.setattr(Path, 'lstat', lstat)


def test_private_directory_uses_real_bootstrap_secure(tmp_path, root_owned_metadata):
    m, b = load(), bootstrap()
    directory = tmp_path/'private-directory'
    directory.mkdir(mode=0o700)
    # Establish the exact dependency contract that exposed the production defect.
    with pytest.raises(b.BootstrapError):
        b.secure(directory, private=True)
    m.private_directory(b, directory)
    directory.chmod(0o755)
    with pytest.raises(m.ClosureError):
        m.private_directory(b, directory)
    directory.chmod(0o777)
    with pytest.raises(b.BootstrapError):
        m.private_directory(b, directory)
    file = tmp_path/'private-file'
    file.write_text('synthetic')
    file.chmod(0o600)
    with pytest.raises(m.ClosureError):
        m.private_directory(b, file)
    link = tmp_path/'link'
    link.symlink_to(file)
    with pytest.raises(b.BootstrapError):
        m.private_directory(b, link)


def test_workspace_uses_real_bootstrap_directory_contract(dinner_workspace, root_owned_metadata):
    m, b, source, root, executor, calls = dinner_workspace
    real = bootstrap()
    b.secure, b._read_json, b._preparation_manifest = real.secure, real._read_json, real._preparation_manifest
    for path in root.iterdir():
        if path.is_file():
            path.chmod(0o600)
    manifest = m.workspace(b, source)['manifest']
    assert manifest['entries'] == 11 and manifest['bytes'] > 0
    (root/'completed.json').chmod(0o644)
    with pytest.raises(real.BootstrapError):
        m.workspace(b, source)


def test_restoration_directories_use_real_bootstrap_secure(restoration_tree, root_owned_metadata):
    m, b, root, child = restoration_tree
    b.secure = bootstrap().secure
    assert m.restoration(b, root)[2]['root']['st_mode'] & 0o777 == 0o700
    child.chmod(0o755)
    with pytest.raises(m.ClosureError):
        m.restoration(b, root)


def test_real_installation_and_closure_inventory_contract(tmp_path, monkeypatch, root_owned_metadata):
    m, b = load(), bootstrap()
    config, library, canonical = (tmp_path/name for name in ('config', 'library', 'canonical'))
    for directory in (config, library, canonical):
        directory.mkdir(mode=0o700)
    (canonical/'scripts').mkdir(mode=0o700)
    code = b'executor synthetic bytes\n'
    (canonical/'scripts/trusted_release_server.py').write_bytes(code)
    executor = hashlib.sha256(code).hexdigest()
    monkeypatch.setattr(b, 'canonical_source', lambda sha: canonical)
    monkeypatch.setattr(b, 'CONFIG', config)
    monkeypatch.setattr(b, 'INSTALLED', library/'trusted_release_server.py')
    monkeypatch.setattr(b, 'AUTHORIZED', tmp_path/'authorized_keys')
    monkeypatch.setattr(b, 'validate_install', lambda *args, **kwargs: None)
    values = {'known_hosts': 'synthetic host', 'loopback.conf': 'synthetic config',
              'authorized-release.json': json.dumps({'sha': m.FAILED, 'expires_at': 0, 'executor_sha256': executor}),
              'cloud.pub': 'ssh-ed25519 cloudsynthetic', 'loopback.pub': 'ssh-ed25519 loopsynthetic'}
    for name, value in values.items():
        (config/name).write_text(value)
        (config/name).chmod(0o600)
    b.INSTALLED.write_bytes(code)
    b.INSTALLED.chmod(0o600)
    b.AUTHORIZED.write_text('unrelated operator key\n')
    b.AUTHORIZED.chmod(0o600)
    expected = {'config': b._inventory(config, set(values)), 'library': b._inventory(library, {b.INSTALLED.name})}
    assert b._installation_evidence(m.FAILED, config, library) == expected
    closure = tmp_path/'closure'
    closure.mkdir(mode=0o700)
    for name in ('intent.json', 'completed.json'):
        (closure/name).write_text(json.dumps({'synthetic': True}))
        (closure/name).chmod(0o600)
    m.private_directory(b, closure)
    assert set(b._inventory(closure, {'intent.json', 'completed.json'})) == {'.', 'intent.json', 'completed.json'}
    assert b._read_json(closure/'intent.json') == {'synthetic': True}
    (closure/'intent.json').chmod(0o644)
    with pytest.raises(b.BootstrapError):
        b._inventory(closure, {'intent.json', 'completed.json'})
    (config/'cloud.pub').chmod(0o644)
    with pytest.raises(b.BootstrapError):
        b._installation_evidence(m.FAILED, config, library)
