"""Native-only retirement must never invent backend success or replay a claim."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    spec = importlib.util.spec_from_file_location(
        "native_retirement_test",
        Path(__file__).with_name("native_release_retirement.py"),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metadata(m):
    run = dict(
        id=m.RUN_ID,
        run_attempt=2,
        workflow_id=m.WORKFLOW_ID,
        path=".github/workflows/trusted-release.yml",
        head_sha=m.OLD_SHA,
        head_branch="main",
        event="workflow_dispatch",
        status="completed",
        conclusion="success",
        repository={"full_name": m.REPOSITORY},
        head_repository={"full_name": m.REPOSITORY},
    )
    jobs = []
    for name in m.JOB_NAMES:
        steps = []
        for step in m.REQUIRED_STEPS.get(name, ()):
            steps.append(dict(name=step, status="completed", conclusion="success"))
        jobs.append(
            dict(
                id=m.JOB_IDS[name],
                name=name,
                status="completed",
                conclusion="skipped" if name == "backend" else "success",
                steps=steps,
            )
        )
    prior = copy.deepcopy(jobs)
    for job in prior:
        job["id"] -= 1
        if job["name"] == "ios-build":
            job["conclusion"] = "failure"
            for step in job["steps"]:
                if step["name"] == m.BUILD_STEP:
                    step["conclusion"] = "skipped"
        if job["name"] == "testflight":
            job.update(conclusion="skipped", steps=[])
        if job["name"] == "release-result":
            job["conclusion"] = "failure"
    log = (
        f"2026-09-25T08:28:18.5590545Z {m.BUILD_ID}\n"
        f"2026-09-25T08:28:22.3230635Z Submission details: https://expo.dev/accounts/itsoso/projects/health-pilot/submissions/{m.SUBMISSION_ID}\n"
        "2026-09-25T08:30:45.2273699Z ✔ Submitted your app to Apple App Store Connect!\n"
        "2026-09-25T08:30:45.2274995Z Your binary has been successfully uploaded to App Store Connect!\n"
    ).encode()
    return (
        run,
        {"total_count": len(jobs), "jobs": jobs},
        {"total_count": len(prior), "jobs": prior},
        log,
    )


def test_vendor_success_is_upload_only_and_binds_prior_attempt():
    m = load()
    args = metadata(m)
    evidence = m.validate_vendor(*args)
    assert evidence["state"] == "VENDOR_UPLOAD_SUCCEEDED"
    assert evidence["build_id"] == m.BUILD_ID
    assert evidence["submission_id"] == m.SUBMISSION_ID
    assert evidence["run_attempt"] == 2
    assert "backend" not in evidence


@pytest.mark.parametrize(
    "mutation",
    [
        "run_sha",
        "repo",
        "run_attempt",
        "run_id",
        "job_id",
        "backend",
        "duplicate",
        "missing",
        "step",
        "prior_vendor",
        "prior_upload",
        "log_terminal",
        "submission",
    ],
)
def test_uncertain_vendor_metadata_is_rejected(mutation):
    m = load()
    run, jobs, prior, log = metadata(m)
    if mutation == "run_sha":
        run["head_sha"] = "b" * 40
    elif mutation == "repo":
        run["repository"]["full_name"] = "attacker/fork"
    elif mutation == "run_attempt":
        run["run_attempt"] = 3
    elif mutation == "run_id":
        run["id"] += 1
    elif mutation == "job_id":
        jobs["jobs"][0]["id"] += 1
    elif mutation == "backend":
        next(j for j in jobs["jobs"] if j["name"] == "backend")["conclusion"] = (
            "success"
        )
    elif mutation == "duplicate":
        jobs["jobs"].append(jobs["jobs"][0])
        jobs["total_count"] += 1
    elif mutation == "missing":
        jobs["jobs"].pop()
    elif mutation == "step":
        next(j for j in jobs["jobs"] if j["name"] == "testflight")["steps"][-1][
            "conclusion"
        ] = "failure"
    elif mutation == "prior_vendor":
        next(
            s
            for j in prior["jobs"]
            if j["name"] == "ios-build"
            for s in j["steps"]
            if s["name"] == m.BUILD_STEP
        )["conclusion"] = "success"
    elif mutation == "prior_upload":
        next(j for j in prior["jobs"] if j["name"] == "testflight")["conclusion"] = (
            "success"
        )
    elif mutation == "log_terminal":
        log = log.replace(b"Submitted your app", b"Cancelled your app")
    elif mutation == "submission":
        log = log.replace(m.SUBMISSION_ID.encode(), b"0" * 36)
    with pytest.raises(m.RetirementError):
        m.validate_vendor(run, jobs, prior, log)


class Adapter:
    def __init__(self, m, root):
        self.record = root / "native-only-closures" / m.OLD_SHA
        self.record.parent.mkdir()
        self.evidence = {
            "old_sha": m.OLD_SHA,
            "closing_sha": "b" * 40,
            "state": "NATIVE_ONLY_VENDOR_UPLOAD_SUCCEEDED",
        }
        self.calls = 0
        self.drift = False

    def inspect(self):
        self.calls += 1
        if self.drift and self.calls > 1:
            return {**self.evidence, "drift": True}
        return copy.deepcopy(self.evidence)

    def check_record_parent(self):
        pass


def test_inspection_does_not_write_then_terminal_requires_same_digest_and_receipt(
    tmp_path,
):
    m = load()
    a = Adapter(m, tmp_path)
    result = m.close_transaction(a)
    assert not a.record.exists()
    result = m.close_transaction(a, result["evidence_sha256"])
    assert result["state"] == m.TERMINAL
    assert len(result["receipt"]) == 64
    intent = json.loads((a.record / "intent.json").read_text())
    done = json.loads((a.record / "completed.json").read_text())
    assert done["intent_sha256"] == m.digest(intent)
    assert done["state"] != "SUCCEEDED"
    assert (
        intent["receipt_sha256"]
        == hashlib.sha256(result["receipt"].encode()).hexdigest()
    )
    with pytest.raises(m.RetirementError, match="retry forbidden"):
        m.close_transaction(a)


def test_digest_mismatch_creates_no_intent(tmp_path):
    m = load()
    a = Adapter(m, tmp_path)
    with pytest.raises(m.RetirementError, match="changed"):
        m.close_transaction(a, "0" * 64)
    assert not a.record.exists()


def test_interrupted_or_drifted_closure_never_writes_terminal_and_cannot_retry(
    tmp_path,
):
    m = load()
    a = Adapter(m, tmp_path)
    a.drift = True
    with pytest.raises(m.RetirementError, match="changed"):
        m.close_transaction(a, m.digest(a.evidence))
    assert (a.record / "intent.json").exists()
    assert not (a.record / "completed.json").exists()
    with pytest.raises(m.RetirementError, match="retry forbidden"):
        m.close_transaction(a)


def fixture_workspace(m, tmp_path):
    workspace = tmp_path / m.OLD_SHA
    workspace.mkdir(mode=0o700)
    for name in ["build-started.json", "native-started.json"]:
        (workspace / name).write_text(
            json.dumps({"sha": m.OLD_SHA, "state": "STARTED"})
        )
    (workspace / "testflight-base.json").write_text(
        json.dumps(
            {"sha": m.OLD_SHA, "state": "COMPATIBLE", "production_sha": "c" * 40}
        )
    )
    (workspace / "build.lock").write_bytes(b"")

    def inventory(path, names):
        if set(p.name for p in path.iterdir()) != set(names):
            raise m.RetirementError("inventory")
        return {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()
        }

    return SimpleNamespace(
        STATE=tmp_path,
        _inventory=inventory,
        _read_json=lambda p: json.loads(p.read_text()),
    ), workspace


def test_native_workspace_is_read_only_and_not_backend_success(tmp_path):
    m = load()
    b, path = fixture_workspace(m, tmp_path)
    before = {p.name: (p.stat().st_ino, p.read_bytes()) for p in path.iterdir()}
    result = m.workspace_evidence(b)
    assert result["production_sha"] == "c" * 40
    assert before == {p.name: (p.stat().st_ino, p.read_bytes()) for p in path.iterdir()}


@pytest.mark.parametrize(
    "mutation",
    ["extra", "backend_success", "missing", "wrong_marker", "wrong_sha", "lock_bytes"],
)
def test_workspace_unknown_inventory_or_conflicting_marker_fails_closed(
    tmp_path, mutation
):
    m = load()
    b, path = fixture_workspace(m, tmp_path)
    if mutation == "extra":
        (path / "source").mkdir()
    elif mutation == "backend_success":
        (path / "completed.json").write_text("{}")
    elif mutation == "missing":
        (path / "native-started.json").unlink()
    elif mutation == "wrong_marker":
        (path / "build-started.json").write_text(
            json.dumps({"sha": m.OLD_SHA, "state": "SUCCEEDED"})
        )
    elif mutation == "wrong_sha":
        (path / "testflight-base.json").write_text(
            json.dumps(
                {"sha": "d" * 40, "state": "COMPATIBLE", "production_sha": "c" * 40}
            )
        )
    elif mutation == "lock_bytes":
        (path / "build.lock").write_text("changed")
    with pytest.raises(m.RetirementError):
        m.workspace_evidence(b)


def test_log_redirect_cannot_forward_token_to_arbitrary_host():
    m = load()
    for url in [
        "http://productionresultssa18.blob.core.windows.net/a",
        "https://evil.test/a",
        "https://productionresultssa18.blob.core.windows.net.evil.test/a",
        "https://user@productionresultssa18.blob.core.windows.net/a",
    ]:
        with pytest.raises(m.RetirementError):
            m.validate_log_redirect(url)
    assert m.validate_log_redirect(
        "https://productionresultssa18.blob.core.windows.net/a?sig=private"
    )


def completed_fixture(m, tmp_path, monkeypatch):
    b, workspace = fixture_workspace(m, tmp_path)
    source = tmp_path / "source"
    source.mkdir()
    record = tmp_path / m.ROOT_NAME / m.OLD_SHA
    record.mkdir(parents=True)
    monkeypatch.setattr(m, "private_directory", lambda *a: None)
    monkeypatch.setattr(m, "canonical_profile", lambda b: None)
    installation = {"config": {"inode": 123}, "library": {"sha256": "d" * 64}}
    b.CONFIG = tmp_path / "config"
    b.INSTALLED = tmp_path / "lib" / "executor.py"
    b._archives = lambda sha: (tmp_path / "config.retired", tmp_path / "lib.retired")
    b.canonical_source = lambda sha: source
    b._installation_evidence = lambda *a: copy.deepcopy(installation)
    b._recovery_file_identity = lambda path: {
        "inode": 321 if path.name == "launcher.lock" else 123,
        "sha256": "e" * 64,
    }
    b._recovery_production_proof = lambda *a: None
    b._assert_idle = lambda: None
    b._recovery_process_proof = lambda: None
    receipt = "a" * 64
    vendor = {
        "state": "VENDOR_UPLOAD_SUCCEEDED",
        "run_id": m.RUN_ID,
        "run_attempt": 2,
        "workflow_id": m.WORKFLOW_ID,
        "build_id": m.BUILD_ID,
        "submission_id": m.SUBMISSION_ID,
        "log_sha256": m.LOG_SHA256,
        "canonical_hashes": m.CANONICAL_HASHES,
        "jobs_sha256": "1" * 64,
        "prior_jobs_sha256": "2" * 64,
    }
    evidence = {
        "old_sha": m.OLD_SHA,
        "closing_sha": "b" * 40,
        "production_sha": "c" * 40,
        "workspace": m.workspace_evidence(b),
        "installation": installation,
        "authorized": {"sha256": "3" * 64},
        "locks": {
            "launcher": b._recovery_file_identity(tmp_path / "launcher.lock"),
            "build": b._recovery_file_identity(workspace / "build.lock"),
        },
        "vendor": vendor,
    }
    intent = {
        **evidence,
        "evidence_sha256": m.digest(evidence),
        "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest(),
    }
    (record / "intent.json").write_text(json.dumps(intent))
    (record / "completed.json").write_text(
        json.dumps(
            {
                "state": m.TERMINAL,
                "old_sha": m.OLD_SHA,
                "intent_sha256": m.digest(intent),
            }
        )
    )
    return b, workspace, record, receipt


def test_complete_native_history_preserves_backend_claims_and_survives_install_archive(
    tmp_path, monkeypatch
):
    m = load()
    b, workspace, record, receipt = completed_fixture(m, tmp_path, monkeypatch)
    result = m.closed_evidence(b, m.OLD_SHA, receipt)
    assert result["state"] == m.TERMINAL
    assert not (workspace / "completed.json").exists()
    (tmp_path / "config.retired").mkdir()
    (tmp_path / "lib.retired").mkdir()
    assert m.closed_evidence(b, m.OLD_SHA, receipt, historical=True) == result


@pytest.mark.parametrize(
    "mutation",
    [
        "receipt",
        "partial",
        "terminal",
        "old_claim",
        "lock",
        "installation",
        "vendor",
        "unknown_record",
        "conflict",
    ],
)
def test_native_history_rejects_tampering_and_incomplete_records(
    tmp_path, monkeypatch, mutation
):
    m = load()
    b, workspace, record, receipt = completed_fixture(m, tmp_path, monkeypatch)
    if mutation == "receipt":
        receipt = "f" * 64
    elif mutation == "partial":
        (record / "completed.json").unlink()
    elif mutation == "terminal":
        (record / "completed.json").write_text("{}")
    elif mutation == "old_claim":
        (workspace / "native-started.json").write_text("{}")
    elif mutation == "lock":
        b._recovery_file_identity = lambda p: {"inode": 999}
    elif mutation == "installation":
        b._installation_evidence = lambda *a: {}
    elif mutation == "vendor":
        intent = json.loads((record / "intent.json").read_text())
        intent["vendor"]["state"] = "APPLE_APPROVED"
        (record / "intent.json").write_text(json.dumps(intent))
    elif mutation == "unknown_record":
        (record / "retry.json").write_text("{}")
    elif mutation == "conflict":
        (tmp_path / "recoveries" / m.OLD_SHA).mkdir(parents=True)
    with pytest.raises(m.RetirementError):
        m.closed_evidence(b, m.OLD_SHA, receipt, historical=True)


def test_operator_rejects_before_reading_any_credential(monkeypatch):
    m = load()
    events = []
    monkeypatch.setattr(
        m.sys, "argv", ["native_release_retirement.py", "--sha", "b" * 40, "--production-sha", "d" * 40]
    )

    def context(sha):
        events.append("context")
        raise m.RetirementError("canonical rejected")

    monkeypatch.setattr(m, "context", context)

    class Input:
        def read(self, *a):
            events.append("secret")
            raise AssertionError("secret should not be read")

    monkeypatch.setattr(m.sys, "stdin", Input())
    with pytest.raises(m.RetirementError):
        m.main()
    assert events == ["context"]


def test_closure_separates_live_and_historical_production(tmp_path, monkeypatch):
    m = load()
    b, workspace, record, receipt = completed_fixture(m, tmp_path, monkeypatch)
    intent = json.loads((record / 'intent.json').read_text())
    intent['production_sha'] = 'd' * 40
    evidence = {k: v for k, v in intent.items() if k not in {'evidence_sha256', 'receipt_sha256'}}
    intent['evidence_sha256'] = m.digest(evidence)
    (record / 'intent.json').write_text(json.dumps(intent))
    (record / 'completed.json').write_text(json.dumps({'state': m.TERMINAL, 'old_sha': m.OLD_SHA, 'intent_sha256': m.digest(intent)}))
    calls = []
    b._recovery_production_proof = lambda sha, source: calls.append(sha)
    m.closed_evidence(b, m.OLD_SHA, receipt)
    assert calls == ['d' * 40]
    assert intent['workspace']['production_sha'] == 'c' * 40
    calls.clear()
    m.closed_evidence(b, m.OLD_SHA, receipt, historical=True)
    assert calls == []
