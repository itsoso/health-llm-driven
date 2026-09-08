"""Check the executable dispatch boundary and workflow capability wiring."""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/trusted-release.yml").read_text())


@pytest.mark.parametrize("job", ["preflight", "build-permission", "backend", "ios-build", "testflight"])
@pytest.mark.parametrize("changes", [
    {"TARGET_SHA": "main"},
    {"TARGET_SHA": "a" * 40},
    {"TARGET_SHA": "$(touch /tmp/reva-never-execute)"},
    {"GITHUB_SHA": "b" * 40},
    {"GITHUB_REF": "refs/heads/unreviewed"},
    {"GITHUB_REPOSITORY": "other/fork"},
])
def test_bad_dispatch_cannot_reach_bootstrap_or_network(job, changes):
    # All mismatches must fail in shell builtins, before sudo, Git or API calls.
    body = WORKFLOW["jobs"][job]["steps"][0]["run"]
    prefix = body.split("/usr/bin/sudo", 1)[0]
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-eu", "-c", prefix + "\necho BOOTSTRAP_REACHED\n"],
        env={
            "PATH": "/nonexistent", "TARGET_SHA": "c" * 40, "GITHUB_SHA": "c" * 40,
            "GITHUB_REF": "refs/heads/main", "GITHUB_REPOSITORY": "itsoso/health-llm-driven",
            **changes,
        }, capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "BOOTSTRAP_REACHED" not in result.stdout


def test_dispatch_cannot_auto_publish_or_reuse_test_runner():
    triggers = WORKFLOW.get("on", WORKFLOW.get(True))
    assert set(triggers) == {"workflow_dispatch"}
    target = triggers["workflow_dispatch"]["inputs"]["target"]
    assert target["default"] == "validate"
    assert set(target["options"]) == {"validate", "backend", "release"}
    assert WORKFLOW["permissions"] == {"contents": "read", "actions": "read"}
    assert WORKFLOW["concurrency"]["cancel-in-progress"] is False
    for name, job in WORKFLOW["jobs"].items():
        assert job["runs-on"] == "ubuntu-24.04"
        assert 1 <= job["timeout-minutes"] <= 90
        if name != "preflight":
            assert job["environment"] == "release-production"
            expected = "inputs.target == 'release' || inputs.target == 'backend'" if name in {"build-permission", "backend"} else "inputs.target == 'release'"
            assert job["if"] == expected
    assert WORKFLOW["jobs"]["build-permission"]["needs"] == "preflight"
    assert WORKFLOW["jobs"]["backend"]["needs"] == "build-permission"
    assert WORKFLOW["jobs"]["ios-build"]["needs"] == "build-permission"
    assert set(WORKFLOW["jobs"]["testflight"]["needs"]) == {"backend", "ios-build"}


def test_backend_only_has_no_vendor_credentials_or_build_claims():
    for name in ("preflight", "build-permission", "backend"):
        body = str(WORKFLOW["jobs"][name])
        assert "EXPO_TOKEN" not in body
        assert "claim-build" not in body
        assert "claim-testflight" not in body
    for name in ("ios-build", "testflight"):
        assert WORKFLOW["jobs"][name]["if"] == "inputs.target == 'release'"


def test_actions_are_immutable_and_preflight_has_no_production_secret():
    for name, job in WORKFLOW["jobs"].items():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"actions/[\w-]+@[0-9a-f]{40}", step["uses"])
            if name == "preflight":
                assert "secrets." not in str(step)


@pytest.mark.parametrize("key,hostkeys", [("", ""), ("fake-private-key", ""), ("", "fake-host-key")])
def test_missing_backend_credential_fails_before_ssh(key, hostkeys):
    body = WORKFLOW["jobs"]["backend"]["steps"][1]["run"]
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-eu", "-c", body],
        env={"PATH": "/nonexistent", "RELEASE_KEY": key, "RELEASE_HOST_KEYS": hostkeys},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert "not found" not in result.stderr
    assert "fake-private-key" not in result.stdout + result.stderr


def test_missing_expo_credential_fails_before_ci_or_vendor_call():
    body = WORKFLOW["jobs"]["testflight"]["steps"][-1]["run"]
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-eu", "-c", body],
        env={"PATH": "/nonexistent", "EXPO_TOKEN": ""}, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 1
    assert "not found" not in result.stderr


@pytest.mark.parametrize("token", ["", " ", "\n", "fake-token\n"])
def test_bad_expo_credential_fails_before_build_permission_is_consumed(token):
    claim = next(step for step in WORKFLOW["jobs"]["ios-build"]["steps"]
                 if '"claim-build $TARGET_SHA"' in step.get("run", ""))
    prefix = claim["run"].split("/usr/bin/sudo", 1)[0]
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-eu", "-c", prefix + "\necho CLAIM_REACHED\n"],
        env={"PATH": "/nonexistent", "EXPO_TOKEN": token, "RELEASE_KEY": "fixture", "RELEASE_HOST_KEYS": "fixture"},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0
    assert "CLAIM_REACHED" not in result.stdout


def test_expo_authentication_probe_precedes_once_build_claim():
    claim = next(step for step in WORKFLOW["jobs"]["ios-build"]["steps"]
                 if '"claim-build $TARGET_SHA"' in step.get("run", ""))
    assert claim["env"]["EXPO_TOKEN"] == "${{ secrets.REVA_RELEASE_EXPO_TOKEN }}"
    body = claim["run"]
    assert body.index("trusted_release_gate.py") < body.index("whoami") < body.index('"claim-build $TARGET_SHA"')
    assert "Expo authentication preflight failed; build permission not consumed" in body


def test_every_run_script_is_valid_bash():
    for job in WORKFLOW["jobs"].values():
        for step in job["steps"]:
            if "run" in step:
                result = subprocess.run(["/bin/bash", "--noprofile", "--norc", "-n"],
                                        input=step["run"], text=True, capture_output=True, check=False)
                assert result.returncode == 0, (step["name"], result.stderr)
