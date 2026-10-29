"""A pre-intent OTA failure closes once and can never authorize retry."""

import base64
import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

OFFICIAL_ARTIFACT_B64 = (
    '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'
)


def load_operator():
    path = Path(__file__).with_name('trusted_ota_preintent_retirement.py')
    spec = importlib.util.spec_from_file_location('ota_preintent_retirement_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeServer:
    def __init__(self, root):
        self.STATE = Path(root)

    def _write_private(self, path, raw):
        path.write_bytes(raw)

    def _read_private(self, path):
        return path.read_bytes()

    def _json(self, raw):
        return json.loads(raw)

    def _sync_directory(self, path):
        assert Path(path).is_dir()

    def secure_path(self, path, directory=False, private=False):
        path = Path(path)
        assert path.is_dir() if directory else path.is_file()


class FakeAdapter:
    def __init__(self, module, root):
        self.server = FakeServer(root)
        self.record = Path(root) / module.ROOT_NAME / module.FAILED_SHA
        self.calls = []
        self.evidence = {
            'failed_sha': module.FAILED_SHA,
            'closing_sha': 'a' * 40,
            'closure_operator_sha256': 'b' * 64,
            'installed_consumer': {'sha': 'a' * 40},
            'source_hashes': module.SOURCE_HASHES,
            'official': {'run': 'fixed'},
            'frontend_publication': {'state': 'FRONTEND_SUCCEEDED'},
            'production': {'sha': module.FAILED_SHA, 'state': 'SUCCEEDED'},
            'locks': {'launcher': [1, 2], 'build': [3, 4]},
            'ota_state_absent': True,
            'business_lease_absent': True,
        }

    def check_locks(self):
        self.calls.append('locks')

    def check_record_parent(self):
        self.calls.append('parent')

    def inspect(self):
        self.calls.append('inspect')
        return self.evidence


def test_close_is_two_phase_and_never_mutates_ota_or_lease(tmp_path):
    module = load_operator()
    adapter = FakeAdapter(module, tmp_path)
    inspected = module.close_transaction(adapter)
    assert inspected['state'] == 'INSPECTED_PREINTENT_OTA_FAILURE'
    result = module.close_transaction(adapter, inspected['evidence_sha256'])
    assert result['state'] == module.TERMINAL
    assert {p.name for p in adapter.record.iterdir()} == {'intent.json', 'completed.json'}
    assert not (tmp_path / 'ota' / module.FAILED_SHA).exists()
    assert not (tmp_path / 'health-app-release').exists()
    with pytest.raises(module.ClosureError, match='retry forbidden'):
        module.close_transaction(adapter, inspected['evidence_sha256'])


def test_close_refuses_changed_inspection(tmp_path):
    module = load_operator()
    adapter = FakeAdapter(module, tmp_path)
    inspected = module.close_transaction(adapter)
    adapter.evidence['business_lease_absent'] = False
    with pytest.raises(module.ClosureError, match='inspection evidence changed'):
        module.close_transaction(adapter, inspected['evidence_sha256'])
    assert not adapter.record.exists()


def artifact_bytes(module, entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, value in entries.items():
            archive.writestr(name, json.dumps(value, sort_keys=True, separators=(',', ':')))
    raw = stream.getvalue()
    raw_entries = {name: json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
                   for name, value in entries.items()}
    module.ENTRY_DIGESTS = {name: hashlib.sha256(value).hexdigest()
                            for name, value in raw_entries.items()}
    module.ARTIFACT_ZIP_SHA256 = hashlib.sha256(raw).hexdigest()
    return raw


def test_artifact_proves_claim_failure_before_vendor(monkeypatch):
    module = load_operator()
    claim = {'sha': module.FAILED_SHA, 'artifact': {'launch': 'x', 'assets': []}}
    preflight = {'sha': module.FAILED_SHA, 'mapping': {'branch_name': 'production'}}
    diagnostic = {'sha': module.FAILED_SHA, 'state': 'BLOCKED',
                  'phase': 'claim-ota', 'reason': 'command_failed'}
    raw = artifact_bytes(module, {'ota-claim.json': claim,
                                  'ota-preflight.json': preflight,
                                  'ota-diagnostic.json': diagnostic})
    assert module.validate_artifact(raw)['ota-diagnostic.json'] == diagnostic
    raw = artifact_bytes(module, {'ota-claim.json': claim,
                                  'ota-preflight.json': preflight,
                                  'ota-vendor-receipt.json': {'sha': module.FAILED_SHA}})
    with pytest.raises(module.ClosureError, match='unknown publication phase'):
        module.validate_artifact(raw)


def test_official_artifact_raw_entry_digests_are_fixed():
    module = load_operator()
    raw = base64.b64decode(OFFICIAL_ARTIFACT_B64, validate=True)
    assert len(raw) == module.ARTIFACT_SIZE
    assert hashlib.sha256(raw).hexdigest() == module.ARTIFACT_ZIP_SHA256
    entries = module.validate_artifact(raw)
    assert entries['ota-diagnostic.json'] == {
        'sha': module.FAILED_SHA, 'state': 'BLOCKED',
        'phase': 'claim-ota', 'reason': 'command_failed'}


def test_closure_requires_closure_aware_installed_executor(monkeypatch, tmp_path):
    module = load_operator()
    source = tmp_path / 'source'
    scripts = source / 'scripts'
    scripts.mkdir(parents=True)
    expected = b'closure-aware-executor\n'
    (scripts / 'trusted_release_server.py').write_bytes(expected)
    config = tmp_path / 'config'
    config.mkdir()
    installed = tmp_path / 'installed.py'
    installed.write_bytes(expected)
    sha = 'a' * 40
    executor_sha256 = hashlib.sha256(expected).hexdigest()
    policy = {'sha': sha, 'expires_at': 0, 'executor_sha256': executor_sha256}
    policy_path = config / 'authorized-release.json'
    policy_path.write_text(json.dumps(policy))

    class Bootstrap:
        CONFIG = config
        INSTALLED = installed

        @staticmethod
        def secure(*_args, **_kwargs):
            return None

        @staticmethod
        def _read_json(path):
            return json.loads(Path(path).read_text())

    class Server(FakeServer):
        @staticmethod
        def validate_policy(value, now):
            assert value['expires_at'] == 0 or value['expires_at'] > now

        @staticmethod
        def validate_metadata(*_args, **_kwargs):
            return None

    monkeypatch.setattr(module.subprocess, 'run', lambda *_a, **_kw:
                        SimpleNamespace(stdout=expected))
    server = Server(tmp_path)
    evidence = module.installed_consumer_evidence(Bootstrap, server, source, sha)
    assert evidence['executor_sha256'] == executor_sha256
    policy_path.write_text(json.dumps({**policy, 'sha': 'b' * 40}))
    with pytest.raises(module.ClosureError, match='closure-aware release authorization required'):
        module.installed_consumer_evidence(Bootstrap, server, source, sha)


def test_server_history_validates_preintent_closure_and_forbids_same_sha(monkeypatch, tmp_path):
    server_path = Path(__file__).with_name('trusted_release_server.py')
    spec = importlib.util.spec_from_file_location('preintent_server_test', server_path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    root = tmp_path / 'state'
    root.mkdir()
    closure = root / 'ota-preintent-failure-closures' / ('c' * 40)
    closure.mkdir(parents=True)
    closure.parent.chmod(0o700)
    (closure / 'intent.json').write_text('{}')
    (closure / 'completed.json').write_text('{}')
    calls = []
    helper = SimpleNamespace(validate_closed_history=lambda _server, record: calls.append(record.name))
    monkeypatch.setattr(server, 'STATE', root)
    monkeypatch.setattr(server, 'secure_path', lambda *a, **kw: None)
    monkeypatch.setattr(server, 'assert_exam_recovery_history', lambda **kw: None)
    monkeypatch.setattr(server, 'assert_xiaoqihou_briefing_history', lambda: None)
    monkeypatch.setattr(server, 'assert_retained_history', lambda: None)
    monkeypatch.setattr(server, '_load_ota_preintent_retirement', lambda: helper)
    server.assert_ota_history()
    assert calls == ['c' * 40]
    with pytest.raises(server.LaunchError, match='retry forbidden'):
        server.assert_ota_preintent_not_closed('c' * 40)


def test_server_rejects_orphan_preintent_closure(monkeypatch, tmp_path):
    server_path = Path(__file__).with_name('trusted_release_server.py')
    spec = importlib.util.spec_from_file_location('preintent_server_orphan_test', server_path)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    root = tmp_path / 'state'
    root.mkdir()
    bad = root / 'ota-preintent-failure-closures' / 'not-a-sha'
    bad.mkdir(parents=True)
    bad.parent.chmod(0o700)
    monkeypatch.setattr(server, 'STATE', root)
    monkeypatch.setattr(server, 'secure_path', lambda *a, **kw: None)
    monkeypatch.setattr(server, 'assert_exam_recovery_history', lambda **kw: None)
    monkeypatch.setattr(server, 'assert_xiaoqihou_briefing_history', lambda: None)
    monkeypatch.setattr(server, 'assert_retained_history', lambda: None)
    with pytest.raises(server.LaunchError, match='invalid OTA pre-intent failure closure'):
        server.assert_ota_history()
