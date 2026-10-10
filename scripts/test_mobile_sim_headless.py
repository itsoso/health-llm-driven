import importlib.util
import json
from pathlib import Path
import subprocess

import pytest


def load_runner():
    spec = importlib.util.spec_from_file_location('headless', Path(__file__).with_name('mobile_sim_headless.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_runner(tmp_path, *, locked=True, fail=None):
    app = tmp_path / 'app'
    app.mkdir()
    (app / 'app').write_bytes(b'actual installed binary')
    calls = []
    def run(argv, **kwargs):
        calls.append(argv)
        if fail and fail in argv:
            raise subprocess.CalledProcessError(1, argv)
        if argv == ['lock-state']:
            return 'locked' if locked else 'unlocked'
        if 'get_app_container' in argv:
            return str(app)
        if 'screenshot' in argv:
            Path(argv[-1]).write_bytes(b'PNG evidence')
        return ''
    return run, calls


def test_locked_capture_has_actual_artifact_and_lock_evidence(tmp_path):
    module = load_runner()
    run, calls = fake_runner(tmp_path)
    receipt = module.capture('2D49F985-8B2F-4BE1-BAA8-CA5A672D9428', 'bundle.id', tmp_path / 'out', ['lock-state'], run=run, require_locked=True)
    assert receipt['status'] == 'passed'
    assert receipt['lock_before'] == receipt['lock_after'] == 'locked'
    assert len(receipt['installed_app_sha256']) == 64
    assert receipt['source_sha'] is None
    assert receipt['functional_acceptance'] == 'unverified'
    assert any('launch' in call for call in calls)


def test_require_locked_fails_before_launch_and_writes_receipt(tmp_path):
    module = load_runner()
    run, calls = fake_runner(tmp_path, locked=False)
    with pytest.raises(RuntimeError):
        module.capture('2D49F985-8B2F-4BE1-BAA8-CA5A672D9428', 'bundle.id', tmp_path / 'out', ['lock-state'], run=run, require_locked=True)
    assert not any('launch' in call for call in calls)
    assert json.loads((tmp_path / 'out/receipt.json').read_text())['status'] == 'failed'


@pytest.mark.parametrize('failure', ['get_app_container', 'launch', 'screenshot'])
def test_command_failure_is_not_success_and_has_no_raw_error(tmp_path, failure):
    module = load_runner()
    run, _ = fake_runner(tmp_path, fail=failure)
    with pytest.raises(subprocess.CalledProcessError):
        module.capture('2D49F985-8B2F-4BE1-BAA8-CA5A672D9428', 'bundle.id', tmp_path / 'out', ['lock-state'], run=run)
    receipt = json.loads((tmp_path / 'out/receipt.json').read_text())
    assert receipt['status'] == 'failed'
    assert 'stderr' not in receipt


def test_lock_state_unknown_blocks(tmp_path):
    module = load_runner()
    run, _ = fake_runner(tmp_path)
    def unknown(argv, **kwargs):
        return 'unknown' if argv == ['lock-state'] else run(argv, **kwargs)
    with pytest.raises(RuntimeError):
        module.capture('2D49F985-8B2F-4BE1-BAA8-CA5A672D9428', 'bundle.id', tmp_path / 'out', ['lock-state'], run=unknown)


def test_receipt_directory_cannot_overwrite_previous_run(tmp_path):
    module = load_runner()
    run, _ = fake_runner(tmp_path)
    output = tmp_path / 'out'
    output.mkdir()
    (output / 'receipt.json').write_text('original')
    with pytest.raises(FileExistsError):
        module.capture('2D49F985-8B2F-4BE1-BAA8-CA5A672D9428', 'bundle.id', output, ['lock-state'], run=run)
    assert (output / 'receipt.json').read_text() == 'original'


@pytest.mark.parametrize('device', ['booted', 'iPhone 17', '', 'not-a-uuid'])
def test_explicit_uuid_required_before_any_command(tmp_path, device):
    module = load_runner()
    run, calls = fake_runner(tmp_path)
    with pytest.raises(ValueError):
        module.capture(device, 'bundle.id', tmp_path / 'out', ['lock-state'], run=run)
    assert calls == []


def test_ui_suite_failure_blocks_and_retains_failed_receipt(tmp_path):
    module = load_runner()
    run, calls = fake_runner(tmp_path, fail='test-without-building')
    suite = tmp_path / 'tests.xctestrun'
    suite.write_text('suite')
    with pytest.raises(subprocess.CalledProcessError):
        module.capture('2D49F985-8B2F-4BE1-BAA8-CA5A672D9428', 'bundle.id', tmp_path / 'out', ['lock-state'], run=run, xctestrun=suite)
    receipt = json.loads((tmp_path / 'out/receipt.json').read_text())
    assert receipt['status'] == 'failed'
    assert 'ui_test_execution' not in receipt


@pytest.mark.parametrize('value, expected', [(True, 'locked'), (False, 'unlocked')])
def test_mac_state_uses_explicit_ioreg_boolean(monkeypatch, value, expected):
    module = load_runner()
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *a, **k: module.plistlib.dumps({'IOConsoleLocked': value}))
    assert module.mac_lock_state() == expected


@pytest.mark.parametrize('state', [{}, {'IOConsoleLocked': 'False'}, {'IOConsoleLocked': 0}])
def test_mac_state_never_defaults_unknown_to_unlocked(monkeypatch, state):
    module = load_runner()
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *a, **k: module.plistlib.dumps(state))
    with pytest.raises(RuntimeError):
        module.mac_lock_state()


def test_successful_ui_suite_relaunches_app_before_final_capture(tmp_path):
    module = load_runner()
    run, calls = fake_runner(tmp_path)
    suite = tmp_path / 'tests.xctestrun'
    suite.write_text('suite')
    receipt = module.capture('2D49F985-8B2F-4BE1-BAA8-CA5A672D9428', 'bundle.id', tmp_path / 'out', ['lock-state'], run=run, xctestrun=suite)
    tests = next(i for i, call in enumerate(calls) if 'test-without-building' in call)
    launch = [i for i, call in enumerate(calls) if 'launch' in call]
    screenshot = next(i for i, call in enumerate(calls) if 'screenshot' in call)
    assert launch[0] < tests < launch[1] < screenshot
    assert receipt['ui_test_execution'] == 'passed'
    assert receipt['functional_acceptance'] == 'unverified'


def test_unlock_during_test_fails_instead_of_claiming_locked_success(tmp_path):
    module = load_runner()
    run, calls = fake_runner(tmp_path)
    states = iter(['locked', 'unlocked'])
    def changing(argv, **kwargs):
        return next(states) if argv == ['lock-state'] else run(argv, **kwargs)
    with pytest.raises(RuntimeError):
        module.capture('2D49F985-8B2F-4BE1-BAA8-CA5A672D9428', 'bundle.id', tmp_path / 'out', ['lock-state'], run=changing, require_locked=True)
    receipt = json.loads((tmp_path / 'out/receipt.json').read_text())
    assert receipt['status'] == 'failed'
    assert receipt['lock_before'] == 'locked'
    assert receipt['lock_after'] == 'unlocked'
    assert (tmp_path / 'out').stat().st_mode & 0o777 == 0o700
    assert (tmp_path / 'out/receipt.json').stat().st_mode & 0o777 == 0o600
