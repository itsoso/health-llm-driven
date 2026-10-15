"""Release API credentials reach only isolated metadata gates via stdin."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / '.github/workflows/trusted-release.yml').read_text())
GATES = [(job, step) for job, config in WORKFLOW['jobs'].items()
         for step in config.get('steps', []) if 'trusted_release_gate.py' in step.get('run', '')]

@pytest.mark.parametrize('job,step', GATES, ids=[f'{job}-{step["name"]}' for job, step in GATES])
def test_every_release_gate_has_scoped_readonly_stdin_auth(job, step):
    assert WORKFLOW['permissions'] == {'contents':'read', 'actions':'read'}
    assert step['env']['GH_TOKEN'] == '${{ github.token }}'
    body = step['run'].replace('\\\n', '')
    lines = [line.strip() for line in body.splitlines() if 'trusted_release_gate.py' in line]
    assert lines
    for line in lines:
        assert line.startswith('printf \'%s\' "$GH_TOKEN" | /usr/bin/sudo /usr/bin/env -i ')
        assert '--token-stdin' in line
        assert 'GH_TOKEN=' not in line
    assert 'test -n "$GH_TOKEN"' in body
    assert 'set -x' not in body


def test_actual_gate_pipeline_keeps_token_out_of_argv_and_environment(tmp_path):
    step = GATES[0][1]
    line = next(line.strip() for line in step['run'].replace('\\\n', '').splitlines()
                if 'trusted_release_gate.py' in line)
    assert line.startswith('printf ')
    receiver = tmp_path / 'receiver.py'
    receiver.write_text('import os,sys\nassert "GH_TOKEN" not in os.environ\n'
                        'assert "synthetic_only_token" not in repr(sys.argv)\n'
                        'assert "--token-stdin" in sys.argv\n'
                        'assert sys.stdin.read()=="synthetic_only_token"\n')
    line = line.replace('/usr/bin/sudo ', '').replace('/usr/bin/python3', sys.executable)
    line = line.replace('/opt/reva-release/source/scripts/trusted_release_gate.py', str(receiver))
    env = {'PATH':'/usr/bin:/bin', 'GH_TOKEN':'synthetic_only_token',
           'TARGET_SHA':'a'*40, 'GITHUB_SHA':'a'*40, 'CI_TARGET':'full'}
    result = subprocess.run(['/bin/bash','--noprofile','--norc','-euo','pipefail','-c',line],
                            env=env, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'synthetic_only_token' not in result.stdout + result.stderr
