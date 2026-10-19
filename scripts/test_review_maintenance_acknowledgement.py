"""Synthetic protocol tests; do not contact production or inspect real accounts."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest


def load():
    path = Path(__file__).with_name('review_maintenance_acknowledgement.py')
    spec = importlib.util.spec_from_file_location('ack_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Adapter:
    def __init__(self, root):
        self.record = root / 'ack'
        self.evidence = {'old_sha': 'a' * 40, 'closing_sha': 'b' * 40,
                         'operation_id': 'c' * 32, 'original_outcome': 'UNKNOWN'}
        self.original = root / 'original.json'
        self.original.write_text('{"state":"NEEDS_OPERATOR"}')
        self.calls = 0
        self.keys = []
        self.account = {'verification': 'CURRENT_ACCOUNT_ONLY_NOT_RESET'}
        self.change_at = None
        self.account_change = False
        self.invalid_account = False

    def inspect(self):
        self.calls += 1
        evidence = copy.deepcopy(self.evidence)
        if self.calls == self.change_at:
            evidence['changed'] = True
        return evidence

    def prepare_record(self):
        self.record.mkdir(mode=0o700)

    def write(self, name, value):
        with (self.record / name).open('x') as stream:
            json.dump(value, stream)

    def inspect_account(self, key):
        assert (self.record / 'intent.json').exists()
        self.keys.append(key)
        if self.account_change and len(self.keys) == 2:
            return {'changed': True}
        return copy.deepcopy(self.account)

    def validate_account(self, value):
        if self.invalid_account:
            raise ValueError('invalid account')


def test_inspect_is_readonly_and_needs_no_acceptance(tmp_path):
    m, a = load(), Adapter(tmp_path)
    assert m.acknowledge(a)['state'] == 'INSPECTED_UNKNOWN_NO_RETRY_AUTHORITY'
    assert not a.record.exists()
    assert not a.keys


def test_exec_requires_explicit_acceptance(tmp_path):
    m, a = load(), Adapter(tmp_path)
    with pytest.raises(m.AcknowledgementError, match='explicit'):
        m.acknowledge(a, evidence_sha256=m.digest(a.evidence))
    assert not a.record.exists()


def test_stale_inspection_is_rejected_before_intent(tmp_path):
    m, a = load(), Adapter(tmp_path)
    with pytest.raises(m.AcknowledgementError, match='changed'):
        m.acknowledge(a, accept_unknown=True, evidence_sha256='f' * 64)
    assert not a.record.exists()


def test_success_preserves_original_unknown_and_grants_no_authority(tmp_path):
    m, a = load(), Adapter(tmp_path)
    old = a.original.read_bytes()
    result = m.acknowledge(a, accept_unknown=True, evidence_sha256=m.digest(a.evidence))
    completed = json.loads((a.record / 'completed.json').read_text())
    assert result['state'] == 'UNKNOWN_ACCEPTED_AUDIT_ONLY'
    assert completed['original_outcome'] == 'UNKNOWN'
    assert completed['reset_authorized'] is False
    assert completed['release_unblocked'] is False
    assert not any(completed['authority'].values())
    assert completed['historical_no_write_proven'] is False
    assert a.original.read_bytes() == old
    assert len(a.keys) == 2 and len(a.keys[0]) == 32 and a.keys[0] == a.keys[1]
    assert {p.name for p in a.record.iterdir()} == {'intent.json', 'completed.json'}
    with pytest.raises(m.AcknowledgementError, match='retry forbidden'):
        m.acknowledge(a)


@pytest.mark.parametrize('change_at', [2, 3, 4])
def test_evidence_drift_retains_intent_and_blocks_retry(tmp_path, change_at):
    m, a = load(), Adapter(tmp_path)
    a.change_at = change_at
    with pytest.raises(m.AcknowledgementError, match='changed'):
        m.acknowledge(a, accept_unknown=True, evidence_sha256=m.digest(a.evidence))
    assert (a.record / 'intent.json').exists()
    assert not (a.record / 'completed.json').exists()
    with pytest.raises(m.AcknowledgementError, match='retry forbidden'):
        m.acknowledge(a)


def test_changed_demo_hmac_cannot_complete(tmp_path):
    m, a = load(), Adapter(tmp_path)
    a.account_change = True
    with pytest.raises(m.AcknowledgementError, match='snapshot changed'):
        m.acknowledge(a, accept_unknown=True, evidence_sha256=m.digest(a.evidence))
    assert not (a.record / 'completed.json').exists()


def test_invalid_demo_proof_cannot_complete(tmp_path):
    m, a = load(), Adapter(tmp_path)
    a.invalid_account = True
    with pytest.raises(ValueError):
        m.acknowledge(a, accept_unknown=True, evidence_sha256=m.digest(a.evidence))
    assert not (a.record / 'completed.json').exists()


def test_existing_symlink_record_is_not_followed(tmp_path):
    m, a = load(), Adapter(tmp_path)
    a.record.symlink_to(tmp_path / 'missing')
    with pytest.raises(m.AcknowledgementError, match='retry forbidden'):
        m.acknowledge(a)


def test_noncanonical_context_rejected():
    m = load()
    with pytest.raises(m.AcknowledgementError, match='canonical'):
        m.context('a' * 40)


def test_no_existing_history_consumer_references_audit_namespace():
    root = Path(__file__).parent
    for name in ('trusted_review_reset.py', 'bootstrap_trusted_release.py', 'trusted_release_server.py'):
        assert 'review-maintenance-acknowledgements' not in (root / name).read_text()


def pair():
    start = {'operator_sha': load().ORIGINAL_OPERATOR, 'target_sha': load().TARGET, 'operation_id': load().OPERATION,
             'production_identity': [1] * 9, 'production_sha256': 'd' * 64,
             'environment_sha256': 'e' * 64, 'ci': {}, 'state': 'STARTED'}
    return start, {**start, 'state': 'NEEDS_OPERATOR'}


def test_exact_failed_maintenance_pair_is_accepted():
    m = load()
    start, end = pair()
    m.validate_failed_pair(start, end, m.TARGET, m.OPERATION)


@pytest.mark.parametrize('field,value', [('state', 'SUCCEEDED'), ('target_sha', 'f' * 40),
                                        ('operation_id', 'f' * 32), ('operator_sha', None)])
def test_inconsistent_failed_maintenance_pair_is_blocked(field, value):
    m = load()
    start, end = pair()
    end[field] = value
    with pytest.raises(m.AcknowledgementError):
        m.validate_failed_pair(start, end, m.TARGET, m.OPERATION)


def test_matching_wrong_operation_pair_still_blocked():
    m = load()
    start, end = pair()
    start['operation_id'] = end['operation_id'] = 'f' * 32
    with pytest.raises(m.AcknowledgementError):
        m.validate_failed_pair(start, end, m.TARGET, m.OPERATION)


def test_probe_refuses_github_token_flag_before_context(monkeypatch):
    import sys
    m = load()
    monkeypatch.setattr(sys, 'argv', ['ack', '--sha', 'b' * 40, '--release-sha', 'a' * 40,
                                   '--operation-id', 'c' * 32, '--account-probe', '--token-stdin'])
    def forbidden(*args, **kwargs):
        pytest.fail('context or stdin must not be reached')
    monkeypatch.setattr(m, 'context', forbidden)
    assert m.main() == 1


def test_real_adapter_constructor_never_requires_or_fabricates_lease(tmp_path, monkeypatch):
    from types import SimpleNamespace
    m = load()
    root = Path(__file__).resolve().parents[1]
    helpers = m.load(root / 'scripts/review_maintenance_retirement.py', 'real_ack_helpers')
    seen = []
    bootstrap = SimpleNamespace(STATE=tmp_path, secure=lambda path, **kwargs: seen.append(path))
    adapter = m.make_adapter(root, bootstrap, object(), helpers, 'b' * 40, m.TARGET,
                             m.OPERATION, lambda: None)
    assert not hasattr(adapter, 'token')
    assert not hasattr(adapter.p, 'token')
    assert not hasattr(adapter.p, 'isolate')
    assert not hasattr(adapter.p, 'stopped')
    assert not hasattr(adapter.p.systemd, 'daemon_reload')
    assert adapter.p.proc == Path('/proc')
    assert adapter.p.cgroup == Path('/sys/fs/cgroup')
    assert adapter.record.parent.name == 'review-maintenance-acknowledgements'
    assert len(seen) >= 4
    with pytest.raises(m.AcknowledgementError, match='revocation forbidden'):
        adapter.isolate({})


@pytest.mark.parametrize('old_sha,operation', [('f' * 40, load().OPERATION), (load().TARGET, 'f' * 32)])
def test_profile_rejects_other_operations(old_sha, operation):
    m = load()
    with pytest.raises(m.AcknowledgementError, match='explicitly accepted'):
        m.validate_profile(old_sha, operation)


def test_real_adapter_child_receives_only_ephemeral_hmac_key(tmp_path, monkeypatch):
    from types import SimpleNamespace
    m = load()
    root = Path(__file__).resolve().parents[1]
    helpers = m.load(root / 'scripts/review_maintenance_retirement.py', 'real_ack_probe_helpers')
    bootstrap = SimpleNamespace(STATE=tmp_path, secure=lambda *args, **kwargs: None)
    adapter = m.make_adapter(root, bootstrap, object(), helpers, 'b' * 40,
                             m.TARGET, m.OPERATION, lambda: None)
    monkeypatch.setattr(adapter, '_quiescent', lambda: None)
    key = bytes(range(32))
    seen = []
    def run(argv, **kwargs):
        seen.append(argv)
        assert '--token-stdin' not in argv
        assert kwargs['input'] == key
        assert kwargs['env'] == m.ENV
        return SimpleNamespace(stdout=b'{"synthetic":true}')
    monkeypatch.setattr(m.subprocess, 'run', run)
    assert adapter.inspect_account(key) == {'synthetic': True}
    assert len(seen) == 1


def test_ci_protected_token_read_once_not_persisted():
    from types import SimpleNamespace
    m = load()
    events = []
    def token():
        events.append('stdin')
        return 'synthetic-ephemeral'
    def get_json(url, **kwargs):
        assert kwargs == {'token': 'synthetic-ephemeral'}
        events.append('request')
        return {}
    def verify(sha, workflow_sha, **kwargs):
        assert sha == workflow_sha == 'b' * 40
        assert kwargs['observed_main'] == sha
        kwargs['_get_json']('/synthetic')
        kwargs['_get_json']('/synthetic2')
    m.verify_operator_ci(SimpleNamespace(_stdin_token=token, _get_json=get_json,
                                        verify_release=verify), 'b' * 40, True)
    assert events == ['stdin', 'request', 'request']


def test_real_adapter_base_reuses_fixed_0640_production_reader(tmp_path, monkeypatch):
    import hashlib
    from types import SimpleNamespace
    m = load()
    root = Path(__file__).resolve().parents[1]
    helpers = m.load(root / 'scripts/review_maintenance_retirement.py', 'real_ack_env_helpers')
    maintenance = m.load(root / 'scripts/trusted_review_maintenance.py', 'real_ack_env')
    server = m.load(root / 'scripts/trusted_release_server.py', 'real_ack_env_server')
    production = tmp_path / 'production.env'
    production.write_text('SYNTHETIC=value\n')
    production.chmod(0o640)
    maintenance.PRODUCTION_ENV = production
    def read_production_env():
        info = production.stat()
        server.validate_production_env_metadata(SimpleNamespace(st_mode=info.st_mode,
            st_uid=0, st_gid=996, st_nlink=1), 996)
        return production.read_text()
    env_server = SimpleNamespace(read_production_env=read_production_env)
    identity, env_digest, _ = maintenance.production_identity(env_server)
    workspace = tmp_path / m.TARGET
    workspace.mkdir()
    (workspace / 'deployment.env').write_text('SYNTHETIC=deployment\n')
    start, _ = pair()
    start['production_identity'] = list(identity)
    start['production_sha256'] = env_digest
    start['environment_sha256'] = hashlib.sha256((workspace / 'deployment.env').read_bytes()).hexdigest()
    end = {**start, 'state': 'NEEDS_OPERATOR'}
    bootstrap = SimpleNamespace(STATE=tmp_path, secure=lambda *args, **kwargs: None,
        _inventory=lambda *args: {'synthetic': True},
        _read_json=lambda path: start if path.name == 'started.json' else end)
    adapter = m.make_adapter(root, bootstrap, env_server, helpers, 'b' * 40,
                            m.TARGET, m.OPERATION, lambda: None)
    monkeypatch.setattr(m, 'STATE', tmp_path)
    monkeypatch.setattr(helpers.Adapter, '_base', lambda self: {'original': 'unchanged'})
    original_load = m.load
    monkeypatch.setattr(m, 'load', lambda path, name: maintenance if name == 'ack_environment_reader' else original_load(path, name))
    assert adapter._base()['production_environment']['sha256'] == env_digest
    production.chmod(0o600)
    with pytest.raises(server.LaunchError, match='0640'):
        adapter._base()


def test_real_adapter_inspect_complete_synthetic_snapshot(tmp_path, monkeypatch):
    """Run actual inspect/_base/lease/services composition over synthetic files.

    Root ownership, OS process/SSH inventory and systemd I/O are simulated;
    source readers, receipt schemas, directory inventories, policy binding,
    environment identity, service stability and absent-lease checks are real.
    """
    import hashlib
    import os
    import stat
    from types import SimpleNamespace
    m = load()
    root = Path(__file__).resolve().parents[1]
    helpers = m.load(root / 'scripts/review_maintenance_retirement.py', 'full_ack_helpers')
    b = m.load(root / 'scripts/bootstrap_trusted_release.py', 'full_ack_bootstrap')
    server = m.load(root / 'scripts/trusted_release_server.py', 'full_ack_server')
    maintenance = m.load(root / 'scripts/trusted_review_maintenance.py', 'full_ack_environment')
    state = tmp_path / 'state'
    state.mkdir(mode=0o700)
    m.STATE = b.STATE = state
    b.CONFIG = tmp_path / 'config'
    b.CONFIG.mkdir(mode=0o700)
    lib = tmp_path / 'library'
    lib.mkdir(mode=0o700)
    b.INSTALLED = lib / 'executor.py'
    b.AUTHORIZED = tmp_path / 'authorized_keys'
    b.BUSINESS_LEASE = tmp_path / 'absent-business-lease'
    workspace = state / m.TARGET
    workspace.mkdir(mode=0o700)
    resets = workspace / 'review-resets'
    resets.mkdir(mode=0o700)
    operation = resets / m.OPERATION
    operation.mkdir(mode=0o700)
    audit_root = state / 'review-maintenance'
    audit_root.mkdir(mode=0o700)
    audit = audit_root / m.TARGET
    audit.mkdir(mode=0o700)
    def write(path, value):
        path.write_text(json.dumps(value) if not isinstance(value, str) else value)
        path.chmod(0o600)
    write(workspace / 'started.json', {'sha': m.TARGET, 'state': 'STARTED'})
    write(workspace / 'completed.json', {'sha': m.TARGET, 'state': 'SUCCEEDED'})
    write(operation / 'started.json', {'sha': m.TARGET, 'operation_id': m.OPERATION, 'state': 'STARTED'})
    write(operation / 'completed.json', {'sha': m.TARGET, 'operation_id': m.OPERATION, 'state': 'NEEDS_OPERATOR'})
    write(workspace / 'deployment.env', 'SYNTHETIC=deployment\n')
    write(state / 'launcher.lock', '')
    write(workspace / 'build.lock', '')
    canonical_digest = hashlib.sha256((root / 'scripts/trusted_release_server.py').read_bytes()).hexdigest()
    b.INSTALLED.write_bytes((root / 'scripts/trusted_release_server.py').read_bytes())
    b.INSTALLED.chmod(0o600)
    write(b.CONFIG / 'authorized-release.json', {'sha': m.TARGET, 'executor_sha256': canonical_digest, 'expires_at': 0})
    for name, text in {'cloud.pub': 'ssh-ed25519 synthetic-cloud', 'loopback.pub': 'ssh-ed25519 synthetic-loopback',
                       'loopback.key': 'synthetic', 'loopback.conf': 'synthetic', 'known_hosts': 'synthetic'}.items():
        write(b.CONFIG / name, text)
    write(b.AUTHORIZED, 'fixed synthetic-cloud\nfixed synthetic-loopback\n')
    production = tmp_path / 'production.env'
    write(production, 'SYNTHETIC=value\n')
    production.chmod(0o640)
    maintenance.PRODUCTION_ENV = production

    # Synthetic root ownership. Retain actual inode, nanosecond timestamps,
    # modes and sizes so the real file-identity comparisons still execute.
    original_lstat = Path.lstat
    def lstat(path):
        if path == Path('/var/lock'):
            return SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0, st_gid=0)
        if path == Path('/run/lock'):
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o1777, st_uid=0, st_gid=0)
        info = original_lstat(path)
        if path == root or root in path.parents or path == tmp_path or tmp_path in path.parents:
            names = ('st_mode', 'st_ino', 'st_dev', 'st_nlink', 'st_size', 'st_atime', 'st_mtime',
                     'st_ctime', 'st_atime_ns', 'st_mtime_ns', 'st_ctime_ns')
            return SimpleNamespace(**{name: getattr(info, name) for name in names},
                                   st_uid=0, st_gid=996 if path == production else 0)
        return info
    monkeypatch.setattr(Path, 'lstat', lstat)
    original_readlink = os.readlink
    monkeypatch.setattr(os, 'readlink', lambda path, **kwargs: '/run/lock' if Path(path) == Path('/var/lock') else original_readlink(path, **kwargs))
    def secure(path, private=False):
        info = path.lstat()
        assert info.st_uid == 0 and not info.st_mode & 0o022
        assert not stat.S_ISLNK(info.st_mode)
        if private:
            assert stat.S_IMODE(info.st_mode) == 0o600
    b.secure = secure
    def read_env():
        server.validate_production_env_metadata(production.lstat(), 996)
        return production.read_text()
    server.read_production_env = read_env
    identity, env_digest, _ = maintenance.production_identity(server)
    start, _ = pair()
    start.update(production_identity=list(identity), production_sha256=env_digest,
                 environment_sha256=hashlib.sha256((workspace / 'deployment.env').read_bytes()).hexdigest())
    write(audit / 'started.json', start)
    write(audit / 'completed.json', {**start, 'state': 'NEEDS_OPERATOR'})
    b.canonical_source = lambda sha: root if sha == m.TARGET else pytest.fail('wrong source')
    b._retired_history = lambda: {}
    b._assert_known_activity = lambda history, sha: None
    b._archives = lambda sha: []
    b.validate_install = lambda sha, expiry, key, now: None
    b.key_lines = lambda expiry, *keys: ['fixed synthetic-cloud', 'fixed synthetic-loopback']
    process_checks, lock_checks = [], []
    b._recovery_process_proof = lambda: process_checks.append(True)
    monkeypatch.setattr(m, 'assert_acknowledgement_ssh_sessions', lambda: None)
    adapter = m.make_adapter(root, b, server, helpers, 'b' * 40, m.TARGET, m.OPERATION,
                             lambda: lock_checks.append(True))
    revision_checks = []
    monkeypatch.setattr(adapter.reset, '_revision_proof', lambda sha, source, bootstrap: revision_checks.append(sha))
    monkeypatch.setattr(adapter.r, '_http_probes', lambda: None)
    original_load = m.load
    monkeypatch.setattr(m, 'load', lambda path, name: maintenance if name == 'ack_environment_reader' else original_load(path, name))
    # Execute real service reader/stability loop with synthetic systemd/proc.
    adapter.p.proc = tmp_path / 'proc'
    adapter.p.cgroup = tmp_path / 'cgroup'
    adapter.p.proc.mkdir()
    adapter.p.cgroup.mkdir()
    units = ['health-backend.socket', 'health-backend.service', 'celery-worker.service', 'celery-beat.service']
    for index, unit in enumerate(units):
        pid = str(100 + index)
        process = adapter.p.proc / pid
        process.mkdir()
        (process / 'stat').write_text(pid + ' (synthetic) ' + ' '.join(['1'] * 20))
        (process / 'environ').write_bytes(b'HEALTH_EVIDENCE_RUNTIME_ENABLED=false\0')
        group = adapter.p.cgroup / unit
        group.mkdir()
        (group / 'cgroup.procs').write_text(pid + '\n')
    def systemctl(argv, **kwargs):
        if argv[1] == 'list-jobs':
            return SimpleNamespace(stdout=b'')
        assert argv[1] == 'show'
        unit, prop = argv[2], argv[3].split('=', 1)[1]
        values = {'ActiveState': 'active', 'SubState': 'listening' if unit.endswith('.socket') else 'running',
                  'MainPID': str(100 + units.index(unit)), 'NRestarts': '0', 'ActiveEnterTimestampMonotonic': '1',
                  'ControlGroup': '/' + unit, 'Result': 'success', 'RestartUSec': '5s'}
        return SimpleNamespace(stdout=values[prop])
    monkeypatch.setattr(m.subprocess, 'run', systemctl)
    clock = [0]
    monkeypatch.setattr(adapter.r, 'time', SimpleNamespace(monotonic=lambda: clock[0], sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds)))
    result = adapter.inspect()
    assert result['old_sha'] == m.TARGET and result['operation_id'] == m.OPERATION
    assert result['original_outcome'] == 'UNKNOWN'
    assert result['lease'] == {'state': 'ABSENT_NOT_AUTHORITY'}
    assert result['original']['maintenance']['completed.json']['sha256']
    assert len(result['services']) == 4
    assert result['config']['authorized-release.json']['sha256']
    assert revision_checks == [m.TARGET, m.TARGET]
    assert process_checks and lock_checks
    assert not adapter.record.exists()
    # Both real receipt readers remain active on subsequent inspect.
    write(operation / 'completed.json', {'sha': m.TARGET, 'operation_id': m.OPERATION, 'state': 'SUCCEEDED'})
    with pytest.raises(helpers.ClosureError, match='unaccepted'):
        adapter.inspect()


def ssh_fixture(tmp_path, m):
    proc = tmp_path / 'synthetic-proc'
    proc.mkdir()
    def add(pid, ppid, *, argv=b'ordinary\0', start='10', uid='0', tty='0'):
        entry = proc / str(pid)
        entry.mkdir()
        fields = ['S', str(ppid), '1', '1', tty] + ['0'] * 14 + [start]
        (entry / 'stat').write_text(str(pid) + ' (synthetic) ' + ' '.join(fields))
        (entry / 'cmdline').write_bytes(argv)
        (entry / 'status').write_text('Uid:\t' + '\t'.join([uid] * 4) + '\n')
        (entry / 'fd').mkdir()
        return entry
    add(900, 1)
    known = add(3202404, 1, argv=b'sshd: root@notty\0', start='2816083071')
    (known / 'fd' / '5').symlink_to('socket:[8877]')
    net = proc / 'net'
    net.mkdir()
    header = 'sl local_address rem_address st tx_queue rx_queue tr tm->when retrnsmt uid timeout inode\n'
    (net / 'tcp').write_text(header + '0: 0100007F:13A6 00000000:0000 0A 0:0 00:0 0 0 0 8877\n')
    (net / 'tcp6').write_text(header)
    return proc, known, add


def test_known_chatlog_session_is_only_specific_exception(tmp_path, monkeypatch):
    m = load()
    proc, known, add = ssh_fixture(tmp_path, m)
    monkeypatch.setattr(m.os, 'getpid', lambda: 900)
    calls = []
    monkeypatch.setattr(m, 'verify_chatlog_authentication', lambda p: calls.append(p))
    m.assert_acknowledgement_ssh_sessions(proc)
    assert len(calls) == 2
    add(111, 1, argv=b'sshd: someone@notty\0')
    with pytest.raises(m.AcknowledgementError, match='other SSH'):
        m.assert_acknowledgement_ssh_sessions(proc)


@pytest.mark.parametrize('change', ['pid_reuse', 'uid', 'tty', 'nonloopback', 'wrong_port', 'missing_socket', 'child'])
def test_chatlog_exception_rejects_changed_identity_or_listener(tmp_path, monkeypatch, change):
    m = load()
    proc, known, add = ssh_fixture(tmp_path, m)
    monkeypatch.setattr(m.os, 'getpid', lambda: 900)
    monkeypatch.setattr(m, 'verify_chatlog_authentication', lambda p: None)
    if change == 'pid_reuse':
        (known / 'stat').write_text((known / 'stat').read_text().replace('2816083071', '2816083072'))
    elif change == 'uid':
        (known / 'status').write_text('Uid:\t1000\t1000\t1000\t1000\n')
    elif change == 'tty':
        raw = (known / 'stat').read_text().split()
        raw[6] = '1'
        (known / 'stat').write_text(' '.join(raw))
    elif change in {'nonloopback', 'wrong_port'}:
        tcp = proc / 'net/tcp'
        tcp.write_text(tcp.read_text().replace('0100007F:13A6', '00000000:13A6' if change == 'nonloopback' else '0100007F:13A7'))
    elif change == 'missing_socket':
        (known / 'fd/5').unlink()
    elif change == 'child':
        add(1000, 3202404)
    with pytest.raises(m.AcknowledgementError):
        m.assert_acknowledgement_ssh_sessions(proc)


def test_chatlog_disappearance_is_not_excused(tmp_path, monkeypatch):
    m = load()
    proc, known, add = ssh_fixture(tmp_path, m)
    monkeypatch.setattr(m.os, 'getpid', lambda: 900)
    def disappear(p):
        (known / 'stat').unlink()
    monkeypatch.setattr(m, 'verify_chatlog_authentication', disappear)
    with pytest.raises(FileNotFoundError):
        m.assert_acknowledgement_ssh_sessions(proc)


@pytest.mark.parametrize('change', [None, 'fingerprint', 'boot', 'pid', 'time', 'uid', 'duplicate', 'missing'])
def test_chatlog_fingerprint_requires_actual_exact_journal_event(tmp_path, monkeypatch, change):
    from types import SimpleNamespace
    m = load()
    boot_path = tmp_path / 'sys/kernel/random'
    boot_path.mkdir(parents=True)
    (boot_path / 'boot_id').write_text('12345678-1234-1234-1234-123456789012\n')
    event = {'_PID': m.CHATLOG_PID, '_UID': '0', '_BOOT_ID': '12345678123412341234123456789012',
             '__REALTIME_TIMESTAMP': m.CHATLOG_AUTH_TIME,
             'MESSAGE': 'Accepted publickey for root from 192.0.2.1 port 1234 ssh2: ED25519 ' + m.CHATLOG_KEY}
    if change == 'fingerprint':
        event['MESSAGE'] += 'bad'
    elif change == 'boot':
        event['_BOOT_ID'] = 'f' * 32
    elif change == 'pid':
        event['_PID'] = '999'
    elif change == 'time':
        event['__REALTIME_TIMESTAMP'] = '1'
    elif change == 'uid':
        event['_UID'] = '1000'
    rows = [] if change == 'missing' else [event, event] if change == 'duplicate' else [event]
    def journal(argv, **kwargs):
        assert argv[0] == '/usr/bin/journalctl'
        assert '--boot' in argv and '_PID=' + m.CHATLOG_PID in argv
        return SimpleNamespace(stdout=b'\n'.join(json.dumps(row).encode() for row in rows))
    monkeypatch.setattr(m.subprocess, 'run', journal)
    if change is None:
        m.verify_chatlog_authentication(tmp_path)
    else:
        with pytest.raises(m.AcknowledgementError):
            m.verify_chatlog_authentication(tmp_path)


@pytest.mark.parametrize('filename,function', [('review_maintenance_acknowledgement.py', 'account_child'), ('trusted_review_briefing_repair.py', 'database_child')])
def test_account_probe_loads_verified_dependencies_before_parsing_environment(filename, function):
    """Exercise the real child prefix under -I/-S, without accounts or a DB."""
    import ast
    import subprocess
    import sys
    source = Path(__file__).with_name(filename).read_text()
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    first = next(i for i, n in enumerate(fn.body) if isinstance(n, ast.Expr) and ast.unparse(n).startswith('reset._assert_isolated_search_path'))
    last = next(i for i, n in enumerate(fn.body) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'environment' for t in n.targets))
    prefix = '\n'.join(ast.unparse(n) for n in fn.body[first:last + 1])
    # Resolve the project's test virtualenv rather than system interpreter path.
    site = str(Path(sys.prefix) / 'lib' / ('python' + str(sys.version_info.major) + '.' + str(sys.version_info.minor)) / 'site-packages')
    prefix = prefix.replace('/opt/health-app/backend/venv/lib/python3.12/site-packages', site)
    script = "import sys\nfrom types import SimpleNamespace\nverified=[]\ndef parse(raw):\n from dotenv.parser import parse_stream\n assert verified == [True]\n return list(parse_stream(__import__('io').StringIO(raw)))\nreset=SimpleNamespace(_assert_isolated_search_path=lambda: None,_validate_production=lambda *a: verified.append(True),_parse_maintenance_environment=parse)\nserver=SimpleNamespace(read_production_env=lambda: 'SYNTHETIC=yes')\nold_sha=TARGET=target=b=None\n" + prefix + "\nassert environment[0].value == 'yes'"
    result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_reconcile_failed_ack_preflights_account_before_durable_intent(tmp_path):
    m, a = load(), Adapter(tmp_path)
    a.inspect_account = lambda key: (_ for _ in ()).throw(ModuleNotFoundError('synthetic'))
    with pytest.raises(ModuleNotFoundError):
        m.reconcile_failed_ack(a, accept_unknown=True, evidence_sha256=m.digest(a.evidence))
    assert not a.record.exists()


def test_reconcile_failed_ack_records_separate_audit_without_authority(tmp_path):
    m, a = load(), Adapter(tmp_path)
    a.inspect_account = lambda key: a.account.copy()
    original = a.original.read_bytes()
    inspected = m.reconcile_failed_ack(a)
    assert inspected['state'] == 'RECONCILIATION_INSPECTED_ONLY'
    assert not a.record.exists()
    result = m.reconcile_failed_ack(a, accept_unknown=True, evidence_sha256=inspected['evidence_sha256'])
    assert result['state'] == 'FAILED_ACK_RECONCILED_AUDIT_ONLY'
    complete = json.loads((a.record / 'completed.json').read_text())
    assert not any(complete['authority'].values())
    assert complete['original_outcome'] == 'UNKNOWN'
    assert not complete['historical_no_write_proven']
    assert a.original.read_bytes() == original
    with pytest.raises(m.AcknowledgementError, match='no retry'):
        m.reconcile_failed_ack(a)


@pytest.mark.parametrize('fault', ['missing_acceptance', 'stale', 'snapshot', 'evidence', 'post_intent'])
def test_reconciliation_fails_closed(tmp_path, fault):
    m, a = load(), Adapter(tmp_path)
    calls = []
    def account(key):
        calls.append(key)
        return {'snapshot': len(calls) if fault == 'snapshot' else 1}
    a.inspect_account = account
    if fault == 'evidence':
        a.change_at = 2
    if fault == 'post_intent':
        a.change_at = 4
    with pytest.raises(m.AcknowledgementError):
        m.reconcile_failed_ack(a, accept_unknown=fault != 'missing_acceptance',
            evidence_sha256='0' * 64 if fault == 'stale' else m.digest(a.evidence))
    assert not (a.record / 'completed.json').exists()
    assert a.record.exists() == (fault == 'post_intent')


@pytest.mark.parametrize('changed', [None, 'hash', 'operator', 'digest', 'accepted'])
def test_failed_ack_is_bound_to_exact_original(tmp_path, changed):
    from types import SimpleNamespace
    m = load()
    evidence = {'closing_sha':m.FAILED_ACK_OPERATOR, 'old_sha':m.TARGET, 'operation_id':m.OPERATION}
    if changed == 'operator':
        evidence['closing_sha'] = 'a' * 40
    intent = {'evidence':evidence,'evidence_sha256':m.digest(evidence),'original_outcome':'UNKNOWN','accept_unknown_review_writes':True}
    if changed == 'digest':intent['evidence_sha256'] = '0' * 64
    if changed == 'accepted':intent['accept_unknown_review_writes'] = False
    inventory = {'intent.json':{'sha256':'0' * 64 if changed == 'hash' else m.FAILED_ACK_INTENT}}
    b = SimpleNamespace(_inventory=lambda *a:inventory, _read_json=lambda *a:intent)
    if changed is None:
        assert m.failed_ack_evidence(b) == (inventory, evidence)
    else:
        with pytest.raises(m.AcknowledgementError):m.failed_ack_evidence(b)
