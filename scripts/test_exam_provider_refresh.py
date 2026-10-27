import time
import pytest
import exam_provider_refresh as refresh


def payload():
    return {'repository': refresh.REPO, 'token': 'ghs_' + 'x' * 40, 'expires_at': int(time.time()) + 3500,
            'app_id': refresh.APP, 'installation_id': refresh.INSTALLATION,
            'permissions': dict(refresh.PERMISSIONS), 'provider_sha256': refresh.PROVIDER_HASH}


def test_exact_scopes_expiration_and_provider_required():
    refresh.validate(payload())
    for changed in ({'app_id': 1}, {'installation_id': 1}, {'repository': 'other/repo'},
                    {'permissions': {'actions': 'write'}}, {'provider_sha256': '0' * 64},
                    {'expires_at': int(time.time()) - 1}, {'token': 'ghp_admin'}):
        with pytest.raises(refresh.RefreshBlocked):
            refresh.validate({**payload(), **changed})


def test_real_api_scope_readback_uses_only_bounded_read_endpoints():
    calls = []
    def api(path, token):
        calls.append(path)
        if path == '/installation/repositories':
            return {'total_count': 1, 'repositories': [{'full_name': refresh.REPO}]}
        if '/contents/' in path:
            return {'type': 'file', 'path': 'AGENTS.md'}
        if path.endswith('/actions/runs?per_page=1'):
            return {'workflow_runs': []}
        return {'full_name': refresh.REPO, 'permissions': {'pull': False, 'push': False, 'admin': False}}
    refresh.verify_token(payload(), api)
    assert len(calls) == 4
    assert all('access_tokens' not in path for path in calls)


def test_unexpected_repository_rejected_before_install():
    with pytest.raises(refresh.RefreshBlocked):
        refresh.verify_token(payload(), lambda *args: {'total_count': 2, 'repositories': []})


def test_provider_signature_bound_to_exact_receiver_and_public_key(tmp_path):
    key = tmp_path / 'public.pem'
    key.write_text('not the pinned provider key')
    envelope = {'receiver_sha': 'a' * 40, 'credential': payload(), 'signature': 'bad'}
    with pytest.raises(refresh.RefreshBlocked):
        refresh.verify_envelope(envelope, 'b' * 40, key)
    with pytest.raises(refresh.RefreshBlocked):
        refresh.verify_envelope(envelope, 'a' * 40, key)


def test_unsigned_arbitrary_stdin_metadata_cannot_be_received():
    with pytest.raises(refresh.RefreshBlocked):
        refresh.verify_envelope(payload(), 'a' * 40, refresh.Path(__file__).with_name('exam-provider-app-public.pem'))


def test_signing_bytes_cover_every_scope_and_token_field():
    value = payload()
    original = refresh.signed_bytes(value, 'a' * 40)
    for field, changed in [('token', 'ghs_' + 'y' * 40), ('permissions', {'actions': 'write'}),
                           ('app_id', 1), ('installation_id', 1), ('expires_at', 1)]:
        assert refresh.signed_bytes({**value, field: changed}, 'a' * 40) != original
    assert refresh.signed_bytes(value, 'b' * 40) != original


def test_real_rsa_signature_roundtrip_and_tampering(tmp_path, monkeypatch):
    private, public = tmp_path / 'private.pem', tmp_path / 'public.pem'
    refresh.subprocess.run(['/usr/bin/openssl', 'genrsa', '-out', str(private), '2048'],
                           check=True, capture_output=True)
    refresh.subprocess.run(['/usr/bin/openssl', 'rsa', '-in', str(private), '-pubout', '-out', str(public)],
                           check=True, capture_output=True)
    monkeypatch.setattr(refresh, 'PUBLIC_KEY_HASH', refresh.hashlib.sha256(public.read_bytes()).hexdigest())
    value, sha = payload(), 'a' * 40
    signature = refresh.subprocess.run(['/usr/bin/openssl', 'dgst', '-sha256', '-sign', str(private)],
        input=refresh.signed_bytes(value, sha), capture_output=True, check=True).stdout
    envelope = {'receiver_sha': sha, 'credential': value, 'signature': refresh.base64.b64encode(signature).decode()}
    assert refresh.verify_envelope(envelope, sha, public) == value
    envelope['credential'] = {**value, 'token': 'ghs_' + 'z' * 40}
    with pytest.raises(refresh.subprocess.CalledProcessError):
        refresh.verify_envelope(envelope, sha, public)


def test_long_existing_provider_installation_token_format_is_supported():
    refresh.validate({**payload(), 'token': 'ghs_' + 'x' * 190 + '.' + 'x' * 195})
