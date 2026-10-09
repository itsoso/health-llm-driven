"""Real filesystem crash/replay checks with no production credentials or network."""
import importlib.util
import json
from pathlib import Path

import pytest

SHA = 'a' * 40
UUID = 'a1234567-1234-1234-1234-123456789abc'


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def state(tmp_path, monkeypatch):
    server = load('trusted_release_server')
    ota = load('trusted_ota_server')
    contract = load('trusted_ota')
    monkeypatch.setattr(server, 'STATE', tmp_path)
    monkeypatch.setattr(ota, 'STATE', tmp_path)
    monkeypatch.setattr(server, 'BUSINESS_LEASE', tmp_path / 'business-lease')
    monkeypatch.setattr(server, 'secure_path', lambda *a, **k: None)
    monkeypatch.setattr(server, 'validate_metadata', lambda *a, **k: None)
    monkeypatch.setattr(server, '_assert_deployment_window', lambda p: None)
    monkeypatch.setattr(server, 'validate_loopback', lambda p: None)
    monkeypatch.setattr(server, 'testflight_backend_proof', lambda p, lease: {'sha': SHA, 'production_sha': SHA, 'state': 'COMPATIBLE'})
    (tmp_path / SHA).mkdir()
    (tmp_path / SHA / 'completed.json').write_text(json.dumps({'sha': SHA, 'state': 'SUCCEEDED'}))
    proof = {'launch': contract.digest(b'bundle'), 'assets': [contract.digest(b'asset')]}
    intent = {'sha': SHA, 'project': contract.PROJECT, 'runtime': contract.RUNTIME, 'platform': 'ios', 'channel': 'production', 'artifact': proof, 'branch_id': UUID, 'branch_name': 'production'}
    manifest = {'id': UUID, 'runtimeVersion': contract.RUNTIME, 'launchAsset': {'hash': proof['launch']}, 'assets': [{'hash': proof['assets'][0]}], 'extra': {'eas': {'projectId': contract.PROJECT}}}
    monkeypatch.setattr(ota, 'manifest', lambda c: manifest)
    return server, ota, contract, intent


def test_claim_is_single_use_and_holds_business_lease_until_proven_finish(state):
    s, o, c, value = state
    assert o.claim(s, c, {'sha': SHA}, value)['state'] == 'CLAIMED'
    assert s.BUSINESS_LEASE.exists()
    with pytest.raises(Exception):
        o.claim(s, c, {'sha': SHA}, value)
    with pytest.raises(s.LaunchError):
        s.assert_ota_history()
    receipt = {'sha': SHA, 'group_id': UUID, 'update_id': UUID}
    assert o.finish(s, c, SHA, receipt)['state'] == 'SUCCEEDED'
    assert not s.BUSINESS_LEASE.exists()
    s.assert_ota_history()
    assert o.finish(s, c, SHA, receipt)['state'] == 'SUCCEEDED'
    with pytest.raises(Exception):
        o.claim(s, c, {'sha': SHA}, value)


def test_manifest_mismatch_keeps_original_lease_and_no_terminal(state, monkeypatch):
    s, o, c, value = state
    o.claim(s, c, {'sha': SHA}, value)
    identity = s.BUSINESS_LEASE.stat().st_ino
    monkeypatch.setattr(o, 'manifest', lambda c: {})
    with pytest.raises(ValueError):
        o.finish(s, c, SHA, {'sha': SHA, 'group_id': UUID, 'update_id': UUID})
    assert s.BUSINESS_LEASE.stat().st_ino == identity
    assert not (s.STATE / 'ota' / SHA / 'verified.json').exists()


@pytest.mark.parametrize('failure', ['verified.json', 'completed.json'])
def test_fsync_boundary_recovery_preserves_original_lease_and_cannot_republish(state, monkeypatch, failure):
    s, o, c, value = state
    o.claim(s, c, {'sha': SHA}, value)
    inode = s.BUSINESS_LEASE.stat().st_ino
    receipt = {'sha': SHA, 'group_id': UUID, 'update_id': UUID}
    original = o.write
    def crash(server, path, data):
        if path.name == failure:
            if failure == 'verified.json':
                original(server, path, data)
            raise OSError('simulated crash')
        original(server, path, data)
    monkeypatch.setattr(o, 'write', crash)
    with pytest.raises(OSError):
        o.finish(s, c, SHA, receipt)
    monkeypatch.setattr(o, 'write', original)
    # Recovery must not depend on network or current auth once receipt verified.
    monkeypatch.setattr(o, 'manifest', lambda c: (_ for _ in ()).throw(AssertionError('unexpected network')))
    assert o.finish(s, c, SHA, receipt)['state'] == 'SUCCEEDED'
    assert s.BUSINESS_LEASE.with_name(s.BUSINESS_LEASE.name + '.ota-' + SHA).stat().st_ino == inode
    s.assert_ota_history()


def test_completed_replay_never_releases_someone_elses_lease(state):
    s, o, c, value = state
    o.claim(s, c, {'sha': SHA}, value)
    receipt = {'sha': SHA, 'group_id': UUID, 'update_id': UUID}
    o.finish(s, c, SHA, receipt)
    s.BUSINESS_LEASE.mkdir()
    (s.BUSINESS_LEASE / 'other').write_text('unrelated')
    o.finish(s, c, SHA, receipt)
    assert (s.BUSINESS_LEASE / 'other').read_text() == 'unrelated'
    with pytest.raises(ValueError):
        o.finish(s, c, SHA, {**receipt, 'group_id': 'b' + UUID[1:]})


def test_partial_claim_and_archive_tampering_block_history(state, monkeypatch):
    s, o, c, value = state
    monkeypatch.setattr(s, 'testflight_backend_proof', lambda *a, **k: (_ for _ in ()).throw(ValueError('backend changed')))
    with pytest.raises(ValueError):
        o.claim(s, c, {'sha': SHA}, value)
    with pytest.raises(s.LaunchError):
        s.assert_ota_history()
    with pytest.raises(Exception):
        o.finish(s, c, SHA, {'sha': SHA, 'group_id': UUID, 'update_id': UUID})
    assert s.BUSINESS_LEASE.exists()


def envelope(parts):
    raw = b''
    for name, payload in parts:
        raw += (b'--ExpoBoundary\r\nContent-Disposition: form-data; name="' + name.encode()
                + b'"\r\nContent-Type: application/json; charset=utf-8\r\n\r\n' + payload + b'\r\n')
    return 'multipart/mixed; boundary="ExpoBoundary"', raw + b'--ExpoBoundary--\r\n'


def test_manifest_parser_accepts_actual_expo_multipart_structure():
    o, c = load('trusted_ota_server'), load('trusted_ota')
    ct, raw = envelope([('manifest', b'{"id":"test"}'), ('extensions', b'{}')])
    assert o.parse_manifest(c, ct, raw) == {'id': 'test'}


def test_manifest_request_uses_client_identity_and_retains_protocol_tls_guards(monkeypatch):
    o, c = load('trusted_ota_server'), load('trusted_ota')
    ct, raw = envelope([('manifest', b'{"id":"test"}')])
    class Response:
        status = 200
        headers = {'Content-Type': ct}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            assert limit == 2_000_001
            return raw
    class Client:
        def open(self, request, *, timeout):
            assert timeout == 20
            assert request.full_url == 'https://u.expo.dev/' + c.PROJECT
            assert request.get_header('User-agent') == 'reva-trusted-ota/1.0'
            assert request.get_header('Expo-protocol-version') == '1'
            assert request.get_header('Expo-runtime-version') == c.RUNTIME
            assert request.get_header('Expo-channel-name') == 'production'
            assert request.get_header('Authorization') is None
            return Response()
    def opener(*handlers):
        assert handlers[0].proxies == {}
        with pytest.raises(ValueError):
            handlers[1].redirect_request(None, None, None, None, None, None)
        assert handlers[2]._context.verify_mode == o.ssl.CERT_REQUIRED
        assert handlers[2]._context.check_hostname
        return Client()
    monkeypatch.setattr(o.urllib.request, 'build_opener', opener)
    assert o.manifest(c) == {'id': 'test'}


@pytest.mark.parametrize('parts', [
    [('manifest', b'{}'), ('manifest', b'{}')],
    [('directive', b'{}')],
    [('manifest', b'{"id":"a","id":"b"}')],
])
def test_manifest_parser_rejects_ambiguous_or_missing_manifests(parts):
    o, c = load('trusted_ota_server'), load('trusted_ota')
    with pytest.raises(ValueError):
        o.parse_manifest(c, *envelope(parts))


def test_manifest_parser_rejects_truncation_and_oversize():
    o, c = load('trusted_ota_server'), load('trusted_ota')
    ct, raw = envelope([('manifest', b'{}')])
    for bad in (raw[:-22], b'a' * 2000001):
        with pytest.raises(ValueError):
            o.parse_manifest(c, ct, bad)


def test_archive_rename_stays_on_lease_filesystem_and_history_survives_reboot(state, monkeypatch):
    import shutil
    s, o, c, value = state
    o.claim(s, c, {'sha': SHA}, value)
    original = o.os.rename
    renamed = []
    def same_filesystem_only(source, target):
        assert source.parent == target.parent == s.BUSINESS_LEASE.parent
        renamed.append(target)
        return original(source, target)
    monkeypatch.setattr(o.os, 'rename', same_filesystem_only)
    receipt = {'sha': SHA, 'group_id': UUID, 'update_id': UUID}
    o.finish(s, c, SHA, receipt)
    assert len(renamed) == 1
    shutil.rmtree(renamed[0])  # /run may disappear after a reboot.
    s.assert_ota_history()
    assert o.finish(s, c, SHA, receipt)['state'] == 'SUCCEEDED'
    (s.STATE / 'ota' / SHA / 'released-lease' / 'token').write_text('tampered')
    with pytest.raises(s.LaunchError):
        s.assert_ota_history()


@pytest.mark.parametrize('held', ['launcher', 'build'])
def test_ota_requires_both_original_locks(state, held):
    import fcntl
    import os
    from types import SimpleNamespace
    s, o, c, value = state
    launcher = s.STATE / 'launcher.lock'
    build = s.STATE / SHA / 'build.lock'
    launcher.touch(mode=0o600)
    build.touch(mode=0o600)
    def original(path, fd):
        assert path.stat().st_ino == os.fstat(fd).st_ino
    bootstrap = SimpleNamespace(_assert_original_lock=original)
    with (launcher if held == 'launcher' else build).open('r+') as other:
        fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            with o.transaction_locks(s, bootstrap, SHA, create=False):
                pytest.fail('overlapping transaction admitted')
    with o.transaction_locks(s, bootstrap, SHA, create=False):
        pass


def test_ota_recovery_never_recreates_missing_original_build_lock(state):
    from types import SimpleNamespace
    s, o, c, value = state
    (s.STATE / 'launcher.lock').touch(mode=0o600)
    with pytest.raises(FileNotFoundError):
        with o.transaction_locks(s, SimpleNamespace(), SHA, create=False):
            pytest.fail('missing lock accepted')
    assert not (s.STATE / SHA / 'build.lock').exists()
