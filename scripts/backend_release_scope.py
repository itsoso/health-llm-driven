"""Conservative initial backend release allowlist; never authenticates production.

The caller must independently bind base_sha to its trusted production receipt
and Git checkout. This read-only module proves only a bounded, clean, linear
Git range and classifies EVERY intermediate change, including reverted edits.
Unknown evidence requests the existing full gate; it is not a successful scope
proof. This initial allowlist is deliberately not a complete dependency graph.
"""
import os
from pathlib import Path
import re
import subprocess

_IMPLEMENTATION = frozenset({
    'backend/app/services/zh_tokenize.py',
    'backend/app/services/llm/prompt_cache.py',
    'backend/app/services/llm/tokenplan_cost.py',
})
_MAX_COMMITS = 8
_MAX_CHANGES = 300
_MAX_OUTPUT = 2_000_000
_SHA = re.compile(r'[0-9a-f]{40}')


def _result(target, reason, count=0):
    return dict(target=target, reason=reason, changed_entries=count)


def _full(reason, count=0):
    return _result('full', reason, count)


def _path_kind(path):
    if (not isinstance(path, str) or not path or path.startswith('/')
            or any(part in ('', '.', '..') for part in path.split('/'))
            or any(ord(char) < 32 or ord(char) == 127 for char in path)
            or '\\' in path):
        return None
    if path in _IMPLEMENTATION:
        return 'implementation'
    if (re.fullmatch(r'backend/tests/test_[A-Za-z0-9_]+\.py', path)
            or re.fullmatch(r'docs/dossiers/[A-Za-z0-9][A-Za-z0-9_-]*\.md', path)
            or re.fullmatch(r'docs/ops/ci-[A-Za-z0-9][A-Za-z0-9_-]*\.md', path)
            or path == 'README.md'):
        return 'nonruntime'
    return None


def classify_changes(changes, *, complete=False):
    """Classify complete raw entries; no path normalization or trust inference.

    Entries have exactly path/status/old_mode/new_mode. Rename entries may also
    carry previous_path, but all renames require the full gate in policy v1.
    Repeated paths across commits count separately and are never net-deduped.
    """
    if complete is not True:
        return _full('incomplete_change_evidence')
    if not isinstance(changes, list) or not 0 < len(changes) <= _MAX_CHANGES:
        return _full('empty_or_oversized_change_evidence')
    for entry in changes:
        if (not isinstance(entry, dict)
                or set(entry) not in ({'path', 'status', 'old_mode', 'new_mode'},
                                      {'path', 'status', 'old_mode', 'new_mode', 'previous_path'})):
            return _full('malformed_change_entry', len(changes))
        status = entry['status']
        if not isinstance(status, str) or status not in ('A', 'M', 'D') or 'previous_path' in entry:
            return _full('unsupported_change_status', len(changes))
        modes = {'A': ('000000', '100644'), 'M': ('100644', '100644'),
                 'D': ('100644', '000000')}
        if (entry['old_mode'], entry['new_mode']) != modes[status]:
            return _full('non_regular_or_changed_file_mode', len(changes))
        kind = _path_kind(entry['path'])
        if kind is None or (kind == 'implementation' and status != 'M'):
            return _full('outside_initial_allowlist', len(changes))
    return _result('backend-v1', 'eligible_initial_allowlist', len(changes))


class _EvidenceError(Exception):
    pass


def _git(repo, *args):
    # Fixed local executable and clean environment: no hooks, replaces, global
    # aliases, fsmonitor, external diff, pager, user proxy or credential helper.
    command = ['/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
               '-c', 'core.fsmonitor=false', '-c', 'core.pager=cat',
               '-c', 'diff.external=', '-c', 'core.quotePath=false',
               '-C', str(repo), *args]
    env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LC_ALL': 'C',
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null',
           'GIT_CONFIG_SYSTEM': '/dev/null', 'GIT_NO_REPLACE_OBJECTS': '1',
           'GIT_TERMINAL_PROMPT': '0', 'GIT_OPTIONAL_LOCKS': '0'}
    result = subprocess.run(command, env=env, stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=15, check=True)
    if len(result.stdout) > _MAX_OUTPUT:
        raise _EvidenceError('oversized git output')
    return result.stdout


def _raw_changes(raw):
    if not raw:
        return []
    parts = raw.split(b'\0')
    if parts[-1] != b'':
        raise _EvidenceError('unterminated diff')
    parts.pop()
    changes = []
    while parts:
        header = parts.pop(0).decode('ascii')
        match = re.fullmatch(r':([0-9]{6}) ([0-9]{6}) ([0-9a-f]{40}) ([0-9a-f]{40}) ([A-Z][0-9]*)', header)
        if match is None or not parts:
            raise _EvidenceError('malformed raw diff')
        path = parts.pop(0).decode('utf-8')
        status = match[5]
        entry = dict(path=path, status=status, old_mode=match[1], new_mode=match[2])
        if status.startswith(('R', 'C')):
            if not parts:
                raise _EvidenceError('missing rename destination')
            entry['previous_path'] = path
            entry['path'] = parts.pop(0).decode('utf-8')
        changes.append(entry)
        if len(changes) > _MAX_CHANGES:
            raise _EvidenceError('oversized raw diff')
    return changes


def evaluate_git_scope(repo, base_sha, candidate_sha):
    """Return full on unproven evidence; caller authenticates production base.

    No network, repository mutation, permissive fallback, or receipt minting.
    Every commit must form one linear chain, so merges and incomplete ancestry
    are intentionally ineligible. A changed-then-reverted file still counts.
    """
    if (not isinstance(base_sha, str) or _SHA.fullmatch(base_sha) is None
            or not isinstance(candidate_sha, str) or _SHA.fullmatch(candidate_sha) is None):
        return _full('invalid_revision')
    if base_sha == candidate_sha:
        return _full('empty_revision_range')
    try:
        root = Path(repo).resolve(strict=True)
        # Server callers supply a reviewed standalone checkout, not a linked
        # worktree or an alternate Git directory controlled by an environment.
        git_dir = root / '.git'
        if (not git_dir.is_dir() or git_dir.is_symlink()
                or os.path.lexists(git_dir / 'info/grafts')):
            return _full('unsupported_git_checkout')
        if _git(root, 'rev-parse', '--show-toplevel').decode().strip() != str(root):
            return _full('git_root_mismatch')
        if _git(root, 'rev-parse', 'HEAD').decode().strip() != candidate_sha:
            return _full('candidate_head_mismatch')
        if _git(root, 'status', '--porcelain=v1', '--untracked-files=all'):
            return _full('dirty_candidate')
        for sha in (base_sha, candidate_sha):
            if _git(root, 'rev-parse', '--verify', sha + '^{commit}').decode().strip() != sha:
                return _full('non_commit_revision')
        _git(root, 'merge-base', '--is-ancestor', base_sha, candidate_sha)
        lines = _git(root, 'rev-list', '--reverse', '--parents', '--max-count=9',
                     base_sha + '..' + candidate_sha).decode('ascii').splitlines()
        if not 0 < len(lines) <= _MAX_COMMITS:
            return _full('empty_or_oversized_history')
        previous = base_sha
        changes = []
        for line in lines:
            fields = line.split()
            if (len(fields) != 2 or _SHA.fullmatch(fields[0]) is None
                    or fields[1] != previous):
                return _full('nonlinear_history')
            current = fields[0]
            raw = _git(root, 'diff-tree', '--no-commit-id', '--raw', '--no-abbrev',
                       '-r', '-z', '--no-ext-diff', '--no-textconv', '--find-renames',
                       previous, current, '--')
            changes.extend(_raw_changes(raw))
            if len(changes) > _MAX_CHANGES:
                return _full('oversized_change_history')
            previous = current
        if previous != candidate_sha:
            return _full('incomplete_commit_chain')
        # Recheck mutable checkout state after all immutable commit comparisons.
        if (_git(root, 'rev-parse', 'HEAD').decode().strip() != candidate_sha
                or _git(root, 'status', '--porcelain=v1', '--untracked-files=all')):
            return _full('candidate_changed_during_check')
        return classify_changes(changes, complete=True)
    except (OSError, ValueError, TypeError, UnicodeError, subprocess.SubprocessError, _EvidenceError):
        # Failure is explicit conservative full-gate selection, never a claim
        # that this narrower policy verified the candidate.
        return _full('git_evidence_unavailable')
