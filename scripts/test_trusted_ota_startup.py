"""Credential-free hosted OTA startup/export fidelity, never release authorization.

The executable phases are only for a fresh dedicated Linux GitHub runner. Normal
pytest runs test the adapter without touching /opt or installing dependencies.
"""
import os
from pathlib import Path
import subprocess
import sys

import pytest


SHA = 'a' * 40


def test_fidelity_reuses_actual_bootstrap_dependencies_and_preflight():
    steps = workflow_steps()
    materialize = fidelity_command('materialize')
    assert 'test "$GITHUB_REF" = refs/heads/main' not in materialize
    assert 'trusted_release_gate.py --sha' not in materialize
    assert 'TEST ONLY: live CI admission omitted; no release authorization' in materialize
    assert 'test "$TARGET_SHA" = "$GITHUB_SHA"' in materialize
    assert 'https://github.com/itsoso/health-llm-driven.git' in materialize
    assert "seal_bootstrap_directory(Path('/opt'))" in materialize
    assert fidelity_command('tools') == '\n'.join(selected_step(steps, name) for name in PHASE_STEPS['tools'])
    assert fidelity_command('smoke') == selected_step(steps, PHASE_STEPS['smoke'][0])
    for phase in PHASE_STEPS:
        assert 'secrets.' not in fidelity_command(phase)
    with pytest.raises(ValueError):
        fidelity_command('publish')


@pytest.mark.parametrize('omission', [
    'test "$GITHUB_REF" = refs/heads/main',
    '/usr/bin/python3 -I scripts/trusted_release_gate.py --sha "$1" --workflow-sha "$1"',
])
@pytest.mark.parametrize('mutation', ['remove', 'duplicate', 'change'])
def test_changed_admission_cannot_be_silently_omitted(monkeypatch, omission, mutation):
    steps = workflow_steps()
    step = next(s for s in steps if s.get('name') == PHASE_STEPS['materialize'][0])
    replacement = '' if mutation == 'remove' else omission + '\n' + omission if mutation == 'duplicate' else omission + ' --changed'
    step['run'] = step['run'].replace(omission, replacement)
    monkeypatch.setattr(sys.modules[__name__], 'workflow_steps', lambda: steps)
    with pytest.raises(ValueError, match='admission changed'):
        fidelity_command('materialize')


def test_export_uses_real_untouched_publisher_without_gate_or_vendor_calls():
    body = fidelity_command('export')
    assert 'publisher.preflight(sha)' in body
    assert 'publisher.Adapter(sha, contract, None)' in body
    assert 'adapter.export()' in body
    assert 'adapter.validate_source()' in body
    assert 'adapter.artifact()' in body
    assert 'TEST_EXPORT_VERIFIED' in body
    for forbidden in ('adapter.rpc', 'adapter.eas', 'adapter.gate', 'vendor_admission', 'publisher.publish', 'EXPO_TOKEN', '--prepare'):
        assert forbidden not in body


def test_fidelity_drops_secrets_and_bounds_execution(monkeypatch):
    monkeypatch.setattr(sys, 'platform', 'linux')
    for name, value in {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'itsoso/health-llm-driven',
                        'GITHUB_SHA': SHA, 'GITHUB_REF': 'refs/heads/codex/diagnostic',
                        'EXPO_TOKEN': 'SECRET', 'RELEASE_KEY': 'PRIVATE', 'NODE_OPTIONS': 'BAD'}.items():
        monkeypatch.setenv(name, value)
    calls = []
    monkeypatch.setattr(subprocess, 'run', lambda args, **kwargs: calls.append((args, kwargs)))
    run_fidelity_phase('export')
    assert len(calls) == 1
    args, options = calls[0]
    assert args[:5] == ['/bin/bash', '--noprofile', '--norc', '-euo', 'pipefail']
    assert options['check'] is True and options['timeout'] == 1000
    assert set(options['env']) == {'PATH', 'HOME', 'GITHUB_REPOSITORY', 'GITHUB_SHA', 'GITHUB_REF', 'TARGET_SHA'}


@pytest.mark.parametrize('variable,value', [
    ('GITHUB_ACTIONS', 'false'), ('GITHUB_REPOSITORY', 'fork/repo'),
    ('GITHUB_SHA', 'not-a-sha'), ('GITHUB_REF', 'refs/tags/v1'),
])
def test_fidelity_refuses_wrong_runner_context(monkeypatch, variable, value):
    monkeypatch.setattr(sys, 'platform', 'linux')
    for name, current in {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': 'itsoso/health-llm-driven',
                          'GITHUB_SHA': SHA, 'GITHUB_REF': 'refs/heads/main'}.items():
        monkeypatch.setenv(name, current)
    monkeypatch.setenv(variable, value)
    monkeypatch.setattr(subprocess, 'run', lambda *args, **kwargs: pytest.fail('must not execute'))
    with pytest.raises(ValueError):
        run_fidelity_phase('materialize')


def test_materialization_requires_fresh_namespace_before_touching_opt():
    body = fidelity_command('materialize')
    guard = 'test ! -e /opt/reva-release\ntest ! -L /opt/reva-release'
    assert guard in body
    assert body.index(guard) < body.index('seal_bootstrap_directory')


@pytest.mark.parametrize('existing', ['directory', 'dangling_symlink'])
def test_fidelity_fresh_namespace_guard_rejects_collisions(tmp_path, existing):
    namespace = tmp_path / 'release'
    if existing == 'directory':
        namespace.mkdir()
    else:
        namespace.symlink_to(tmp_path / 'missing')
    # Execute only the two guards; never execute root bootstrap on the test host.
    guard = '\n'.join(fidelity_command('materialize').splitlines()[:2])
    command = guard.replace('/opt/reva-release', '"$1"') + '\nprintf MUST_NOT_RUN'
    result = subprocess.run(['/bin/bash', '--noprofile', '--norc', '-euo', 'pipefail',
                             '-c', command, 'guard-test', str(namespace)],
                            capture_output=True, text=True, check=False)
    assert result.returncode != 0 and not result.stdout
    assert os.path.lexists(namespace)


@pytest.mark.parametrize('phase', ['materialize', 'tools', 'smoke', 'export'])
def test_generated_fidelity_shell_is_valid_without_executing_it(phase):
    subprocess.run(['/bin/bash', '-n'], input=fidelity_command(phase), text=True, check=True)


def test_generated_export_python_is_valid():
    import ast
    body = EXPORT_COMMAND.split("<<'PY_EXPORT'\n", 1)[1].split('\nPY_EXPORT', 1)[0]
    ast.parse(body)


PHASE_STEPS = {
    'materialize': (
        'Materialize exact canonical source and verify current main CI before credentials',
        'Canonical source metadata after_checkout',
    ),
    'tools': (
        'Harden fixed Node toolchain ownership before dependencies and credentials',
        'Install locked CLI and app dependencies without lifecycle scripts or shared cache',
        'Canonical source metadata after_dependencies',
    ),
    'smoke': ('Read-only publisher context and native source preflight',),
}


def workflow_steps():
    import yaml
    root = Path(__file__).resolve().parents[1]
    return yaml.safe_load((root / '.github/workflows/trusted-ota.yml').read_text())['jobs']['ota']['steps']


def selected_step(steps, name):
    selected = [step for step in steps if step.get('name') == name]
    if (len(selected) != 1 or 'secrets.' in str(selected[0])
            or not isinstance(selected[0].get('run'), str)):
        raise ValueError('ambiguous or credential-bearing startup phase')
    return selected[0]['run']


EXPORT_COMMAND = '''
[[ "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]]
test "$TARGET_SHA" = "$GITHUB_SHA"
/usr/bin/sudo /usr/bin/env -i PATH=/usr/bin:/bin HOME=/root /usr/bin/python3 -I -S -B - "$TARGET_SHA" <<'PY_EXPORT'
import importlib.util
import json
from pathlib import Path
import sys

# Test-only caller of unchanged production methods. This does not certify CI,
# native vendor cohort, live channel/environment, backend health or publication.
try:
    sha = sys.argv[1]
    spec = importlib.util.spec_from_file_location(
        'reviewed_test_ota_publisher', '/opt/reva-release/source/scripts/trusted_ota_publish.py')
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    contract = publisher.preflight(sha)
    adapter = publisher.Adapter(sha, contract, None)
    adapter.export()
    adapter.validate_source()
    proof = adapter.artifact()
    contract.validate_proof(proof)
    # Only non-authorizing status; no release/claim/vendor receipt is persisted.
    print(json.dumps({'sha': sha, 'state': 'TEST_EXPORT_VERIFIED',
                      'release_authorized': False}, sort_keys=True))
except Exception:
    print('Credential-free OTA startup/export fidelity failed.', file=sys.stderr)
    raise SystemExit(1)
PY_EXPORT
'''


def fidelity_command(phase):
    """Source-derived shell; only two explicit release-admission omissions.

    No production helper is patched. Export calls unchanged production methods
    with no token and cannot reach a gate, server RPC or vendor mutation.
    """
    if phase == 'export':
        return EXPORT_COMMAND
    if phase not in PHASE_STEPS:
        raise ValueError('only credential-free startup/export phases are allowed')
    steps = workflow_steps()
    bodies = [selected_step(steps, name) for name in PHASE_STEPS[phase]]
    if phase == 'materialize':
        body = bodies[0]
        omissions = (
            'test "$GITHUB_REF" = refs/heads/main',
            '/usr/bin/python3 -I scripts/trusted_release_gate.py --sha "$1" --workflow-sha "$1"',
        )
        for omitted in omissions:
            lines = body.splitlines()
            if sum(line.strip() == omitted for line in lines) != 1:
                raise ValueError('production admission changed; review test adapter explicitly')
            body = '\n'.join(line for line in lines if line.strip() != omitted) + '\n'
        # Reject collisions before any hardening. Never clean up or normalize an
        # existing release namespace; the dedicated hosted VM is disposable.
        bodies[0] = ('test ! -e /opt/reva-release\ntest ! -L /opt/reva-release\n'
                     'printf "%s\\n" "TEST ONLY: live CI admission omitted; no release authorization"\n'
                     + body)
    return '\n'.join(bodies)


def run_fidelity_phase(phase):
    import re
    if sys.platform != 'linux' or os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('fidelity requires a fresh dedicated Linux GitHub runner')
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    sha, ref = os.environ.get('GITHUB_SHA', ''), os.environ.get('GITHUB_REF', '')
    if repository != 'itsoso/health-llm-driven':
        raise ValueError('actual canonical CI repository required')
    if re.fullmatch(r'[0-9a-f]{40}', sha) is None or not ref.startswith(('refs/heads/', 'refs/pull/')):
        raise ValueError('actual CI revision and ref required')
    command = fidelity_command(phase)
    # Do not inherit credentials, Git/CA/proxy overrides or language startup hooks.
    env = {'PATH': '/usr/bin:/bin', 'HOME': os.environ['HOME'],
           'GITHUB_REPOSITORY': repository, 'GITHUB_SHA': sha,
           'GITHUB_REF': ref, 'TARGET_SHA': sha}
    print('Credential-free OTA fidelity: ' + phase + '; no release authorization.', flush=True)
    subprocess.run(['/bin/bash', '--noprofile', '--norc', '-euo', 'pipefail', '-c', command],
                   env=env, check=True, timeout=1000 if phase == 'export' else 900)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--fidelity-phase', choices=(*PHASE_STEPS, 'export'), required=True)
    run_fidelity_phase(parser.parse_args().fidelity_phase)
