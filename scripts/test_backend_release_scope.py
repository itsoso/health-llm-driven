"""Conservative release eligibility, including real immutable Git histories."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name('backend_release_scope.py')
ALLOWED = 'backend/app/services/zh_tokenize.py'


def module():
    spec = importlib.util.spec_from_file_location('scope_under_test', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def change(path=ALLOWED, status='M', **extra):
    return dict(path=path, status=status, old_mode='100644', new_mode='100644', **extra)


def test_scope_requires_explicit_complete_proof():
    assert module().classify_changes([change()])['target'] == 'full'
    assert module().classify_changes([change()], complete=True)['target'] == 'backend-v1'


@pytest.mark.parametrize('path', [ALLOWED, 'backend/app/services/llm/prompt_cache.py',
    'backend/app/services/llm/tokenplan_cost.py', 'backend/tests/test_example.py',
    'docs/dossiers/2026-10-09-ci.md', 'docs/ops/ci-latency.md', 'README.md'])
def test_initial_allowlist(path):
    assert module().classify_changes([change(path)], complete=True)['target'] == 'backend-v1'


@pytest.mark.parametrize('path', ['backend/app/api/chat.py', 'backend/app/models/meal.py',
    'backend/app/services/phone_auth.py', 'backend/app/services/other.py',
    'backend/tests/conftest.py', 'backend/tests/sub/test_safe.py', 'docs/prompts.md',
    '.github/workflows/ci.yml', 'scripts/trusted_release_gate.py', 'backend/requirements.lock',
    'backend/migrations/one.py', '../README.md', './README.md', '/README.md',
    'docs/dossiers/nested/x.md', 'docs/ops/ci-../x.md', 'README.md\n', 'README.md\x00'])
def test_unknown_sensitive_or_noncanonical_path_requires_full(path):
    assert module().classify_changes([change(path)], complete=True)['target'] == 'full'


@pytest.mark.parametrize('changes', [[], [change(status='A')], [change(status='D')],
    [change(status='R100', previous_path='backend/app/api/chat.py')],
    [change(status='T')], [dict(change(), new_mode='120000')],
    [dict(change(), old_mode='160000')], [dict(change(), new_mode='100755')],
    [dict(change(), status='unknown')], [dict(change(), surprise=True)],
    [None], [change()] * 301])
def test_invalid_or_oversized_changes_require_full(changes):
    assert module().classify_changes(changes, complete=True)['target'] == 'full'


@pytest.mark.parametrize('path', ['backend/tests/test_new.py', 'docs/dossiers/new.md'])
def test_nonruntime_additions_and_deletions_allowed(path):
    for status, old, new in [('A', '000000', '100644'), ('D', '100644', '000000')]:
        assert module().classify_changes([dict(path=path, status=status, old_mode=old, new_mode=new)], complete=True)['target'] == 'backend-v1'


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        return subprocess.run(['/usr/bin/git', '-C', str(tmp_path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()
    git('init', '-b', 'main')
    git('config', 'user.name', 'Test')
    git('config', 'user.email', 'test@example.invalid')
    def commit(path, content):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        git('add', '--', path)
        git('commit', '-m', 'test')
        return git('rev-parse', 'HEAD')
    base = commit(ALLOWED, 'baseline\n')
    return tmp_path, git, commit, base


def test_real_git_accumulates_all_unpublished_commits(repo):
    root, git, commit, base = repo
    commit(ALLOWED, 'second\n')
    head = commit('backend/tests/test_local.py', 'pass\n')
    result = module().evaluate_git_scope(root, base, head)
    assert result == dict(target='backend-v1', reason='eligible_initial_allowlist', changed_entries=2)


def test_edit_then_revert_sensitive_file_cannot_hide_in_net_diff(repo):
    root, git, commit, base = repo
    commit('backend/app/api/new.py', 'bad\n')
    git('rm', 'backend/app/api/new.py')
    git('commit', '-m', 'revert')
    head = commit(ALLOWED, 'allowed\n')
    assert module().evaluate_git_scope(root, base, head)['target'] == 'full'


@pytest.mark.parametrize('variant', ['rename', 'symlink', 'executable', 'dirty', 'untracked', 'too_many', 'empty', 'wrong_head', 'not_ancestor', 'merge'])
def test_real_git_rejects_ambiguous_histories(repo, variant):
    root, git, commit, base = repo
    head = commit(ALLOWED, 'change\n')
    if variant == 'rename':
        git('mv', ALLOWED, 'backend/app/services/llm_cost.py')
        git('commit', '-m', 'rename')
    elif variant == 'symlink':
        (root / ALLOWED).unlink()
        (root / ALLOWED).symlink_to('/etc/passwd')
        git('add', ALLOWED)
        git('commit', '-m', 'type change')
    elif variant == 'executable':
        git('update-index', '--chmod=+x', ALLOWED)
        git('commit', '-m', 'mode change')
    elif variant == 'dirty':
        (root / ALLOWED).write_text('dirty')
    elif variant == 'untracked':
        (root / 'untracked').write_text('unknown')
    elif variant == 'too_many':
        for i in range(8):
            commit(ALLOWED, str(i))
    elif variant == 'empty':
        base = head
    elif variant == 'wrong_head':
        head = base
    elif variant == 'not_ancestor':
        git('checkout', '--orphan', 'new')
        commit(ALLOWED, 'unrelated')
    elif variant == 'merge':
        git('checkout', '-b', 'side', base)
        commit('README.md', 'side')
        git('checkout', 'main')
        git('merge', '--no-ff', 'side', '-m', 'merge')
    if variant != 'wrong_head':
        head = git('rev-parse', 'HEAD')
    assert module().evaluate_git_scope(root, base, head)['target'] == 'full'


def test_git_failure_is_explicit_full_not_success(repo):
    root, git, commit, base = repo
    head = commit(ALLOWED, 'two')
    result = module().evaluate_git_scope(root, 'a' * 40, head)
    assert result['target'] == 'full'
    assert result['reason'] == 'git_evidence_unavailable'


def test_transport_environment_is_fixed_and_invalid_sha_never_executes(monkeypatch, repo):
    root, git, commit, base = repo
    head = commit(ALLOWED, 'two')
    mod = module()
    original = mod.subprocess.run
    seen = []
    def capture(args, **kwargs):
        seen.append((args, kwargs))
        return original(args, **kwargs)
    monkeypatch.setattr(mod.subprocess, 'run', capture)
    monkeypatch.setenv('GIT_EXTERNAL_DIFF', '/bad')
    monkeypatch.setenv('GIT_CONFIG_COUNT', '1')
    assert mod.evaluate_git_scope(root, base, head)['target'] == 'backend-v1'
    assert seen
    for args, kwargs in seen:
        assert args[0] == '/usr/bin/git'
        assert 'core.hooksPath=/dev/null' in args
        assert kwargs['env']['GIT_NO_REPLACE_OBJECTS'] == '1'
        assert 'GIT_EXTERNAL_DIFF' not in kwargs['env']
        assert 'GIT_CONFIG_COUNT' not in kwargs['env']
    seen.clear()
    assert mod.evaluate_git_scope(root, '--help', head)['target'] == 'full'
    assert seen == []


def test_real_git_shallow_history_requires_complete_candidate_range(repo, tmp_path):
    root, git, commit, base = repo
    head = commit(ALLOWED, 'second')
    for depth in (1, 2):
        clone = root.parent / f'shallow-{depth}'
        subprocess.run(['/usr/bin/git', 'clone', '--depth', str(depth), root.as_uri(), str(clone)],
                       check=True, capture_output=True)
        result = module().evaluate_git_scope(clone, base, head)
        assert result['target'] == ('full' if depth == 1 else 'backend-v1')


def test_replace_refs_cannot_conceal_sensitive_commit(repo):
    root, git, commit, base = repo
    sensitive = commit('backend/app/api/new.py', 'bad')
    git('rm', 'backend/app/api/new.py')
    git('commit', '-m', 'revert')
    head = commit(ALLOWED, 'two')
    git('replace', sensitive, base)
    assert module().evaluate_git_scope(root, base, head)['target'] == 'full'


def test_grafts_and_oversized_files_are_ineligible(repo):
    root, git, commit, base = repo
    for i in range(301):
        file = root / 'backend/tests' / f'test_{i}.py'
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text('pass')
    git('add', 'backend/tests')
    git('commit', '-m', 'many')
    head = git('rev-parse', 'HEAD')
    assert module().evaluate_git_scope(root, base, head)['target'] == 'full'
    (root / '.git/info/grafts').write_text(head)
    assert module().evaluate_git_scope(root, base, head)['reason'] == 'unsupported_git_checkout'


def test_subprocess_errors_are_sanitized(repo, monkeypatch):
    root, git, commit, base = repo
    head = commit(ALLOWED, 'two')
    mod = module()
    def failed(*args, **kwargs):
        raise subprocess.TimeoutExpired('secret-token', 15)
    monkeypatch.setattr(mod.subprocess, 'run', failed)
    result = mod.evaluate_git_scope(root, base, head)
    assert result == dict(target='full', reason='git_evidence_unavailable', changed_entries=0)
    assert 'secret' not in str(result)
