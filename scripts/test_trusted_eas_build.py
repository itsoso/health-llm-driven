"""Only the exact finished production iOS build may cross the upload gate."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("trusted_eas_build.py")
SHA = "a" * 40
BUILD_ID = "71b2da1d-b4ea-4f9d-82b2-43eb2dd54849"


def invoke(payload, *extra):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), "--sha", SHA, *extra],
                          input=json.dumps(payload), text=True, capture_output=True, check=False)


def build(**changes):
    return {"id": BUILD_ID, "gitCommitHash": SHA, "status": "FINISHED",
            "platform": "IOS", "distribution": "STORE", "buildProfile": "production",
            "appIdentifier": "life.executor.health",
            "app": {"id": "911ea84f-bc7e-4a12-90cf-33966b6f7398"}, **changes}


@pytest.mark.parametrize("wrapped", [False, True])
def test_accept_exact_finished_build(wrapped):
    result = invoke([build()] if wrapped else build(), "--id", BUILD_ID)
    assert result.returncode == 0, result.stderr
    assert result.stdout == BUILD_ID + "\n"


@pytest.mark.parametrize("changes", [
    {"id": "$(secret)"}, {"gitCommitHash": "b" * 40}, {"status": "IN_PROGRESS"},
    {"status": "ERRORED"}, {"platform": "ANDROID"}, {"distribution": "INTERNAL"},
    {"buildProfile": "preview"}, {"gitCommitHash": None},
    {"appIdentifier": "life.executor.other"}, {"app": {"id": "other-project"}},
])
def test_reject_wrong_artifact_without_payload_leak(changes):
    result = invoke(build(**changes, secret="DO_NOT_PRINT"))
    assert result.returncode != 0
    assert BUILD_ID not in result.stdout
    assert "DO_NOT_PRINT" not in result.stdout + result.stderr


def test_reject_multiple_builds_or_wrong_selected_id():
    assert invoke([build(), build()]).returncode != 0
    assert invoke(build(), "--id", "81b2da1d-b4ea-4f9d-82b2-43eb2dd54849").returncode != 0


def test_reject_duplicate_json_keys_and_oversized_input():
    for raw in ['{"id":"first","id":"second"}', ' ' * 1000001]:
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--sha", SHA],
                                input=raw, text=True, capture_output=True, check=False)
        assert result.returncode != 0


def test_workflow_build_is_parallel_but_upload_joins_successful_branches():
    import yaml
    workflow = yaml.safe_load((SCRIPT.parent.parent / ".github/workflows/trusted-release.yml").read_text())
    jobs = workflow["jobs"]
    assert jobs["backend"]["needs"] == "build-permission"
    assert jobs["ios-build"]["needs"] == "build-permission"
    assert set(jobs["testflight"]["needs"]) == {"backend", "ios-build"}
    build_steps = str(jobs["ios-build"]["steps"])
    assert "--auto-submit" not in build_steps
    assert "submit -p ios" not in build_steps
    # Rerunning just this job must claim again, not reuse an upstream grant.
    assert 'claim-build $TARGET_SHA' in build_steps
    submit_steps = str(jobs["testflight"]["steps"])
    assert "submit -p ios --id" in submit_steps
    assert "build:view" in submit_steps
    assert "build -p ios" not in submit_steps
    assert "--latest" not in submit_steps
