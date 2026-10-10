"""Synthetic local provisioning transactions; no real owner input or deployment."""
import base64
import json
import os
import stat

import pytest

from scripts import neo_wechat_provision_transaction as transaction
from scripts.neo_wechat_provisioning import prepare, _Bundle


def bundle():
    return prepare(config=dict(owner='synthetic-owner', origin='https://health.example',
        client_id='synthetic-client', redirect_uri='https://client.example/callback',
        proxy_gid=1234, health_client_id='synthetic-health'),
        encryption_key=base64.b64encode(bytes(range(32))).decode(),
        password='synthetic-test-password', password_confirmation='synthetic-test-password',
        webhook='https://hooks.slack.com/services/T6TNPEFLY/B123/synthetic-only',
        workspace_confirmation='T6TNPEFLY', channel_confirmation='C0C89QBQLBB')


@pytest.fixture
def setup(tmp_path):
    config, audit = tmp_path / 'config', tmp_path / 'lifecycle'
    config.mkdir(mode=0o710)
    audit.mkdir(mode=0o700)
    os.chmod(config, 0o710)
    os.chmod(audit, 0o700)
    config_fd = os.open(config, os.O_RDONLY | os.O_DIRECTORY)
    audit_fd = os.open(audit, os.O_RDONLY | os.O_DIRECTORY)
    def identity(fd):
        info = os.fstat(fd)
        return (info.st_dev, info.st_ino)
    args = dict(config_fd=config_fd, audit_root_fd=audit_fd,
        config_identity=identity(config_fd), audit_identity=identity(audit_fd),
        owner_uid=os.getuid(), bridge_gid=os.getgid(), audit_gid=os.getgid(),
        operation_id='a' * 32, dormant_receipt_sha256='b' * 64,
        publisher_sha='c' * 40, guard=lambda: None, bundle=bundle())
    try:
        yield config, audit, args
    finally:
        os.close(config_fd)
        os.close(audit_fd)


def audit_records(audit):
    return sorted((audit / transaction.NAMESPACE / ('a' * 32)).glob('*.json'))


def test_success_is_dormant_exact_private_files_and_separate_durable_audit(setup):
    config, audit, args = setup
    result = transaction.provision(**args)
    assert result['state'] == 'PROVISIONED_DORMANT'
    assert result['activation_authorized'] is False
    assert sorted(p.name for p in config.iterdir()) == sorted(transaction.FILENAMES)
    for name in transaction.FILENAMES:
        path = config / name
        info = path.stat()
        assert path.read_bytes() == args['bundle'].content(name)
        assert info.st_uid == os.getuid()
        assert info.st_gid == os.getgid()
        assert stat.S_IMODE(info.st_mode) == (0o640 if name == 'config.json' else 0o600)
        assert info.st_nlink == 1
    records = audit_records(audit)
    assert len(records) == 10  # initial intent, four intent/verified pairs, completion
    for path in records:
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        row = json.loads(path.read_text())
        assert row['operation_id'] == 'a' * 32
        assert row['dormant_receipt_sha256'] == 'b' * 64
    raw = ''.join(path.read_text() for path in records) + repr(result)
    for secret in ('synthetic-owner', 'synthetic-only', 'synthetic-test-password',
                   args['bundle'].content('encryption_key').decode().strip()):
        assert secret not in raw


@pytest.mark.parametrize('field,value', [
    ('operation_id', '../escape'), ('operation_id', 'A' * 32),
    ('publisher_sha', 'a' * 39), ('dormant_receipt_sha256', 'bad'),
    ('config_identity', (1, 2)), ('audit_identity', (1, 2)),
    ('owner_uid', True), ('bridge_gid', True), ('audit_gid', -1),
    ('guard', None), ('bundle', object()),
])
def test_invalid_preconditions_write_nothing(setup, field, value):
    config, audit, args = setup
    args[field] = value
    with pytest.raises(transaction.TransactionError, match='^provisioning_precondition_failed$'):
        transaction.provision(**args)
    assert not list(config.iterdir()) and not list(audit.iterdir())


@pytest.mark.parametrize('target,mode', [('config', 0o777), ('config', 0o700), ('audit', 0o755)])
def test_directory_permissions_exact_not_silently_repaired(setup, target, mode):
    config, audit, args = setup
    os.chmod(config if target == 'config' else audit, mode)
    with pytest.raises(transaction.TransactionError, match='precondition'):
        transaction.provision(**args)
    assert not list(config.iterdir()) and not list(audit.iterdir())


@pytest.mark.parametrize('kind', ['regular', 'symlink', 'hardlink'])
def test_existing_destination_never_opened_or_overwritten(setup, tmp_path, kind):
    config, audit, args = setup
    original = tmp_path / 'original'
    original.write_bytes(b'synthetic-existing-material')
    path = config / 'encryption_key'
    if kind == 'regular':
        path.write_bytes(b'synthetic-existing-material')
    elif kind == 'symlink':
        path.symlink_to(original)
    else:
        os.link(original, path)
    with pytest.raises(transaction.TransactionError, match='precondition'):
        transaction.provision(**args)
    assert original.read_bytes() == b'synthetic-existing-material'
    assert path.read_bytes() == b'synthetic-existing-material'
    assert not list(audit.iterdir())


def test_guard_exception_is_sanitized_before_any_write(setup):
    config, audit, args = setup
    def guard():
        raise RuntimeError('synthetic-sensitive-guard-value')
    args['guard'] = guard
    with pytest.raises(transaction.TransactionError) as error:
        transaction.provision(**args)
    assert str(error.value) == 'provisioning_precondition_failed'
    assert not list(config.iterdir()) and not list(audit.iterdir())


def test_fsync_failure_after_secret_write_preserves_intent_and_blocks_new_operation(setup, monkeypatch):
    config, audit, args = setup
    original = os.fsync
    size = len(args['bundle'].content('encryption_key'))
    def interrupted(fd):
        if os.fstat(fd).st_size == size and stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('synthetic-sensitive-fsync-error')
        original(fd)
    monkeypatch.setattr(transaction.os, 'fsync', interrupted)
    with pytest.raises(transaction.TransactionError, match='^provisioning_outcome_uncertain$'):
        transaction.provision(**args)
    assert (config / 'encryption_key').exists()
    records = audit_records(audit)
    assert [p.name for p in records] == ['000-intent.json', '001-intent.json']
    assert 'synthetic-sensitive' not in ''.join(p.read_text() for p in records)
    args['operation_id'] = 'd' * 32
    with pytest.raises(transaction.TransactionError, match='precondition'):
        transaction.provision(**args)
    assert len(list((audit / transaction.NAMESPACE).iterdir())) == 1


def test_claimed_namespace_blocks_even_if_no_config_was_written(setup):
    config, audit, args = setup
    (audit / transaction.NAMESPACE).mkdir(mode=0o700)
    with pytest.raises(transaction.TransactionError, match='precondition'):
        transaction.provision(**args)
    assert not list(config.iterdir())


def test_guard_failure_after_claim_retains_only_metadata(setup):
    config, audit, args = setup
    calls = []
    def guard():
        calls.append(None)
        if len(calls) == 2:
            raise RuntimeError('synthetic-private')
    args['guard'] = guard
    with pytest.raises(transaction.TransactionError, match='outcome_uncertain'):
        transaction.provision(**args)
    assert not list(config.iterdir())
    assert (audit / transaction.NAMESPACE).is_dir()


def test_no_cli_network_or_secret_input_adapter():
    assert not hasattr(transaction, 'main')
    assert not hasattr(transaction, 'getpass')
    assert not hasattr(transaction, 'subprocess')


@pytest.mark.parametrize('name,value', [
    ('config.json', b'{}'), ('config.json', b'{"owner":"one","owner":"two"}'),
    ('encryption_key', b'bad'), ('admin_password_hash', b'plaintext-password'),
    ('slack_webhook', b'https://hooks.slack.com/services/OTHER/B/secret\n'),
    ('extra', b'secret'), ('encryption_key', 'not-bytes'),
])
def test_malformed_bundle_rejected_before_writes(setup, name, value):
    config, audit, args = setup
    values = {key: args['bundle'].content(key) for key in transaction.FILENAMES}
    values[name] = value
    args['bundle'] = _Bundle(values)
    with pytest.raises(transaction.TransactionError, match='precondition'):
        transaction.provision(**args)
    assert not list(config.iterdir()) and not list(audit.iterdir())


@pytest.mark.parametrize('kind', ['symlink', 'hardlink'])
def test_destination_race_fails_exclusive_create_and_preserves_original(setup, tmp_path, monkeypatch, kind):
    config, audit, args = setup
    original = tmp_path / 'original'
    original.write_bytes(b'unchanged-synthetic')
    writer = transaction._new_file
    def raced(parent, name, *rest):
        if parent == args['config_fd'] and name == 'encryption_key':
            if kind == 'symlink':
                (config / name).symlink_to(original)
            else:
                os.link(original, config / name)
        return writer(parent, name, *rest)
    monkeypatch.setattr(transaction, '_new_file', raced)
    with pytest.raises(transaction.TransactionError, match='outcome_uncertain'):
        transaction.provision(**args)
    assert original.read_bytes() == b'unchanged-synthetic'
    assert len(audit_records(audit)) == 2


def test_completion_fsync_failure_is_uncertain_and_cannot_retry(setup, monkeypatch):
    config, audit, args = setup
    original = os.fsync
    def interrupted(fd):
        info = os.fstat(fd)
        if stat.S_ISREG(info.st_mode):
            raw = os.pread(fd, 2048, 0)
            if b'"phase":"completed"' in raw:
                raise OSError('synthetic-private')
        original(fd)
    monkeypatch.setattr(transaction.os, 'fsync', interrupted)
    with pytest.raises(transaction.TransactionError, match='outcome_uncertain'):
        transaction.provision(**args)
    assert set(p.name for p in config.iterdir()) == set(transaction.FILENAMES)
    assert len(audit_records(audit)) == 10
    with pytest.raises(transaction.TransactionError, match='precondition'):
        transaction.provision(**args)


def test_parent_directory_fsync_failure_does_not_create_credentials(setup, monkeypatch):
    config, audit, args = setup
    original = os.fsync
    def interrupted(fd):
        if fd == args['audit_root_fd']:
            raise OSError('synthetic-private')
        original(fd)
    monkeypatch.setattr(transaction.os, 'fsync', interrupted)
    with pytest.raises(transaction.TransactionError, match='outcome_uncertain'):
        transaction.provision(**args)
    assert not list(config.iterdir())
    assert (audit / transaction.NAMESPACE).exists()


def test_initial_intent_fsync_failure_stops_before_any_credential(setup, monkeypatch):
    config, audit, args = setup
    original = os.fsync
    def interrupted(fd):
        if stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError('synthetic-sensitive')
        original(fd)
    monkeypatch.setattr(transaction.os, 'fsync', interrupted)
    with pytest.raises(transaction.TransactionError, match='outcome_uncertain'):
        transaction.provision(**args)
    assert not list(config.iterdir())
    assert [p.name for p in audit_records(audit)] == ['000-intent.json']


def test_partial_secret_write_keeps_original_partial_file_and_intent(setup, monkeypatch):
    config, audit, args = setup
    original = os.write
    raw = args['bundle'].content('encryption_key')
    def interrupted(fd, data):
        if data == raw:
            original(fd, data[:5])
            raise OSError('synthetic-sensitive')
        return original(fd, data)
    monkeypatch.setattr(transaction.os, 'write', interrupted)
    with pytest.raises(transaction.TransactionError, match='outcome_uncertain'):
        transaction.provision(**args)
    assert (config / 'encryption_key').read_bytes() == raw[:5]
    assert [p.name for p in audit_records(audit)] == ['000-intent.json', '001-intent.json']


def test_hardlink_drift_of_written_credential_blocks_verification(setup, tmp_path, monkeypatch):
    config, audit, args = setup
    original = transaction._new_file
    def linked(parent, name, *rest):
        metadata = original(parent, name, *rest)
        if parent == args['config_fd'] and name == 'encryption_key':
            os.link(config / name, tmp_path / 'synthetic-link')
        return metadata
    monkeypatch.setattr(transaction, '_new_file', linked)
    with pytest.raises(transaction.TransactionError, match='outcome_uncertain'):
        transaction.provision(**args)
    assert [p.name for p in config.iterdir()] == ['encryption_key']
    assert [p.name for p in audit_records(audit)] == ['000-intent.json', '001-intent.json']
