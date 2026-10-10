"""Offline validation for a future reviewed owner secret-entry transaction.

This module has no CLI, filesystem writer, environment reader or network. It does
not authorize provisioning or activation. The lifecycle entry must establish
trusted execution and durable ownership before requesting any real owner input.
Never log inputs or bundle contents. Python does not guarantee memory zeroization.
"""
import base64
import hashlib
import json
import re
import secrets
from urllib.parse import urlsplit


class ProvisioningError(ValueError):
    """A constant rejection that cannot reveal supplied values."""


class _Bundle:
    __slots__ = ('__files',)

    def __init__(self, files):
        self.__files = dict(files)

    def __repr__(self):
        return '<OwnerProvisioningBundle contents=redacted>'

    @property
    def filenames(self):
        return tuple(sorted(self.__files))

    def content(self, name):
        if not isinstance(name, str) or name not in self.__files:
            raise ProvisioningError('provisioning_inputs_rejected')
        return self.__files[name]


def _https(uri, *, origin=False):
    if (not isinstance(uri, str) or not 1 <= len(uri) <= (250 if origin else 500)
            or any(ord(c) < 33 or ord(c) > 126 for c in uri) or '*' in uri):
        raise ValueError()
    parsed = urlsplit(uri)
    if (parsed.scheme != 'https' or not parsed.hostname
            or not re.fullmatch(r'[A-Za-z0-9.-]+', parsed.hostname)
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or (origin and parsed.path) or (parsed.port is not None and parsed.port != 443)):
        raise ValueError()


def validate_config(config):
    """Validate the existing Config contract without importing third-party code as root."""
    required = {'owner', 'origin', 'client_id', 'redirect_uri', 'proxy_gid', 'health_client_id'}
    optional = {'state_dir', 'channel_version'}
    try:
        if (not isinstance(config, dict) or not required <= set(config)
                or set(config) - required - optional):
            raise ValueError()
        for key, pattern in [('owner', r'[A-Za-z0-9_-]{1,128}'),
                ('client_id', r'[A-Za-z0-9_.-]{1,128}'),
                ('health_client_id', r'[A-Za-z0-9_.-]{1,200}')]:
            if not isinstance(config[key], str) or not re.fullmatch(pattern, config[key]):
                raise ValueError()
        _https(config['origin'], origin=True)
        _https(config['redirect_uri'])
        if type(config['proxy_gid']) is not int or not 1 <= config['proxy_gid'] < 2**31:
            raise ValueError()
        if config.get('state_dir', '/var/lib/neo-wechat') != '/var/lib/neo-wechat':
            raise ValueError()
        version = config.get('channel_version', '2.4.9')
        if (not isinstance(version, str) or not re.fullmatch(r'\d{1,3}\.\d{1,3}\.\d{1,3}', version)
                or any(int(part) > 255 for part in version.split('.'))):
            raise ValueError()
        return {**config, 'state_dir': '/var/lib/neo-wechat', 'channel_version': version}
    except (ValueError, TypeError, UnicodeError):
        raise ProvisioningError('provisioning_inputs_rejected') from None


def prepare(*, config, encryption_key, password, password_confirmation, webhook,
            workspace_confirmation, channel_confirmation):
    """Prepare in-memory bytes only after the owner deliberately enters all values.

    Confirmation cannot independently prove a webhook's actual channel; activation
    still requires the owner-selected Slack app/channel and synthetic sender test.
    Key shape checks do not establish entropy. The owner supplies a CSPRNG key;
    this function never creates or exports a replacement encryption key.
    """
    config = validate_config(config)
    try:
        if not isinstance(encryption_key, str) or len(encryption_key) != 44:
            raise ValueError()
        key = base64.b64decode(encryption_key, validate=True)
        if len(key) != 32 or len(set(key)) < 2 or base64.b64encode(key).decode() != encryption_key:
            raise ValueError()
        if (not isinstance(password, str) or not 16 <= len(password) <= 256
                or any(ord(c) < 32 or ord(c) == 127 for c in password)
                or not isinstance(password_confirmation, str)
                or not secrets.compare_digest(password.encode(), password_confirmation.encode())):
            raise ValueError()
        if (not isinstance(webhook, str) or len(webhook) > 256 or not re.fullmatch(
                r'https://hooks\.slack\.com/services/T6TNPEFLY/[A-Za-z0-9]+/[A-Za-z0-9_-]+', webhook)
                or workspace_confirmation != 'T6TNPEFLY' or channel_confirmation != 'C0C89QBQLBB'):
            raise ValueError()
        salt = secrets.token_bytes(16)
        hashed = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
        return _Bundle({
            'config.json': (json.dumps(config, sort_keys=True, separators=(',', ':')) + '\n').encode(),
            'encryption_key': encryption_key.encode() + b'\n',
            'admin_password_hash': b'scrypt-v1:' + base64.b64encode(salt) + b':' + base64.b64encode(hashed) + b'\n',
            'slack_webhook': webhook.encode() + b'\n',
        })
    except (ValueError, TypeError, UnicodeError):
        raise ProvisioningError('provisioning_inputs_rejected') from None
