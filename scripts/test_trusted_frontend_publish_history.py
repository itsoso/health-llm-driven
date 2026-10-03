"""Frontend publication receipts fail closed independently of backend history."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    server = load('trusted_release_server')
    rebuild = load('trusted_frontend_rebuild')
    monkeypatch.setattr(server, 'secure_path', lambda *a, **kw: None)
    monkeypatch.setattr(server, '_read_private', lambda p: p.read_bytes())
    monkeypatch.setattr(server, 'validate_metadata', lambda *a, **kw: None)
    root = tmp_path / 'frontend-publications'
    root.mkdir(mode=0o700)
    op = root / ('a' * 32)
    op.mkdir(mode=0o700)
    intent = dict(kind='frontend-publication', publisher_sha='b' * 40, production_sha='c' * 40,
                  operation_id=op.name, frontend_tree='d' * 40, state='FRONTEND_STARTED', artifact_digest=None)
    def write(name, value):
        (op / name).write_text(json.dumps(value))
    write('intent.json', intent)
    write('before.json', {k: intent[k] for k in ('publisher_sha', 'production_sha', 'operation_id', 'frontend_tree')})
    (op / 'build.log').write_text('built')
    for name, state in [('install-started.json', 'FRONTEND_INSTALLING'), ('verified.json', 'FRONTEND_VERIFIED')]:
        write(name, {**intent, 'state': state, 'artifact_digest': 'e' * 64})
    backups = {}
    for name in ('previous-next', 'previous-node-modules'):
        (op / name).mkdir()
        (op / name / 'file').write_text(name)
        backups[name] = server._frontend_publication_backup_digest(op / name)
    complete = {**intent, 'state': 'FRONTEND_SUCCEEDED', 'artifact_digest': 'e' * 64,
                'proof_sha256': {n: hashlib.sha256((op / n).read_bytes()).hexdigest()
                                 for n in ('before.json', 'build.log', 'install-started.json', 'verified.json')},
                'backups_digest': backups}
    write('completed.json', complete)
    return server, tmp_path, op, complete


def test_completed_publication_allowed(evidence):
    server, state, _, _ = evidence
    server.assert_frontend_rebuild_history(state)


@pytest.mark.parametrize('mutation', ['partial', 'failed', 'unknown', 'binding', 'proof', 'backup', 'permissions', 'symlink'])
def test_invalid_publication_blocks_all_existing_history_callers(evidence, mutation):
    server, state, op, complete = evidence
    if mutation == 'partial':
        (op / 'completed.json').unlink()
    elif mutation in ('failed', 'unknown'):
        (op / ('failed.json' if mutation == 'failed' else 'extra')).write_text('{}')
    elif mutation == 'binding':
        complete['production_sha'] = 'f' * 40
        (op / 'completed.json').write_text(json.dumps(complete))
    elif mutation == 'proof':
        (op / 'build.log').write_text('tampered')
    elif mutation == 'backup':
        (op / 'previous-next' / 'file').write_text('tampered')
    elif mutation == 'permissions':
        op.chmod(0o755)
    else:
        (op / 'previous-next' / 'escape').symlink_to('/tmp')
    with pytest.raises(server.LaunchError):
        server.assert_frontend_rebuild_history(state)


@pytest.mark.parametrize('violation', [None, 'owner', 'group', 'mode', 'outside', 'link', 'ownership-drift', 'ancestor'])
@pytest.mark.parametrize('live', [False, True])
def test_private_cache_metadata_is_preserved_and_narrowly_allowed(tmp_path, monkeypatch, violation, live):
    import os
    from types import SimpleNamespace
    server = load('trusted_release_server')
    monkeypatch.setattr(server, 'PRODUCTION', tmp_path / 'production')
    root = server.PRODUCTION / 'frontend' / '.next' if live else tmp_path / 'previous-next'
    cache = root / 'cache'
    cache.mkdir(parents=True)
    (cache / 'entry').write_text('cache')
    (root / 'BUILD_ID').write_text('build')
    monkeypatch.setattr(server.pwd, 'getpwnam', lambda name: SimpleNamespace(pw_uid=995, pw_gid=994))
    original = Path.lstat
    drift = False
    def metadata(path):
        nonlocal drift
        info = original(path)
        fields = list(info)
        fields[4:6] = [0, 0]
        # The fixture stands for protected /opt ancestors, not Linux /tmp 1777.
        # Keep artifact modes untouched so cache permission failures remain real.
        if path in root.parents:
            fields[0] = (fields[0] & ~0o7777) | 0o755
            if violation == 'ancestor' and path == server.PRODUCTION:
                fields[0] |= 0o002
        if path == cache or cache in path.parents:
            fields[4:6] = [995, 994]
            if violation == 'owner':
                fields[4] = 996
            elif violation == 'group':
                fields[5] = 996
            elif violation == 'mode':
                fields[0] |= 0o020
            elif violation == 'ownership-drift' and drift:
                fields[4:6] = [0, 0]
        elif violation == 'outside' and path.name == 'BUILD_ID':
            fields[4:6] = [995, 994]
        return os.stat_result(fields)
    monkeypatch.setattr(Path, 'lstat', metadata)
    if violation == 'link':
        (cache / 'link').symlink_to('entry')
    if violation in ('owner', 'group', 'mode', 'outside', 'link') or (violation == 'ancestor' and live):
        with pytest.raises(server.LaunchError):
            server._frontend_publication_backup_digest(root, live=live)
    else:
        first = server._frontend_publication_backup_digest(root, live=live)
        assert len(first) == 64
        assert (cache / 'entry').read_text() == 'cache'
        if violation == 'ownership-drift':
            drift = True
            assert server._frontend_publication_backup_digest(root, live=live) != first


def test_live_validation_only_accepts_fixed_secure_production_artifacts(tmp_path, monkeypatch):
    server = load('trusted_release_server')
    monkeypatch.setattr(server, 'PRODUCTION', tmp_path / 'production')
    production = server.PRODUCTION / 'frontend'
    production.mkdir(parents=True)
    for name in ('.next', 'node_modules'):
        (production / name).mkdir()
    calls = []
    monkeypatch.setattr(server, 'secure_path', lambda path, **kw: calls.append((path, kw)))
    monkeypatch.setattr(server, 'validate_metadata', lambda *a, **kw: None)
    for name in ('.next', 'node_modules'):
        assert len(server._frontend_publication_backup_digest(production / name, live=True)) == 64
        assert calls[-1] == (production / name, {'directory': True})
    for path in (tmp_path / '.next', production / 'previous-next', production / '.next' / 'cache'):
        with pytest.raises(server.LaunchError, match='fixed live'):
            server._frontend_publication_backup_digest(path, live=True)
