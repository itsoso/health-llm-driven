"""Exercise actual predeploy production checks with isolated local observations."""
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_bootstrap_trusted_release import load_bootstrap, SHA

PRODUCTION = 'c' * 40


def production_fixture(monkeypatch, tmp_path):
    b = load_bootstrap()
    monkeypatch.setattr(b, 'secure', lambda *a, **k: None)
    monkeypatch.setattr(b, 'STATE', tmp_path / 'state')
    monkeypatch.setattr(b, 'PROC', tmp_path / 'proc')
    monkeypatch.setattr(b.time, 'time', lambda: 10000)
    monkeypatch.setattr(b.time, 'sleep', lambda _: None)
    b.PROC.mkdir()
    (b.PROC / 'uptime').write_text('1000 0\n')
    workspace = b.STATE / SHA
    workspace.mkdir(parents=True)
    started = workspace / 'started.json'
    started.write_text('{}')
    os.utime(started, (9900, 9900))
    live = 'DECISION_MODE=on\nDEPLOY_SERVER=old\nDEPLOY_PATH=old\n'
    (workspace / 'deployment.env').write_text('DECISION_MODE=on\nDEPLOY_SERVER=health\nDEPLOY_PATH=/opt/health-app\n')
    server = SimpleNamespace(read_production_env=lambda: live, invitation_only_config=lambda x: x)
    # Real terminal-marker parser, not a mock of its result.
    path = Path(__file__).parents[1] / 'backend/scripts/runtime_state_release_transaction.py'
    spec = importlib.util.spec_from_file_location('predeploy_runtime_test', path)
    runtime = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, runtime)
    spec.loader.exec_module(runtime)
    root = tmp_path / 'runtime'
    root.mkdir()
    transaction_id = hashlib.sha256(f'{SHA}:{PRODUCTION}'.encode()).hexdigest()[:32]
    marker = root / 'runtime-state-terminal.json'
    marker.write_text(json.dumps(dict(version=1, old_sha=SHA, candidate_sha=PRODUCTION,
        terminal_sha=PRODUCTION, transaction_id=transaction_id,
        reap_name=f'runtime-state-transaction.reap-{transaction_id}', target='candidate',
        phase='COMMITTED', result='finalized')))
    values = {'service': {'ActiveEnterTimestampMonotonic': '1000000', 'NRestarts': '0',
        'processes': {'123': '100'}}}
    observations = []
    def absent(*paths):
        if any(os.path.lexists(p) for p in paths):
            raise b.BootstrapError('conflicting runtime state')
    proof = SimpleNamespace(runtime_root=root, runtime=runtime, systemd=None,
        _absent=absent, running_services_snapshot=lambda: json.loads(json.dumps(values)))
    def factory(source, reader, server, old_sha, production_sha, token):
        assert reader.secure is b.secure
        assert not hasattr(reader, 'rotate')
        observations.append('readonly')
        return proof
    monkeypatch.setattr(b, '_predeploy_module', lambda _, name: server if name == 'trusted_release_server.py'
        else SimpleNamespace(RecoveryProof=factory, UNITS=('socket', 'backend.service', 'worker.service', 'beat.service')))
    monkeypatch.setattr(b, '_run', lambda args, **kw: SimpleNamespace(stdout='200'))
    monkeypatch.setattr(b, 'canonical_source', lambda _: tmp_path)
    monkeypatch.setattr(b, '_predeploy_unit_configuration', lambda *args: {'canonical': 'stable'})
    return b, workspace, root, marker, server, proof, values, observations


def test_predeploy_live_proof_uses_real_terminal_and_deterministic_environment(monkeypatch, tmp_path):
    b, w, root, marker, server, proof, values, calls = production_fixture(monkeypatch, tmp_path)
    result = b._predeploy_production_proof(SHA, PRODUCTION, tmp_path)
    assert result['health_http'] == 200
    assert result['candidate_environment_sha256'] == hashlib.sha256((w / 'deployment.env').read_bytes()).hexdigest()
    assert calls == ['readonly']
    assert not (root / 'runtime-state-transaction').exists()
    assert set(root.iterdir()) == {marker}


@pytest.mark.parametrize('damage', ['random_env', 'candidate_env', 'marker_sha', 'marker_fields',
    'transaction', 'preparing', 'reap', 'activation', 'restart', 'child', 'health', 'stable_services', 'stable_env', 'stable_units', 'activation_override'])
def test_predeploy_live_proof_blocks_unproven_production(monkeypatch, tmp_path, damage):
    b, w, root, marker, server, proof, values, _ = production_fixture(monkeypatch, tmp_path)
    if damage == 'random_env': server.read_production_env = lambda: 'SECRET=value\n'
    elif damage == 'candidate_env': (w / 'deployment.env').write_text('different')
    elif damage in ('marker_sha', 'marker_fields'):
        data = json.loads(marker.read_text())
        data['terminal_sha' if damage == 'marker_sha' else 'transaction_id'] = 'f' * 40
        marker.write_text(json.dumps(data))
    elif damage in ('transaction', 'preparing', 'reap'):
        name = {'transaction': 'runtime-state-transaction', 'preparing': '.runtime-state-transaction.preparing',
                'reap': 'runtime-state-transaction.reap-unknown'}[damage]
        (root / name).mkdir()
    elif damage == 'activation': values['service']['ActiveEnterTimestampMonotonic'] = '900000000'
    elif damage == 'restart': values['service']['NRestarts'] = '1'
    elif damage == 'child': values['service']['processes']['123'] = str(1000 * os.sysconf('SC_CLK_TCK'))
    elif damage == 'health': monkeypatch.setattr(b, '_run', lambda *a, **k: SimpleNamespace(stdout='503'))
    elif damage == 'stable_services': monkeypatch.setattr(b.time, 'sleep', lambda _: values['service'].update(MainPID='changed'))
    elif damage == 'stable_env': monkeypatch.setattr(b.time, 'sleep', lambda _: setattr(server, 'read_production_env', lambda: 'changed'))
    elif damage == 'stable_units': monkeypatch.setattr(b.time, 'sleep', lambda _: monkeypatch.setattr(b, '_predeploy_unit_configuration', lambda *args: {'canonical': 'changed'}))
    else:
        original = proof._absent
        def absent(*paths):
            if any(p.name == '90-reva-health-evidence-activation.conf' for p in paths): raise b.BootstrapError('activation override remains')
            original(*paths)
        proof._absent = absent
    with pytest.raises((b.BootstrapError, proof.runtime.TransactionError)):
        b._predeploy_production_proof(SHA, PRODUCTION, tmp_path)


@pytest.mark.parametrize('damage', [None, 'mismatch', 'drift'])
def test_predeploy_loopback_private_key_is_bound_without_exposing_it(monkeypatch, tmp_path, damage):
    b = load_bootstrap()
    monkeypatch.setattr(b, 'CONFIG', tmp_path)
    monkeypatch.setattr(b, 'secure', lambda *a, **k: None)
    (tmp_path / 'loopback.key').write_text('private fixture')
    (tmp_path / 'loopback.pub').write_text('ssh-ed25519 public\n')
    calls = []
    def run(args, **kw):
        calls.append(args)
        if damage == 'drift': (tmp_path / 'loopback.key').write_text('changed')
        return SimpleNamespace(stdout='ssh-ed25519 different' if damage == 'mismatch' else 'ssh-ed25519 public\n')
    monkeypatch.setattr(b, '_run', run)
    if damage:
        with pytest.raises(b.BootstrapError, match='identity differs'): b._predeploy_loopback_key_proof()
    else: b._predeploy_loopback_key_proof()
    assert calls == [['/usr/bin/ssh-keygen', '-y', '-f', str(tmp_path / 'loopback.key')]]


def test_predeploy_stability_spans_service_restart_delay(monkeypatch, tmp_path):
    b, _, _, _, _, _, values, _ = production_fixture(monkeypatch, tmp_path)
    def delayed_restart(seconds):
        if seconds >= 5: values['service']['NRestarts'] = '1'
    monkeypatch.setattr(b.time, 'sleep', delayed_restart)
    with pytest.raises(b.BootstrapError, match='stability window'):
        b._predeploy_production_proof(SHA, PRODUCTION, tmp_path)


def unit_fixture(monkeypatch, tmp_path):
    b, _, _, _, _, proof, _, _ = production_fixture(monkeypatch, tmp_path)
    path_type = Path
    def mapped(value):
        value = path_type(value)
        return tmp_path / value.relative_to('/') if str(value).startswith(('/etc/', '/var/')) else value
    monkeypatch.setattr(b, 'Path', mapped)
    source = Path(__file__).parents[1]
    transaction = proof.runtime.ReleaseTransaction(SimpleNamespace(), None)
    observations = {}
    for unit in ('health-backend.socket', 'health-backend.service', 'celery-worker.service', 'celery-beat.service'):
        base = mapped('/etc/systemd/system') / unit
        base.parent.mkdir(parents=True, exist_ok=True)
        base.write_text('root managed base')
        os.utime(base, (9800, 9800))
        fields = dict(NeedDaemonReload='no', FragmentPath=str(base), DropInPaths='', ExecStart='', EnvironmentFiles='', Listen='')
        if unit.endswith('.socket'): fields['Listen'] = '127.0.0.1:8000 (Stream)'
        else:
            parent = Path(str(base) + '.d')
            parent.mkdir()
            paths = []
            for name in ('80-reva-health-evidence-runtime.conf', '90-runtime-state.conf'):
                p = parent / name
                p.write_text('root managed dropin')
                os.utime(p, (9800, 9800))
                paths.append(str(p))
            fields['DropInPaths'] = ' '.join(paths)
            command_path = (source / 'infra/systemd' / unit if unit == 'celery-worker.service' else
                source / 'infra/systemd/dropins' / ('health-backend-runtime-state.conf' if unit == 'health-backend.service' else 'celery-beat-runtime-state.conf'))
            import re
            command = re.findall(r'^ExecStart=(.+)$', command_path.read_text(), re.M)[0]
            fields['ExecStart'] = 'path=' + command.split()[0] + '\nargv[]=' + command + '\nignore_errors=no'
            fields['EnvironmentFiles'] = '/opt/health-app/backend/.env (ignore_errors=no)\n/var/lib/reva-health-evidence-runtime/enabled.env (ignore_errors=yes)'
        observations[unit] = fields
    proof.systemd = SimpleNamespace(show=lambda unit, name: observations[unit][name])
    # production_fixture mocks this helper; use a fresh module's actual function.
    actual = load_bootstrap()._predeploy_unit_configuration
    actual.__globals__.update(Path=mapped, secure=b.secure)
    return actual, proof, transaction, source, observations


def test_predeploy_effective_unit_snapshot_is_canonical_and_readonly(monkeypatch, tmp_path):
    function, proof, transaction, source, observations = unit_fixture(monkeypatch, tmp_path)
    result = function(proof, transaction, source, 9900)
    assert set(result) == set(observations)
    assert result['health-backend.service']['effective']['ExecStart'] == observations['health-backend.service']['ExecStart']


@pytest.mark.parametrize('damage', ['command', 'reload', 'fragment', 'dropin', 'environment', 'socket', 'recent_file'])
def test_predeploy_effective_unit_rejects_replaced_configuration(monkeypatch, tmp_path, damage):
    function, proof, transaction, source, observations = unit_fixture(monkeypatch, tmp_path)
    fields = observations['health-backend.service']
    if damage == 'command': fields['ExecStart'] = '{ path=/bin/false ; argv[]=/bin/false ; ignore_errors=no ; }'
    elif damage == 'reload': fields['NeedDaemonReload'] = 'yes'
    elif damage == 'fragment': fields['FragmentPath'] = '/unreviewed/unit'
    elif damage == 'dropin': fields['DropInPaths'] += ' /unreviewed/dropin'
    elif damage == 'environment': fields['EnvironmentFiles'] += ' /unreviewed/env (ignore_errors=no)'
    elif damage == 'socket': observations['health-backend.socket']['Listen'] = '0.0.0.0:8000 (Stream)'
    else: os.utime(fields['FragmentPath'], (9901, 9901))
    with pytest.raises((function.__globals__['BootstrapError'], proof.runtime.TransactionError)): function(proof, transaction, source, 9900)
