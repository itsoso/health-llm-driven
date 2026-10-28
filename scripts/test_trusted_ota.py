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


def test_native_baseline_matches_delivered_testflight_283():
    m = module()
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('ota_publisher', root / 'scripts/trusted_ota_publish.py')
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    expected = ('1.3.6', 'ae7a5972921ee9d51eec2c90c7893e6941d2d7ff', 'ea1dda2a-86b3-4e46-adf8-b2b024465154')
    for contract in (m, publisher):
        assert (contract.RUNTIME, contract.NATIVE_SHA, contract.NATIVE_BUILD) == expected
    assert json.loads(source_bytes(m.NATIVE_SHA, 'mobile/app.json'))['expo']['version'] == m.RUNTIME


def test_historical_reviewed_lock_is_not_a_forward_exception(tmp_path, monkeypatch):
    m = module()
    root = Path(__file__).resolve().parents[1]
    relative = 'mobile/package-lock.json'
    target = tmp_path / relative
    target.parent.mkdir()
    reviewed = source_bytes(REVIEWED_LOCK_SHA, relative)
    target.write_bytes(reviewed)
    with pytest.raises(ValueError):
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


def test_historical_tooling_evidence_is_not_an_active_forward_exception():
    m = module()
    root = Path(__file__).resolve().parents[1]
    evidence = json.loads((root/'docs/reviews/2026-10-26-ota-runtime136-tooling-equivalence.json').read_text())
    assert set(evidence['candidate_source_exceptions']) <= m.NATIVE_BASELINE_PATHS
    assert not hasattr(m, 'REVIEWED_NATIVE_SOURCE')
    assert not hasattr(m, 'REVIEWED_BRANDING_SOURCE')


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


@pytest.mark.parametrize('sha,allowed', [('ae7a5972921ee9d51eec2c90c7893e6941d2d7ff', True), (REVIEWED_LOCK_SHA, False), (SECURITY_DEPENDENCY_SHA, False)])
def test_283_migration_contract_admits_only_descendant_runtime_source(tmp_path, sha, allowed):
    m = module()
    assert (m.RUNTIME, m.NATIVE_SHA, m.NATIVE_BUILD) == (
        '1.3.6', 'ae7a5972921ee9d51eec2c90c7893e6941d2d7ff',
        'ea1dda2a-86b3-4e46-adf8-b2b024465154')
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
        with pytest.raises((ValueError, subprocess.CalledProcessError)):
            m.validate_source(source, sha)


@pytest.mark.parametrize('relative', [
    'mobile/package.json', 'mobile/package-lock.json', 'mobile/patches/README.md',
    'mobile/patches/expo++@expo+cli+55.0.33.patch', 'mobile/patches/zod+4.6.6.patch', 'mobile/scripts/security-dependency-compat.node.cjs',
])
def test_historical_280_tooling_bytes_are_not_forward_exceptions(tmp_path, relative):
    m = module()
    materialize_sources(tmp_path, 'c28050786c1e9aa70cca33d7e3d5c093652aeb26', [relative])
    with pytest.raises(ValueError):
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


BRANDING_SHA = '8f7d94696424f92ff57243edb906cd6d2dd14a3a'
BRANDING_PATHS = ('mobile/app.json', 'mobile/app.config.ts', 'mobile/assets/images/icon.png',
    'mobile/assets/images/splash-icon.png', 'mobile/assets/images/adaptive-icon.png',
    'mobile/assets/images/favicon.png', 'mobile/plugins/withWatchApp.js',
    'mobile/plugins/withIntentsExtension.js', 'mobile/plugins/__tests__/withWatchApp.test.js',
    'mobile/modules/rokid-bridge/__tests__/rokidBridge.test.ts',
    'mobile/scripts/__tests__/parser-security.test.js', 'mobile/strings/zh.ts', 'mobile/PRODUCT_MAP.md')

@pytest.mark.parametrize('relative', BRANDING_PATHS)
def test_historical_281_branding_bytes_are_not_forward_exceptions(tmp_path, relative):
    m = module()
    materialize_sources(tmp_path, BRANDING_SHA, [relative])
    with pytest.raises(ValueError):
        m.validate_runtime_changes([relative], root=tmp_path)
    target = tmp_path / relative
    target.write_bytes(target.read_bytes() + b' ')
    with pytest.raises(ValueError): m.validate_runtime_changes([relative], root=tmp_path)
    with pytest.raises(ValueError): m.validate_runtime_changes([relative])


def test_283_review_evidence_binds_forward_pinned_native_paths():
    m = module()
    evidence = json.loads((Path(__file__).resolve().parents[1]/'docs/reviews/2026-10-29-ota-runtime136-guardian-baseline.json').read_text())
    assert set(evidence['source_admission']['pinned_native_paths']) == m.NATIVE_BASELINE_PATHS
    assert m.NATIVE_SHA == 'ae7a5972921ee9d51eec2c90c7893e6941d2d7ff'


@pytest.mark.parametrize('relative', [
    'mobile/app.json',
    'mobile/assets/images/icon.png',
    'mobile/assets/images/splash-icon.png',
    'mobile/assets/images/adaptive-icon.png',
    'mobile/assets/images/favicon.png',
])
def test_full_source_rejects_reverting_283_branding_to_281(tmp_path, relative):
    m = module()
    root = Path(__file__).resolve().parents[1]
    source = tmp_path / 'source'
    source_env = {**os.environ, 'GIT_LFS_SKIP_SMUDGE': '1'}
    subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout', str(root), str(source)], check=True, env=source_env)
    subprocess.run(['git', '-C', str(source), 'checkout', '--quiet', '--detach', m.NATIVE_SHA], check=True, env=source_env)
    target = source / relative
    target.write_bytes(source_bytes(BRANDING_SHA, relative))
    subprocess.run(['git', '-C', str(source), 'add', '--', relative], check=True, env=source_env)
    subprocess.run([
        'git', '-C', str(source), '-c', 'user.name=OTA Test', '-c',
        'user.email=ota-test@example.invalid', 'commit', '--quiet', '-m', 'revert branding fixture'
    ], check=True, env=source_env)
    candidate = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    with pytest.raises(ValueError, match='native or unknown mobile input changed'):
        m.validate_source(source, candidate)
