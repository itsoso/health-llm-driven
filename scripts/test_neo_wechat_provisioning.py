"""Synthetic owner-entry validation; no TTY, filesystem writer or network."""
import base64
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    'neo_provisioning', Path(__file__).with_name('neo_wechat_provisioning.py'))
provision = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provision)


def public():
    return dict(owner='synthetic-owner', origin='https://health.example',
        client_id='neo-public', redirect_uri='https://client.example/callback',
        proxy_gid=1234, health_client_id='neo-health-read')


def inputs():
    return dict(config=public(), encryption_key=base64.b64encode(bytes(range(32))).decode(),
        password='synthetic-owner-password', password_confirmation='synthetic-owner-password',
        webhook='https://hooks.slack.com/services/T6TNPEFLY/B123/synthetic-only',
        workspace_confirmation='T6TNPEFLY', channel_confirmation='C0C89QBQLBB')


def test_valid_bundle_uses_existing_service_contract_without_plain_password():
    bundle = provision.prepare(**inputs())
    assert set(bundle.filenames) == {'config.json', 'encryption_key',
        'admin_password_hash', 'slack_webhook'}
    from services.neo_wechat.server import Config, password_ok
    config = Config.model_validate_json(bundle.content('config.json'))
    assert config.health_client_id == 'neo-health-read'
    assert config.state_dir == '/var/lib/neo-wechat'
    auth = 'Basic ' + base64.b64encode(b'owner:synthetic-owner-password').decode()
    assert password_ok(auth, bundle.content('admin_password_hash'))
    assert b'synthetic-owner-password' not in bundle.content('admin_password_hash')
    assert 'synthetic-only' not in repr(bundle)
    assert 'synthetic-owner-password' not in repr(bundle)
    assert 'synthetic-owner' not in repr(bundle)


@pytest.mark.parametrize('key,value', [
    ('origin', 'http://health.example'), ('origin', 'https://health.example/'),
    ('origin', 'https://health.example:bad'), ('origin', 'https://health.example:443;evil'),
    ('redirect_uri', 'https://user:password@client.example/callback'),
    ('redirect_uri', 'https://client.example/callback?x=1'),
    ('redirect_uri', 'https://client.example/callback#x'),
    ('redirect_uri', 'https://*.example/callback'),
    ('redirect_uri', 'https://client.example/\ncallback'),
    ('owner', '../owner'), ('proxy_gid', True), ('proxy_gid', 0),
    ('health_client_id', None), ('state_dir', '/opt/health-app'),
    ('unknown', 'value'),
])
def test_public_input_rejects_scope_and_path_expansion(key, value):
    args = inputs()
    args['config'][key] = value
    with pytest.raises(provision.ProvisioningError):
        provision.prepare(**args)


@pytest.mark.parametrize('key,value', [
    ('encryption_key', 'bad-key'), ('encryption_key', base64.b64encode(b'x' * 31).decode()),
    ('encryption_key', base64.b64encode(b'x' * 32).decode()),
    ('password', 'too-short'), ('password_confirmation', 'different-password'),
    ('webhook', 'https://hooks.slack.com/services/OTHER/B123/synthetic-only'),
    ('webhook', 'https://hooks.slack.com/services/T6TNPEFLY/B123/synthetic-only\n'),
    ('workspace_confirmation', 'OTHER'), ('channel_confirmation', 'C_OTHER'),
])
def test_secret_validation_errors_never_echo_input(key, value):
    args = inputs()
    args[key] = value
    with pytest.raises(provision.ProvisioningError) as error:
        provision.prepare(**args)
    assert str(error.value) == 'provisioning_inputs_rejected'
    assert 'synthetic-only' not in repr(error.value)
    assert 'synthetic-owner-password' not in repr(error.value)


def test_fresh_password_salt_and_exact_credential_names():
    first, second = provision.prepare(**inputs()), provision.prepare(**inputs())
    assert first.content('admin_password_hash') != second.content('admin_password_hash')
    with pytest.raises(provision.ProvisioningError):
        first.content('../encryption_key')
    with pytest.raises(provision.ProvisioningError):
        first.content('password')


def test_helper_exposes_no_writer_cli_or_environment_secret_reader():
    import ast
    tree = ast.parse(Path(provision.__file__).read_text())
    imports = {alias.name.split('.')[0] for node in ast.walk(tree)
        if isinstance(node, ast.Import) for alias in node.names}
    assert not imports & {'subprocess', 'socket', 'httpx', 'requests', 'getpass', 'os'}
    assert not hasattr(provision, 'main')
    assert not hasattr(provision, 'write')
