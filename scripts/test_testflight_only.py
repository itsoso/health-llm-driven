"""Native-only continuation never redeploys or manufactures backend success."""

import importlib.util
import json
from pathlib import Path

import pytest
from test_trusted_release_server import SHA, policy, setup_state

PRODUCTION_SHA = "c" * 40


def native_state(monkeypatch, tmp_path):
    server = setup_state(monkeypatch, tmp_path)
    server.STATE = tmp_path
    server.BUSINESS_LEASE = tmp_path / "business-lease"
    workspace = tmp_path / SHA
    workspace.mkdir()
    monkeypatch.setattr(server, "check_readiness", lambda _: None)
    monkeypatch.setattr(server, "validate_loopback", lambda _: None)
    monkeypatch.setattr(server, "testflight_backend_proof", lambda _: {
        "sha": SHA, "production_sha": PRODUCTION_SHA, "state": "COMPATIBLE",
    })
    return server, workspace


def test_native_only_claims_keep_backend_ready_and_cannot_replay(monkeypatch, tmp_path):
    server, workspace = native_state(monkeypatch, tmp_path)
    assert server.testflight_only(policy(), workspace, "check")["state"] == "CHECKED"
    assert list(workspace.iterdir()) == []
    assert server.testflight_only(policy(), workspace, "build")["state"] == "CLAIMED"
    assert server.testflight_only(policy(), workspace, "upload")["state"] == "CLAIMED"
    assert server.read_status(SHA, workspace)["state"] == "READY"
    assert not (workspace / "completed.json").exists()
    for action in ("build", "upload"):
        with pytest.raises(server.LaunchError):
            server.testflight_only(policy(), workspace, action)
    calls = []
    with pytest.raises(server.LaunchError):
        server.run_once(policy(), workspace, lambda: calls.append("prepare"), lambda: calls.append("deploy"))
    assert calls == []


@pytest.mark.parametrize("claim", ["claim_build", "claim_testflight"])
def test_native_binding_cannot_be_bypassed_through_legacy_rpc(monkeypatch, tmp_path, claim):
    server, workspace = native_state(monkeypatch, tmp_path)
    server.testflight_only(policy(), workspace, "build")
    with pytest.raises(server.LaunchError, match="native-only"):
        getattr(server, claim)(policy(), workspace)
    assert not (workspace / "native-started.json").exists()


@pytest.mark.parametrize("cause", ["backend_changed", "lease", "expired", "unknown_health"])
def test_native_upload_rechecks_backend_under_lock_before_consumption(monkeypatch, tmp_path, cause):
    server, workspace = native_state(monkeypatch, tmp_path)
    server.testflight_only(policy(), workspace, "build")
    if cause == "backend_changed":
        monkeypatch.setattr(server, "testflight_backend_proof", lambda _: {
            "sha": SHA, "production_sha": "d" * 40, "state": "COMPATIBLE",
        })
    elif cause == "lease":
        server.BUSINESS_LEASE.mkdir()
    elif cause == "expired":
        monkeypatch.setattr(server.time, "time", lambda: 7400)
    else:
        def fail(_):
            raise server.LaunchError("health unavailable")
        monkeypatch.setattr(server, "testflight_backend_proof", fail)
    with pytest.raises(server.LaunchError):
        server.testflight_only(policy(), workspace, "upload")
    assert not (workspace / "native-started.json").exists()


def test_existing_backend_or_legacy_build_cannot_be_relabelled_native_only(monkeypatch, tmp_path):
    server, workspace = native_state(monkeypatch, tmp_path)
    server.claim_build(policy(), workspace)
    with pytest.raises(server.LaunchError):
        server.testflight_only(policy(), workspace, "build")
    assert not (workspace / "testflight-base.json").exists()


@pytest.mark.parametrize("claim", ["claim_build", "claim_testflight"])
def test_legacy_claim_rechecks_native_binding_after_acquiring_vendor_lock(monkeypatch, tmp_path, claim):
    server, workspace = native_state(monkeypatch, tmp_path)
    if claim == "claim_testflight":
        server.claim_build(policy(), workspace)
    original = server.fcntl.flock
    def interleave(fd, operation):
        original(fd, operation)
        binding = {"sha": SHA, "production_sha": PRODUCTION_SHA, "state": "COMPATIBLE"}
        server._write_private(workspace / "testflight-base.json", json.dumps(binding).encode())
    monkeypatch.setattr(server.fcntl, "flock", interleave)
    with pytest.raises(server.LaunchError, match="native-only"):
        getattr(server, claim)(policy(), workspace)
    marker = "build-started.json" if claim == "claim_build" else "native-started.json"
    assert not (workspace / marker).exists()


def test_native_check_rejects_concurrent_backend_lock(monkeypatch, tmp_path):
    import fcntl
    server, workspace = native_state(monkeypatch, tmp_path)
    with (tmp_path / "launcher.lock").open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(server.LaunchError):
            server.testflight_only(policy(), workspace, "check")


@pytest.mark.parametrize("action", ["check-testflight", "claim-testflight-build", "claim-testflight-upload"])
def test_native_rpc_remains_bound_to_exact_policy_sha(monkeypatch, tmp_path, action):
    server = setup_state(monkeypatch, tmp_path)
    assert server.authorize_command(action + " " + SHA, policy()) == action
    with pytest.raises(server.LaunchError):
        server.authorize_command(action + " " + PRODUCTION_SHA, policy())


def load_proof():
    path = Path(__file__).with_name("trusted_testflight_preflight.py")
    spec = importlib.util.spec_from_file_location("native_proof", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("path", ["backend/app/main.py", "mobile/app.json", "packages/shared/src/index.ts",
                                  "frontend/package.json", "scripts/unknown.py", "docs/prompts.md"])
def test_native_only_rejects_any_undeployed_runtime_or_unknown_change(path):
    proof = load_proof()
    with pytest.raises(proof.PreflightError):
        proof.validate_changed_paths([path])


def test_native_only_allows_only_reviewed_publisher_and_dossier_delta():
    proof = load_proof()
    proof.validate_changed_paths([
        ".github/workflows/trusted-release.yml", "scripts/trusted_release_server.py",
        "scripts/trusted_testflight_preflight.py", "scripts/test_testflight_only.py",
        "docs/dossiers/2026-09-24-exam-explain-continuation.md",
    ])


@pytest.mark.parametrize("receipt", [None, {}, {"sha": PRODUCTION_SHA, "state": "NEEDS_OPERATOR"},
                                     {"sha": SHA, "state": "SUCCEEDED"}])
def test_native_only_requires_exact_successful_live_backend_receipt(receipt):
    proof = load_proof()
    with pytest.raises(proof.PreflightError):
        proof.validate_receipt(PRODUCTION_SHA, receipt)


def test_native_health_requires_all_services_not_just_http_200():
    proof = load_proof()
    healthy = {"status": "healthy", "services": {"api": "running", "database": "connected", "redis": "connected", "celery": "connected"}}
    proof.validate_health(healthy)
    for service in healthy["services"]:
        broken = json.loads(json.dumps(healthy))
        broken["services"][service] = "disconnected"
        with pytest.raises(proof.PreflightError):
            proof.validate_health(broken)


def test_workflow_offers_native_only_without_backend_execution():
    import yaml
    workflow = yaml.safe_load(Path(".github/workflows/trusted-release.yml").read_text())
    triggers = workflow.get("on", workflow.get(True))
    assert "testflight" in triggers["workflow_dispatch"]["inputs"]["target"]["options"]
    assert "testflight" not in workflow["jobs"]["backend"]["if"]
    for job in ("build-permission", "ios-build", "testflight"):
        assert "inputs.target == 'testflight'" in workflow["jobs"][job]["if"]
    for rpc in ("check-testflight", "claim-testflight-build", "claim-testflight-upload"):
        assert rpc in json.dumps(workflow)
