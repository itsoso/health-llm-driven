"""No-network tests for the unauthenticated fixed production transport probe."""
import importlib.util
import json
import socket
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location('transport', ROOT / 'scripts/trusted_runner_transport.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Peer:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.timeouts = []
        self.closed = False
    def settimeout(self, timeout):
        self.timeouts.append(timeout)
    def recv(self, size):
        value = next(self.chunks, b'')
        if isinstance(value, Exception):
            raise value
        return value
    def close(self):
        self.closed = True


def probe(monkeypatch, chunks):
    module = load()
    peer = Peer(chunks)
    calls = []
    monkeypatch.setattr(module.socket, 'create_connection', lambda address, timeout: calls.append((address, timeout)) or peer)
    monkeypatch.setattr(module.time, 'monotonic', lambda: 100.0)
    return module, peer, calls


def test_valid_fragmented_banner_is_read_only_bounded_and_not_authentication(monkeypatch, capsys):
    m, peer, calls = probe(monkeypatch, [b'SSH-', b'2.0-OpenSSH_private-fixture\r\n'])
    assert m.main([]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['stage'] == 'runner_transport'
    assert receipt['status'] == 'reachable'
    assert receipt['authenticated'] is False
    assert receipt['host_identity_verified'] is False
    assert receipt['elapsed_seconds'] == 0
    assert calls == [(('39.98.206.178', 22), 5.0)]
    assert peer.closed and all(0 < t <= 5 for t in peer.timeouts)
    assert 'OpenSSH' not in json.dumps(receipt)
    # Peer has no send/sendall API: any protocol/authentication write would fail.


@pytest.mark.parametrize('chunks', [[b'HTTP/1.1 200 OK\r\n'], [b'SSH-1.5-legacy\r\n'], [b'SSH-2.0-\r\n'], [b'SSH-2.0-secret\x00\r\n'], [b'SSH-2.0-' + b'x'*300], [b''], [socket.timeout('private-data')]])
def test_invalid_silent_or_oversized_peer_blocks_without_exposing_input(monkeypatch, capsys, chunks):
    m, peer, _ = probe(monkeypatch, chunks)
    assert m.main([]) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['status'] == 'blocked'
    assert receipt['authenticated'] is False
    assert receipt['host_identity_verified'] is False
    assert peer.closed
    assert 'private-data' not in json.dumps(receipt)
    assert 'secret' not in json.dumps(receipt)


def test_connect_error_is_redacted_and_attempted_once(monkeypatch, capsys):
    m = load()
    calls = []
    def connect(address, timeout):
        calls.append(address)
        raise OSError('credential-looking-fixture')
    monkeypatch.setattr(m.socket, 'create_connection', connect)
    assert m.main([]) == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['reason'] == 'connect_failed'
    assert 'credential-looking-fixture' not in json.dumps(receipt)
    assert calls == [('39.98.206.178',22)]


def test_deadline_covers_connect_and_banner(monkeypatch, capsys):
    m = load()
    peer = Peer([b'SSH-2.0-valid\r\n'])
    times = iter([100., 104., 105.1, 105.2])
    monkeypatch.setattr(m.time, 'monotonic', lambda: next(times,105.2))
    monkeypatch.setattr(m.socket, 'create_connection', lambda *args, **kwargs: peer)
    assert m.main([]) == 1
    assert json.loads(capsys.readouterr().out)['reason'] == 'deadline_exceeded'
    assert peer.closed


def test_cli_cannot_override_target_or_supply_credentials(monkeypatch):
    m = load()
    monkeypatch.setattr(m.socket, 'create_connection', lambda *a, **k: pytest.fail('network must not be reached'))
    for args in [['--host','other'], ['--key','fixture'], ['--timeout','900']]:
        with pytest.raises(SystemExit):
            m.main(args)


def test_workflow_transport_is_after_exact_gate_and_before_any_secret():
    workflow = yaml.safe_load((ROOT / '.github/workflows/trusted-release.yml').read_text())
    triggers = workflow.get('on', workflow.get(True))
    assert 'transport' in triggers['workflow_dispatch']['inputs']['target']['options']
    preflight = workflow['jobs']['preflight']
    steps = preflight['steps']
    index = next(i for i,s in enumerate(steps) if 'trusted_runner_transport.py' in s.get('run',''))
    assert index > 0
    assert 'trusted_release_gate.py' in steps[index-1]['run']
    assert 'secrets.' not in str(preflight)
    assert steps[index].get('continue-on-error') is not True
    assert '--host' not in steps[index]['run']
    assert '/usr/bin/env -i PATH=/usr/bin:/bin HOME=/root' in steps[index]['run']
    for name,job in workflow['jobs'].items():
        if name!='preflight':
            assert "inputs.target == 'transport'" not in job.get('if','')
    assert workflow['jobs']['build-permission']['needs'] == 'preflight'
    readiness = next(s for s in workflow['jobs']['build-permission']['steps'] if 'RELEASE_KEY' in s.get('env',{}))
    assert 'StrictHostKeyChecking=yes' in readiness['run']
    assert '--state CHECKED' in readiness['run']
