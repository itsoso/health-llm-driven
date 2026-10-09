"""Backend eligibility derives from production evidence, never a caller base SHA."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SHA = "a" * 40
BASE = "b" * 40


def load():
    spec = importlib.util.spec_from_file_location("backend_admission", Path(__file__).with_name("trusted_backend_admission.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_eligible_production_baseline_selects_backend_only_after_binding():
    m = load()
    calls = []
    gate = SimpleNamespace(verify_release=lambda sha, workflow_sha, **kwargs: calls.append(kwargs) or kwargs)
    scope = SimpleNamespace(evaluate_git_scope=lambda repo, base, sha: {"target": "backend-v1", "reason": "eligible"})
    receipt = {"sha": BASE, "state": "SUCCEEDED"}
    result = m.admit(SHA, Path("/canonical"), gate, scope, lambda: (BASE, receipt))
    assert result["target"] == "backend-v1"
    assert calls == [{"target": "backend-v1"}]


@pytest.mark.parametrize("receipt", [{}, {"sha": SHA, "state": "SUCCEEDED"}, {"sha": BASE, "state": "FAILED"}])
def test_missing_or_wrong_production_proof_uses_full_gate(receipt):
    m = load()
    calls = []
    gate = SimpleNamespace(verify_release=lambda *args, **kwargs: calls.append(kwargs) or kwargs)
    scope = SimpleNamespace(evaluate_git_scope=lambda *args: pytest.fail("unbound base must not enter scope evaluation"))
    m.admit(SHA, Path("/canonical"), gate, scope, lambda: (BASE, receipt))
    assert calls == [{}]


def test_unknown_scope_uses_full_and_gate_failure_is_not_swallowed():
    m = load()
    def reject(*args, **kwargs):
        assert not kwargs
        raise RuntimeError("CI is not green")
    scope = SimpleNamespace(evaluate_git_scope=lambda *args: {"target": "full", "reason": "unknown"})
    with pytest.raises(RuntimeError, match="not green"):
        m.admit(SHA, Path("/canonical"), SimpleNamespace(verify_release=reject), scope,
                lambda: (BASE, {"sha": BASE, "state": "SUCCEEDED"}))


def test_production_change_during_admission_is_rejected():
    m = load()
    values = iter([(BASE, {"sha": BASE, "state": "SUCCEEDED"}), (SHA, {"sha": SHA, "state": "SUCCEEDED"})])
    with pytest.raises(m.AdmissionError, match="changed"):
        m.admit(SHA, Path("/canonical"), SimpleNamespace(verify_release=lambda *args, **kwargs: {}),
                SimpleNamespace(evaluate_git_scope=lambda *args: {"target": "backend-v1", "reason": "eligible"}),
                lambda: next(values))


@pytest.fixture
def local_evidence(monkeypatch, tmp_path):
    """Real inode/mode/read tests; map only trusted UID/ancestors for rootless CI."""
    import os
    m = load()
    monkeypatch.setattr(m, '_ROOT_UID', os.getuid(), raising=False)
    monkeypatch.setattr(m, '_secure_ancestors', lambda path: None, raising=False)
    return m, tmp_path


def test_read_proof_uses_stable_descriptor(local_evidence):
    m, root = local_evidence
    path = root / 'receipt.json'
    path.write_bytes(b'{"ok":true}')
    assert m.read_secure(path, limit=100) == b'{"ok":true}'


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'writable', 'oversized', 'directory', 'fifo'])
def test_real_evidence_rejects_unsafe_files(local_evidence, kind):
    import os
    m, root = local_evidence
    path = root / 'receipt.json'
    target = root / 'target'
    target.write_bytes(b'proof')
    if kind == 'symlink':
        path.symlink_to(target)
    elif kind == 'hardlink':
        os.link(target, path)
    elif kind == 'directory':
        path.mkdir()
    elif kind == 'fifo':
        os.mkfifo(path)
    else:
        path.write_bytes(b'x' * (101 if kind == 'oversized' else 5))
        if kind == 'writable':
            path.chmod(0o666)
    with pytest.raises(m.AdmissionError):
        m.read_secure(path, limit=100)


@pytest.mark.parametrize('when', ['open', 'read'])
def test_real_inode_replacement_is_detected(local_evidence, monkeypatch, when):
    m, root = local_evidence
    path = root / 'receipt.json'
    path.write_bytes(b'old')
    replacement = root / 'replacement'
    replacement.write_bytes(b'new')
    original = getattr(m.os, when)
    changed = False
    def swapping(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            changed = True
            replacement.replace(path)
        return result
    monkeypatch.setattr(m.os, when, swapping)
    with pytest.raises(m.AdmissionError):
        m.read_secure(path, limit=100)


def test_in_place_mutation_during_read_is_detected(local_evidence, monkeypatch):
    m, root = local_evidence
    path = root / 'receipt.json'
    path.write_bytes(b'old')
    original = m.os.read
    changed = False
    def rewriting(fd, count):
        nonlocal changed
        result = original(fd, count)
        if not changed:
            changed = True
            path.write_bytes(b'longer changed bytes')
        return result
    monkeypatch.setattr(m.os, 'read', rewriting)
    with pytest.raises(m.AdmissionError):
        m.read_secure(path, limit=100)


def test_extra_success_receipt_fields_do_not_authorize_fast_lane():
    m = load()
    calls = []
    gate = SimpleNamespace(verify_release=lambda *a, **kw: calls.append(kw) or kw)
    scope = SimpleNamespace(evaluate_git_scope=lambda *a: pytest.fail('invalid receipt'))
    m.admit(SHA, Path('/canonical'), gate, scope,
            lambda: (BASE, dict(sha=BASE, state='SUCCEEDED', unknown=True)))
    assert calls == [{}]


def test_compiled_loader_ignores_poisoned_bytecode(local_evidence, monkeypatch):
    import importlib.util
    import py_compile
    m, root = local_evidence
    scripts = root / 'scripts'
    scripts.mkdir()
    helper = scripts / 'backend_release_scope.py'
    helper.write_text('value = "poison"\n')
    py_compile.compile(str(helper), doraise=True, invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH)
    canonical = b'value = "canonical"\n'
    helper.write_bytes(canonical)
    spec = importlib.util.spec_from_file_location('poison_control', helper)
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    assert control.value == 'poison'
    monkeypatch.setattr(m, 'git', lambda repo, *a, **kw: canonical if kw.get('_raw') else SHA)
    imported = m.load('backend_release_scope', root, SHA)
    assert imported.value == 'canonical'
    assert Path(importlib.util.cache_from_source(str(helper))).exists()


def test_loader_rejects_worktree_bytes_different_from_commit(local_evidence, monkeypatch):
    m, root = local_evidence
    (root / 'scripts').mkdir()
    (root / 'scripts/backend_release_scope.py').write_text('raise RuntimeError("must not execute")')
    monkeypatch.setattr(m, 'git', lambda repo, *a, **kw: b'value=1\n')
    with pytest.raises(m.AdmissionError, match='canonical'):
        m.load('backend_release_scope', root, SHA)


@pytest.fixture
def production_repo(local_evidence, monkeypatch):
    import subprocess
    import json
    m, root = local_evidence
    production = root / 'production'
    production.mkdir()
    def git(*args):
        return subprocess.run(['/usr/bin/git', '-C', str(production), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init', '-b', 'main')
    git('remote', 'add', 'origin', 'https://github.com/itsoso/health-llm-driven.git')
    (production / 'README.md').write_text('production')
    git('add', 'README.md')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'base')
    sha = git('rev-parse', 'HEAD')
    state = root / 'state'
    proof = state / sha / 'completed.json'
    proof.parent.mkdir(parents=True)
    proof.write_text(json.dumps({'sha': sha, 'state': 'SUCCEEDED'}))
    proof.chmod(0o600)
    monkeypatch.setattr(m, 'PRODUCTION', production)
    monkeypatch.setattr(m, 'STATE', state)
    return m, production, git, sha, proof


def test_real_production_git_and_receipt_bind_baseline(production_repo):
    m, production, git, sha, proof = production_repo
    assert m.production_evidence() == (sha, {'sha': sha, 'state': 'SUCCEEDED'})


@pytest.mark.parametrize('kind', ['writable_head', 'writable_index', 'writable_ref', 'writable_object',
    'object_symlink', 'unsafe_config', 'noncanonical_origin', 'graft', 'alternate',
    'ref_symlink', 'receipt_symlink', 'receipt_extra_link', 'receipt_duplicate', 'dirty'])
def test_real_production_metadata_tampering_blocks_admission(production_repo, kind):
    import os
    m, production, git, sha, proof = production_repo
    gd = production / '.git'
    if kind in ('writable_head', 'writable_index', 'writable_ref'):
        path = {'writable_head': gd / 'HEAD', 'writable_index': gd / 'index',
                'writable_ref': gd / 'refs/heads/main'}[kind]
        path.chmod(0o666)
    elif kind in ('writable_object', 'object_symlink'):
        obj = gd / 'objects' / sha[:2] / sha[2:]
        if kind == 'writable_object':
            obj.chmod(0o666)
        else:
            preserved = production.parent / 'object'
            obj.rename(preserved)
            obj.symlink_to(preserved)
    elif kind == 'unsafe_config':
        git('config', 'core.worktree', '/untrusted')
    elif kind == 'noncanonical_origin':
        git('remote', 'set-url', 'origin', 'https://evil.invalid/repo')
    elif kind == 'graft':
        (gd / 'info/grafts').write_text(sha)
    elif kind == 'alternate':
        (gd / 'objects/info/alternates').write_text('/other\n')
    elif kind == 'ref_symlink':
        ref = gd / 'refs/heads/main'
        ref.unlink()
        ref.symlink_to(gd / 'HEAD')
    elif kind == 'receipt_symlink':
        original = proof.with_name('original')
        proof.rename(original)
        proof.symlink_to(original)
    elif kind == 'receipt_extra_link':
        os.link(proof, proof.with_name('linked'))
    elif kind == 'receipt_duplicate':
        proof.write_text('{"sha":"' + sha + '","state":"SUCCEEDED","state":"FAILED"}')
    elif kind == 'dirty':
        (production / 'README.md').write_text('dirty')
    with pytest.raises(m.AdmissionError):
        m.production_evidence()


def test_missing_receipt_is_full_fallback_not_fast_lane(production_repo):
    m, production, git, sha, proof = production_repo
    proof.unlink()
    assert m.production_evidence() == (sha, None)


def test_wrong_owner_is_rejected(local_evidence, monkeypatch):
    import os
    m, root = local_evidence
    path = root / 'proof'
    path.write_bytes(b'proof')
    monkeypatch.setattr(m, '_ROOT_UID', os.getuid() + 1)
    with pytest.raises(m.AdmissionError):
        m.read_secure(path, limit=100)


def test_source_alternate_must_bind_fixed_production_object_store(production_repo):
    import subprocess
    m, production, git, sha, proof = production_repo
    source = production.parent / 'source'
    subprocess.run(['/usr/bin/git', 'clone', '--shared', str(production), str(source)],
                   check=True, capture_output=True)
    subprocess.run(['/usr/bin/git', '-C', str(source), 'remote', 'set-url', 'origin',
                    'https://github.com/itsoso/health-llm-driven.git'], check=True, capture_output=True)
    m.validate_git_metadata(source, source=True)
    alternate = source / '.git/objects/info/alternates'
    alternate.write_text('/untrusted/objects\n')
    with pytest.raises(m.AdmissionError, match='alternate'):
        m.validate_git_metadata(source, source=True)


def test_http_alternate_never_reaches_git(production_repo):
    m, production, git, sha, proof = production_repo
    (production / '.git/objects/info/http-alternates').write_text('https://evil.invalid/objects\n')
    with pytest.raises(m.AdmissionError, match='alternates'):
        m.production_evidence()


def test_existing_production_ssh_origin_and_historical_tracking_branches(production_repo):
    m, production, git, sha, proof = production_repo
    git('remote', 'set-url', 'origin', 'git@github.com:itsoso/health-llm-driven.git')
    for branch in ('main', 'executor-v2', 'claude/quizzical-matsumoto'):
        git('config', f'branch.{branch}.remote', 'origin')
        git('config', f'branch.{branch}.merge', f'refs/heads/{branch}')
    assert m.production_evidence() == (sha, {'sha': sha, 'state': 'SUCCEEDED'})


@pytest.mark.parametrize('kind', ['ssh_origin', 'historical_branch'])
def test_source_does_not_inherit_production_config_exceptions(production_repo, kind):
    m, production, git, sha, proof = production_repo
    if kind == 'ssh_origin':
        git('remote', 'set-url', 'origin', 'git@github.com:itsoso/health-llm-driven.git')
    else:
        git('config', 'branch.executor-v2.remote', 'origin')
        git('config', 'branch.executor-v2.merge', 'refs/heads/executor-v2')
    with pytest.raises(m.AdmissionError, match='noncanonical Git'):
        m.validate_git_metadata(production, source=True)


@pytest.mark.parametrize('key,value', [
    ('branch.executor-v2.remote', 'evil'),
    ('branch.executor-v2.merge', 'refs/heads/main'),
    ('branch.executor-v2.merge', 'refs/heads/../executor-v2'),
    ('branch.executor-v2.merge', 'refs/heads/executor-v2\n'),
    ('branch.executor-v2.remote', 'origin\n'),
    ('branch.executor-v2.rebase', 'true'),
    ('core.hooksPath', '/untrusted'),
    ('core.fsmonitor', '/untrusted'),
    ('core.sshCommand', '/untrusted'),
    ('include.path', '/untrusted'),
    ('diff.external', '/untrusted'),
    ('credential.helper', '/untrusted'),
    ('remote.origin.uploadpack', '/untrusted'),
    ('remote.origin.url', 'git@evil.invalid:itsoso/health-llm-driven.git'),
    ('remote.origin.url', 'git@github.com:evil/health-llm-driven.git'),
])
def test_production_config_compatibility_never_allows_unsafe_settings(production_repo, key, value):
    m, production, git, sha, proof = production_repo
    git('config', 'branch.executor-v2.remote', 'origin')
    git('config', 'branch.executor-v2.merge', 'refs/heads/executor-v2')
    git('config', key, value)
    with pytest.raises(m.AdmissionError, match='noncanonical Git'):
        m.validate_git_metadata(production)


@pytest.mark.parametrize('branch', ['../outside', '.hidden', 'topic.lock', 'a//b', 'a..b', 'a/', 'a\\b', 'topic\n'])
def test_production_branch_names_must_be_canonical_refs(production_repo, branch):
    m, production, git, sha, proof = production_repo
    if '\n' in branch:
        # Git's writer rejects literal newline keys; inspect malicious on-disk
        # escaped subsection syntax without depending on that writer safeguard.
        with (production / '.git/config').open('a') as stream:
            stream.write('[branch "topic\\n"]\n remote = origin\n merge = refs/heads/topic\\n\n')
    else:
        git('config', f'branch.{branch}.remote', 'origin')
        git('config', f'branch.{branch}.merge', f'refs/heads/{branch}')
    with pytest.raises(m.AdmissionError, match='noncanonical Git'):
        m.validate_git_metadata(production)
