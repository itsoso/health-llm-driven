"""OTA claims bind bytes; unknown native changes and manifests fail closed."""
import importlib.util
import json
from pathlib import Path

import pytest


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


def test_native_baseline_matches_delivered_testflight_276():
    m = module()
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('ota_publisher', root / 'scripts/trusted_ota_publish.py')
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    expected = ('1.3.5', '7fe06d8b34750b6bd56db8d5ec45d1aee705b02e', '09719eb6-2887-4100-9ccb-6533fd9d71ed')
    for contract in (m, publisher):
        assert (contract.RUNTIME, contract.NATIVE_SHA, contract.NATIVE_BUILD) == expected
    assert json.loads((root / 'mobile/app.json').read_text())['expo']['version'] == m.RUNTIME


def test_fixed_native_equivalence_source_hashes_and_environment(monkeypatch):
    import subprocess
    m = module()
    root = Path(__file__).resolve().parents[1]
    paths = ['mobile/app.config.ts', 'mobile/eas.json', 'mobile/plugins/withIosSupportedOrientations.js',
             'mobile/plugins/__tests__/withIosSupportedOrientations.test.js', 'mobile/jest.config.js']
    m.validate_runtime_changes(paths, root=root)
    for variable in ('REVA_IPAD_ENABLED', 'ROKID_IOS_SDK_ENABLED', 'INCLUDE_WATCH_APP', 'INCLUDE_SIRI_INTENTS'):
        monkeypatch.setenv(variable, '1')
        with pytest.raises(ValueError): m.validate_runtime_changes(paths, root=root)
        monkeypatch.delenv(variable)


def test_fixed_native_equivalence_rejects_changed_known_file(tmp_path):
    m = module()
    path = tmp_path/'mobile/eas.json'; path.parent.mkdir(); path.write_text('{}')
    with pytest.raises(ValueError): m.validate_runtime_changes(['mobile/eas.json'], root=tmp_path)


def test_fixed_native_equivalence_rejects_symlink(tmp_path):
    m = module()
    root = Path(__file__).resolve().parents[1]
    (tmp_path/'mobile').mkdir()
    (tmp_path/'mobile/eas.json').symlink_to(root/'mobile/eas.json')
    with pytest.raises(ValueError): m.validate_runtime_changes(['mobile/eas.json'], root=tmp_path)


def test_fixed_equivalence_real_git_source_contract(tmp_path, monkeypatch):
    import subprocess
    m = module()
    repository = Path(__file__).resolve().parents[1]
    def git(*args):
        return subprocess.check_output(['git', '-C', str(tmp_path), *args], text=True).strip()
    git('init', '-q')
    git('config', 'user.name', 'Synthetic Test')
    git('config', 'user.email', 'synthetic@example.invalid')
    native = '7fe06d8b34750b6bd56db8d5ec45d1aee705b02e'
    for relative in ('mobile/app.json', *m.REVIEWED_NATIVE_SOURCE):
        target = tmp_path/relative; target.parent.mkdir(parents=True, exist_ok=True)
        previous = subprocess.run(['git','-C',str(repository),'show',native+':'+relative],capture_output=True)
        if previous.returncode == 0: target.write_bytes(previous.stdout)
    git('add', 'mobile'); git('commit', '-qm', 'baseline')
    monkeypatch.setattr(m, 'NATIVE_SHA', git('rev-parse', 'HEAD'))
    for relative in m.REVIEWED_NATIVE_SOURCE:
        (tmp_path/relative).write_bytes((repository/relative).read_bytes())
    git('add', 'mobile'); git('commit', '-qm', 'reviewed equivalent production config')
    sha=git('rev-parse','HEAD')
    m.validate_source(tmp_path, sha)
    altered=tmp_path/'mobile/plugins/withIosSupportedOrientations.js'
    altered.write_text(altered.read_text()+'\n// changed native source\n')
    git('add','mobile');git('commit','-qm','unreviewed')
    with pytest.raises(ValueError): m.validate_source(tmp_path,git('rev-parse','HEAD'))


def test_fixed_equivalence_evidence_matches_implementation():
    import hashlib
    m=module();root=Path(__file__).resolve().parents[1]
    evidence=json.loads((root/'docs/reviews/2026-10-14-ota-native-equivalence.json').read_text())
    assert evidence['candidate_source_exceptions']==m.REVIEWED_NATIVE_SOURCE
    assert evidence['source_count']==287 and evidence['equal_source_count']==285
    assert evidence['production_config_equal'] is True
    assert evidence['observed_production_supports_tablet'] is False
    for relative, expected in m.REVIEWED_NATIVE_SOURCE.items():
        assert hashlib.sha256((root/relative).read_bytes()).hexdigest()==expected
