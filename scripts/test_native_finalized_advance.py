"""A finalized runtime transaction is not a trusted backend success receipt."""

import importlib.util
from pathlib import Path

import pytest


def load():
    spec = importlib.util.spec_from_file_location(
        "advance_test", Path(__file__).with_name("native_finalized_advance.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def saved(m):
    return {
        "kind": "finalized-native-production-advance",
        "native_sha": m.NATIVE,
        "production_sha": m.PRODUCTION,
        "terminal": dict(m.TERMINAL),
        "identity": {"uid": 0, "gid": 0, "mode": 0o600, "inode": 1,
                     "device": 1, "sha256": m.TERMINAL_DIGEST},
    }


def test_historical_proof_is_self_contained_and_never_backend_success():
    m = load()
    proof = saved(m)
    m.validate_saved(proof, m.NATIVE)
    assert "state" not in proof
    assert "SUCCEEDED" not in str(proof)


@pytest.mark.parametrize("fault", ["native", "production", "old", "phase", "target", "result",
                                  "transaction", "extra", "hash", "mode", "owner", "bool_inode"])
def test_malformed_or_other_transaction_cannot_authorize_retirement(fault):
    m = load()
    proof = saved(m)
    if fault == "native": proof["native_sha"] = "a" * 40
    elif fault == "production": proof["production_sha"] = "a" * 40
    elif fault == "old": proof["terminal"]["old_sha"] = "a" * 40
    elif fault == "phase": proof["terminal"]["phase"] = "INSTALLED"
    elif fault == "target": proof["terminal"]["target"] = "old"
    elif fault == "result": proof["terminal"]["result"] = "pending"
    elif fault == "transaction": proof["terminal"]["transaction_id"] = "a" * 32
    elif fault == "extra": proof["terminal"]["extra"] = True
    elif fault == "hash": proof["identity"]["sha256"] = "a" * 64
    elif fault == "mode": proof["identity"]["mode"] = 0o640
    elif fault == "owner": proof["identity"]["uid"] = 1000
    elif fault == "bool_inode": proof["identity"]["inode"] = True
    with pytest.raises(m.AdvanceError):
        m.validate_saved(proof, m.NATIVE)


def test_other_native_profile_cannot_use_saved_advance():
    m = load()
    with pytest.raises(m.AdvanceError):
        m.validate_saved(saved(m), "a" * 40)


@pytest.mark.parametrize("name", ["runtime-state-transaction", ".runtime-state-transaction.preparing",
                                  "runtime-state-transaction.reap-unknown"])
def test_residual_transaction_and_dangling_link_block_advance(tmp_path, name):
    m = load()
    (tmp_path / name).symlink_to(tmp_path / "missing")
    with pytest.raises(m.AdvanceError):
        m.assert_no_transaction(tmp_path)


def live_fixture(monkeypatch, tmp_path):
    import hashlib
    import json
    import stat
    from types import SimpleNamespace
    m = load()
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    path = tmp_path / 'runtime-state-terminal.json'
    path.write_text(json.dumps(m.TERMINAL, sort_keys=True, separators=(',', ':')) + '\n')
    path.chmod(0o600)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == m.TERMINAL_DIGEST
    calls = []
    def identity(p):
        info = p.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600:
            raise m.AdvanceError('unsafe file')
        return dict(uid=0, gid=0, mode=0o600, inode=info.st_ino,
                    device=info.st_dev, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
    def run(args, **kwargs):
        calls.append(args)
        if args[0] == '/usr/bin/systemctl':
            return SimpleNamespace(stdout='ActiveState=active\nSubState=running\nMainPID=20\nNRestarts=0\nExecMainStartTimestampMonotonic=123\n')
        return SimpleNamespace(stdout='tree ignored\nparent ' + m.PRODUCTION + '\n\nmessage')
    b = SimpleNamespace(STATE=tmp_path, secure=lambda p: None, _run=run,
        _read_json=lambda p: dict(production_sha=m.ORIGINAL), _recovery_file_identity=identity,
        _assert_idle=lambda: calls.append('idle'), _recovery_process_proof=lambda: calls.append('process'),
        _recovery_production_proof=lambda sha, source: calls.append(('revision', sha)))
    gate = SimpleNamespace(_get_json=None, _latest=lambda get, sha: calls.append(('ci', sha)))
    monkeypatch.setattr(m.importlib.util, 'spec_from_file_location', lambda *a: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None)))
    monkeypatch.setattr(m.importlib.util, 'module_from_spec', lambda spec: gate)
    response = SimpleNamespace(status=200, geturl=lambda: 'http://127.0.0.1:8000/api/v1/health',
        read=lambda n: json.dumps(dict(status='healthy', services=dict(api='running', database='connected', redis='connected', celery='connected'))).encode())
    class Response:
        def __enter__(self): return response
        def __exit__(self, *args): return False
    monkeypatch.setattr(m.urllib.request, 'build_opener', lambda *a: SimpleNamespace(open=lambda *a, **k: Response()))
    monkeypatch.setattr(m.time, 'sleep', lambda n: None)
    return m, b, path, calls, gate


def test_live_advance_replaces_all_live_checks_and_copies_exact_terminal(monkeypatch, tmp_path):
    m, b, path, calls, gate = live_fixture(monkeypatch, tmp_path)
    proof = m.inspect(b, tmp_path, m.NATIVE, m.PRODUCTION)
    m.validate_saved(proof, m.NATIVE)
    assert calls.count('idle') == calls.count('process') == 2
    assert calls.count(('revision', m.PRODUCTION)) == 2
    assert ('ci', m.PRODUCTION) in calls
    path.unlink()
    m.validate_saved(proof, m.NATIVE)


@pytest.mark.parametrize('fault', ['ci', 'ancestry', 'parent', 'service', 'revision', 'process', 'lease',
                                  'bytes', 'duplicate_json', 'mode', 'symlink', 'hardlink', 'drift'])
def test_failed_live_proof_never_returns_retirement_authority(monkeypatch, tmp_path, fault):
    import os
    from types import SimpleNamespace
    m, b, path, calls, gate = live_fixture(monkeypatch, tmp_path)
    def fail(*a, **k): raise m.AdvanceError('blocked')
    if fault == 'ci': gate._latest = fail
    elif fault in {'ancestry', 'parent', 'service'}:
        original = b._run
        def run(args, **kwargs):
            if fault == 'ancestry' and 'merge-base' in args: fail()
            if fault == 'parent' and 'cat-file' in args: return SimpleNamespace(stdout='parent bad\n\n')
            if fault == 'service' and args[0] == '/usr/bin/systemctl': return SimpleNamespace(stdout='ActiveState=failed')
            return original(args, **kwargs)
        b._run = run
    elif fault == 'revision': b._recovery_production_proof = fail
    elif fault == 'process': b._recovery_process_proof = fail
    elif fault == 'lease': b._assert_idle = fail
    elif fault in {'bytes', 'duplicate_json'}: path.write_text('{"version":1,"version":1}' if fault == 'duplicate_json' else '{}')
    elif fault == 'mode': path.chmod(0o640)
    elif fault == 'hardlink': os.link(path, tmp_path / 'alias')
    elif fault == 'symlink':
        real = tmp_path / 'real'; path.rename(real); path.symlink_to(real)
    elif fault == 'drift': monkeypatch.setattr(m.time, 'sleep', lambda n: path.write_text('{}'))
    with pytest.raises(m.AdvanceError):
        m.inspect(b, tmp_path, m.NATIVE, m.PRODUCTION)
