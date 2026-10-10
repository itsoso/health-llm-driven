"""Release timing must remain inert, sanitized, and separate from receipts."""
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def helper():
    source = (ROOT / 'deploy.sh').read_text()
    match = re.search(r'^release_timing_checkpoint\(\) \{\n.*?^\}', source, re.M | re.S)
    assert match, 'release timing helper missing'
    return match.group()


@pytest.mark.parametrize('phase', ['backend_started', 'guard_started', 'finalized'])
def test_checkpoint_is_stderr_only_and_uses_shell_elapsed_time(phase):
    result = subprocess.run(['/bin/bash', '-eu', '-c', helper() +
        f'\nSECONDS=17\nrelease_timing_checkpoint {phase}\nprintf receipt'], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout == 'receipt'
    assert result.stderr == f'REVA_RELEASE_TIMING phase={phase} shell_elapsed_seconds=17\n'


def test_checkpoint_does_not_disclose_invalid_input():
    result = subprocess.run(['/bin/bash', '-eu', '-c', helper() +
        '\nrelease_timing_checkpoint "secret=value"'], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'secret' not in result.stdout + result.stderr


def test_failed_command_still_stops_before_later_checkpoint():
    result = subprocess.run(['/bin/bash', '-eu', '-c', helper() +
        '\nrelease_timing_checkpoint guard_started\n(exit 23)\nrelease_timing_checkpoint finalized'],
        capture_output=True, text=True)
    assert result.returncode == 23
    assert 'phase=guard_started' in result.stderr
    assert 'phase=finalized' not in result.stderr


def test_guard_has_separate_remote_clock_and_dependency_schema_restart_boundaries():
    source = (ROOT / 'deploy.sh').read_text()
    body = source.split('release_timing_checkpoint guard_started', 1)[1].split('CODE_EXIT=$?', 1)[0]
    assert '$(declare -f release_timing_checkpoint)' in body
    assert 'SECONDS=0' in body
    boundaries = [
        'release_timing_checkpoint remote_guard_started',
        'systemctl stop health-backend.socket',
        'release_timing_checkpoint remote_writers_stopped',
        '$remote_git_sync',
        'release_timing_checkpoint remote_checkout_completed',
        '$remote_dependency_sync',
        'release_timing_checkpoint remote_dependencies_completed',
        'python scripts/apply_managed_migrations.py',
        'release_timing_checkpoint remote_migrations_completed',
        'verify_runtime_schema_compatibility.py',
        'release_timing_checkpoint remote_schema_completed',
        'systemctl restart celery-worker celery-beat',
        'release_timing_checkpoint remote_services_restarted',
    ]
    offsets = [body.index(x) for x in boundaries]
    assert offsets == sorted(offsets)
    for label in [x for x in boundaries if x.startswith('release_timing_checkpoint')]:
        assert label + ' &&' in body


@pytest.mark.parametrize('installer_exit', [0, 23])
def test_pi_install_checkpoints_use_real_generated_command_and_preserve_exit(tmp_path, installer_exit):
    import os
    import shlex
    env_file = tmp_path / 'deploy.env'
    env_file.write_text('DEPLOY_SERVER=synthetic\nDEPLOY_PATH=/tmp/synthetic-release\n')
    prepared = subprocess.run(['/bin/bash', '-eu', '-c',
        'source ' + shlex.quote(str(ROOT / 'deploy.sh')) +
        '\nREMOTE_RELEASE_STATE_DIR=/tmp/synthetic-release-state\nREQUIREMENTS_LOCK_SHA=' + 'c' * 64 +
        '\nremote_dependency_sync_command'], capture_output=True, text=True,
        env={**os.environ, 'DEPLOY_ENV_FILE': str(env_file)})
    assert prepared.returncode == 0, prepared.stderr
    # Execute the actual Pi preamble from the generated remote command. Stop at
    # the Python-cache boundary so this test needs no live host or dependencies.
    preamble = prepared.stdout.split("    release_state_dir=", 1)[0]
    runtime = tmp_path / 'pi-runtime'
    runtime.mkdir()
    (runtime / 'install.sh').write_text(f'printf "installer-called\\n"\nexit {installer_exit}\n')
    result = subprocess.run(['/bin/bash', '-eu', '-c', preamble + '\n}\nsync_backend_dependencies'],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == installer_exit, (result.stdout, result.stderr)
    assert result.stdout == 'installer-called\n'
    assert re.search(r'REVA_RELEASE_TIMING phase=remote_pi_install_started shell_elapsed_seconds=\d+\n', result.stderr)
    if installer_exit == 0:
        assert re.search(r'REVA_RELEASE_TIMING phase=remote_pi_install_completed shell_elapsed_seconds=\d+\n', result.stderr)
    else:
        assert 'phase=remote_pi_install_completed' not in result.stderr
