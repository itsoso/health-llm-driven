"""A pre-intent OTA failure closes once and can never authorize retry."""

import hashlib
import importlib.util
import io
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


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
    module.ENTRY_DIGESTS = {name: module.digest(value) for name, value in entries.items()}
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
