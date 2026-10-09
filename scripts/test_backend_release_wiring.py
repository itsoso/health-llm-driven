"""Target admission must reach the privileged executor before any claim."""
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.mark.parametrize("action", ["check-backend-v1", "run-backend-v1"])
def test_backend_rpc_is_an_explicit_fixed_action(action):
    server = module("trusted_release_server")
    sha = "a" * 40
    assert server.parse_command(action + " " + sha) == (action, sha)
    with pytest.raises(server.LaunchError):
        server.parse_command(action + " " + sha + " --target full")


def test_backend_admission_uses_policy_canonical_helper_without_base_override(monkeypatch, tmp_path):
    server = module("trusted_release_server")
    calls = []
    monkeypatch.setattr(server, "STATE", tmp_path)
    monkeypatch.setattr(server, "secure_path", lambda path: None)
    monkeypatch.setattr(server, "clean_environment", lambda path: {"PATH": "/usr/bin:/bin"})
    monkeypatch.setattr(server.subprocess, "run", lambda command, **kwargs: calls.append((command, kwargs)))
    server.attest_backend_ci({"sha": "a" * 40})
    command, kwargs = calls[0]
    assert command == [server.PYTHON, "-I", "-S", "-B", str(tmp_path / "bootstrap" / ("a" * 40) / "source/scripts/trusted_backend_admission.py"), "--sha", "a" * 40]
    assert kwargs["check"] is True
    assert kwargs["stdin"] == server.subprocess.DEVNULL


def test_backend_ready_requires_success_not_skipped_scope():
    jobs = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    job = jobs["backend-release-ready-v1"]
    expected = {"classify-changes", "docs-quality", "backend-test-shards", "backend-quality", "agent-runtime-postgres", "backend-tests", "release-invariants", "type-drift"}
    assert set(job["needs"]) == expected
    assert "always()" in job["if"]
    assert "toJSON(needs)" in str(job)
    body = job["steps"][0]["run"]
    assert 'result' in body and 'success' in body and 'sys.exit' in body


def test_backend_fast_workflow_does_not_change_native_or_ota_admission():
    workflow = yaml.safe_load((ROOT / ".github/workflows/trusted-release.yml").read_text())
    inputs = workflow.get("on", workflow.get(True))["workflow_dispatch"]["inputs"]
    assert "backend-v1" in inputs["target"]["options"]
    for name in ("preflight", "build-permission", "backend"):
        assert "backend-v1" in str(workflow["jobs"][name])
    for name in ("ios-build", "testflight"):
        assert "backend-v1" not in str(workflow["jobs"][name])


@pytest.mark.parametrize('bad_result', [None, 'skipped', 'cancelled', 'failure', 'unknown'])
def test_ready_script_rejects_missing_or_non_successful_dependency(tmp_path, bad_result):
    import json
    import os
    import subprocess
    import sys
    job = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']['backend-release-ready-v1']
    payload = {name: {'result': 'success'} for name in job['needs']}
    if bad_result is None:
        payload.pop('backend-test-shards')
    else:
        payload['backend-test-shards']['result'] = bad_result
    body = job['steps'][0]['run'].replace('python -', '"' + sys.executable + '" -')
    result = subprocess.run(['/bin/bash', '-c', body], env={**os.environ, 'REQUIRED_RESULTS': json.dumps(payload)}, capture_output=True)
    assert result.returncode != 0
    payload = {name: {'result': 'success'} for name in job['needs']}
    result = subprocess.run(['/bin/bash', '-c', body], env={**os.environ, 'REQUIRED_RESULTS': json.dumps(payload)}, capture_output=True)
    assert result.returncode == 0


def test_real_artifact_verification_runs_in_parallel_without_skip_flag():
    jobs = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())['jobs']
    job = jobs['frontend-artifact-integration']
    assert job['needs'] == 'classify-changes'
    command = job['steps'][-1]['run']
    assert 'REVA_TEST_FRONTEND_ARTIFACT_BUILD=1' in command
    assert '-k native_prepare' in command
    assert 'continue-on-error' not in job and 'continue-on-error' not in job['steps'][-1]
