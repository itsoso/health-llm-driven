from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
    path = ROOT / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location('tested_' + name, path)
    result = importlib.util.module_from_spec(spec)
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
    m = load('bootstrap_trusted_release')
    monkeypatch.setattr(m, 'STATE', tmp_path)
    monkeypatch.setattr(m, 'secure', lambda *args, **kwargs: None)
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
    with pytest.raises(m.BootstrapError):
        m._host_hardening_evidence(sha)


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
    evidence={'frontend':frontend,'legacy':proc,'services':{},'key_modes':keys,'lease':lease,
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
