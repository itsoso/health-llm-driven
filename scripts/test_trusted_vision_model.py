import importlib.util
from pathlib import Path
import pytest

SPEC = importlib.util.spec_from_file_location('vision_operator', Path(__file__).with_name('trusted_vision_model.py'))
vision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vision)


def test_only_fixed_model_configuration():
    assert vision.model_bytes('qwen3.8-flash') == b'LLM_VISION_MODEL=qwen3.8-flash\n'
    for value in ('qwen-vl-max', 'x\nAPI_KEY=secret', '', 'qwen3-vl-flash'):
        with pytest.raises(vision.VisionError):
            vision.model_bytes(value)


def test_dropin_has_only_environment_file():
    assert vision.dropin_bytes() == b'[Service]\nEnvironmentFile=/var/lib/reva-vision-model/model.env\n'


def test_environment_sources_exact_order():
    base = '/opt/health-app/backend/.env (ignore_errors=no) /var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=no)'
    vision.validate_env_sources(base, installed=False)
    vision.validate_env_sources(base + ' /var/lib/reva-vision-model/model.env (ignore_errors=no)', installed=True)
    for value in (base[::-1], base + ' /other.env (ignore_errors=no)', base + ' /var/lib/reva-vision-model/model.env (ignore_errors=yes)'):
        with pytest.raises(vision.VisionError):
            vision.validate_env_sources(value, installed=True)


def test_digest_bound_to_nonsecret_snapshot():
    assert vision.digest({'sha': 'a'}) != vision.digest({'sha': 'b'})
    assert vision.digest({'a':1,'b':2}) == vision.digest({'b':2,'a':1})


def test_symlinks_and_hardlinks_rejected(tmp_path):
    p = tmp_path / 'file'
    p.write_bytes(b'model')
    link = tmp_path / 'link'
    link.symlink_to(p)
    with pytest.raises(vision.VisionError):
        vision.metadata(link)
    import os
    os.link(p, tmp_path / 'hard')
    with pytest.raises(vision.VisionError):
        vision.metadata(p)


def test_absent_metadata_and_model_snapshot(tmp_path):
    p = tmp_path / 'absent'
    assert vision.optional_model_file(p) is None
    p.write_bytes(b'API_KEY=private\n')
    with pytest.raises(vision.VisionError):
        vision.optional_model_file(p)


def test_atomic_install_replaces_only_target(tmp_path):
    p = tmp_path / 'target'
    p.write_bytes(b'old')
    other = tmp_path / 'grant'
    other.write_bytes(b'grant')
    vision.atomic_model_write(p, vision.model_bytes('qwen3.8-flash'))
    assert p.read_bytes() == vision.model_bytes('qwen3.8-flash')
    assert other.read_bytes() == b'grant'
    assert p.stat().st_mode & 0o777 == 0o600


def test_binding_rejects_failed_receipt():
    sha = 'a'*40
    vision.validate_binding(sha, sha, {'sha':sha,'state':'SUCCEEDED'})
    for receipt in ({'sha':sha,'state':'NEEDS_OPERATOR'}, {'sha':'b'*40,'state':'SUCCEEDED'}):
        with pytest.raises(vision.VisionError):
            vision.validate_binding(sha, sha, receipt)


def test_any_unset_rules_require_review():
    vision.validate_unset_environment('')
    for value in ('LLM_VISION_MODEL', 'LLM_VISION_MODEL=qwen3.8-flash', 'OTHER'):
        with pytest.raises(vision.VisionError):
            vision.validate_unset_environment(value)


def test_apply_keeps_model_acceptance_pending():
    source = Path(vision.__file__).read_text()
    assert 'CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE' in source
    assert 'read_production_env' not in source
    assert 'HARNESS_LIVE_LLM_EVAL_CONFIRMED' not in source


def test_sensitive_snapshot_reads_metadata_only(monkeypatch):
    seen = []
    monkeypatch.setattr(vision, 'secure_path', lambda path,**kwargs: seen.append(str(path)) or {'dev':1,'ino':1,'mode':0,'uid':0,'gid':0})
    actual = vision.protected_metadata()
    assert len(actual) == 4
    assert '/opt/health-app/backend/.env' in actual
    assert '/var/lib/reva-health-evidence-runtime/enabled.env' in actual


def test_no_paid_client_in_operator():
    assert 'openai' not in Path(vision.__file__).read_text().lower()


def process_fixture(tmp_path, raw):
    root = tmp_path / '123'
    root.mkdir()
    (root / 'environ').write_bytes(raw)
    (root / 'stat').write_text('123 (worker complex) ' + ' '.join(['S'] + ['0']*18 + ['999'] + ['0']*4))
    return root


def test_target_only_process_environment(tmp_path):
    process_fixture(tmp_path, b'API_KEY=must-not-return\0LLM_VISION_MODEL=qwen3.8-flash\0OTHER=value\0')
    assert vision.target_process_model(123,proc=tmp_path) == 'qwen3.8-flash'


@pytest.mark.parametrize('raw',[
    b'LLM_VISION_MODEL=qwen3.8-flash\0LLM_VISION_MODEL=qwen3.8-flash\0',
    b'API_KEY=private\0',
    b'LLM_VISION_MODEL=qwen-vl-max\0',
    b'LLM_VISION_MODEL=qwen3.8-flash',
    b'LLM_VISION_MODEL=' + b'x'*257 + b'\0',
])
def test_ambiguous_or_invalid_target_blocked(tmp_path,raw):
    process_fixture(tmp_path,raw)
    with pytest.raises(vision.VisionError):
        vision.target_process_model(123,proc=tmp_path)


def test_pid_starttime_change_blocked(tmp_path,monkeypatch):
    process_fixture(tmp_path,b'LLM_VISION_MODEL=qwen3.8-flash\0')
    values = iter(['before','after'])
    monkeypatch.setattr(vision,'process_start',lambda *args,**kwargs: next(values))
    with pytest.raises(vision.VisionError):
        vision.target_process_model(123,proc=tmp_path)


def test_release_only_own_lease_inventory(tmp_path,monkeypatch):
    monkeypatch.setattr(vision,'LEASE',tmp_path)
    monkeypatch.setattr(vision,'lease_check',lambda *args: None)
    (tmp_path / 'foreign').write_text('unrelated')
    with pytest.raises(vision.VisionError):
        vision.release_own_lease(None,None,None,'token',())
    assert (tmp_path / 'foreign').read_text() == 'unrelated'


def test_real_systemd_multiline_environment_file_order():
    raw = 'User=health-app\nEnvironmentFiles=/opt/health-app/backend/.env (ignore_errors=no)\nEnvironmentFiles=/var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes)\nUnsetEnvironment=\n'
    properties = vision.parse_service_properties(raw)
    vision.validate_env_sources(properties['EnvironmentFiles'],installed=False)
    assert properties['User'] == 'health-app'
    with pytest.raises(vision.VisionError):
        vision.parse_service_properties(raw + 'User=root\n')


def test_only_authorization_allowlist_process_flags(tmp_path):
    root = process_fixture(tmp_path,b'API_KEY=do-not-collect\0HEALTH_EVIDENCE_RUNTIME_ENABLED=true\0')
    assert vision.target_process_value(123,'HEALTH_EVIDENCE_RUNTIME_ENABLED',proc=tmp_path) == 'true'
    assert vision.target_process_value(123,'REGISTRATION_INVITATION_ROLLOUT_ENABLED',proc=tmp_path) is None
    with pytest.raises(vision.VisionError):
        vision.target_process_value(123,'API_KEY',proc=tmp_path)
    (root / 'environ').write_bytes(b'HEALTH_EVIDENCE_RUNTIME_ENABLED=unknown\0')
    with pytest.raises(vision.VisionError):
        vision.target_process_value(123,'HEALTH_EVIDENCE_RUNTIME_ENABLED',proc=tmp_path)


def transaction_fixture(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    state,units,model,lease = (tmp_path / n for n in ('state','units','model','lease'))
    state.mkdir(); units.mkdir()
    monkeypatch.setattr(vision,'STATE',state)
    monkeypatch.setattr(vision,'SYSTEMD',units)
    monkeypatch.setattr(vision,'MODEL_ROOT',model)
    monkeypatch.setattr(vision,'MODEL',model / 'model.env')
    monkeypatch.setattr(vision,'LEASE',lease)
    monkeypatch.setattr(vision,'secure_path',lambda *args,**kwargs: {})
    monkeypatch.setattr(vision,'target_process_model',lambda *args,**kwargs: 'qwen3.8-flash')
    monkeypatch.setattr(vision,'protected_metadata',lambda: {'grant':{'ino':1}})
    monkeypatch.setattr(vision,'verify_health',lambda: None)
    before = {name:{'MainPID':'123','process_start':'old','authorization_flags':{},'EnvironmentFiles':'baseline',
                   **{key:'fixed' for key in ('User','Group','WorkingDirectory','NoNewPrivileges','ProtectSystem','ProtectHome','PrivateTmp','CapabilityBoundingSet')}} for name in vision.SERVICES}
    monkeypatch.setattr(vision,'process_start',lambda *args,**kwargs: 'new')
    monkeypatch.setattr(vision,'verify_production_sha',lambda *args: None)
    monkeypatch.setattr(vision,'verify_stability',lambda **kwargs: {'proof':'target-model-only'})
    monkeypatch.setattr(vision,'rollback_time_gate',lambda: None)
    monkeypatch.setattr(vision,'validate_env_sources',lambda *args,**kwargs: None)
    plan = {'publisher_sha':'a'*40,'production_sha':'b'*40,'operation_id':'c'*32,
            'services':before,'protected_metadata':{'grant':{'ino':1}}}
    monkeypatch.setattr(vision,'inspect',lambda *args: plan)
    helper = SimpleNamespace(_lease_identity=lambda *args: ((lease.stat().st_dev,lease.stat().st_ino),
                                                              ((lease/'token').stat().st_dev,(lease/'token').stat().st_ino)))
    written = []
    def write(path,raw):
        path.write_bytes(raw)
        written.append(path.name)
    server = SimpleNamespace(_write_private=write,_sync_business_lease_parent=lambda: None)
    return state,units,model,lease,plan,helper,server,written


def test_configuration_commit_precedes_lease_release(tmp_path,monkeypatch):
    state,units,model,lease,plan,helper,server,written = transaction_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(vision,'service_snapshot',lambda **kwargs: {})
    monkeypatch.setattr(vision,'configuration_readback',lambda p: {'proof':'target-model-only'})
    monkeypatch.setattr(vision,'run',lambda *args,**kwargs: '')
    original = vision.release_own_lease
    def release(*args):
        assert (state/'vision-models'/plan['operation_id']/'completed.json').exists()
        original(*args)
    monkeypatch.setattr(vision,'release_own_lease',release)
    receipt = vision.execute(plan,None,helper,None,server,None)
    assert receipt['state'] == 'CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE'
    assert receipt['model_requests'] == 0
    assert not lease.exists()
    assert (model/'model.env').read_bytes() == vision.model_bytes('qwen3.8-flash')


def test_restart_timeout_retains_lease_and_audit(tmp_path,monkeypatch):
    state,units,model,lease,plan,helper,server,written = transaction_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(vision,'service_snapshot',lambda **kwargs: {})
    def fail_restart(args,**kwargs):
        if 'restart' in args:
            raise vision.VisionError('timeout')
        return ''
    monkeypatch.setattr(vision,'run',fail_restart)
    with pytest.raises(vision.VisionError):
        vision.execute(plan,None,helper,None,server,None)
    audit = state/'vision-models'/plan['operation_id']
    assert lease.exists() and (audit/'failed.json').exists()
    assert not (audit/'completed.json').exists()


def test_partial_apply_has_no_restart_and_keeps_lease(tmp_path,monkeypatch):
    state,units,model,lease,plan,helper,server,written = transaction_fixture(tmp_path,monkeypatch)
    calls = []
    real = vision.atomic_model_write
    def partial(path,raw):
        calls.append(path)
        if len(calls) == 3:
            raise OSError('disk failure')
        real(path,raw)
    monkeypatch.setattr(vision,'atomic_model_write',partial)
    monkeypatch.setattr(vision,'run',lambda *args,**kwargs: pytest.fail('restart must not occur'))
    with pytest.raises(vision.VisionError):
        vision.execute(plan,None,helper,None,server,None)
    assert lease.exists()
    assert (model/'model.env').exists()
    assert (units/(vision.SERVICES[0]+'.service.d')/vision.DROPIN_NAME).exists()
    assert not (units/(vision.SERVICES[1]+'.service.d')/vision.DROPIN_NAME).exists()


def test_partial_rollback_removes_only_operator_files(tmp_path,monkeypatch):
    state,units,model,lease,before,helper,server,written = transaction_fixture(tmp_path,monkeypatch)
    audit = state/'vision-models'/before['operation_id']
    audit.mkdir(parents=True)
    model.mkdir()
    paths = [model/'model.env',*(units/(s+'.service.d')/vision.DROPIN_NAME for s in vision.SERVICES)]
    for path in paths:
        path.parent.mkdir(exist_ok=True)
    paths[0].write_bytes(vision.model_bytes('qwen3.8-flash'))
    paths[1].write_bytes(vision.dropin_bytes())
    unrelated = paths[1].parent/'other.conf'
    unrelated.write_bytes(b'unchanged')
    plan = {'publisher_sha':before['publisher_sha'],'production_sha':before['production_sha'],
            'operation_id':before['operation_id'],'before':before,'lease':None,
            'files':{str(path):vision.optional_model_file(path) for path in paths}}
    monkeypatch.setattr(vision,'inspect_rollback',lambda *args: plan)
    monkeypatch.setattr(vision,'run',lambda *args,**kwargs: '')
    restored = {name:{**values,'MainPID':'456','process_start':'new'} for name,values in before['services'].items()}
    monkeypatch.setattr(vision,'verify_stability',lambda **kwargs: restored)
    monkeypatch.setattr(vision,'run',lambda args,**kwargs: 'EnvironmentFiles=baseline\nUnsetEnvironment=\n' if 'show' in args else '')
    result = vision.rollback(plan,None,helper,None,server,None)
    assert result['state'] == 'CONFIG_ROLLED_BACK'
    assert not lease.exists()
    assert all(not path.exists() for path in paths)
    assert unrelated.read_bytes() == b'unchanged'


def history_fixture(tmp_path,monkeypatch):
    spec = importlib.util.spec_from_file_location('vision_history_test_server',Path(__file__).with_name('trusted_release_server.py'))
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    monkeypatch.setattr(server,'secure_path',lambda *args,**kwargs: None)
    audit = tmp_path/'vision-models'/('a'*32)
    audit.mkdir(parents=True)
    return server,audit


def test_unfinished_history_blocks_even_if_lease_absent(tmp_path,monkeypatch):
    server,audit = history_fixture(tmp_path,monkeypatch)
    with pytest.raises(server.LaunchError):
        server.assert_vision_model_history(tmp_path)
    server.assert_vision_model_history(tmp_path,pending_operation=audit.name)


def test_config_pending_is_honest_terminal_and_rollback_unknown_blocks(tmp_path,monkeypatch):
    import json
    server,audit = history_fixture(tmp_path,monkeypatch)
    receipt = {'state':'CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE','operation_id':audit.name,'model_requests':0,'model_acceptance':'PENDING'}
    (audit/'completed.json').write_text(json.dumps(receipt))
    server.assert_vision_model_history(tmp_path)
    receipt['model_acceptance'] = 'PASSED'
    (audit/'completed.json').write_text(json.dumps(receipt))
    with pytest.raises(server.LaunchError):
        server.assert_vision_model_history(tmp_path)
    receipt['model_acceptance'] = 'PENDING'
    (audit/'completed.json').write_text(json.dumps(receipt))
    (audit/'rollback-intent.json').write_text('{}')
    with pytest.raises(server.LaunchError):
        server.assert_vision_model_history(tmp_path)
    (audit/'rollback-completed.json').write_text(json.dumps({'state':'CONFIG_ROLLED_BACK','operation_id':audit.name,'model_requests':0}))
    server.assert_vision_model_history(tmp_path)


def test_old_model_retirement_and_restart_budget_are_enforced(monkeypatch):
    import datetime
    assert datetime.datetime.fromtimestamp(vision.OLD_MODEL_RETIREMENT_UTC,datetime.timezone.utc).isoformat() == '2026-10-09T16:00:00+00:00'
    monkeypatch.setattr(vision.time,'time',lambda: vision.OLD_MODEL_RETIREMENT_UTC-vision.ROLLBACK_TIME_BUDGET-1)
    vision.rollback_time_gate()
    for now in (vision.OLD_MODEL_RETIREMENT_UTC-vision.ROLLBACK_TIME_BUDGET,vision.OLD_MODEL_RETIREMENT_UTC+1):
        monkeypatch.setattr(vision.time,'time',lambda: now)
        with pytest.raises(vision.VisionError):
            vision.rollback_time_gate()


def test_stability_window_detects_restart_count_change(monkeypatch):
    values = iter([{'MainPID':'123','NRestarts':'0'},{'MainPID':'123','NRestarts':'1'}])
    monkeypatch.setattr(vision,'service_snapshot',lambda **kwargs: next(values))
    monkeypatch.setattr(vision.time,'sleep',lambda *args: None)
    monkeypatch.setattr(vision,'verify_health',lambda: None)
    with pytest.raises(vision.VisionError):
        vision.verify_stability(installed=True)


def test_health_body_requires_all_dependencies_healthy():
    import json
    response = {'status':'healthy','services':{'api':'running','database':'connected','redis':'connected','celery':'connected'}}
    assert vision.health_response_healthy(json.dumps(response).encode())
    response['services']['celery'] = 'no_workers'
    assert not vision.health_response_healthy(json.dumps(response).encode())
    assert not vision.health_response_healthy(b'{"status":"healthy","status":"healthy"}')
    assert not vision.health_response_healthy(b'x'*4097)


def test_redirects_refused_before_external_request():
    with pytest.raises(vision.VisionError):
        vision.NoRedirect().redirect_request(None,None,None,None,None,None)


def test_missing_enabled_file_snapshot_stays_absent(tmp_path,monkeypatch):
    production = tmp_path/'production'
    production.mkdir()
    monkeypatch.setattr(vision,'PRODUCTION',production)
    monkeypatch.setattr(vision,'secure_path',lambda *args,**kwargs: {'dev':1,'ino':1,'mode':0,'uid':0,'gid':0})
    result = vision.protected_metadata()
    assert result[str(production/'backend/.env')]['absent'] is True
    assert not (production/'backend/.env').exists()


def test_durable_finalizer_never_restarts_or_installs(tmp_path,monkeypatch):
    state,units,model,lease,before,helper,server,written = transaction_fixture(tmp_path,monkeypatch)
    audit = state/'vision-models'/before['operation_id']
    audit.mkdir(parents=True)
    lease.mkdir()
    for name,value in {'token':'a'*64,'stage':str(audit),'label':'vision-model-selection','started_at':'1'}.items():
        (lease/name).write_text(value+'\n')
    identity = helper._lease_identity(None,None,None,None)
    verified = {'state':'CONFIG_ROLLED_BACK','operation_id':before['operation_id'],'model_requests':0}
    plan = {'publisher_sha':before['publisher_sha'],'production_sha':before['production_sha'],
            'operation_id':before['operation_id'],'rolled_back':True,'lease_identity':identity,'verified':verified}
    monkeypatch.setattr(vision,'inspect_finalization',lambda *args,**kwargs: plan)
    monkeypatch.setattr(vision,'run',lambda *args,**kwargs: pytest.fail('must not replay any service command'))
    monkeypatch.setattr(vision,'atomic_model_write',lambda *args: pytest.fail('must not install files'))
    result = vision.finalize(plan,None,helper,None,server,None)
    assert result['state'] == 'CONFIG_LEASE_FINALIZED'
    assert not lease.exists()
    assert (audit/'rollback-completed.json').exists()
    assert (audit/'rollback-finalized.json').exists()


def test_finalization_checks_own_files_and_rollback_absence(tmp_path,monkeypatch):
    model = tmp_path/'model.env'
    units = tmp_path/'units'
    units.mkdir()
    monkeypatch.setattr(vision,'MODEL',model)
    monkeypatch.setattr(vision,'SYSTEMD',units)
    monkeypatch.setattr(vision,'secure_path',lambda *args,**kwargs: None)
    paths = [model,*(units/(service+'.service.d')/vision.DROPIN_NAME for service in vision.SERVICES)]
    for path in paths:
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(vision.model_bytes('qwen3.8-flash') if path == model else vision.dropin_bytes())
    vision.finalization_model_files(rolled_back=False)
    with pytest.raises(vision.VisionError):
        vision.finalization_model_files(rolled_back=True)
    model.write_bytes(b'LLM_VISION_MODEL=qwen-vl-max\n')
    with pytest.raises(vision.VisionError):
        vision.finalization_model_files(rolled_back=False)
    for path in paths:
        path.unlink()
    vision.finalization_model_files(rolled_back=True)


@pytest.mark.parametrize('state,rollback_pending,expected',[
    (None,False,1),
    ('CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE',False,0),
    ('CONFIG_SUCCEEDED_PENDING_MODEL_ACCEPTANCE',True,1),
    ('UNKNOWN',False,1),
])
def test_bound_history_mode_no_lease_or_model_access(tmp_path,monkeypatch,state,rollback_pending,expected):
    import json
    from types import SimpleNamespace
    server,audit = history_fixture(tmp_path,monkeypatch)
    if state:
        (audit/'completed.json').write_text(json.dumps({'state':state,'operation_id':audit.name,'model_requests':0,'model_acceptance':'PENDING'}))
    if rollback_pending:
        (audit/'rollback-intent.json').write_text('{}')
    gate_calls = []
    history_server = SimpleNamespace(assert_vision_model_history=lambda: server.assert_vision_model_history(tmp_path))
    gate = SimpleNamespace(verify_release=lambda *args: gate_calls.append(args))
    monkeypatch.setattr(vision,'load_reviewed',lambda *args: (None,None,None,history_server,gate))
    monkeypatch.setattr(vision.os,'geteuid',lambda: 0)
    monkeypatch.setattr(vision.sys,'executable','/usr/bin/python3.12')
    monkeypatch.setattr(vision.sys,'flags',SimpleNamespace(isolated=True,no_site=True,dont_write_bytecode=True))
    monkeypatch.setattr(vision,'protected_metadata',lambda: pytest.fail('history cannot inspect env/grants'))
    monkeypatch.setattr(vision,'service_snapshot',lambda **kwargs: pytest.fail('history cannot inspect model/process'))
    assert vision.history_main(['--publisher-sha','b'*40]) == expected
    assert gate_calls == [('b'*40,'b'*40)]


def test_generic_history_function_uses_fixed_remote_staging_and_full_sha(tmp_path):
    import os
    import subprocess
    script = Path(__file__).parents[1].joinpath('deploy.sh').read_text()
    body = script[script.index('check_remote_vision_model_history() {'):script.index('acquire_remote_release_lock() {')]
    # Fake SSH inspects the actual generated Python/argv, no host/model call.
    fake = tmp_path/'bin'
    fake.mkdir()
    log = tmp_path/'remote-source'
    ssh = fake/'ssh'
    ssh.write_text('#!/bin/sh\nset -eu\ntest "$1" = health\ntest "$2" = /usr/bin/python3.12\ntest "$3" = -I\ntest "$4" = -S\ntest "$5" = -B\ntest "$6" = -\ntest "$7" = '+ 'a'*40 +'\ncat > "$VISION_FAKE_LOG"\nexit "${VISION_FAKE_STATUS:-0}"\n')
    ssh.chmod(0o700)
    git = fake/'git'
    git.write_text('#!/bin/sh\nprintf "%s\\n" '+ 'a'*40 +'\n')
    git.chmod(0o700)
    command = 'print_error() { :; }; '+body+'\ncheck_remote_vision_model_history\n'
    env = {**os.environ,'PATH':str(fake)+':'+os.environ['PATH'],'SERVER':'health','SCRIPT_DIR':str(tmp_path),'VISION_FAKE_LOG':str(log)}
    result = subprocess.run(['/bin/bash','-e','-c',command],env=env,capture_output=True,text=True)
    assert result.returncode == 0
    transmitted = log.read_text()
    assert '/var/lib/reva-release/bootstrap' in transmitted
    assert 'sha+":scripts/trusted_vision_model.py"' in transmitted
    assert 'os.execve' in transmitted and '--check-history' in transmitted
    assert '/opt/health-app' not in transmitted
    for status in ('1','70'):
        result = subprocess.run(['/bin/bash','-e','-c',command],env={**env,'VISION_FAKE_STATUS':status},capture_output=True,text=True)
        assert result.returncode != 0
    for sha in ('main','$(id)','A'*40,'b'*40):
        log.unlink(missing_ok=True)
        result = subprocess.run(['/bin/bash','-e','-c',command],env={**env,'DEPLOY_SOURCE_SHA':sha},capture_output=True,text=True)
        assert result.returncode != 0
        assert not log.exists()
