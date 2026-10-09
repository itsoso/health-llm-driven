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
