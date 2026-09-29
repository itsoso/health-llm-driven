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
    m.validate_runtime_changes(['mobile/app/login.tsx', 'mobile/hooks/useAuth.tsx'])
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
