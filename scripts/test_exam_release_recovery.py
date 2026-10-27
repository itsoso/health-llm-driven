"""Offline fail-closed tests for the fixed post-checkout exam incident."""
import importlib.util
import json
from pathlib import Path

import pytest


def module():
    path = Path(__file__).with_name('exam_release_recovery.py')
    spec = importlib.util.spec_from_file_location('exam_forward_test', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Adapter:
    recovery_sha = 'c' * 40
    def __init__(self, audit):
        self.audit = audit
        self.events = []
        self.fail = None
        self.state = 'PENDING'
        self.generation = 0
    def call(self, name):
        self.events.append(name)
        if self.fail == name:
            raise RuntimeError('secret must never be copied')
    def snapshot(self):
        self.call('snapshot')
        return {'original': 'sealed', 'generation': self.generation}
    def stopped(self): self.call('stopped')
    def preflight(self): self.call('preflight'); return {'database_state': self.state}
    def database_apply(self, plan):
        self.call('database_apply')
        assert (self.audit / 'intent.json').exists()
        assert (self.audit / 'database-started.json').exists()
        self.state = 'APPLIED'
        return {'schema_sha256': 'd' * 64}
    def readback(self, plan): self.call('readback'); return {'schema_sha256': 'd' * 64}
    def candidate_guards(self): self.call('guards')
    def start(self): self.call('start')
    def stable(self): self.call('stable'); return {'stable': True}
    def http(self): self.call('http')
    def commit_runtime(self): self.call('commit')
    def finalize_runtime(self): self.call('finalize'); return {'terminal_sha': module().FAILED}
    def stop(self): self.call('stop')


def test_inspect_is_default_and_read_only(tmp_path):
    m = module(); a = Adapter(tmp_path / 'fixed')
    result = m.recover(a)
    assert result['state'] == 'INSPECTED'
    assert not a.audit.exists()
    assert a.events == ['snapshot', 'stopped', 'preflight', 'snapshot', 'stopped']


@pytest.mark.parametrize('digest,accept', [(None, True), ('0'*64, False)])
def test_execution_requires_digest_and_fixed_authorization_together(tmp_path, digest, accept):
    m = module(); a = Adapter(tmp_path / 'fixed')
    with pytest.raises(m.RecoveryError): m.recover(a, digest, accept=accept)
    assert not a.audit.exists()


def test_digest_drift_never_consumes_attempt(tmp_path):
    m = module(); a = Adapter(tmp_path / 'fixed')
    expected = m.recover(a)['evidence_sha256']; a.generation += 1
    with pytest.raises(m.RecoveryError): m.recover(a, expected, accept=True)
    assert not a.audit.exists()


def test_preflight_failure_never_consumes_attempt(tmp_path):
    m = module(); a = Adapter(tmp_path / 'fixed'); a.fail = 'preflight'
    with pytest.raises(RuntimeError): m.recover(a)
    assert not a.audit.exists()


def test_applied_is_not_replay_authority(tmp_path):
    m = module(); a = Adapter(tmp_path / 'fixed'); a.state = 'APPLIED'
    with pytest.raises(m.RecoveryError): m.recover(a)
    assert not a.audit.exists()


@pytest.mark.parametrize('artifact', ['directory', 'file', 'dangling_symlink'])
def test_existing_attempt_is_always_terminal_to_operator(tmp_path, artifact):
    m = module(); a = Adapter(tmp_path / 'fixed')
    if artifact == 'directory': a.audit.mkdir()
    elif artifact == 'file': a.audit.write_text('unknown')
    else: a.audit.symlink_to(tmp_path / 'absent')
    with pytest.raises(m.RecoveryError): m.recover(a)
    assert a.events == []


def test_complete_order_preserves_old_release_and_names_a8_only(tmp_path):
    m = module(); a = Adapter(tmp_path / 'fixed')
    expected = m.recover(a)['evidence_sha256']; a.events.clear()
    result = m.recover(a, expected, accept=True)
    assert result['state'] == 'FORWARD_RECOVERED'
    assert result['production_sha'] == m.FAILED
    assert result['original_release_state'] == 'NEEDS_OPERATOR'
    assert result['original_lease_and_authorization_preserved'] is True
    assert a.events.index('database_apply') < a.events.index('readback') < a.events.index('guards') < a.events.index('start')
    assert a.events.index('http') < a.events.index('commit') < a.events.index('finalize')
    assert a.events.count('stable') >= 3
    assert json.loads((a.audit / 'completed.json').read_text()) == result
    with pytest.raises(m.RecoveryError): m.recover(a, expected, accept=True)


@pytest.mark.parametrize('phase', ['database_apply','readback','guards','start','stable','http','commit','finalize'])
def test_consumed_failure_is_durable_contained_secret_free_and_not_retried(tmp_path, phase):
    m = module(); a = Adapter(tmp_path / 'fixed')
    expected = m.recover(a)['evidence_sha256']; a.fail = phase
    with pytest.raises(m.RecoveryError): m.recover(a, expected, accept=True)
    assert a.events[-1] == 'stop'
    assert (a.audit / 'intent.json').exists()
    assert not (a.audit / 'completed.json').exists()
    failure = (a.audit / 'failure.json').read_text()
    assert 'secret' not in failure
    assert json.loads(failure)['state'] == 'NEEDS_OPERATOR'
    with pytest.raises(m.RecoveryError): m.recover(a, expected, accept=True)


def test_stop_failure_is_not_reported_as_contained(tmp_path):
    m = module(); a = Adapter(tmp_path / 'fixed')
    expected = m.recover(a)['evidence_sha256']; a.fail = 'database_apply'
    a.stop = lambda: (_ for _ in ()).throw(OSError('stop secret'))
    with pytest.raises(m.RecoveryError): m.recover(a, expected, accept=True)
    failure = json.loads((a.audit / 'failure.json').read_text())
    assert failure['containment'] == 'UNPROVEN'


@pytest.mark.parametrize('field,value', [('phase','COMMITTED'),('mode','snapshot'),('version',1),('candidate_sha','d'*40),('old_sha','e'*40),('boot_gate_armed',False),('boot_gate_released',True),('release_target','candidate')])
def test_original_runtime_journal_has_exact_fixed_shape(field, value):
    m = module(); j = {'version':2,'mode':'code-only-no-backup','phase':'INSTALLED','candidate_sha':m.FAILED,'old_sha':m.PREVIOUS,'boot_gate_armed':True,'boot_gate_released':False,'release_target':None}
    m.validate_journal(j)
    j[field] = value
    with pytest.raises(m.RecoveryError): m.validate_journal(j)


def test_pi_lock_rejects_missing_required_and_changed_integrity():
    m = module()
    item = {'version':'1.0.0','resolved':'https://registry.npmjs.org/x','integrity':'sha512-x'}
    expected = {'lockfileVersion':3,'packages':{'':{},'node_modules/x':item,'node_modules/y':{**item,'optional':True}}}
    actual = {'lockfileVersion':3,'packages':{'node_modules/x':item}}
    assert m.validate_pi_lock(expected, actual) == ['node_modules/x']
    for altered in ({}, {'node_modules/x':{**item,'integrity':'bad'}}, {'node_modules/x':item,'node_modules/z':item}):
        with pytest.raises(m.RecoveryError): m.validate_pi_lock(expected, {'lockfileVersion':3,'packages':altered})


def test_stop_with_lost_original_lease_does_not_touch_services():
    m = module(); a = object.__new__(m.Adapter)
    calls = []
    from types import SimpleNamespace
    a.core = SimpleNamespace(_systemctl=lambda *args: calls.append(args))
    a._authority = lambda: (_ for _ in ()).throw(m.RecoveryError('changed lease'))
    a.stopped = a._authority
    with pytest.raises(m.RecoveryError): a.stop()
    assert not calls


def test_existing_missing_build_lock_proof_creates_nothing(tmp_path):
    spec = importlib.util.spec_from_file_location('exam_original_bootstrap_test', Path(__file__).with_name('bootstrap_trusted_release.py'))
    b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
    b.STATE = tmp_path
    (tmp_path / 'a').mkdir()
    assert b._acquire_existing_build_lock('a') is None
    assert not list((tmp_path / 'a').iterdir())


def test_gate_projection_never_relaxes_network_guard_and_rejects_actual_drift():
    m = module()
    from types import SimpleNamespace
    values = dict.fromkeys(m.UNITS, 'disabled')
    values['health-network-guard.service'] = 'enabled'
    raw = SimpleNamespace(is_enabled=lambda unit: values[unit], show=lambda unit, prop: 'raw')
    view = m.GateView(raw, dict.fromkeys(m.UNITS, 'enabled'), released=False)
    assert view.is_enabled('health-network-guard.service') == 'enabled'
    assert view.is_enabled(m.UNITS[0]) == 'enabled'
    assert view.show(m.UNITS[0], 'ExecStart') == 'raw'
    values[m.UNITS[0]] = 'enabled'
    with pytest.raises(m.RecoveryError): view.is_enabled(m.UNITS[0])


def test_actual_runtime_installed_validation_is_read_only_and_finalizes_forward(tmp_path):
    import sys
    path = Path(__file__).with_name('test_runtime_state_release_transaction.py')
    spec = importlib.util.spec_from_file_location('exam_runtime_fixture', path)
    fixture = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = fixture
    spec.loader.exec_module(fixture)
    transaction, layout, lease, token = fixture._code_transaction(tmp_path)
    m = module()
    transaction.prepare(m.PREVIOUS, m.FAILED, lease, token)
    transaction.install(m.PREVIOUS, m.FAILED, lease, token)
    journal = layout.transaction_root / 'journal.json'
    before = (journal.read_bytes(), journal.stat().st_ino, journal.stat().st_mtime_ns)
    assert transaction.install(m.PREVIOUS, m.FAILED, lease, token) == 'INSTALLED'
    assert (journal.read_bytes(), journal.stat().st_ino, journal.stat().st_mtime_ns) == before
    with pytest.raises(fixture.TransactionError): transaction.commit(m.FAILED, lease, token)
    fixture._mark_boot_gate_active(transaction)
    assert transaction.commit(m.FAILED, lease, token) == 'COMMITTED'
    assert transaction.finalize(m.FAILED, lease, token) == 'finalized'
    marker = transaction._load_terminal_marker()
    assert marker['terminal_sha'] == m.FAILED
    assert marker['old_sha'] == m.PREVIOUS
    assert lease.exists()
    assert not layout.transaction_root.exists()


def test_dependency_hash_is_streamed_and_has_no_one_megabyte_limit(tmp_path):
    import hashlib
    from types import SimpleNamespace
    m = module(); path = tmp_path / 'package.js'
    raw = b'x' * 1000001; path.write_bytes(raw)
    assert m.dependency_digest(path, SimpleNamespace(secure=lambda _: None)) == hashlib.sha256(raw).hexdigest()


# Reuse the dedicated local cluster fixture; it rejects non-local/admin targets,
# creates unique databases/roles and removes only those synthetic objects.
_pg_spec = importlib.util.spec_from_file_location('exam_forward_pg_fixture', Path(__file__).with_name('test_exam_attempts_release_postgres.py'))
_pg_module = importlib.util.module_from_spec(_pg_spec)
_pg_spec.loader.exec_module(_pg_module)
pg = _pg_module.pg


def database_adapter(pg):
    import hashlib
    m = module()
    helper, migration, runtime, role, old_plan, expected, directory = pg
    a = object.__new__(m.Adapter)
    from types import SimpleNamespace
    a.bootstrap = SimpleNamespace(_recovery_process_proof=lambda: None)
    a.helper, a.migration, a.runtime, a.expected = helper, migration, runtime, expected
    a.failed_source = Path(__file__).resolve().parents[1]
    a.audit = directory / 'new-attempt'; a.audit.mkdir()
    a.check = a.stopped = a._authority = lambda: None
    a.snapshot = lambda: {'unchanged': True}
    with migration.connect() as c: identity = helper.role_identity(c)
    with runtime.connect() as c: runtime_identity = helper.role_identity(c)
    a.old_plan = {'database_sha256': hashlib.sha256(json.dumps([identity,runtime_identity],sort_keys=True).encode()).hexdigest()}
    return m, a


def test_real_forward_adapter_transaction_tightens_only_new_object_acl(pg):
    from sqlalchemy import text
    m, a = database_adapter(pg)
    role = pg[3]
    with a.migration.begin() as c:
        c.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO {role}'))
        c.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,USAGE ON SEQUENCES TO {role}'))
        defaults = c.execute(text('SELECT defaclobjtype,defaclacl::text FROM pg_default_acl ORDER BY defaclobjtype')).all()
    plan = {'attempt':m.ATTEMPT,'source_sha':m.FAILED,'original_intent_sha256':m.INTENT_PIN}
    completed = a.database_apply(plan)
    assert a.readback(plan) == completed
    with a.migration.connect() as c:
        assert a.helper.database_state(c,a.expected) == 'APPLIED'
        assert c.execute(text('SELECT count(*) FROM life_exam_attempts')).scalar_one() == 0
        assert c.execute(text('SELECT is_called FROM life_exam_attempts_sequence_seq')).scalar_one() is False
        assert c.execute(text('SELECT defaclobjtype,defaclacl::text FROM pg_default_acl ORDER BY defaclobjtype')).all() == defaults
    with pytest.raises(m.RecoveryError): a.database_apply(plan)
    assert a.readback(plan) == completed


def test_real_forward_adapter_rejects_database_identity_drift_before_ddl(pg):
    m, a = database_adapter(pg)
    a.old_plan['database_sha256'] = '0' * 64
    with pytest.raises(m.RecoveryError): a.database_apply({'attempt':m.ATTEMPT})
    with a.migration.connect() as c: assert a.helper.database_state(c,a.expected) == 'PENDING'


def test_real_forward_adapter_rolls_back_when_original_lease_changes(pg):
    m, a = database_adapter(pg)
    a._authority = lambda: (_ for _ in ()).throw(m.RecoveryError('lease changed before commit'))
    with pytest.raises(m.RecoveryError): a.database_apply({'attempt':m.ATTEMPT})
    with a.migration.connect() as c: assert a.helper.database_state(c,a.expected) == 'PENDING'


def vision_configuration_fixture(monkeypatch):
    """Exercise the real NoBackupPreflightProof wrapper at the adapter boundary."""
    from types import SimpleNamespace
    import sys
    m = module()
    path = Path(__file__).with_name('no_backup_preflight_proof.py')
    spec = importlib.util.spec_from_file_location('exam_vision_no_backup_test', path)
    no_backup = importlib.util.module_from_spec(spec); sys.modules[spec.name] = no_backup
    spec.loader.exec_module(no_backup)
    state = {'active':False, 'pid':'0'}
    def active_only(*args):
        if not state['active']: raise no_backup.ProofError('service is not active and stable')
        return {'raw_dropins':dict.fromkeys(m.UNITS[1:],'unused'), 'services':{'pid':state['pid']}}
    monkeypatch.setattr(no_backup._retained, 'inspect_vision_overlay', active_only)
    monkeypatch.setattr(no_backup._retained, 'VisionBaseView', lambda raw, paths: raw)
    monkeypatch.setattr(no_backup.RecoveryProof, '_units', lambda *args, **kwargs: {'static':'verified'})
    raw = SimpleNamespace(is_enabled=lambda unit:'disabled', show=lambda *args:'static')
    proof = object.__new__(no_backup.NoBackupPreflightProof)
    proof.systemd = raw; proof.bootstrap = None; proof.source = Path('/canonical')
    proof._started_text = 'fixed'
    adapter = object.__new__(m.Adapter)
    adapter.proof = proof; adapter.finalized = False
    adapter.failed_source = Path('/canonical/a8')
    adapter.journal = {'original_enablement':dict.fromkeys(m.UNITS,'enabled')}
    adapter.transaction = SimpleNamespace(systemd=raw, _verify_boot_gate_armed=lambda _:None,
                                         _verify_original_enablement=lambda _:None)
    adapter.base_units = no_backup.RecoveryProof._units
    adapter.retained = no_backup._retained
    adapter._vision_static = lambda: {'model':'qwen3.8-flash','history':{'fixed':True},
                                     'files':{'fixed':True},'services':{'static':True},
                                     'raw_dropins':dict.fromkeys(m.UNITS[1:],'unused')}
    return adapter,state


def test_stopped_inspection_uses_static_vision_proof_without_requiring_running_pid(monkeypatch):
    a, state = vision_configuration_fixture(monkeypatch)
    result = a._configuration()
    assert result['static'] == 'verified'
    assert result['vision_overlay']['model'] == 'qwen3.8-flash'
    assert state['active'] is False


def test_immutable_configuration_does_not_change_when_services_start(monkeypatch):
    a,state = vision_configuration_fixture(monkeypatch)
    state.update(active=True,pid='1')
    before = a._configuration()
    state['pid'] = '2'
    assert a._configuration() == before


def test_model_identity_is_sampled_inside_the_same_stability_window():
    from types import SimpleNamespace
    m=module();a=object.__new__(m.Adapter);seen=[]
    a.check=lambda:None
    a.proof=object()
    a.running_snapshot=lambda:seen.append('services and model') or {'both':True}
    a.core=SimpleNamespace(_wait_ready=lambda subject:(subject.running_snapshot(),subject.running_snapshot())[1])
    assert a.stable()=={'both':True}
    assert seen==['services and model','services and model']


def static_vision_fixture(tmp_path,monkeypatch):
    from types import SimpleNamespace
    m=module()
    spec=importlib.util.spec_from_file_location('exam_static_vision_test',Path(__file__).with_name('trusted_vision_model.py'))
    vision=importlib.util.module_from_spec(spec);spec.loader.exec_module(vision)
    spec=importlib.util.spec_from_file_location('exam_static_retained_test',Path(__file__).with_name('retained_candidate_retirement.py'))
    retained=importlib.util.module_from_spec(spec);spec.loader.exec_module(retained)
    (tmp_path/'vision-models'/('a'*32)).mkdir(parents=True)
    monkeypatch.setattr(retained,'private_directory',lambda *args:None)
    monkeypatch.setattr(retained,'vision_history',lambda *args:{'history':'bound'})
    monkeypatch.setattr(vision,'finalization_model_files',lambda **kw:None)
    files={'metadata':{'uid':0,'gid':0,'mode':0o100600},'content':'reviewed exact file'}
    monkeypatch.setattr(vision,'optional_model_file',lambda path:files)
    props={unit:{key:'fixed' for key in m.VISION_STATIC_PROPERTIES} for unit in vision.SERVICES}
    for unit,values in props.items():
        values['EnvironmentFiles']='/opt/health-app/backend/.env (ignore_errors=no) /var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes) /var/lib/reva-vision-model/model.env (ignore_errors=no)'
        values['UnsetEnvironment']=''
        values['DropInPaths']=' '.join(retained.vision_paths(unit+'.service'))
    def run(args):
        # Active fields must not be queried by a stopped-source proof.
        assert not any(key in args[-1] for key in ('MainPID','ActiveState','NRestarts','Timestamp'))
        return '\n'.join(key+'='+value for key,value in props[args[2]].items())
    monkeypatch.setattr(vision,'run',run)
    monkeypatch.setattr(vision,'service_snapshot',lambda **kw:(_ for _ in ()).throw(AssertionError('active-only helper forbidden')))
    a=object.__new__(m.Adapter)
    a.vision=vision;a.retained=retained;a.source=tmp_path
    a.bootstrap=SimpleNamespace(STATE=tmp_path)
    a.server=SimpleNamespace(assert_vision_model_history=lambda _:None)
    a.proof=SimpleNamespace(systemd=SimpleNamespace(show=lambda unit,key:props[unit.removesuffix('.service')][key]))
    return m,a,props,files


def test_static_vision_reuses_env_order_unset_and_exact_dropin_contract(tmp_path,monkeypatch):
    m,a,props,files=static_vision_fixture(tmp_path,monkeypatch)
    result=a._vision_static()
    assert result['model']=='qwen3.8-flash'
    assert all(set(value)==set(m.VISION_STATIC_PROPERTIES) for value in result['services'].values())


@pytest.mark.parametrize('mutation',['env_order','unset','dropin','root_mode','history','unknown_static_field'])
def test_static_vision_contract_drift_blocks_stopped_inspection(tmp_path,monkeypatch,mutation):
    m,a,props,files=static_vision_fixture(tmp_path,monkeypatch)
    item=props['health-backend']
    if mutation=='env_order':item['EnvironmentFiles']='/var/lib/reva-vision-model/model.env (ignore_errors=no)'
    elif mutation=='unset':item['UnsetEnvironment']='LLM_VISION_MODEL'
    elif mutation=='dropin':item['DropInPaths']+=' /etc/systemd/system/health-backend.service.d/unknown.conf'
    elif mutation=='root_mode':files['metadata']['mode']=0o100644
    elif mutation=='history':a.server.assert_vision_model_history=lambda _:(_ for _ in ()).throw(RuntimeError('history incomplete'))
    else:item['UnknownProperty']='unexpected'
    with pytest.raises(Exception):a._vision_static()


def running_vision_fixture():
    from types import SimpleNamespace
    m=module();services={};models={};starts={};flags={};applied={}
    units=('health-backend','celery-worker','celery-beat')
    for index,unit in enumerate(units):
        main=str(100+index*10);child=str(101+index*10)
        starts.update({main:'111',child:'222'})
        flags.update({main:{'HEALTH_EVIDENCE_RUNTIME_ENABLED':'false'},child:{'HEALTH_EVIDENCE_RUNTIME_ENABLED':'false'}})
        applied.update({main:'qwen3.8-flash',child:'qwen3.8-flash'})
        services[unit+'.service']={'MainPID':main,'processes':{main:'111',child:'222'}}
        models[unit]={'MainPID':main,'process_start':'111','authorization_flags':flags[main]}
    def target(pid):
        if applied[str(pid)]!='qwen3.8-flash':raise RuntimeError('model mismatch')
        return applied[str(pid)]
    vision=SimpleNamespace(SERVICES=units,FLAGS=('HEALTH_EVIDENCE_RUNTIME_ENABLED',),
        process_start=lambda pid:starts[str(pid)],target_process_model=target,
        target_process_value=lambda pid,key:flags[str(pid)][key])
    return m,vision,services,models,starts,flags,applied


def test_running_vision_checks_every_cgroup_process():
    m,vision,services,models,*_=running_vision_fixture()
    result=m.verify_running_vision(vision,services,models)
    assert sum(len(value) for value in result.values())==6


@pytest.mark.parametrize('mutation',['child_model','child_flag','child_start','main_binding'])
def test_running_vision_rejects_child_or_main_identity_drift(mutation):
    m,vision,services,models,starts,flags,applied=running_vision_fixture()
    if mutation=='child_model':applied['101']='qwen-vl-max'
    elif mutation=='child_flag':flags['101']['HEALTH_EVIDENCE_RUNTIME_ENABLED']='true'
    elif mutation=='child_start':starts['101']='333'
    else:models['health-backend']['MainPID']='999'
    with pytest.raises(Exception):m.verify_running_vision(vision,services,models)


def health_report():
    return {'total_score':45,'max_possible':60,'threshold':35,'pass':True,
            'critical_failures':[],'deferred_failures':[],
            'dimensions':{'agent_runtime_circuit':{'healthy':True,'release_safe':True,'detail':'disabled'}}}


def test_g5_health_summary_accepts_only_normal_or_proven_coordinated_pause():
    m=module();report=health_report()
    assert m.health_summary(report)['score']==45
    report['dimensions']['agent_runtime_circuit']={'healthy':False,'release_safe':True,
        'detail':'paused:reconciliation_detected:generation=2:ack=1'}
    report['deferred_failures']=['agent_runtime_circuit']
    assert m.health_summary(report)['runtime_pause_preserved'] is True


@pytest.mark.parametrize('mutation',['score','nan','bool','critical','unsafe_pause','wrong_pause','deferred','threshold','maximum'])
def test_g5_health_summary_rejects_hard_gate_or_json_contract_failures(mutation):
    m=module();report=health_report()
    if mutation=='score':report['total_score']=34
    elif mutation=='nan':report['total_score']=float('nan')
    elif mutation=='bool':report['total_score']=True
    elif mutation=='critical':report['critical_failures']=['agent_runtime_circuit']
    elif mutation=='unsafe_pause':report['dimensions']['agent_runtime_circuit']['healthy']=False
    elif mutation=='wrong_pause':
        report['dimensions']['agent_runtime_circuit']={'healthy':False,'release_safe':True,'detail':'paused:reconciliation_detected:generation=1:ack=1'}
        report['deferred_failures']=['agent_runtime_circuit']
    elif mutation=='deferred':report['deferred_failures']=['agent_runtime_circuit']
    elif mutation=='threshold':report['threshold']=0
    else:report['max_possible']=100
    with pytest.raises(m.RecoveryError):m.health_summary(report)


def test_manifest_guard_requires_exact_unique_canonical_skill_slugs():
    m=module();payload={'skills':[{'slug':'one'},{'slug':'two'}]}
    assert m.manifest_summary(payload,{'one','two'})['count']==2
    for skills in ([],[{'slug':'one'}],[{'slug':'one'},{'slug':'one'}],[{'slug':'one'},{'slug':'three'}]):
        with pytest.raises(m.RecoveryError):m.manifest_summary({'skills':skills},{'one','two'})
