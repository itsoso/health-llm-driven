"""A completed exam repair must be consumed before ordinary publication."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


FAILED = 'a8cd1e7635eb697c0f0bc528382c98b3602893c3'
TERMINAL = 'CLOSED_EXAM_FORWARD_FAILURE'


def load(name):
    path = Path(__file__).with_name(name + '.py')
    spec = importlib.util.spec_from_file_location('exam_publish_' + name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def test_bootstrap_dispatches_exam_closure_with_receipt_and_history(tmp_path, monkeypatch):
    b = load('bootstrap_trusted_release')
    monkeypatch.setattr(b, 'STATE', tmp_path)
    (tmp_path / 'exam-forward-closures' / FAILED).mkdir(parents=True)
    calls = []
    def consume(owner, sha, receipt, *, historical):
        calls.append((owner, sha, receipt, historical))
        return {'state': TERMINAL}
    monkeypatch.setattr(b, '_exam_forward_module', lambda: SimpleNamespace(closed_evidence=consume))
    assert b._workspace_evidence(FAILED, recovery_receipt='e' * 64, historical=True) == {'state': TERMINAL}
    assert calls == [(b, FAILED, 'e' * 64, True)]
    (tmp_path / 'retained-candidate-closures' / FAILED).mkdir(parents=True)
    with pytest.raises(b.BootstrapError, match='conflicting'):
        b._workspace_evidence(FAILED, recovery_receipt='e' * 64)
    assert len(calls) == 1


@pytest.mark.parametrize('filename', ['bootstrap_trusted_release', 'trusted_release_server'])
def test_ordinary_history_consumes_complete_closure_even_when_attempts_exist(tmp_path, monkeypatch, filename):
    m = load(filename)
    monkeypatch.setattr(m, 'STATE', tmp_path)
    (tmp_path / 'exam-a8-forward-acl-v1').mkdir()
    (tmp_path / 'exam-a8-read-credential-v1').mkdir()
    (tmp_path / 'exam-forward-closures' / FAILED).mkdir(parents=True)
    calls = []
    proof = SimpleNamespace(history_evidence=lambda b: calls.append(b))
    if filename == 'bootstrap_trusted_release':
        owner = m
        monkeypatch.setattr(m, '_exam_forward_module', lambda: proof)
    else:
        owner = SimpleNamespace(STATE=tmp_path)
        monkeypatch.setattr(m, '_load_exam_forward_history', lambda: (owner, proof))
    m.assert_exam_recovery_history()
    assert calls == [owner]


@pytest.mark.parametrize('filename', ['bootstrap_trusted_release', 'trusted_release_server'])
def test_malformed_closure_never_becomes_a_completed_string_exemption(tmp_path, monkeypatch, filename):
    m = load(filename)
    monkeypatch.setattr(m, 'STATE', tmp_path)
    root = tmp_path / 'exam-forward-closures' / FAILED
    root.mkdir(parents=True)
    (root / 'completed.json').write_text('{"state":"CLOSED_EXAM_FORWARD_FAILURE"}')
    def reject(b):
        raise ValueError('invalid closure chain')
    proof = SimpleNamespace(history_evidence=reject)
    if filename == 'bootstrap_trusted_release':
        monkeypatch.setattr(m, '_exam_forward_module', lambda: proof)
        error = m.BootstrapError
    else:
        monkeypatch.setattr(m, '_load_exam_forward_history', lambda: (SimpleNamespace(STATE=tmp_path), proof))
        error = m.LaunchError
    with pytest.raises(error):
        m.assert_exam_recovery_history()


def test_server_history_rejects_mismatched_state_root(tmp_path, monkeypatch):
    m = load('trusted_release_server')
    monkeypatch.setattr(m, 'STATE', tmp_path)
    (tmp_path / 'exam-forward-closures' / FAILED).mkdir(parents=True)
    proof = SimpleNamespace(history_evidence=lambda b: pytest.fail('wrong root must not be consumed'))
    monkeypatch.setattr(m, '_load_exam_forward_history', lambda: (SimpleNamespace(STATE=tmp_path / 'other'), proof))
    with pytest.raises(m.LaunchError):
        m.assert_exam_recovery_history()


@pytest.mark.parametrize('filename', ['bootstrap_trusted_release', 'trusted_release_server'])
def test_pending_rotation_requires_a_separate_full_validator(tmp_path, monkeypatch, filename):
    m = load(filename)
    monkeypatch.setattr(m, 'STATE', tmp_path)
    (tmp_path / 'exam-forward-closures' / FAILED).mkdir(parents=True)
    calls = []
    pending = {'old_sha': FAILED, 'new_sha': 'd' * 40}
    def validate(owner, value):
        calls.append(value)
        raise ValueError('pending rotation proof rejected')
    proof = SimpleNamespace(history_evidence=lambda b: pytest.fail('normal proof cannot replace pending proof'),
                            validate_pending_rotation=validate)
    if filename == 'bootstrap_trusted_release':
        monkeypatch.setattr(m, '_exam_forward_module', lambda: proof)
        error = m.BootstrapError
    else:
        monkeypatch.setattr(m, '_load_exam_forward_history', lambda: (SimpleNamespace(STATE=tmp_path), proof))
        error = m.LaunchError
    with pytest.raises(error):
        m.assert_exam_recovery_history(_exam_pending_rotation=pending)
    assert calls == [pending]


@pytest.mark.parametrize('fault', ['bootstrap_tamper', 'closure_tamper', 'dirty_source', 'cache', 'wrong_source', None])
def test_server_loader_checks_bytes_and_source_before_executing_closure(tmp_path, monkeypatch, fault):
    m = load('trusted_release_server')
    monkeypatch.setattr(m, 'STATE', tmp_path)
    sha = 'd' * 40
    source = tmp_path / 'bootstrap' / sha / 'source'
    scripts = source / 'scripts'; scripts.mkdir(parents=True)
    entry = scripts / 'trusted_release_server.py'
    entry.write_text('# fixture executor')
    monkeypatch.setattr(m, '__file__', str(entry if fault != 'wrong_source' else tmp_path / entry.name))
    checked = []
    monkeypatch.setattr(m, 'secure_path', lambda path, **kw: checked.append(path))
    bootstrap = ('from pathlib import Path\nSTATE=Path(' + repr(str(tmp_path)) + ')\n'
                 'def canonical_source(sha):\n    ' +
                 ('raise ValueError("dirty canonical tree")' if fault == 'dirty_source' else 'return None') + '\n')
    helper = 'VALUE="verified closure bytes"\n'
    expected = {'bootstrap_trusted_release.py': bootstrap.encode(), 'exam_forward_retirement.py': helper.encode()}
    for name, raw in expected.items():
        (scripts / name).write_bytes(raw)
    if fault == 'bootstrap_tamper': (scripts / 'bootstrap_trusted_release.py').write_text('raise AssertionError("unverified code executed")')
    if fault == 'closure_tamper': (scripts / 'exam_forward_retirement.py').write_text('raise AssertionError("unverified code executed")')
    if fault == 'cache': (scripts / '__pycache__').mkdir()
    calls = []
    def git(command, **kwargs):
        assert command[-2] == 'show' and command[-1].startswith(sha + ':scripts/')
        assert kwargs['env']['GIT_NO_REPLACE_OBJECTS'] == '1'
        name = command[-1].split('/')[-1]
        calls.append(name)
        return SimpleNamespace(stdout=expected[name])
    monkeypatch.setattr(m.subprocess, 'run', git)
    if fault is None:
        b, closure = m._load_exam_forward_history()
        assert b.STATE == tmp_path and closure.VALUE == 'verified closure bytes'
        assert len(checked) == 2
    else:
        with pytest.raises((m.LaunchError, ValueError)):
            m._load_exam_forward_history()
        if fault in {'dirty_source', 'bootstrap_tamper'}:
            assert calls == ['bootstrap_trusted_release.py']


def test_installed_history_disables_bytecode_for_real_archived_vision_loader(tmp_path, monkeypatch):
    """The archived helper uses exec_module, so compile-only outer loads are insufficient."""
    import sys
    m = load('trusted_release_server'); monkeypatch.setattr(m, 'STATE', tmp_path)
    sha = 'd' * 40; scripts = tmp_path / 'bootstrap' / sha / 'source/scripts'
    scripts.mkdir(parents=True); entry = scripts / 'trusted_release_server.py'
    entry.write_text('# fixture executor'); monkeypatch.setattr(m, '__file__', str(entry))
    monkeypatch.setattr(m, 'secure_path', lambda *a, **kw: None)
    retained = Path(__file__).with_name('retained_candidate_retirement.py')
    bootstrap = ('from pathlib import Path\nSTATE=Path(' + repr(str(tmp_path)) + ')\n'
                 'def canonical_source(sha): return None\ndef secure(path): pass\n')
    helper = ('import runpy\nfrom pathlib import Path\n'
              'saved=runpy.run_path(' + repr(str(retained)) + ')\n'
              'def probe(b): return saved["load"](b, Path(' + repr(str(scripts / 'trusted_vision_model.py')) +
              '), "real_archived_vision_probe")\n')
    expected = {'bootstrap_trusted_release.py': bootstrap.encode(), 'exam_forward_retirement.py': helper.encode()}
    for name, raw in expected.items(): (scripts / name).write_bytes(raw)
    (scripts / 'trusted_vision_model.py').write_bytes(Path(__file__).with_name('trusted_vision_model.py').read_bytes())
    monkeypatch.setattr(m.subprocess, 'run', lambda args, **kw: SimpleNamespace(stdout=expected[args[-1].split('/')[-1]]))
    monkeypatch.setattr(sys, 'dont_write_bytecode', False)
    b, closure = m._load_exam_forward_history()
    closure.probe(b)
    assert not (scripts / '__pycache__').exists()
    closure.probe(b)


@pytest.mark.parametrize('tamper', [False, True])
@pytest.mark.parametrize('reuse_cloud', [False, True])
def test_rotation_consumes_exam_closure_after_no_copy_discard(tmp_path, monkeypatch, tamper, reuse_cloud):
    import hashlib
    import json
    from test_bootstrap_trusted_release import rotation_fixture, SHA, NEW_SHA, HOST, PUBLIC
    b, _ = rotation_fixture(monkeypatch, tmp_path)
    closure = load('exam_forward_retirement')
    monkeypatch.setattr(closure, 'FAILED', SHA)
    old = b.STATE / SHA / 'completed.json'
    old.parent.mkdir(exist_ok=True)
    old.write_text(json.dumps({'sha': SHA, 'state': 'NEEDS_OPERATOR'}))
    original = old.read_bytes()
    workspace = {'state': TERMINAL, 'closure': 'c' * 64}
    # Exercise the real rotation and receipt consumer together; the fixture
    # supplies the already verified service/closure evidence and local ownership.
    saved_intent = {'receipt_sha256': hashlib.sha256(('e' * 64).encode()).hexdigest()}
    saved_done = {'installation': b._installation_evidence(SHA, b.CONFIG, b.INSTALLED.parent)}
    def audit(owner, path, names):
        closure.need({p.name for p in path.iterdir()} == set(names))
        return {name: json.loads((path / name).read_text()) for name in names}, {}
    monkeypatch.setattr(closure, 'audit', audit)
    history_calls = []
    def history(*, _exam_pending_rotation=None):
        if _exam_pending_rotation is not None:
            assert _exam_pending_rotation['workspace'] == workspace
            assert _exam_pending_rotation['old_sha'] == SHA
            assert _exam_pending_rotation['new_sha'] == NEW_SHA
            assert closure.retired_history(b, saved_intent, saved_done, workspace,
                                           pending=_exam_pending_rotation)
            history_calls.append(_exam_pending_rotation)
    monkeypatch.setattr(b, 'assert_exam_recovery_history', history)
    observations = []
    def consume(sha, *, recovery_receipt=None, historical=False):
        assert recovery_receipt == 'e' * 64
        observations.append((historical, b.CONFIG.exists()))
        if not historical:
            assert b.CONFIG.exists(), 'live proof must precede installation deletion'
        else:
            assert closure.retired_history(b, saved_intent, saved_done, workspace)
        return workspace
    monkeypatch.setattr(b, '_workspace_evidence', consume)
    write = b._write
    def maybe_tamper(path, raw):
        write(path, raw)
        if tamper and path == b.STATE / 'retired' / SHA / 'completed.json':
            value = json.loads(path.read_text())
            value['new_sha'] = 'f' * 40
            path.write_text(json.dumps(value))
    monkeypatch.setattr(b, '_write', maybe_tamper)
    installed = []
    monkeypatch.setattr(b, '_install_locked', lambda *a, **kw: installed.append(True) or {'state': 'INSTALLED'})
    expiry, public = (0, PUBLIC) if reuse_cloud else (200, HOST)
    if tamper:
        with pytest.raises(b.BootstrapError):
            b.rotate(SHA, NEW_SHA, expiry, public, recovery_receipt='e' * 64)
        assert not installed
    else:
        assert b.rotate(SHA, NEW_SHA, expiry, public, recovery_receipt='e' * 64)['state'] == 'INSTALLED'
        assert observations == [(False, True), (True, False)]
        assert installed == [True]
    assert old.read_bytes() == original
    assert not any(p.exists() for p in b._archives(SHA))
    assert history_calls
