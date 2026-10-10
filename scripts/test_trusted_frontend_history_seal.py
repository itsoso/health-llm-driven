"""Sealing archives removes blob I/O, never operation or rollback validation."""
import hashlib
import json
import shutil

import pytest

from test_trusted_frontend_publish_history import evidence  # noqa: F401


def second_operation(server, op, operation_id="b" * 32):
    other = op.with_name(operation_id)
    shutil.copytree(op, other)
    for name in ('intent.json', 'before.json', 'install-started.json', 'verified.json', 'completed.json'):
        path = other / name
        value = json.loads(path.read_text())
        value['operation_id'] = other.name
        path.write_text(json.dumps(value))
    path = other / 'completed.json'
    value = json.loads(path.read_text())
    value['proof_sha256'] = {name: hashlib.sha256((other / name).read_bytes()).hexdigest()
                            for name in value['proof_sha256']}
    path.write_text(json.dumps(value))
    return other


def seal(server, state, active):
    return server.seal_frontend_publication_history(state, active_operation=active,
                                                   live_digest='e' * 64)


def test_seal_once_then_only_one_rollback_content_read(evidence, monkeypatch):
    server, state, op, _ = evidence
    other = second_operation(server, op)
    original = server._frontend_publication_backup_digest
    reads = []
    def digest(path, **kwargs):
        reads.append(path.parent.name)
        return original(path, **kwargs)
    monkeypatch.setattr(server, '_frontend_publication_backup_digest', digest)
    result = seal(server, state, other.name)
    assert result['state'] == 'FRONTEND_HISTORY_SEALED'
    assert set(reads) == {op.name, other.name}
    reads.clear()
    server.assert_frontend_publication_history(state)
    assert reads == [other.name, other.name]


def test_archive_blob_not_scanned_but_cannot_be_promoted_corrupt(evidence, monkeypatch):
    server, state, op, _ = evidence
    other = second_operation(server, op)
    seal(server, state, other.name)
    (op / 'previous-next/file').write_text('corrupt archived content')
    original = server._frontend_publication_backup_entries
    def entries(root, **kwargs):
        assert root.parent != op, 'archived blob must not be traversed'
        return original(root, **kwargs)
    with monkeypatch.context() as context:
        context.setattr(server, '_frontend_publication_backup_entries', entries)
        server.assert_frontend_publication_history(state)
    anchor = (state / 'frontend-history-seal/anchor.json').read_bytes()
    with pytest.raises(server.LaunchError):
        seal(server, state, op.name)
    assert (state / 'frontend-history-seal/anchor.json').read_bytes() == anchor


@pytest.mark.parametrize('mutation', ['hot-blob', 'proof', 'terminal', 'missing-audit', 'unknown-operation'])
def test_sealing_never_hides_required_operation_validation(evidence, mutation):
    server, state, op, _ = evidence
    other = second_operation(server, op)
    seal(server, state, other.name)
    if mutation == 'hot-blob':
        (other / 'previous-next/file').write_text('corrupt rollback')
    elif mutation == 'proof':
        (op / 'build.log').write_text('corrupt proof')
    elif mutation == 'terminal':
        (op / 'completed.json').unlink()
    elif mutation == 'missing-audit':
        shutil.rmtree(op)
    else:
        (op.parent / ('c' * 32)).mkdir(mode=0o700)
    with pytest.raises(server.LaunchError):
        server.assert_frontend_publication_history(state)


@pytest.mark.parametrize('mutation', ['checkpoint', 'anchor', 'key-mode', 'partial', 'extra-file'])
def test_invalid_or_partial_seal_blocks_without_full_fallback(evidence, mutation):
    server, state, op, _ = evidence
    seal(server, state, op.name)
    root = state / 'frontend-history-seal'
    if mutation in ('checkpoint', 'anchor'):
        path = root / ('0000000001.json' if mutation == 'checkpoint' else 'anchor.json')
        path.write_text('{}')
    elif mutation == 'key-mode':
        (root / 'key').chmod(0o644)
    elif mutation == 'partial':
        (root / 'anchor.json').unlink()
    else:
        (root / 'unknown').write_text('unknown')
    with pytest.raises(server.LaunchError):
        server.assert_frontend_publication_history(state)


def test_checkpoint_replay_cannot_roll_back_anchor(evidence):
    server, state, op, _ = evidence
    other = second_operation(server, op)
    seal(server, state, op.name)
    root = state / 'frontend-history-seal'
    old = (root / '0000000001.json').read_bytes()
    seal(server, state, other.name)
    (root / '0000000002.json').write_bytes(old)
    with pytest.raises(server.LaunchError):
        server.assert_frontend_publication_history(state)


def test_live_binding_mismatch_cannot_create_seal(evidence):
    server, state, op, _ = evidence
    with pytest.raises(server.LaunchError):
        server.seal_frontend_publication_history(state, active_operation=op.name,
                                                 live_digest='f' * 64)
    assert not (state / 'frontend-history-seal').exists()


def test_unsealed_new_operation_is_fully_checked(evidence):
    server, state, op, _ = evidence
    seal(server, state, op.name)
    other = second_operation(server, op)
    (other / 'previous-next/file').write_text('corrupt new rollback')
    with pytest.raises(server.LaunchError):
        server.assert_frontend_publication_history(state)


@pytest.mark.parametrize('sync_number', [3, 4, 5, 6, 7])
def test_each_commit_sync_failure_retains_blocked_state_and_exact_recovery(evidence, monkeypatch, sync_number):
    server, state, op, _ = evidence
    original = server._sync_directory
    calls = 0
    def fail_once(path):
        nonlocal calls
        calls += 1
        if calls == sync_number:
            raise OSError('synthetic fsync failure')
        original(path)
    with monkeypatch.context() as context:
        context.setattr(server, '_sync_directory', fail_once)
        with pytest.raises(OSError):
            seal(server, state, op.name)
    with pytest.raises(server.LaunchError):
        server.assert_frontend_publication_history(state)
    root = state / 'frontend-history-seal'
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    plan = server.inspect_frontend_history_seal(state)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    with pytest.raises(server.LaunchError):
        server.finish_frontend_history_seal(state, checkpoint_sha256='f' * 64, live_digest='e' * 64)
    result = server.finish_frontend_history_seal(state, checkpoint_sha256=plan['checkpoint_sha256'],
                                               live_digest='e' * 64)
    assert result['state'] == 'FRONTEND_HISTORY_SEALED'
    server.assert_frontend_publication_history(state)
    with pytest.raises(server.LaunchError):
        server.finish_frontend_history_seal(state, checkpoint_sha256=plan['checkpoint_sha256'],
                                           live_digest='e' * 64)


def test_anchor_replace_failure_is_not_success(evidence, monkeypatch):
    server, state, op, _ = evidence
    with monkeypatch.context() as context:
        context.setattr(server.os, 'replace', lambda *args: (_ for _ in ()).throw(OSError('replace failed')))
        with pytest.raises(OSError):
            seal(server, state, op.name)
    plan = server.inspect_frontend_history_seal(state)
    with pytest.raises(server.LaunchError):
        server.assert_frontend_publication_history(state)
    server.finish_frontend_history_seal(state, checkpoint_sha256=plan['checkpoint_sha256'], live_digest='e' * 64)


@pytest.mark.parametrize('mutation', ['hot', 'audit', 'live', 'new-operation'])
def test_changes_after_inspection_prevent_finishing(evidence, monkeypatch, mutation):
    server, state, op, _ = evidence
    original = server._history_commit_anchor
    with monkeypatch.context() as context:
        context.setattr(server, '_history_commit_anchor', lambda *args: (_ for _ in ()).throw(OSError('interrupted')))
        with pytest.raises(OSError):
            seal(server, state, op.name)
    plan = server.inspect_frontend_history_seal(state)
    assert server._history_commit_anchor == original
    if mutation == 'hot':
        (op / 'previous-next/file').write_text('changed rollback')
    elif mutation == 'audit':
        (op / 'build.log').write_text('changed proof')
    elif mutation == 'new-operation':
        second_operation(server, op)
    with pytest.raises(server.LaunchError):
        server.finish_frontend_history_seal(state, checkpoint_sha256=plan['checkpoint_sha256'],
                                           live_digest='f' * 64 if mutation == 'live' else 'e' * 64)


@pytest.mark.parametrize('mutation', ['key-only', 'gap', 'two-tails', 'wrong-previous'])
def test_ambiguous_or_unverified_recovery_is_rejected(evidence, monkeypatch, mutation):
    server, state, op, _ = evidence
    if mutation == 'key-only':
        root = state / 'frontend-history-seal'
        root.mkdir(mode=0o700)
        server._history_write(root / 'key', b'k' * 32)
    else:
        seal(server, state, op.name)
        root = state / 'frontend-history-seal'
        with monkeypatch.context() as context:
            context.setattr(server, '_history_commit_anchor', lambda *args: (_ for _ in ()).throw(OSError('interrupted')))
            with pytest.raises(OSError):
                seal(server, state, op.name)
        if mutation == 'gap':
            (root / '0000000001.json').unlink()
        else:
            key = (root / 'key').read_bytes()
            value = json.loads((root / '0000000002.json').read_bytes())['payload']
            if mutation == 'wrong-previous':
                value['previous'] = 'f' * 64
                (root / '0000000002.json').write_bytes(server._history_signed(key, 'reva-frontend-history-checkpoint-v1', value))
            else:
                value['generation'] = 3
                value['previous'] = hashlib.sha256((root / '0000000002.json').read_bytes()).hexdigest()
                server._history_write(root / '0000000003.json', server._history_signed(key, 'reva-frontend-history-checkpoint-v1', value))
    with pytest.raises(server.LaunchError):
        server.inspect_frontend_history_seal(state)

@pytest.mark.parametrize('measurement', [True, False])
def test_io_receipt_is_explicit_and_contains_no_payload(evidence, monkeypatch, capsys, measurement):
    server, state, op, _ = evidence
    snapshots = iter([{'rchar': 100, 'read_bytes': 20}, {'rchar': 130, 'read_bytes': 25}])
    monkeypatch.setattr(server, '_release_io_snapshot', lambda: next(snapshots) if measurement else None)
    server.assert_frontend_publication_history(state)
    receipt = json.loads(capsys.readouterr().err)
    assert receipt['io'] == ({'rchar': 30, 'read_bytes': 5} if measurement else None)
    assert receipt['io_measurement'] == ('available' if measurement else 'unavailable')
    assert receipt['rollback_operations_verified'] == 1
    assert str(state) not in json.dumps(receipt)


@pytest.mark.parametrize('mutation', ['hardlink', 'symlink', 'directory-mode', 'active-binding'])
def test_sealed_private_metadata_and_live_binding_fail_closed(evidence, mutation):
    server, state, op, _ = evidence
    seal(server, state, op.name)
    root = state / 'frontend-history-seal'
    if mutation == 'hardlink':
        import os
        os.link(root / 'key', state / 'outside-key')
    elif mutation == 'symlink':
        key = (root / 'key').read_bytes()
        (root / 'key').unlink()
        (state / 'outside-key').write_bytes(key)
        (root / 'key').symlink_to(state / 'outside-key')
    elif mutation == 'directory-mode':
        root.chmod(0o755)
    else:
        checkpoint = root / '0000000001.json'
        payload = json.loads(checkpoint.read_bytes())['payload']
        payload['live_digest'] = 'f' * 64
        key = (root / 'key').read_bytes()
        raw = server._history_signed(key, 'reva-frontend-history-checkpoint-v1', payload)
        checkpoint.write_bytes(raw)
        anchor = dict(generation=1, checkpoint_sha256=hashlib.sha256(raw).hexdigest())
        (root / 'anchor.json').write_bytes(server._history_signed(key, 'reva-frontend-history-anchor-v1', anchor))
    with pytest.raises((server.LaunchError, OSError)):
        server.assert_frontend_publication_history(state)


@pytest.mark.parametrize('archive_count', [0, 4, 12])
def test_hot_content_read_count_does_not_grow_with_archive_inventory(evidence, monkeypatch, archive_count):
    server, state, op, _ = evidence
    for number in range(archive_count):
        second_operation(server, op, f'{number + 1:032x}')
    seal(server, state, op.name)
    original = server._frontend_publication_backup_digest
    reads = []
    def digest(path, **kwargs):
        reads.append(path.parent.name)
        return original(path, **kwargs)
    monkeypatch.setattr(server, '_frontend_publication_backup_digest', digest)
    records = server.assert_frontend_publication_history(state)
    assert len(records) == archive_count + 1
    assert reads == [op.name, op.name]
