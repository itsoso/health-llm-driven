"""OTA claims bind bytes; unknown native changes and manifests fail closed."""
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


# Immutable source that matched the reviewed 276/277 equivalence hashes. The
# working tree can legitimately move to a new native runtime without changing
# what the old production OTA contract admits.
REVIEWED_EQUIVALENT_SHA = '25b85536e3722dc111c528b8a915062a3f971397'
GPS_NATIVE_SHA = 'd1780551d17f3314cf401b91c4846c826fe07c5d'
REVIEWED_LOCK_SHA = 'c28050786c1e9aa70cca33d7e3d5c093652aeb26'
SECURITY_DEPENDENCY_SHA = '20e111d1ba18a21f99ee2611541b083dfddb4916'


def source_bytes(sha, relative):
    repository = Path(__file__).resolve().parents[1]
    return subprocess.check_output(['git', '-C', str(repository), 'show', f'{sha}:{relative}'])


def materialize_sources(root, sha, paths):
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source_bytes(sha, relative))


def module():
    spec = importlib.util.spec_from_file_location('trusted_ota', Path(__file__).with_name('trusted_ota.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_native_changes_require_new_build():
    m = module()
    m.validate_runtime_changes(['mobile/app/login.tsx', 'mobile/hooks/useAuth.tsx', 'mobile/applib/queryClient.ts', 'mobile/applib/__tests__/queryClient.test.ts'])
    for path in ['mobile/app.config.ts', 'mobile/package-lock.json', 'mobile/ios/App.mm', 'mobile/plugins/native.js', 'mobile/modules/bridge.ts']:
        with pytest.raises(ValueError):
            m.validate_runtime_changes([path])


def test_export_hashes_actual_bytes_and_rejects_escape(tmp_path):
    m = module()
    (tmp_path / 'bundle.js').write_bytes(b'bundle')
    (tmp_path / 'asset').write_bytes(b'image')
    metadata = {'version': 0, 'fileMetadata': {'ios': {'bundle': 'bundle.js', 'assets': [{'path': 'asset', 'ext': 'png'}]}}}
    (tmp_path / 'metadata.json').write_text(json.dumps(metadata))
    proof = m.artifact(tmp_path)
    assert proof == {'launch': m.digest(b'bundle'), 'assets': [m.digest(b'image')]}
    metadata['fileMetadata']['ios']['bundle'] = '../secret'
    (tmp_path / 'metadata.json').write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        m.artifact(tmp_path)


def test_manifest_must_match_project_runtime_id_and_all_asset_bytes():
    m = module()
    proof = {'launch': m.digest(b'bundle'), 'assets': [m.digest(b'asset')]}
    ident = 'a1234567-1234-1234-1234-123456789abc'
    payload = {'id': ident, 'runtimeVersion': m.RUNTIME, 'launchAsset': {'hash': proof['launch']}, 'assets': [{'hash': proof['assets'][0]}], 'extra': {'eas': {'projectId': m.PROJECT}}}
    m.validate_manifest(payload, ident, proof)
    for bad in [{**payload, 'runtimeVersion': 'other'}, {**payload, 'assets': []}, {**payload, 'id': 'b1234567-1234-1234-1234-123456789abc'}, {**payload, 'extra': {}}]:
        with pytest.raises(ValueError):
            m.validate_manifest(bad, ident, proof)


def test_local_publishers_do_not_execute_repo_helpers_or_vendor():
    import subprocess
    root = Path(__file__).resolve().parents[1]
    for name in ('mobile-ota.sh', 'mobile-ota-rollback.sh'):
        script = root / 'scripts' / name
        result = subprocess.run(['/bin/sh', str(script), 'production', '--confirm'], env={'PATH': '/nonexistent'}, capture_output=True, text=True)
        assert result.returncode == 78
        assert 'trusted-ota.yml' in result.stderr


def test_native_baseline_matches_delivered_testflight_279():
    m = module()
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('ota_publisher', root / 'scripts/trusted_ota_publish.py')
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    expected = ('1.3.6', '1ba724dcb62ac389a72e41eecf40fea7aaca27e3', '399eb452-402e-47cd-a0e3-18dff2d1ca51')
    for contract in (m, publisher):
        assert (contract.RUNTIME, contract.NATIVE_SHA, contract.NATIVE_BUILD) == expected
    assert json.loads(source_bytes(m.NATIVE_SHA, 'mobile/app.json'))['expo']['version'] == m.RUNTIME


def test_exact_reviewed_lock_is_allowed_but_other_bytes_and_symlinks_rejected(tmp_path, monkeypatch):
    m = module()
    root = Path(__file__).resolve().parents[1]
    relative = 'mobile/package-lock.json'
    target = tmp_path / relative
    target.parent.mkdir()
    reviewed = source_bytes(REVIEWED_LOCK_SHA, relative)
    import hashlib
    assert hashlib.sha256(reviewed).hexdigest() == m.REVIEWED_NATIVE_SOURCE[relative]
    target.write_bytes(reviewed)
    m.validate_runtime_changes([relative], root=tmp_path)
    for variable in ('REVA_IPAD_ENABLED', 'ROKID_IOS_SDK_ENABLED', 'INCLUDE_WATCH_APP', 'INCLUDE_SIRI_INTENTS'):
        monkeypatch.setenv(variable, '1')
        with pytest.raises(ValueError): m.validate_runtime_changes([relative], root=tmp_path)
        monkeypatch.delenv(variable)
    target.write_bytes(source_bytes('59c64cca666d85f3c7b738a508dd197d4ad6c84e', relative))
    with pytest.raises(ValueError): m.validate_runtime_changes([relative], root=tmp_path)
    target.write_bytes(reviewed + b' ')
    with pytest.raises(ValueError): m.validate_runtime_changes([relative], root=tmp_path)
    target.unlink()
    target.symlink_to(root / relative)
    with pytest.raises(ValueError): m.validate_runtime_changes([relative], root=tmp_path)


def test_unreviewed_dependency_lock_does_not_inherit_ota_exception(tmp_path):
    m = module()
    relative = 'mobile/package-lock.json'
    target = tmp_path / relative
    target.parent.mkdir()
    target.write_bytes(source_bytes(SECURITY_DEPENDENCY_SHA, relative) + b' ')
    with pytest.raises(ValueError, match='native or unknown mobile input changed'):
        m.validate_runtime_changes([relative], root=tmp_path)


def test_current_baseline_evidence_has_no_old_native_exceptions():
    m = module()
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads((root/'docs/reviews/2026-10-26-ota-runtime136-tooling-equivalence.json').read_text())
    assert evidence['candidate_source_exceptions'] == m.REVIEWED_NATIVE_SOURCE
    assert set(m.REVIEWED_NATIVE_SOURCE) == {'mobile/scripts/security-dependency-compat.node.cjs', 'mobile/patches/README.md', 'mobile/patches/expo++@expo+cli+55.0.33.patch', 'mobile/package-lock.json', 'mobile/package.json', 'mobile/patches/zod+4.6.6.patch'}


@pytest.mark.parametrize('relative', [
    'mobile/app.json', 'mobile/app.config.ts',
    'mobile/plugins/withIosSupportedOrientations.js',
])
def test_gps_native_candidate_is_rejected_by_delivered_ota_contract(tmp_path, relative):
    m = module()
    materialize_sources(tmp_path, GPS_NATIVE_SHA, [relative])
    with pytest.raises(ValueError, match='native or unknown mobile input changed'):
        m.validate_runtime_changes([relative], root=tmp_path)


def test_old_runtime_manifest_is_rejected_by_279_contract():
    m = module()
    gps_runtime = '1.3.5'
    assert gps_runtime != m.RUNTIME
    proof = {'launch': m.digest(b'bundle'), 'assets': []}
    ident = 'a1234567-1234-1234-1234-123456789abc'
    payload = {'id': ident, 'runtimeVersion': gps_runtime,
               'launchAsset': {'hash': proof['launch']}, 'assets': [],
               'extra': {'eas': {'projectId': m.PROJECT}}}
    with pytest.raises(ValueError):
        m.validate_manifest(payload, ident, proof)


@pytest.mark.parametrize('sha,allowed', [(REVIEWED_LOCK_SHA, True), (SECURITY_DEPENDENCY_SHA, True), ('59c64cca666d85f3c7b738a508dd197d4ad6c84e', False)])
def test_279_migration_contract_admits_only_reviewed_source(tmp_path, sha, allowed):
    m = module()
    assert (m.RUNTIME, m.NATIVE_SHA, m.NATIVE_BUILD) == (
        '1.3.6', '1ba724dcb62ac389a72e41eecf40fea7aaca27e3',
        '399eb452-402e-47cd-a0e3-18dff2d1ca51')
    source = tmp_path / 'source'
    # Source admission compares committed paths/bytes, not Android APK payloads.
    # A shared Git clone has no LFS object store; never download unrelated assets.
    source_env = {**os.environ, 'GIT_LFS_SKIP_SMUDGE': '1'}
    subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout',
                    str(Path(__file__).resolve().parents[1]), str(source)], check=True, env=source_env)
    subprocess.run(['git', '-C', str(source), 'checkout', '--quiet', '--detach', sha], check=True, env=source_env)
    if allowed:
        m.validate_source(source, sha)
    else:
        with pytest.raises(ValueError, match='native or unknown mobile input changed'):
            m.validate_source(source, sha)


@pytest.mark.parametrize('relative', [
    'mobile/package.json', 'mobile/package-lock.json', 'mobile/patches/README.md',
    'mobile/patches/expo++@expo+cli+55.0.33.patch', 'mobile/patches/zod+4.6.6.patch', 'mobile/scripts/security-dependency-compat.node.cjs',
])
def test_reviewed_280_tooling_bytes_only_are_ota_compatible(tmp_path, relative):
    m = module()
    materialize_sources(tmp_path, 'c28050786c1e9aa70cca33d7e3d5c093652aeb26', [relative])
    m.validate_runtime_changes([relative], root=tmp_path)
    target = tmp_path / relative
    target.write_bytes(target.read_bytes() + b' ')
    with pytest.raises(ValueError): m.validate_runtime_changes([relative], root=tmp_path)
    target.unlink()
    with pytest.raises(ValueError): m.validate_runtime_changes([relative], root=tmp_path)


def test_unknown_patch_still_requires_native_review(tmp_path):
    relative = 'mobile/patches/unknown.patch'
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_text('unreviewed')
    with pytest.raises(ValueError): module().validate_runtime_changes([relative], root=tmp_path)
