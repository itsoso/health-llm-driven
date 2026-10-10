from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_monitor_ingress_persistent_rule_precedes_established_and_preserves_bytes():
    import pytest
    m = load('monitor_ingress_repair')
    for chain in ('ufw-before-input', 'ufw6-before-input'):
        raw = f'*filter\n:{chain} - [0:0]\n-A {chain} -i lo -j ACCEPT\n-A {chain} -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT\nCOMMIT\n'
        updated = m.config_after(raw, chain)
        assert updated.replace(m.rule_line(chain)+'\n', '', 1) == raw
        assert updated.index(m.rule_line(chain)) < updated.index(f'-A {chain} -i lo')
        assert '! -i lo' in updated and '--dports 9090,9100' in updated
        with pytest.raises(RuntimeError):
            m.config_after(updated, chain)
        with pytest.raises(RuntimeError):
            m.config_after(raw.replace('*filter', '*nat'), chain)
        for invalid in (f'-A {chain} -j ACCEPT\n'+raw,raw+f'-A {chain} -j ACCEPT\n',raw.replace('\n','\r\n')):
            with pytest.raises(RuntimeError):m.config_after(invalid,chain)


def test_monitor_ingress_firewall_delta_rejects_noop_wrong_order_and_other_changes():
    import pytest
    m = load('monitor_ingress_repair')
    chain = 'ufw-before-input'
    before = ['*filter', ':'+chain+' - [COUNTERS]', '-A '+chain+' -i lo -j ACCEPT', 'COMMIT']
    expected = m.policy_after(before, chain)
    assert expected[2] == m.rule_line(chain)
    assert m.verify_delta(before, expected, chain) is None
    for after in (before, [*before[:-1],m.rule_line(chain),'COMMIT'], expected+['unknown']):
        with pytest.raises(RuntimeError):m.verify_delta(before, after, chain)


def test_monitor_ingress_input_path_rejects_earlier_accept_or_logging_jump():
    import pytest
    m = load('monitor_ingress_repair')
    good=['-P INPUT DROP','-A INPUT -j ufw-before-logging-input','-A INPUT -j ufw-before-input']
    m.verify_reachability(good,['-N ufw-before-logging-input'],'ufw-before-input')
    for rows,logging in ((['-A INPUT -j ACCEPT',*good],['-N ufw-before-logging-input']),
                         (good,['-N ufw-before-logging-input','-A ufw-before-logging-input -j ACCEPT'])):
        with pytest.raises(RuntimeError):m.verify_reachability(rows,logging,'ufw-before-input')


def monitor_intent(m):
    import hashlib
    value={'production_sha':m.PRODUCTION,'publisher_sha':'a'*40,
           'host_history':{'kind':'recovered-host-hardening','intent_sha256':'b'*64,'completion_sha256':'c'*64},
           'services':{},'families':{}}
    for name in m.SERVICES:
        value['services'][name]={'properties':{'MainPID':'42','ActiveState':'active','NRestarts':'0','NeedDaemonReload':'no'},
            'process':{'pid':42,'starttime':'123','uid':['997' if name.startswith(('health','celery')) else '0']*4,
                       'cgroup':'/test.service','argv_sha256':'d'*64}}
    for binary,chain,_ in m.FAMILIES:
        raw=f'*filter\n:{chain} - [0:0]\n-A {chain} -i lo -j ACCEPT\nCOMMIT\n'
        value['families'][binary]={'policy':['*filter',':INPUT DROP [COUNTERS]',f':{chain} - [COUNTERS]',f'-A {chain} -i lo -j ACCEPT','COMMIT'],
            'config':{'text':raw,'mode':0o644,'uid':0,'gid':0,'sha256':hashlib.sha256(raw.encode()).hexdigest()}}
    return value


def test_monitor_ingress_history_requires_inner_evidence(tmp_path,monkeypatch):
    import copy
    import pytest
    m=load('monitor_ingress_repair');value=monitor_intent(m);m.validate_intent(value)
    for mutate in (lambda v:v.update(services={}),
                   lambda v:v['services']['eth1']['process'].update(uid=['997']*4),
                   lambda v:v['services']['health-backend']['process'].update(uid=['0']*4),
                   lambda v:v['families']['/usr/sbin/iptables']['config'].update(sha256='e'*64),
                   lambda v:v['families']['/usr/sbin/iptables']['config'].update(mode=0o666)):
        bad=copy.deepcopy(value);mutate(bad)
        with pytest.raises(RuntimeError):m.validate_intent(bad)


def test_monitor_ingress_digest_and_partial_failure_keep_intent_and_lease(tmp_path,monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace
    import pytest
    m=load('monitor_ingress_repair');lease=tmp_path/'business';monkeypatch.setattr(m,'LEASE',lease)
    before=monitor_intent(m);events=[]
    def write(path,raw):path.write_bytes(raw)
    server=SimpleNamespace(secure_path=lambda *a,**k:None,_sync_directory=lambda *a:None,_write_private=write,
                           _testflight_lease_parent=lambda:None,_sync_business_lease_parent=lambda:None)
    digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def apply(value):
        assert (a.record/'intent.json').is_file() and (lease/'token').is_file()
        events.append('ipv4-applied');raise RuntimeError('synthetic IPv6 mutation failure')
    a=SimpleNamespace(record=tmp_path/'records'/'fixed',publisher='a'*40,server=server,r=SimpleNamespace(digest=digest),
                      check=lambda:events.append('lock-checked'),inspect=lambda:before,apply=apply,verify=lambda _:None)
    monkeypatch.setattr(m,'lease_snapshot',lambda *_:{'.':{'dev':1,'ino':2}})
    assert m.transaction(a)['state']=='MONITOR_INGRESS_PREFLIGHT'
    assert not a.record.exists() and not lease.exists()
    with pytest.raises(RuntimeError,match='preflight evidence'):m.transaction(a,'f'*64)
    assert not a.record.exists() and not lease.exists()
    with pytest.raises(RuntimeError,match='IPv6'):m.transaction(a,digest(before))
    assert (a.record/'intent.json').is_file() and lease.exists()
    assert not (a.record/'completed.json').exists()
    with pytest.raises(RuntimeError,match='no retry'):m.transaction(a,digest(before))
    assert events.count('ipv4-applied')==1 and events.count('lock-checked')>=4


def test_monitor_ingress_apply_rejects_exit_zero_without_rule(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import pytest
    m=load('monitor_ingress_repair');before=monitor_intent(m)
    monkeypatch.setattr(m,'config_snapshot',lambda path,b:before['families'][next(x[0] for x in m.FAMILIES if x[2]==path)]['config'])
    g=SimpleNamespace(atomic_write=lambda *a:None,run=lambda *a:before['families']['/usr/sbin/iptables']['policy'])
    a=SimpleNamespace(g=g,b=None,r=SimpleNamespace(firewall_policy=lambda x:x),check=lambda:None)
    with pytest.raises(RuntimeError,match='firewall delta'):m.Adapter.apply(a,before)


def test_monitor_ingress_success_consumes_immutable_history(tmp_path,monkeypatch):
    import hashlib
    import json
    import stat
    from types import SimpleNamespace
    import pytest
    m=load('monitor_ingress_repair');before=monitor_intent(m);events=[]
    monkeypatch.setattr(m,'STATE',tmp_path/'state');monkeypatch.setattr(m,'LEASE',tmp_path/'active')
    monkeypatch.setattr(m,'RETIRED_PARENT',tmp_path);monkeypatch.setattr(m.time,'sleep',lambda _:None)
    monkeypatch.setattr(m,'source_scope',lambda *a:None)
    def write(path,raw):path.write_bytes(raw);path.chmod(0o600)
    def inventory(path,names):
        assert set(p.name for p in path.iterdir())==set(names)
        assert stat.S_IMODE(path.stat().st_mode)==0o700
        assert all(stat.S_IMODE(p.stat().st_mode)==0o600 for p in path.iterdir())
    server=SimpleNamespace(secure_path=lambda *a,**k:None,_sync_directory=lambda *a:None,_write_private=write,
                           _testflight_lease_parent=lambda:None,_sync_business_lease_parent=lambda:None)
    digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def lease_snapshot(*args):
        return {'.' if p==m.LEASE else p.name:{'dev':p.stat().st_dev,'ino':p.stat().st_ino,'uid':0,'gid':0,
            'mode':0o700 if p==m.LEASE else 0o600,'sha256':None if p==m.LEASE else hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in [m.LEASE,*m.LEASE.iterdir()]}
    monkeypatch.setattr(m,'lease_snapshot',lease_snapshot)
    real_run=m.subprocess.run
    def move(args,**kwargs):
        assert args[:4]==['/usr/bin/mv','--no-clobber','-T','--']
        Path(args[4]).rename(args[5])
    monkeypatch.setattr(m.subprocess,'run',move)
    a=SimpleNamespace(record=m.STATE/'monitor-ingress-repairs'/m.PRODUCTION,publisher='a'*40,server=server,r=SimpleNamespace(digest=digest),
        check=lambda:events.append('check'),inspect=lambda:before,apply=lambda _:events.append('apply'),verify=lambda _:events.append('verify'))
    a.record.parent.parent.mkdir()
    done=m.transaction(a,digest(before))
    assert done['state']=='MONITOR_INGRESS_LOCAL_VERIFIED' and events.count('apply')==1 and events.count('verify')==2
    assert not m.LEASE.exists()
    b=SimpleNamespace(secure=lambda *a,**k:None,_inventory=inventory,_read_json=lambda p:json.loads(p.read_text()),canonical_source=lambda _:tmp_path)
    proof=m.history_evidence(b,before['host_history'])
    assert proof['intent_sha256']==digest(before) and proof['completion_sha256']==digest(done)
    identity=json.loads((a.record/'lease.json').read_text());identity['token']['mode']=0o644
    done['lease_sha256']=digest(identity)
    write(a.record/'lease.json',json.dumps(identity).encode());write(a.record/'completed.json',json.dumps(done).encode())
    with pytest.raises(RuntimeError,match='lease inner evidence'):m.history_evidence(b,before['host_history'])


def test_application_units_hide_staking_data_and_bound_resources():
    for name in ("health-backend", "celery-worker", "celery-beat"):
        for path in (ROOT / "infra/systemd" / f"{name}.service",
                     ROOT / "infra/systemd/dropins" / f"{name}-runtime-state.conf"):
            body = path.read_text()
            assert "InaccessiblePaths=-/mnt -/opt/eth-ops" in body
            assert "MemoryMax=" in body
            assert "CPUQuota=" in body
            assert "IPAddressDeny=100.64.0.0/10 169.254.0.0/16" in body
            assert "CapabilityBoundingSet=\n" in body


def load(name):
    import importlib.util
    import sys
    path = ROOT / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location('tested_' + name, path)
    result = importlib.util.module_from_spec(spec)
    # Match Python's import protocol, including helpers that consult their own
    # module object. Do not rely on a stale __pycache__ masking this branch.
    sys.modules[spec.name] = result
    spec.loader.exec_module(result)
    return result


def test_canonical_rule_comparison_preserves_reply_direction_and_chain_order():
    m = load('harden_public_host')
    _, rules, _ = m.firewall_rules('health-app', 997)
    canonical = m.canonical_rule
    assert canonical(rules[0]) == canonical(('-m','conntrack','--ctstate','RELATED,ESTABLISHED','--ctdir','REPLY','-j','RETURN'))
    assert canonical(rules[0]) != canonical(('-m','conntrack','--ctstate','RELATED,ESTABLISHED','--ctdir','ORIGINAL','-j','RETURN'))
    assert canonical(rules[2]) == canonical(('-p','udp','-m','addrtype','--dst-type','LOCAL','-m','udp','--dport','53','-j','RETURN'))


def test_backup_reads_every_file_and_records_absence(tmp_path, monkeypatch):
    import hashlib
    import json
    m = load('harden_public_host')
    monkeypatch.setattr(m, 'trusted', lambda *args, **kwargs: None)
    source = tmp_path / 'old.service'
    source.write_text('synthetic previous configuration')
    missing = tmp_path / 'absent.service'
    receipt = tmp_path / 'receipt'
    receipt.mkdir()
    m.backup_configuration(receipt, [source, missing])
    manifest = json.loads((receipt / 'config-manifest.json').read_text())
    assert manifest[0]['sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest[1] == {'path': str(missing), 'exists': False}
    assert (receipt / 'config-before.tar.gz').stat().st_mode & 0o777 == 0o600


def test_host_operator_rejects_noncanonical_entry_before_loading_code():
    import pytest
    m = load('trusted_public_host')
    with pytest.raises(RuntimeError, match='canonical operator staging'):
        m.load_reviewed('a' * 40)


def test_hardening_requires_exact_backend_success():
    import pytest
    m = load('trusted_public_host')
    m.require_backend_receipt('a' * 40, {'sha': 'a' * 40, 'state': 'SUCCEEDED'})
    for receipt in ({'sha': 'b' * 40, 'state': 'SUCCEEDED'}, {'sha': 'a' * 40, 'state': 'STARTED'}, {}):
        with pytest.raises(RuntimeError):
            m.require_backend_receipt('a' * 40, receipt)


def test_host_entry_precedes_any_environment_or_shell_helper():
    body = (ROOT / 'deploy.sh').read_text()
    assert body.index('--security-hardening') < body.index('ENV_FILE=') < body.index('source "$SCRIPT_DIR/scripts/release_lock.sh"')
    assert '/usr/bin/python3.12 -I -S -B "$SCRIPT_DIR/scripts/trusted_public_host.py"' in body


def test_frontend_unknown_state_cannot_choose_legacy_root_branch(tmp_path):
    import subprocess
    body = (ROOT / 'deploy.sh').read_text()
    start = body.index('frontend_runtime_kind() {')
    end = body.index('# 推送代码到 GitHub', start)
    functions = body[start:end]
    for response, status, expected in [('hardened',0,'systemctl restart'),('legacy',0,'pm2 restart'),('',255,None),('garbage',0,None)]:
        script = functions + '''
print_step() { :; }
print_error() { :; }
print_success() { :; }
assert_remote_release_lock_if_acquired() { :; }
SERVER=fixture
frontend_runtime_kind() { printf '%s' "$RESPONSE"; return "$STATUS"; }
ssh() { printf '%s\\n' "$*" >> "$RECORD"; }
restart_frontend_service
'''
        record = tmp_path / ('record' + str(status) + response)
        result = subprocess.run(['bash','-c',script], env={'PATH':'/usr/bin:/bin','RESPONSE':response,'STATUS':str(status),'RECORD':str(record)}, capture_output=True)
        if expected:
            assert result.returncode == 0
            assert expected in record.read_text()
        else:
            assert result.returncode != 0
            assert not record.exists()


def test_release_candidate_cannot_reenable_public_registration():
    m = load('trusted_release_server')
    result = m.invitation_only_config('AUTH_PHONE_SELF_REGISTRATION_ENABLED=true\n export REGISTRATION_INVITATION_ENFORCEMENT_ENABLED=false\nUNCHANGED=value\n')
    assert result.count('AUTH_PHONE_SELF_REGISTRATION_ENABLED=') == 1
    assert 'AUTH_PHONE_SELF_REGISTRATION_ENABLED=false\n' in result
    assert 'REGISTRATION_INVITATION_ENFORCEMENT_ENABLED=true\n' in result
    assert 'UNCHANGED=value\n' in result


def test_cached_helper_is_rejected_before_top_level_execution(tmp_path, monkeypatch):
    import pytest
    m = load('trusted_public_host')
    monkeypatch.setattr(m, 'secure', lambda path: None)
    path = tmp_path / 'helper.py'
    path.write_text('raise AssertionError("must not execute")')
    (tmp_path / '__pycache__').mkdir()
    with pytest.raises(RuntimeError, match='cached code forbidden'):
        m.module(path, 'dangerous_cached_helper')


def test_completed_host_audit_is_retireable_but_unknown_attempt_is_not(tmp_path, monkeypatch):
    import json
    import pytest
    import sys
    m = load('bootstrap_trusted_release')
    monkeypatch.setattr(m, 'STATE', tmp_path)
    monkeypatch.setattr(m, 'secure', lambda *args, **kwargs: None)
    # Exercise the failure-history branch, not an unrelated source-cache guard.
    source = tmp_path / 'source'
    source.mkdir()
    for name in ('bootstrap_trusted_release.py', 'public_host_recovery.py'):
        (source / name).write_bytes((ROOT / 'scripts' / name).read_bytes())
    monkeypatch.setattr(m, '__file__', str(source / 'bootstrap_trusted_release.py'))
    monkeypatch.setattr(sys, 'dont_write_bytecode', True)
    sha = 'a' * 40
    root = tmp_path / sha / 'host-hardening'
    root.mkdir(parents=True, mode=0o700)
    records = {'frontend.json': {'operation_id': 'b' * 32, 'frontend_tree': 'c' * 40, 'artifact_digest': 'd' * 64}, 'started.json': {'sha': sha, 'state': 'STARTED'},
               'verified.json': {'sha': sha, 'state': 'LOCAL_VERIFIED'},
               'completed.json': {'sha': sha, 'state': 'LOCAL_VERIFIED', 'external_readback_required': True}}
    for name, value in records.items():
        (root / name).write_text(json.dumps(value))
    assert set(m._host_hardening_evidence(sha)) == set(records) | {"."}
    (root / 'completed.json').unlink()
    with pytest.raises(m.BootstrapError):
        m._host_hardening_evidence(sha)
    (root / 'completed.json').write_text(json.dumps(records['completed.json']))
    (root / 'failed.json').write_text('{}')
    with pytest.raises(Exception, match='unknown host recovery history') as failure:
        m._host_hardening_evidence(sha)
    assert type(failure.value) is sys.modules['host_recovery_history'].RecoveryError


def test_final_frontend_receipt_requires_live_digest_and_unique_attempt(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    import pytest
    m = load('trusted_public_host')
    monkeypatch.setattr(m, 'STATE', tmp_path)
    sha = 'a' * 40
    tree = 'b' * 40
    op = 'c' * 32
    operation = tmp_path / 'frontend-rebuilds' / op
    operation.mkdir(parents=True)
    frontend = load('trusted_frontend_rebuild')
    frontend.PRODUCTION = tmp_path / 'production'
    monkeypatch.setattr(frontend, 'git', lambda *args: tree)
    monkeypatch.setattr(frontend, 'artifact_digest', lambda *args: 'd' * 64)
    monkeypatch.setattr(m, 'module', lambda *args: frontend)
    digest = hashlib.sha256(('d' * 128).encode()).hexdigest()
    receipts = {name: frontend.receipt(sha, sha, op, tree, state, digest) for name, state in (
        ('completed.json','FRONTEND_SUCCEEDED'),('verified.json','FRONTEND_VERIFIED'),('install-started.json','FRONTEND_INSTALLING'))}
    bootstrap = SimpleNamespace(_read_json=lambda path: receipts[path.name])
    checked = []
    server = SimpleNamespace(secure_path=lambda *args, **kwargs: None,
                             assert_frontend_rebuild_history=lambda *args: checked.append(True))
    assert m.verify_frontend_artifacts(sha, tmp_path, bootstrap, server)['artifact_digest'] == digest
    assert checked
    old = operation.parent / ('9' * 32)
    old.mkdir()
    (old / 'failed.json').write_text('{}')
    # Only the mocked whole-history gate accepts this synthetic old closure.
    assert m.verify_frontend_artifacts(sha, tmp_path, bootstrap, server)['artifact_digest'] == digest
    def reject_unknown_history(*args):
        raise RuntimeError('unfinished historical attempt')
    original_history = server.assert_frontend_rebuild_history
    server.assert_frontend_rebuild_history = reject_unknown_history
    with pytest.raises(RuntimeError, match='unfinished historical'):
        m.verify_frontend_artifacts(sha, tmp_path, bootstrap, server)
    server.assert_frontend_rebuild_history = original_history
    monkeypatch.setattr(frontend, 'artifact_digest', lambda *args: 'e' * 64)
    with pytest.raises(RuntimeError, match='artifacts differ'):
        m.verify_frontend_artifacts(sha, tmp_path, bootstrap, server)
    monkeypatch.setattr(frontend, 'artifact_digest', lambda *args: 'd' * 64)
    (operation.parent / ('f' * 32)).mkdir()
    with pytest.raises(RuntimeError, match='exactly one'):
        m.verify_frontend_artifacts(sha, tmp_path, bootstrap, server)


def test_unfinished_ota_without_business_lease_blocks_host_mutations(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import pytest
    m = load('trusted_public_host')
    monkeypatch.setattr(m, 'STATE', tmp_path)
    monkeypatch.setattr(m, 'LEASE', tmp_path / 'absent-business-lease')
    (tmp_path / 'launcher.lock').write_bytes(b'')
    calls = []
    helper = SimpleNamespace(_assert_lock=lambda *args: None,
                             _revision_proof=lambda *args: calls.append('revision'))
    def reject_pending_ota():
        raise RuntimeError('unfinished OTA intent')
    server = SimpleNamespace(secure_path=lambda *args, **kwargs: None,
                             assert_ota_history=reject_pending_ota)
    gate = SimpleNamespace(verify_release=lambda *args: None)
    monkeypatch.setattr(m, 'load_reviewed', lambda sha: (tmp_path, helper, None, server, gate, None))
    with pytest.raises(RuntimeError, match='unfinished OTA'):
        m.execute('a' * 40)
    assert calls == []
    assert not m.LEASE.exists()
    assert not (tmp_path / ('a' * 40)).exists()


def test_host_transaction_syncs_real_lease_parent_without_relaxing_nofollow(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import pytest

    m = load('trusted_public_host')
    strict_server = load('trusted_release_server')
    state = tmp_path / 'state'
    sha = 'a' * 40
    (state / sha).mkdir(parents=True)
    (state / 'launcher.lock').write_bytes(b'')
    real_parent = tmp_path / 'run-lock'
    real_parent.mkdir()
    alias = tmp_path / 'var-lock'
    alias.symlink_to(real_parent, target_is_directory=True)
    lease = alias / 'health-app-release'
    monkeypatch.setattr(m, 'STATE', state)
    monkeypatch.setattr(m, 'LEASE', lease)
    # Exercise the actual OS behavior that stopped the production transaction.
    with pytest.raises(OSError):
        strict_server._sync_directory(alias)

    events = []

    def sync_business_parent():
        assert alias.is_symlink() and alias.resolve(strict=True) == real_parent
        strict_server._sync_directory(real_parent)
        events.append(('sync', lease.exists()))

    helper = SimpleNamespace(
        _assert_lock=lambda *args: None,
        _revision_proof=lambda *args: None,
        _lease_identity=lambda *args: 'synthetic-lease-identity',
    )
    server = SimpleNamespace(
        secure_path=lambda *args, **kwargs: None,
        assert_ota_history=lambda: None,
        _write_private=strict_server._write_private,
        _sync_directory=strict_server._sync_directory,
        _sync_business_lease_parent=sync_business_parent,
    )
    bootstrap = SimpleNamespace(_read_json=lambda path: {'sha': sha, 'state': 'SUCCEEDED'})
    gate = SimpleNamespace(verify_release=lambda *args: None)
    guard = SimpleNamespace(apply=lambda value: events.append(('apply', value)), preflight_commands=lambda: None)
    monkeypatch.setattr(m, 'load_reviewed', lambda value: (tmp_path, helper, bootstrap, server, gate, guard))
    monkeypatch.setattr(m, 'verify_runtime', lambda *args, **kwargs: None)
    monkeypatch.setattr(m, 'verify_frontend_artifacts', lambda *args: {'synthetic': 'proof'})

    assert m.execute(sha) == {'sha': sha, 'state': 'LOCAL_VERIFIED', 'external_readback_required': True}
    assert events == [('sync', True), ('apply', sha), ('sync', False)]
    assert not lease.exists()
    audit = state / sha / 'host-hardening'
    assert json.loads((audit / 'completed.json').read_text())['state'] == 'LOCAL_VERIFIED'
    assert not (audit / 'failed.json').exists()


def test_host_privileged_commands_use_fixed_paths_with_constrained_environment(monkeypatch):
    from types import SimpleNamespace
    m = load('harden_public_host')
    calls = []
    monkeypatch.setattr(m.subprocess, 'run', lambda args, **kwargs: (calls.append(args) or SimpleNamespace(returncode=0, stdout='')))
    m.run('useradd', '--system', 'health-web')
    m.run('ufw', 'status')
    assert calls == [('/usr/sbin/useradd', '--system', 'health-web'), ('/usr/sbin/ufw', 'status')]


def test_host_command_preflight_precedes_any_audit_or_lease():
    import inspect
    m = load('trusted_public_host')
    body = inspect.getsource(m.execute)
    assert body.index('guard.preflight_commands()') < body.index('audit.mkdir') < body.index('LEASE.mkdir')


def test_host_recovery_firewall_normalization_preserves_security_semantics():
    import pytest
    m = load('public_host_recovery')
    before = '# Generated by iptables-save v1.8.7 on Tue Sep 30\n*filter\n:OUTPUT ACCEPT [1:2]\n-A OUTPUT -j safe\nCOMMIT\n# Completed on Tue Sep 30\n'
    after = before.replace('[1:2]', '[33:44]').replace('Tue Sep 30', 'Wed Oct 1')
    assert m.firewall_policy(before) == m.firewall_policy(after)
    assert m.firewall_policy(before) != m.firewall_policy(after.replace('ACCEPT', 'DROP'))
    assert m.firewall_policy(before) != m.firewall_policy(after.replace('-j safe', '-j ACCEPT'))
    with pytest.raises(m.RecoveryError):
        m.firewall_policy(before + '# unknown unreviewed comment\n')


def test_host_recovery_source_scope_rejects_business_or_network_drift(tmp_path):
    import subprocess
    import pytest
    m = load('public_host_recovery')
    old, new = tmp_path/'old', tmp_path/'new'
    for path in (old,new):
        (path/'scripts').mkdir(parents=True)
        (path/'scripts/harden_public_host.py').write_text('APPLICATION_PORTS = {"health-app": (8000,)}\ndef firewall_rules(): return 1\ndef canonical_rule(): return 2\ndef network_guard(): return 3\n')
        subprocess.run(['git','init',str(path)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(path),'add','scripts/harden_public_host.py'],check=True)
        subprocess.run(['git','-C',str(path),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=/dev/null','commit','-m','fixture'],check=True,capture_output=True)
    (new/'scripts/public_host_recovery.py').write_text('# fixture\n')
    subprocess.run(['git','-C',str(new),'add','scripts/public_host_recovery.py'],check=True)
    subprocess.run(['git','-C',str(new),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=/dev/null','commit','-m','recovery'],check=True,capture_output=True)
    assert m.source_scope(new,old,None) == ['scripts/public_host_recovery.py']
    (new/'scripts/harden_public_host.py').write_text('APPLICATION_PORTS = {"health-app": (8000,)}\ndef firewall_rules(): return 9\ndef canonical_rule(): return 2\ndef network_guard(): return 3\n')
    with pytest.raises(m.RecoveryError,match='persistent network policy'):
        m.source_scope(new,old,None)
    (new/'scripts/harden_public_host.py').write_text((old/'scripts/harden_public_host.py').read_text().replace('8000','8001'))
    with pytest.raises(m.RecoveryError,match='network policy constant'):
        m.source_scope(new,old,None)
    (new/'business.py').write_text('changed')
    subprocess.run(['git','-C',str(new),'add','business.py'],check=True)
    subprocess.run(['git','-C',str(new),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','-c','core.hooksPath=/dev/null','commit','-m','business'],check=True,capture_output=True)
    with pytest.raises(m.RecoveryError,match='fixed scope'):
        m.source_scope(new,old,None)


def test_host_recovery_backup_detects_live_archive_and_absence_drift(tmp_path,monkeypatch):
    import json
    from types import SimpleNamespace
    import pytest
    m=load('public_host_recovery');g=load('harden_public_host')
    present=tmp_path/'present';absent=tmp_path/'absent';present.write_text('configuration')
    paths=[present,absent];backup=tmp_path/'backup';backup.mkdir()
    monkeypatch.setattr(g,'trusted',lambda *a,**kw:None)
    g.backup_configuration(backup,paths)
    monkeypatch.setattr(m,'write_set',lambda:paths)
    # Test archive identity with real local ownership; fixture does not assert root.
    real_open=m.tarfile.open
    class Archive:
        def __init__(self,*a,**kw):self.inner=real_open(*a,**kw)
        def __enter__(self):return self
        def __exit__(self,*a):self.inner.close()
        def getmembers(self):return self.inner.getmembers()
        def getmember(self,name):
            member=self.inner.getmember(name);member.uid=0;member.gid=0;return member
        def extractfile(self,member):return self.inner.extractfile(member)
    monkeypatch.setattr(m.tarfile,'open',Archive)
    real_lstat=Path.lstat
    def lstat(path,*a,**kw):
        result=real_lstat(path,*a,**kw)
        if path==present:return SimpleNamespace(st_uid=0,st_gid=0,st_mode=result.st_mode)
        return result
    monkeypatch.setattr(Path,'lstat',lstat)
    assert m.verify_backup(backup,g)
    present.write_text('changed')
    with pytest.raises(m.RecoveryError,match='changed'):m.verify_backup(backup,g)
    present.write_text('configuration');absent.write_text('appeared')
    with pytest.raises(m.RecoveryError,match='absent'):m.verify_backup(backup,g)
    absent.unlink()
    manifest=json.loads((backup/'config-manifest.json').read_text());manifest.append(manifest[0]);(backup/'config-manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(m.RecoveryError,match='write set'):m.verify_backup(backup,g)


def test_host_recovery_never_mutates_on_inspect_or_changed_proof(tmp_path):
    import json
    from types import SimpleNamespace
    import pytest
    m=load('public_host_recovery')
    record=tmp_path/'recoveries'/'fixed'
    evidence={'synthetic':'original'}
    events=[]
    def write(path,raw):events.append(path.name);path.write_bytes(raw)
    adapter=SimpleNamespace(record=record,publisher='b'*40,inspect=lambda:evidence,
        server=SimpleNamespace(secure_path=lambda *a,**kw:None,_sync_directory=lambda *a:None,_write_private=write))
    assert m.recover(adapter)['state']=='HOST_RECOVERY_PREFLIGHT'
    assert not record.exists() and events==[]
    with pytest.raises(m.RecoveryError,match='evidence changed'):m.recover(adapter,'0'*64)
    assert not record.exists()
    calls=iter([evidence,{'synthetic':'changed'}]);adapter.inspect=lambda:next(calls)
    with pytest.raises(m.RecoveryError,match='drift after intent'):m.recover(adapter,m.digest(evidence))
    assert events==['intent.json']
    assert json.loads((record/'intent.json').read_text())==evidence
    with pytest.raises(m.RecoveryError,match='replay forbidden'):m.recover(adapter,m.digest(evidence))


def host_recovery_evidence_fixture(tmp_path,monkeypatch):
    import copy
    import hashlib
    from types import SimpleNamespace
    import pytest
    m=load('public_host_recovery')
    monkeypatch.setattr(m,'BACKUPS',tmp_path/'backups')
    backup=m.BACKUPS/m.FAILED_SHA;backup.mkdir(parents=True)
    raw='*filter\n:OUTPUT ACCEPT [0:0]\nCOMMIT\n'
    for family in ('iptables','ip6tables'):(backup/(family+'-before.txt')).write_text(raw)
    g=SimpleNamespace(ROOT=Path('/opt/health-app'),STAKING=Path('/mnt/data/lighthouse/validators'))
    frontend={'operation_id':'a'*32,'frontend_tree':'b'*40,'artifact_digest':'c'*64}
    proc={'pid':123,'starttime':'100','uid':['0']*4,'cgroup':'0::/system.slice/test.service\n','argv_sha256':'d'*64}
    values={'token':b'a'*64+b'\n','label':b'host-hardening\n',
            'stage':(str(m.STATE/m.FAILED_SHA/'host-hardening')+'\n').encode(),'started_at':b'1234567890\n'}
    lease={name:{'dev':1,'ino':idx+1,'uid':0,'gid':0,'mode':0o600,'sha256':hashlib.sha256(raw).hexdigest()} for idx,(name,raw) in enumerate(values.items())}
    lease['.']={'dev':1,'ino':9,'uid':0,'gid':0,'mode':0o700,'sha256':None}
    keys=[{'path':str(g.STAKING/'fixture-keystore.json'),'mode':0o644}]
    backup_intent={'sha':m.FAILED_SHA,'legacy_pid':123,'key_modes':keys}
    evidence={'permission_repair':None,'frontend':frontend,'legacy':proc,'services':{},'key_modes':keys,'lease':lease,
              'firewall':{family:m.firewall_policy(raw) for family in ('iptables','ip6tables')},
              'cache':{str(g.ROOT/'frontend/.next/cache'):[1,2,0o40755,0,0]}}
    for name in m.SERVICES:
        evidence['services'][name]={'properties':{'ActiveState':'active','MainPID':'123','NRestarts':'0','NeedDaemonReload':'no'},
          'process':{**proc,'uid':['997']*4 if name in m.SERVICES[:3] else ['0']*4}}
    return m,g,evidence,backup_intent,frontend,values


def test_host_recovery_inner_evidence_and_lease_binding(tmp_path,monkeypatch):
    import copy
    import pytest
    m,g,evidence,backup_intent,frontend,values=host_recovery_evidence_fixture(tmp_path,monkeypatch)
    m.validate_intent(evidence,backup_intent,frontend,values,g)
    for field in ('legacy','services','cache','firewall','key_modes','frontend','lease'):
        for empty in (None,{},[]):
            broken=copy.deepcopy(evidence);broken[field]=empty
            with pytest.raises(m.RecoveryError):m.validate_intent(broken,backup_intent,frontend,values,g)
    for name in values:
        broken={**values,name:b'forged\n'}
        with pytest.raises(m.RecoveryError):m.validate_intent(evidence,backup_intent,frontend,broken,g)
    broken=copy.deepcopy(evidence);broken['services']['health-backend']['process']['uid']=['0']*4
    with pytest.raises(m.RecoveryError):m.validate_intent(broken,backup_intent,frontend,values,g)
    broken=copy.deepcopy(evidence);broken['legacy']['pid']=124
    with pytest.raises(m.RecoveryError):m.validate_intent(broken,backup_intent,frontend,values,g)


def test_host_recovery_lease_uses_fixed_alias_proof_for_all_four_files(tmp_path,monkeypatch):
    from types import SimpleNamespace
    m=load('public_host_recovery');monkeypatch.setattr(m,'LEASE',tmp_path/'lease');m.LEASE.mkdir()
    audit=m.STATE/m.FAILED_SHA/'host-hardening'
    values={'token':b'a'*64+b'\n','label':b'host-hardening\n','stage':(str(audit)+'\n').encode(),'started_at':b'123\n'}
    for name,raw in values.items():(m.LEASE/name).write_bytes(raw)
    events=[]
    class Proof:
        def _directory(self,path):events.append(('directory',path));return {'fixture':True}
        def _file(self,path,mode):events.append(('file',path.name,mode));return path.read_bytes(),{'fixture':True}
    adapter=m.Adapter(tmp_path,tmp_path,'b'*40,SimpleNamespace(module=lambda *a:SimpleNamespace(RecoveryProof=Proof)),
       SimpleNamespace(_lease_identity=lambda *a:None),None,None,None,'a'*64,lambda:None)
    assert set(adapter.lease())=={'.',*values}
    assert events==[('directory',m.LEASE),*(('file',name,0o600) for name in values)]


def test_host_recovery_success_preserves_original_evidence_and_retires_inode(tmp_path,monkeypatch):
    import hashlib
    import json
    from types import SimpleNamespace
    m=load('public_host_recovery');monkeypatch.setattr(m,'LEASE',tmp_path/'active');monkeypatch.setattr(m,'VOLATILE',tmp_path)
    m.LEASE.mkdir();original_ino=m.LEASE.stat().st_ino
    for name in ('token','label','stage','started_at'):(m.LEASE/name).write_text(name+'\n')
    evidence={'legacy':{'pid':123},'key_modes':[],'services':{'stable':True},'preserved':{'original':True},'lease':{'.':{'ino':original_ino}}}
    events=[]
    def write(path,raw):events.append(path.name);path.write_bytes(raw)
    def apply(sha,record,pid,keys):
        assert 'intent.json' in events and json.loads((record.parent/'intent.json').read_text())==evidence
        events.append('apply')
    server=SimpleNamespace(secure_path=lambda *a,**kw:None,_sync_directory=lambda *a:None,_write_private=write,
      _sync_business_lease_parent=lambda:events.append('lease-parent-sync'))
    adapter=SimpleNamespace(record=tmp_path/'recoveries'/'fixed',publisher='b'*40,inspect=lambda:evidence,server=server,
      guard=SimpleNamespace(_apply_prepared=apply,run=lambda *a:'User=health-web\nMainPID=321\nActiveState=active'),
      host=SimpleNamespace(verify_runtime=lambda *a:None),helper=SimpleNamespace(_revision_proof=lambda *a:None),old=tmp_path,b=None,
      preserved=lambda:evidence['preserved'],lease=lambda:evidence['lease'],check=lambda:None)
    monkeypatch.setattr(m,'services',lambda *a:evidence['services'])
    monkeypatch.setattr(m.pwd,'getpwnam',lambda name:SimpleNamespace(pw_uid=998))
    monkeypatch.setattr(m,'process_identity',lambda pid:{'uid':['998']*4})
    original_run=m.subprocess.run
    def move(args,**kwargs):
        assert args[:4]==['/usr/bin/mv','--no-clobber','-T','--']
        Path(args[4]).rename(args[5]);return SimpleNamespace(returncode=0)
    monkeypatch.setattr(m.subprocess,'run',move)
    result=m.recover(adapter,m.digest(evidence))
    assert result['state']=='RECOVERED_LOCAL_VERIFIED' and not m.LEASE.exists()
    assert (tmp_path/('health-app-release.host-retired-'+m.FAILED_SHA)).stat().st_ino==original_ino
    assert events.index('intent.json')<events.index('apply')<events.index('lease-parent-sync')<events.index('completed.json')
    assert {p.name for p in (adapter.record/'lease').iterdir()}=={'token','label','stage','started_at'}


def test_host_recovery_completed_transaction_passes_actual_history_reader(tmp_path,monkeypatch):
    import sys
    monkeypatch.setattr(sys,'dont_write_bytecode',True)
    import hashlib
    import json
    import shutil
    from types import SimpleNamespace
    import pytest
    m,g,evidence,backup_intent,frontend,values=host_recovery_evidence_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(m,'STATE',tmp_path/'state')
    monkeypatch.setattr(m,'LEASE',tmp_path/'active')
    monkeypatch.setattr(m,'VOLATILE',tmp_path)
    audit=m.STATE/m.FAILED_SHA/'host-hardening';audit.mkdir(parents=True)
    values['stage']=(str(audit)+'\n').encode()
    m.LEASE.mkdir()
    def write(path,raw):path.write_bytes(raw);path.chmod(0o600)
    for name,raw in values.items():
        write(m.LEASE/name,raw)
        evidence['lease'][name]['sha256']=hashlib.sha256(raw).hexdigest()
    evidence['lease']['.']['ino']=m.LEASE.stat().st_ino
    evidence['production_sha']=m.FAILED_SHA;evidence['publisher_sha']='b'*40
    backup=m.BACKUPS/m.FAILED_SHA
    write(backup/'intent.json',json.dumps(backup_intent).encode())
    # Empty initial write set still uses the real archive and manifest validator.
    paths=[tmp_path/'absent-config'];monkeypatch.setattr(m,'write_set',lambda:paths)
    hostguard=load('harden_public_host');hostguard.backup_configuration(backup,paths)
    for name,state in (('started.json','STARTED'),('failed.json','NEEDS_OPERATOR')):
        write(audit/name,json.dumps({'sha':m.FAILED_SHA,'state':state}).encode())
    write(audit/'frontend.json',json.dumps(frontend).encode())
    def inventory(path,names):
        assert {p.name for p in path.iterdir()}==names
        result={}
        for p in [path,*(path/name for name in names)]:
            st=p.stat();isdir=p==path
            result['.' if isdir else p.name]={'uid':0,'gid':0,'mode':0o700 if isdir else 0o600,
                'inode':st.st_ino,'device':st.st_dev,'sha256':None if isdir else hashlib.sha256(p.read_bytes()).hexdigest()}
        return result
    preserved=lambda:{'audit':inventory(audit,m.AUDIT_NAMES),'backup':inventory(backup,m.BACKUP_NAMES)}
    evidence['preserved']=preserved()
    source=tmp_path/'canonical';(source/'scripts').mkdir(parents=True)
    shutil.copyfile(Path(__file__).parent/'harden_public_host.py',source/'scripts/harden_public_host.py')
    b=SimpleNamespace(secure=lambda *a,**kw:None,_inventory=inventory,_read_json=lambda p:json.loads(p.read_text()),canonical_source=lambda sha:source)
    server=SimpleNamespace(secure_path=lambda *a,**kw:None,_sync_directory=lambda *a:None,_write_private=write,_sync_business_lease_parent=lambda:None)
    def apply(sha,path,*args):
        write(path/'phase.json',b'{"phase":"frontend_cutover"}')
        write(path/'completed.json',json.dumps({'sha':sha,'status':'APPLIED'}).encode())
    adapter=SimpleNamespace(record=m.STATE/'host-hardening-recoveries'/m.FAILED_SHA,publisher='b'*40,
      inspect=lambda:evidence,server=server,guard=SimpleNamespace(_apply_prepared=apply,
      run=lambda *a:'User=health-web\nMainPID=321\nActiveState=active'),host=SimpleNamespace(verify_runtime=lambda *a:None),
      helper=SimpleNamespace(_revision_proof=lambda *a:None),old=source,b=b,preserved=preserved,lease=lambda:evidence['lease'],check=lambda:None)
    monkeypatch.setattr(m,'services',lambda *a:evidence['services'])
    monkeypatch.setattr(m.pwd,'getpwnam',lambda name:SimpleNamespace(pw_uid=998))
    monkeypatch.setattr(m,'process_identity',lambda pid:{'uid':['998']*4})
    monkeypatch.setattr(m.subprocess,'run',lambda args,**kw:Path(args[4]).rename(args[5]))
    monkeypatch.setattr(m,'source_scope',lambda *a:None)
    m.validate_intent(evidence,backup_intent,frontend,values,g)
    assert m.recover(adapter,m.digest(evidence))['state']=='RECOVERED_LOCAL_VERIFIED'
    assert m.history_evidence(b,m.FAILED_SHA)['kind']=='recovered-host-hardening'
    # A digest-consistent completion with missing inner proof must still fail.
    evidence['services']={}
    write(adapter.record/'intent.json',json.dumps(evidence).encode())
    completed=b._read_json(adapter.record/'completed.json');completed['intent_sha256']=m.digest(evidence)
    write(adapter.record/'completed.json',json.dumps(completed).encode())
    with pytest.raises(m.RecoveryError,match='inner evidence'):m.history_evidence(b,m.FAILED_SHA)


def test_host_recovery_auxiliary_scope_requires_exact_reviewed_blob(tmp_path,monkeypatch):
    import subprocess
    import pytest
    m=load('public_host_recovery');old=tmp_path/'old';new=tmp_path/'new'
    content='APPLICATION_PORTS = {}\ndef firewall_rules(): pass\ndef canonical_rule(): pass\ndef network_guard(): pass\n'
    for root in (old,new):
        (root/'scripts').mkdir(parents=True);(root/'scripts/harden_public_host.py').write_text(content)
        subprocess.run(['git','init',str(root)],check=True,capture_output=True)
        subprocess.run(['git','-C',str(root),'add','scripts/harden_public_host.py'],check=True)
        subprocess.run(['git','-C',str(root),'-c','user.name=Fixture','-c','user.email=f@example.invalid','-c','core.hooksPath=/dev/null','commit','-m','fixture'],check=True,capture_output=True)
    def commit():
        subprocess.run(['git','-C',str(new),'add','auxiliary'],check=True)
        subprocess.run(['git','-C',str(new),'-c','user.name=Fixture','-c','user.email=f@example.invalid','-c','core.hooksPath=/dev/null','commit','-m','auxiliary'],check=True,capture_output=True)
    (new/'auxiliary').write_text('reviewed');commit()
    pin=subprocess.check_output(['git','-C',str(new),'ls-tree','HEAD','--','auxiliary']).split(b'\t')[0]
    monkeypatch.setattr(m,'REVIEWED_AUXILIARY',{'auxiliary':pin})
    assert m.source_scope(new,old,None)==['auxiliary']
    (new/'auxiliary').write_text('changed');commit()
    with pytest.raises(m.RecoveryError,match='fixed scope'):m.source_scope(new,old,None)
    (new/'auxiliary').write_text('reviewed');(new/'auxiliary').chmod(0o755);commit()
    with pytest.raises(m.RecoveryError,match='fixed scope'):m.source_scope(new,old,None)

    (new/'auxiliary').chmod(0o644);commit()
    (old/'unknown').write_text('must not silently disappear')
    subprocess.run(['git','-C',str(old),'add','unknown'],check=True)
    subprocess.run(['git','-C',str(old),'-c','user.name=Fixture','-c','user.email=f@example.invalid','-c','core.hooksPath=/dev/null','commit','-m','unknown'],check=True,capture_output=True)
    with pytest.raises(m.RecoveryError,match='fixed scope'):m.source_scope(new,old,None)


def permission_package_fixture(tmp_path,monkeypatch):
    import hashlib,base64,csv,io,stat
    from types import SimpleNamespace
    m=load('runtime_permission_repair');site=tmp_path/'site';site.mkdir(parents=True)
    monkeypatch.setattr(m,'SITE',site)
    contents={'jwt/__init__.py':b'fixture source','jwt/api_jwt.py':b'fixture decode','jwt/py.typed':b''}
    monkeypatch.setattr(m,'SOURCE_HASHES',{p:hashlib.sha256(raw).hexdigest() for p,raw in contents.items()})
    metadata='pyjwt-2.14.0.dist-info'
    for name in ('INSTALLER','REQUESTED','WHEEL','licenses/AUTHORS.rst','licenses/LICENSE','top_level.txt'):contents[metadata+'/'+name]=b'fixture metadata'
    contents[metadata+'/METADATA']=b'Name: PyJWT\nVersion: 2.14.0\n'
    for name in ('__init__','api_jwt'):contents['jwt/__pycache__/'+name+'.cpython-312.pyc']=b'private generated cache'
    rows=[]
    for name,raw in contents.items():
        p=site/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);p.chmod(0o600)
        cache='__pycache__' in name
        rows.append([name,'' if cache else 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).decode().rstrip('='),'' if cache else str(len(raw))])
    rows.append([metadata+'/RECORD','',''])
    stream=io.StringIO();csv.writer(stream).writerows(rows);record=site/metadata/'RECORD';record.write_text(stream.getvalue());record.chmod(0o600)
    for p in site.rglob('*'):
        if p.is_dir():p.chmod(0o700)
    original=Path.lstat
    def rootstat(path,*args,**kwargs):
        v=original(path,*args,**kwargs);mode=v.st_mode
        if path in [*site.parents,site]:mode=stat.S_IFDIR|0o755
        return SimpleNamespace(st_uid=0,st_gid=0,st_mode=mode,st_nlink=v.st_nlink,st_dev=v.st_dev,st_ino=v.st_ino)
    monkeypatch.setattr(Path,'lstat',rootstat)
    return m,site,record


def test_permission_repair_fixed_package_and_private_cache(tmp_path,monkeypatch):
    import copy,pytest
    m,site,record=permission_package_fixture(tmp_path,monkeypatch)
    before=m.package_snapshot()
    after={p:{**v,'mode':v['target_mode']} for p,v in before.items()}
    m.unchanged_package(before,after)
    assert all(v['target_mode']==(0o700 if v['directory'] else 0o600) for p,v in after.items() if '__pycache__' in p)
    changed=copy.deepcopy(after);changed[str(site/'jwt/__init__.py')]['sha256']='0'*64
    with pytest.raises(RuntimeError):m.unchanged_package(before,changed)
    (site/'jwt/__init__.py').write_bytes(b'tampered')
    with pytest.raises(RuntimeError):m.package_snapshot()


def test_permission_repair_rejects_missing_record_link_unknown_and_cache_exposure(tmp_path,monkeypatch):
    import pytest
    m,site,record=permission_package_fixture(tmp_path,monkeypatch)
    item=site/'pyjwt-2.14.0.dist-info/WHEEL';raw=item.read_bytes();item.unlink()
    with pytest.raises(OSError):m.package_snapshot()
    item.write_bytes(raw);item.chmod(0o600)
    extra=site/'jwt/unknown.py';extra.write_text('unknown')
    with pytest.raises(RuntimeError):m.package_snapshot()
    extra.unlink()
    cache=site/'jwt/__pycache__';cache.chmod(0o755)
    with pytest.raises(RuntimeError):m.package_snapshot()
    cache.chmod(0o700)
    original=item.read_bytes();item.unlink();item.symlink_to(site/'jwt/__init__.py')
    with pytest.raises(RuntimeError):m.package_snapshot()


def test_permission_repair_never_mutates_without_digest_and_intent(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import pytest
    m,site,record=permission_package_fixture(tmp_path,monkeypatch)
    r=load('public_host_recovery');monkeypatch.setattr(r,'STATE',tmp_path/'state')
    evidence={'stable':'before'}
    a=SimpleNamespace(publisher='b'*40,inspect=lambda:evidence)
    proof=m.execute(a,r)
    assert proof['state']=='RUNTIME_PERMISSION_PREFLIGHT'
    assert not (r.STATE/m.NAME/r.FAILED_SHA).exists()
    with pytest.raises(RuntimeError,match='evidence changed'):m.execute(a,r,'0'*64)
    target=r.STATE/m.NAME/r.FAILED_SHA;target.mkdir(parents=True)
    with pytest.raises(RuntimeError,match='already attempted'):m.execute(a,r,proof['evidence_sha256'])


def test_permission_repair_transaction_and_history_preserve_staking(tmp_path,monkeypatch):
    import copy,json,os
    from types import SimpleNamespace
    m,site,record=permission_package_fixture(tmp_path/'package',monkeypatch)
    r,g,before,backup_intent,frontend,values=host_recovery_evidence_fixture(tmp_path/'host',monkeypatch)
    monkeypatch.setattr(r,'STATE',tmp_path/'state');monkeypatch.setattr(r,'LEASE',tmp_path/'lease');r.LEASE.mkdir()
    audit=r.STATE/r.FAILED_SHA/'host-hardening';audit.mkdir(parents=True)
    values['stage']=(str(audit)+'\n').encode()
    import hashlib
    for name,raw in values.items():
        (r.LEASE/name).write_bytes(raw);before['lease'][name]['sha256']=hashlib.sha256(raw).hexdigest()
    backup=r.BACKUPS/r.FAILED_SHA
    (backup/'intent.json').write_text(json.dumps(backup_intent));(audit/'frontend.json').write_text(json.dumps(frontend))
    before.update(production_sha=r.FAILED_SHA,publisher_sha='b'*40,preserved={'unchanged':True})
    services=copy.deepcopy(before['services']);events=[]
    def inventory(path,names):assert {p.name for p in path.iterdir()}==names;return {}
    b=SimpleNamespace(_inventory=inventory,_read_json=lambda p:json.loads(p.read_text()),canonical_source=lambda sha:tmp_path)
    def write(path,raw):path.write_bytes(raw);events.append(path.name)
    def run(*args):
        assert args[:2]==('/usr/bin/systemctl','restart') and args[2] in r.SERVICES[:3]
        assert (r.STATE/m.NAME/r.FAILED_SHA/'intent.json').exists()
        events.append(args[2]);value=services[args[2]];value['process']['pid']+=100;value['process']['starttime']=str(int(value['process']['starttime'])+100);value['properties']['MainPID']=str(value['process']['pid'])
    a=SimpleNamespace(publisher='b'*40,inspect=lambda:before,b=b,old=tmp_path,guard=g,backup=backup,audit=audit,
      check=lambda:None,lease=lambda:before['lease'],preserved=lambda:before['preserved'],
      helper=SimpleNamespace(_revision_proof=lambda *a:None),server=SimpleNamespace(secure_path=lambda *a,**kw:None,_sync_directory=lambda *a:None,_write_private=write))
    g.run=run
    monkeypatch.setattr(m,'restart_service',lambda name:run('/usr/bin/systemctl','restart',name))
    monkeypatch.setattr(r,'services',lambda *a:copy.deepcopy(services));monkeypatch.setattr(r,'source_scope',lambda *a:None)
    monkeypatch.setattr(m,'runtime_probe',lambda:events.append('runtime-probe'));monkeypatch.setattr(m,'http_probe',lambda:events.append('http-probe'));monkeypatch.setattr(m.time,'sleep',lambda *a:None)
    original_fstat=os.fstat
    def rootfstat(fd):
        v=original_fstat(fd)
        return SimpleNamespace(st_dev=v.st_dev,st_ino=v.st_ino,st_mode=v.st_mode,st_uid=0,st_gid=0)
    monkeypatch.setattr(m.os,'fstat',rootfstat);monkeypatch.setattr(m.os,'fsync',lambda *a:None)
    proof=m.execute(a,r)
    assert m.execute(a,r,proof['evidence_sha256'])['state']=='RUNTIME_PERMISSIONS_REPAIRED'
    intent,done=m.inspect_history(a,r)
    assert done['after_services']==services
    assert all(done['after_services'][name]==before['services'][name] for name in r.SERVICES[3:])
    assert events[0]=='intent.json' and events[-1]=='completed.json'
    assert events.index('runtime-probe')<events.index('health-backend')


def test_permission_repair_rejects_directory_symlink_before_leaf_read(tmp_path,monkeypatch):
    import pytest
    m,site,record=permission_package_fixture(tmp_path,monkeypatch)
    original=site/'jwt';target=site/'saved';original.rename(target);original.symlink_to(target,target_is_directory=True)
    read=Path.read_bytes
    def guarded(path):
        if path.is_relative_to(original):pytest.fail('must reject parent before reading package content')
        return read(path)
    monkeypatch.setattr(Path,'read_bytes',guarded)
    with pytest.raises(RuntimeError,match='ancestry'):m.package_snapshot()


def test_permission_repair_restart_targets_timeout_and_continuity(monkeypatch):
    import copy
    import pytest
    from types import SimpleNamespace
    m=load('runtime_permission_repair');r=load('public_host_recovery');calls=[]
    monkeypatch.setattr(m.subprocess,'run',lambda args,**kw:calls.append((args,kw)))
    m.restart_service('celery-worker')
    assert calls[0][0]==['/usr/bin/systemctl','restart','celery-worker'] and calls[0][1]['timeout']==180
    with pytest.raises(RuntimeError):m.restart_service('eth1')
    process={'pid':1,'starttime':'1','uid':['997']*4,'cgroup':'stable','argv_sha256':'a'*64}
    before={name:{'process':copy.deepcopy(process)} for name in r.SERVICES};after=copy.deepcopy(before)
    for name in r.SERVICES[:3]:after[name]['process'].update(pid=2,starttime='2')
    m.validate_restarted_services(before,after,r)
    for field,new in (('uid',['0']*4),('cgroup','wrong'),('argv_sha256','b'*64),('pid',1),('starttime','1')):
        changed=copy.deepcopy(after);changed['health-backend']['process'][field]=new
        with pytest.raises(RuntimeError):m.validate_restarted_services(before,changed,r)
    changed=copy.deepcopy(after);changed['eth1']['process']['pid']=2
    with pytest.raises(RuntimeError):m.validate_restarted_services(before,changed,r)


def test_bootstrap_host_permission_history_chain(tmp_path,monkeypatch):
    import sys
    monkeypatch.setattr(sys,'dont_write_bytecode',True)
    import hashlib
    import json
    import shutil
    from types import SimpleNamespace
    import pytest
    m,g,evidence,backup_intent,frontend,values=host_recovery_evidence_fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(m,'STATE',tmp_path/'state')
    monkeypatch.setattr(m,'LEASE',tmp_path/'active')
    monkeypatch.setattr(m,'VOLATILE',tmp_path)
    audit=m.STATE/m.FAILED_SHA/'host-hardening';audit.mkdir(parents=True)
    values['stage']=(str(audit)+'\n').encode()
    m.LEASE.mkdir()
    def write(path,raw):path.write_bytes(raw);path.chmod(0o600)
    for name,raw in values.items():
        write(m.LEASE/name,raw)
        evidence['lease'][name]['sha256']=hashlib.sha256(raw).hexdigest()
    evidence['lease']['.']['ino']=m.LEASE.stat().st_ino
    evidence['production_sha']=m.FAILED_SHA;evidence['publisher_sha']='b'*40
    backup=m.BACKUPS/m.FAILED_SHA
    write(backup/'intent.json',json.dumps(backup_intent).encode())
    # Empty initial write set still uses the real archive and manifest validator.
    paths=[tmp_path/'absent-config'];monkeypatch.setattr(m,'write_set',lambda:paths)
    hostguard=load('harden_public_host');hostguard.backup_configuration(backup,paths)
    for name,state in (('started.json','STARTED'),('failed.json','NEEDS_OPERATOR')):
        write(audit/name,json.dumps({'sha':m.FAILED_SHA,'state':state}).encode())
    write(audit/'frontend.json',json.dumps(frontend).encode())
    def inventory(path,names):
        assert {p.name for p in path.iterdir()}==names
        result={}
        for p in [path,*(path/name for name in names)]:
            st=p.stat();isdir=p==path
            result['.' if isdir else p.name]={'uid':0,'gid':0,'mode':0o700 if isdir else 0o600,
                'inode':st.st_ino,'device':st.st_dev,'sha256':None if isdir else hashlib.sha256(p.read_bytes()).hexdigest()}
        return result
    preserved=lambda:{'audit':inventory(audit,m.AUDIT_NAMES),'backup':inventory(backup,m.BACKUP_NAMES)}
    evidence['preserved']=preserved()
    source=tmp_path/'canonical';(source/'scripts').mkdir(parents=True)
    shutil.copyfile(ROOT/'scripts/harden_public_host.py',source/'scripts/harden_public_host.py')
    b=SimpleNamespace(secure=lambda *a,**kw:None,_inventory=inventory,_read_json=lambda p:json.loads(p.read_text()),canonical_source=lambda sha:source)
    server=SimpleNamespace(secure_path=lambda *a,**kw:None,_sync_directory=lambda *a:None,_write_private=write,_sync_business_lease_parent=lambda:None)
    def apply(sha,path,*args):
        write(path/'phase.json',b'{"phase":"frontend_cutover"}')
        write(path/'completed.json',json.dumps({'sha':sha,'status':'APPLIED'}).encode())
    adapter=SimpleNamespace(record=m.STATE/'host-hardening-recoveries'/m.FAILED_SHA,publisher='b'*40,
      inspect=lambda:evidence,server=server,guard=SimpleNamespace(_apply_prepared=apply,
      run=lambda *a:'User=health-web\nMainPID=321\nActiveState=active'),host=SimpleNamespace(verify_runtime=lambda *a:None),
      helper=SimpleNamespace(_revision_proof=lambda *a:None),old=source,b=b,preserved=preserved,lease=lambda:evidence['lease'],check=lambda:None)
    monkeypatch.setattr(m,'services',lambda *a:evidence['services'])
    monkeypatch.setattr(m.pwd,'getpwnam',lambda name:SimpleNamespace(pw_uid=998))
    monkeypatch.setattr(m,'process_identity',lambda pid:{'uid':['998']*4})
    monkeypatch.setattr(m.subprocess,'run',lambda args,**kw:Path(args[4]).rename(args[5]))
    monkeypatch.setattr(m,'source_scope',lambda *a:None)
    import copy
    repair=load('runtime_permission_repair')
    metadata='pyjwt-2.14.0.dist-info'
    dirs={'jwt','jwt/__pycache__',metadata,metadata+'/licenses'}
    files=set(repair.SOURCE_HASHES)
    files.update('jwt/__pycache__/'+Path(p).stem+'.cpython-312.pyc' for p in repair.SOURCE_HASHES if p.endswith('.py'))
    files.update(metadata+'/'+p for p in ('INSTALLER','METADATA','RECORD','REQUESTED','WHEEL','licenses/AUTHORS.rst','licenses/LICENSE','top_level.txt'))
    package={}
    for i,name in enumerate(sorted(dirs|files),1):
        directory=name in dirs;cache='__pycache__' in Path(name).parts
        package[str(repair.SITE/name)]={'uid':0,'gid':0,'dev':1,'ino':i,'directory':directory,
            'mode':0o700 if directory else 0o600,
            'target_mode':(0o700 if directory else 0o600) if cache else (0o755 if directory else 0o644),
            'sha256':None if directory else repair.SOURCE_HASHES.get(name,'e'*64)}
    repair.validate_package_snapshot(package)
    before=copy.deepcopy(evidence)
    for name in m.SERVICES[:3]:
        service=evidence['services'][name];service['process']['pid']+=100
        service['process']['starttime']='200';service['properties']['MainPID']=str(service['process']['pid'])
    repair_intent={'production_sha':m.FAILED_SHA,'publisher_sha':adapter.publisher,'before':before,'package':package}
    repair_done={'state':'RUNTIME_PERMISSIONS_REPAIRED','production_sha':m.FAILED_SHA,'publisher_sha':adapter.publisher,
        'intent_sha256':m.digest(repair_intent),'after_services':copy.deepcopy(evidence['services']),
        'after_package':{p:{**v,'mode':v['target_mode']} for p,v in package.items()}}
    repair_record=m.STATE/repair.NAME/m.FAILED_SHA;repair_record.mkdir(parents=True)
    write(repair_record/'intent.json',json.dumps(repair_intent).encode())
    write(repair_record/'completed.json',json.dumps(repair_done).encode())
    evidence['permission_repair']={'intent_sha256':m.digest(repair_intent),'completion_sha256':m.digest(repair_done)}
    for name in ('public_host_recovery','runtime_permission_repair','monitor_ingress_repair'):
        shutil.copyfile(ROOT/'scripts'/f'{name}.py',source/'scripts'/f'{name}.py')
    bootstrap=load('bootstrap_trusted_release')
    monkeypatch.setitem(sys.modules,bootstrap.__name__,bootstrap)
    monkeypatch.setattr(bootstrap,'STATE',m.STATE)
    monkeypatch.setattr(bootstrap,'__file__',str(source/'scripts/bootstrap_trusted_release.py'))
    for name in ('secure','_inventory','_read_json','canonical_source'):
        monkeypatch.setattr(bootstrap,name,getattr(b,name))
    # Preserve actual loader execution and sys.modules registration. Only map
    # fixed host paths and canonical-source validation to this local fixture.
    import importlib.util
    real_spec=importlib.util.spec_from_file_location
    def fixture_spec(name,path,*args,**kwargs):
        spec=real_spec(name,path,*args,**kwargs)
        if name=='host_recovery_history':
            real_exec=spec.loader.exec_module
            def execute(module):
                real_exec(module)
                for key in ('STATE','BACKUPS','LEASE','VOLATILE','write_set','source_scope'):
                    setattr(module,key,getattr(m,key))
            spec.loader.exec_module=execute
        if name=='monitor_ingress_history':
            real_exec=spec.loader.exec_module
            def execute_monitor(module):
                real_exec(module);module.STATE=m.STATE;module.source_scope=lambda *a:None
            spec.loader.exec_module=execute_monitor
        return spec
    monkeypatch.setattr(importlib.util,'spec_from_file_location',fixture_spec)
    m.validate_intent(evidence,backup_intent,frontend,values,g)
    assert m.recover(adapter,m.digest(evidence))['state']=='RECOVERED_LOCAL_VERIFIED'
    assert bootstrap._host_hardening_evidence(m.FAILED_SHA)['kind']=='recovered-host-hardening'
    assert sys.modules['host_recovery_history'].__name__=='host_recovery_history'

    monitor=load('monitor_ingress_repair');monitor_before=monitor_intent(monitor)
    monitor_before['host_history']=bootstrap._host_hardening_evidence(m.FAILED_SHA)
    monitor_record=m.STATE/'monitor-ingress-repairs'/m.FAILED_SHA
    monitor_record.mkdir(parents=True,mode=0o700);(monitor_record/'lease').mkdir(mode=0o700)
    monitor_values={'token':'e'*64,'label':'monitor-ingress','stage':str(monitor_record),'started_at':'123'}
    monitor_lease={'.':{'dev':1,'ino':1,'uid':0,'gid':0,'mode':0o700,'sha256':None}}
    for i,(name,value) in enumerate(monitor_values.items(),2):
        raw=(value+'\n').encode();write(monitor_record/'lease'/name,raw)
        monitor_lease[name]={'dev':1,'ino':i,'uid':0,'gid':0,'mode':0o600,'sha256':hashlib.sha256(raw).hexdigest()}
    monitor_done={'state':'MONITOR_INGRESS_LOCAL_VERIFIED','production_sha':m.FAILED_SHA,'publisher_sha':'a'*40,
        'intent_sha256':m.digest(monitor_before),'lease_sha256':m.digest(monitor_lease),'external_readback_required':True}
    for name,value in (('intent.json',monitor_before),('lease.json',monitor_lease),('completed.json',monitor_done)):
        write(monitor_record/name,json.dumps(value).encode())
    assert bootstrap._host_hardening_evidence(m.FAILED_SHA)['monitor_ingress']['kind']=='monitor-ingress-repair'
    original_services=monitor_before['services'];monitor_before['services']={}
    monitor_done['intent_sha256']=m.digest(monitor_before)
    write(monitor_record/'intent.json',json.dumps(monitor_before).encode());write(monitor_record/'completed.json',json.dumps(monitor_done).encode())
    with pytest.raises(RuntimeError,match='inner evidence'):bootstrap._host_hardening_evidence(m.FAILED_SHA)
    monitor_before['services']=original_services;monitor_done['intent_sha256']=m.digest(monitor_before)
    write(monitor_record/'intent.json',json.dumps(monitor_before).encode());write(monitor_record/'completed.json',json.dumps(monitor_done).encode())

    # Even self-consistent outer digests cannot authorize unknown package code.
    repair_done['after_package'][str(repair.SITE/'jwt/__init__.py')]['sha256']='0'*64
    write(repair_record/'completed.json',json.dumps(repair_done).encode())
    evidence['permission_repair']['completion_sha256']=m.digest(repair_done)
    write(adapter.record/'intent.json',json.dumps(evidence).encode())
    completed=b._read_json(adapter.record/'completed.json');completed['intent_sha256']=m.digest(evidence)
    write(adapter.record/'completed.json',json.dumps(completed).encode())
    with pytest.raises(RuntimeError,match='historical source digest'):
        bootstrap._host_hardening_evidence(m.FAILED_SHA)
