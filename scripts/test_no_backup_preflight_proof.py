"""Fail-closed contracts for the no-copy preflight retirement proof."""
import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import no_backup_preflight_proof as proof


def test_exact_failure_log_only():
    raw = b'original deployment prefix\n' + proof.FAILURE_SUFFIX
    proof.validate_failure_log(raw)
    for invalid in (raw + b'resumed\n', raw[:-1], proof.FAILURE_SUFFIX * 2,
                    raw.replace(b'migrated persistent state', b'other failure')):
        with pytest.raises(proof.ProofError):
            proof.validate_failure_log(invalid)


@pytest.mark.parametrize('addition', [b'HEALTH_GENE_KNOWLEDGE_PATH=/tmp/gene\0',
    b'HEALTH_RUNTIME_DATA_DIR=/tmp/runtime\0', b'APP_ENV=staging\0',
    b'HEALTH_EVIDENCE_RUNTIME_ENABLED=true\0'])
def test_process_authority_rejects_overrides(addition):
    raw = b'\0'.join(k.encode() + b'=' + v.encode() for k,v in proof.AUTHORITY.items()
                      if k != 'HEALTH_GENE_KNOWLEDGE_PATH') + b'\0'
    proof.validate_process_environment(raw)
    with pytest.raises(proof.ProofError):
        proof.validate_process_environment(raw + addition)


def test_env_temporal_proof_never_claims_historical_digest():
    marker = proof.temporal_environment_proof(100, 100, 200, 300, 400)
    assert marker['historical_env_digest_available'] is False
    for times in [(200,100,200,300,400),(100,100,300,200,400),
                  (100,100,200,500,400),(0,100,200,300,400)]:
        with pytest.raises(proof.ProofError):
            proof.temporal_environment_proof(*times)


def test_implementation_binding_is_content_not_revision_allowlist():
    assert set(proof.FAILED_IMPLEMENTATIONS) == {
        'deploy.sh', 'scripts/trusted_release_server.py',
        'backend/scripts/runtime_state_release_transaction.py'}
    assert all(len(value) == 64 for value in proof.FAILED_IMPLEMENTATIONS.values())


def test_manifest_rejects_env_copy_duplicate_or_unknown():
    hashes = {name: 'a'*64 for name in proof.ARTIFACTS}
    raw = ''.join(f'{digest}  {name}\n' for name,digest in hashes.items()).encode()
    assert proof.parse_manifest(raw) == hashes
    for bad in (raw + b'a'*64 + b'  backend.env.rollback\n', raw + raw,
                raw.replace(b'backup_db.sh', b'unknown.sh')):
        with pytest.raises(proof.ProofError):
            proof.parse_manifest(bad)

@pytest.fixture
def stage_case(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import os
    stage = tmp_path / 'stage'
    stage.mkdir()
    failed = tmp_path / 'failed'
    production = tmp_path / 'production'
    (production / 'backend').mkdir(parents=True)
    lease = tmp_path / 'lease'
    lease.mkdir()
    source = tmp_path / 'receipts' / ('a' * 40)
    source.mkdir(parents=True)
    (source / 'started.json').write_text('{}')
    start = '2026-10-13T12:00:00Z\n'
    (lease / 'started_at').write_text(start)
    (lease / 'stage').write_text(str(stage) + '\n')
    entries = []
    for name, relative in proof.ARTIFACTS.items():
        data = name.encode()
        path = failed / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        (stage / name).write_bytes(data)
        entries.append(hashlib.sha256(data).hexdigest() + '  ' + name + '\n')
    (stage / 'staged.sha256').write_text(''.join(entries))
    env = production / 'backend/.env'
    env.write_text(''.join(k + '=' + v + '\n' for k,v in proof.AUTHORITY.items()))
    instance = proof.NoBackupPreflightProof.__new__(proof.NoBackupPreflightProof)
    instance._closed = False
    instance.production, instance.lease, instance.failed_sha = production, lease, 'a'*40
    instance.bootstrap = SimpleNamespace(STATE=tmp_path / 'receipts')
    instance._lease_snapshot = lambda: {'lease': {'ino': 1}}
    instance._directory = lambda path: {'ino': path.stat().st_ino}
    instance._file = lambda path, *a: (path.read_bytes(), {'gid': 0, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    monkeypatch.setattr(proof.grp, 'getgrnam', lambda _: SimpleNamespace(gr_gid=0))
    monkeypatch.setattr(proof, 'STAGE_PATTERN', str(stage))
    monkeypatch.setattr(proof, 'temporal_environment_proof', lambda *args: {'verified': True})
    return instance, failed, stage, env


def test_stage_accepts_exact_fourteen_artifacts_and_no_env_copies(stage_case):
    instance, failed, stage, env = stage_case
    result = instance._stage(failed)
    assert 'live_env' in result
    assert not any(name.startswith('backend.env.') for name in result)


@pytest.mark.parametrize('damage', ['env_copy', 'changed_artifact', 'gene_override', 'duplicate_env', 'multiline_env'])
def test_stage_rejects_damage(stage_case, damage):
    instance, failed, stage, env = stage_case
    if damage == 'env_copy':
        (stage / 'backend.env.rollback').write_text('forbidden')
    elif damage == 'changed_artifact':
        (stage / 'backup_db.sh').write_text('modified')
    elif damage == 'gene_override':
        env.write_text(env.read_text().replace('/runtime/gene_knowledge.json', '/runtime/other.json'))
    elif damage == 'duplicate_env':
        env.write_text(env.read_text() + 'APP_ENV=production\n')
    else:
        env.write_text('SECRET="unclosed\n' + env.read_text())
    with pytest.raises(proof.ProofError):
        instance._stage(failed)


def test_closed_revalidation_restores_modes_on_error(monkeypatch):
    instance = proof.NoBackupPreflightProof.__new__(proof.NoBackupPreflightProof)
    instance._original_lease = {}
    instance._closed = False
    original = lambda failed: {'original': True}
    instance._workspace = original
    def snapshot():
        assert instance._closed is True
        raise proof.ProofError('changed')
    instance.snapshot = snapshot
    monkeypatch.setattr(proof, 'validate_snapshot', lambda snapshot: None)
    with pytest.raises(proof.ProofError):
        proof.verify_closed(instance, {'workspace': {}})
    assert instance._closed is False
    assert instance._workspace is original


def test_isolated_import_without_script_search_path():
    import subprocess
    path = str(Path(proof.__file__).resolve())
    code = ('import importlib.util; '
            f's=importlib.util.spec_from_file_location("isolated_no_backup", {path!r}); '
            'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
            'assert callable(m.NoBackupPreflightProof.verify_closed)')
    result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_bound_closed_verifier_uses_own_loader_class(monkeypatch):
    spec = importlib.util.spec_from_file_location('separate_proof', proof.__file__)
    separate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(separate)
    instance = separate.NoBackupPreflightProof.__new__(separate.NoBackupPreflightProof)
    assert not isinstance(instance, proof.NoBackupPreflightProof)
    instance._original_lease = {'original': 'lease'}
    instance._closed = False
    instance._workspace = lambda failed: {'old': True}
    expected = {'workspace': {'old': True}, 'stage': {'retained': True}}
    def snapshot():
        assert instance._closed is True
        assert instance._lease_snapshot() == {'original': 'lease'}
        return expected
    instance.snapshot = snapshot
    monkeypatch.setattr(separate, 'validate_snapshot', lambda _: None)
    instance.verify_closed(expected)
    assert instance._closed is False


def complete_snapshot():
    from datetime import UTC, datetime
    started = '2020-01-01T12:00:00Z\n'
    stamp = int(datetime.strptime(started, '%Y-%m-%dT%H:%M:%SZ\n').replace(tzinfo=UTC).timestamp() * 1_000_000_000)
    marker = {'profile': 'pre-mutation-no-copy-v1', 'failed_sha': 'a'*40,
        'production_sha': 'b'*40, 'original_stage': '/tmp/health-app-backup-preflight-123-456',
        'failed_implementations': dict(proof.FAILED_IMPLEMENTATIONS), 'started_at': started,
        'chronology': proof.temporal_environment_proof(stamp-300, stamp-300, stamp-100, stamp, stamp),
        'historical_env_digest_available': False, 'laya_install_not_reached': True}
    def identity(mode=0o600, raw=b'evidence'):
        return {'dev': 1, 'ino': 2, 'mode': mode, 'uid': 0, 'gid': 0, 'sha256': hashlib.sha256(raw).hexdigest()}
    stage = {name: identity() for name in proof.ARTIFACTS}
    stage.update({name: identity() for name in ['token','label','stage','started_at','pointer']})
    stage.update({name: {k:v for k,v in identity(0o700).items() if k != 'sha256'} for name in ['lease','directory']})
    stage['live_env'] = identity(0o640)
    stage['manifest'] = identity(0o400)
    stage['stage'] = identity(raw=(marker['original_stage']+'\n').encode())
    stage['pointer'] = dict(stage['stage'])
    stage['label'] = identity(raw=b'deploy:backend\n')
    stage['started_at'] = identity(raw=started.encode())
    stage['runtime_state_release_transaction.py']['sha256'] = proof.FAILED_IMPLEMENTATIONS['backend/scripts/runtime_state_release_transaction.py']
    return {'workspace': {'original': True}, 'units': {'original': True}, 'terminal': identity(),
            'stage': stage, 'no_backup_preflight': marker}


def test_nested_snapshot_accepts_exact_shape_and_stable_chronology():
    snapshot = complete_snapshot()
    assert proof.validate_snapshot(snapshot) == snapshot['no_backup_preflight']
    assert proof.validate_snapshot(snapshot) == snapshot['no_backup_preflight']


@pytest.mark.parametrize('damage', ['copy','missing','owner','mode','hash','extra_identity','pointer',
                                    'label','time','runtime_hash','terminal','bool_inode','negative_gid'])
def test_nested_snapshot_rejects_invalid_or_unbound_evidence(damage):
    snapshot = complete_snapshot()
    stage = snapshot['stage']
    if damage == 'copy': stage['backend.env.rollback'] = dict(stage['live_env'])
    elif damage == 'missing': stage.pop('manifest')
    elif damage == 'owner': stage['backup_db.sh']['uid'] = 1000
    elif damage == 'mode': stage['manifest']['mode'] = 0o666
    elif damage == 'hash': stage['backup_db.sh']['sha256'] = 'not a digest'
    elif damage == 'extra_identity': stage['backup_db.sh']['contents'] = 'not allowed'
    elif damage == 'pointer': stage['pointer']['sha256'] = 'f'*64
    elif damage == 'label': stage['label']['sha256'] = 'f'*64
    elif damage == 'time': stage['started_at']['sha256'] = 'f'*64
    elif damage == 'runtime_hash': stage['runtime_state_release_transaction.py']['sha256'] = 'f'*64
    elif damage == 'terminal': snapshot['terminal'] = {'some': 'metadata'}
    elif damage == 'bool_inode': stage['backup_db.sh']['ino'] = True
    else: stage['live_env']['gid'] = -1
    with pytest.raises(proof.ProofError):
        proof.validate_snapshot(snapshot)
