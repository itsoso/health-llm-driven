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


def fixture_workspace(m, tmp_path, native_sha=None):
    native_sha = native_sha or m.OLD_SHA
    workspace = tmp_path / native_sha
    workspace.mkdir(mode=0o700)
    for name in ["build-started.json", "native-started.json"]:
        (workspace / name).write_text(
            json.dumps({"sha": native_sha, "state": "STARTED"})
        )
    (workspace / "testflight-base.json").write_text(
        json.dumps(
            {"sha": native_sha, "state": "COMPATIBLE", "production_sha": "c" * 40}
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


def completed_fixture(m, tmp_path, monkeypatch, native_sha=None):
    native_sha = native_sha or m.OLD_SHA
    profile = m.profile_for(native_sha)
    b, workspace = fixture_workspace(m, tmp_path, native_sha)
    source = tmp_path / "source"
    source.mkdir()
    record = tmp_path / m.ROOT_NAME / native_sha
    record.mkdir(parents=True)
    monkeypatch.setattr(m, "private_directory", lambda *a: None)
    monkeypatch.setattr(m, "canonical_profile", lambda b, native_sha=m.OLD_SHA: None)
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
        "run_id": profile["run_id"],
        "run_attempt": profile["run_attempt"],
        "workflow_id": m.WORKFLOW_ID,
        "build_id": profile["build_id"],
        "submission_id": profile["submission_id"],
        "log_sha256": profile["log_sha256"],
        "canonical_hashes": profile["canonical_hashes"],
        "jobs_sha256": profile["jobs_sha256"] or "1" * 64,
        "prior_jobs_sha256": "2" * 64 if profile["run_attempt"] == 2 else None,
    }
    evidence = {
        "old_sha": native_sha,
        "closing_sha": "b" * 40,
        "production_sha": "c" * 40,
        "workspace": m.workspace_evidence(b, native_sha),
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
                "old_sha": native_sha,
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


NATIVE_273_SHA = 'e19043ecb269e20f3bc0a546165e43d467f1fc8c'


def modern_metadata(m):
    run, jobs, _prior, log = metadata(m)
    run.update(id=36877321184, run_attempt=1, head_sha=NATIVE_273_SHA)
    job_ids = {
        'preflight': 110419973839, 'build-permission': 110420049172,
        'ios-build': 110420683984, 'backend': 110420686145,
        'testflight': 110424934683, 'release-result': 110427264251,
    }
    for job in jobs['jobs']:
        job['id'] = job_ids[job['name']]
    log = log.replace(m.BUILD_ID.encode(), b'20d5e73a-a6b9-4c70-ad69-e63d31e058f2').replace(
        m.SUBMISSION_ID.encode(), b'fcfbb57d-4804-4a36-9c57-eab062bf321e')
    return run, jobs, None, log


def test_second_profile_validates_first_attempt_without_inventing_backend_success():
    m = load()
    proof = m.validate_vendor(*modern_metadata(m), native_sha=NATIVE_273_SHA)
    assert proof['run_id'] == 36877321184
    assert proof['run_attempt'] == 1
    assert proof['build_id'] == '20d5e73a-a6b9-4c70-ad69-e63d31e058f2'
    assert proof['prior_jobs_sha256'] is None
    assert proof['state'] == 'VENDOR_UPLOAD_SUCCEEDED'
    assert 'backend' not in proof
    assert m.validate_vendor(*metadata(m))['run_id'] == m.RUN_ID


@pytest.mark.parametrize('mutation', ['unknown_sha', 'wrong_attempt', 'mixed_jobs', 'mixed_log', 'unexpected_prior'])
def test_second_profile_cannot_mix_or_expand_reviewed_evidence(mutation):
    m = load()
    run, jobs, prior, log = modern_metadata(m)
    sha = NATIVE_273_SHA
    if mutation == 'unknown_sha':
        sha = 'f' * 40
    elif mutation == 'wrong_attempt':
        run['run_attempt'] = 2
    elif mutation == 'mixed_jobs':
        jobs = metadata(m)[1]
    elif mutation == 'mixed_log':
        log = metadata(m)[3]
    elif mutation == 'unexpected_prior':
        prior = metadata(m)[2]
    with pytest.raises(m.RetirementError):
        m.validate_vendor(run, jobs, prior, log, native_sha=sha)


def test_new_operator_selects_native_sha_before_reading_credentials(monkeypatch):
    m = load()
    events = []
    monkeypatch.setattr(m.sys, 'argv', ['native_release_retirement.py', '--sha', 'b' * 40,
        '--production-sha', 'd' * 40, '--native-sha', 'f' * 40])
    monkeypatch.setattr(m, 'context', lambda sha: events.append('context'))
    class Input:
        def read(self, *args):
            events.append('secret')
            raise AssertionError('credential read forbidden')
    monkeypatch.setattr(m.sys, 'stdin', Input())
    with pytest.raises(m.RetirementError):
        m.main()
    assert events == []


def reseal_fixture(m, record, intent):
    evidence = {k: v for k, v in intent.items() if k not in {'evidence_sha256', 'receipt_sha256'}}
    intent['evidence_sha256'] = m.digest(evidence)
    (record / 'intent.json').write_text(json.dumps(intent))
    (record / 'completed.json').write_text(json.dumps({
        'state': m.TERMINAL, 'old_sha': intent['old_sha'], 'intent_sha256': m.digest(intent),
    }))


def test_second_profile_historical_and_live_roundtrip_preserves_original_evidence(tmp_path, monkeypatch):
    m = load()
    b, workspace, record, receipt = completed_fixture(m, tmp_path, monkeypatch, NATIVE_273_SHA)
    before = {p.name: (p.stat().st_ino, p.read_bytes()) for p in workspace.iterdir()}
    calls = []
    b._recovery_production_proof = lambda sha, source: calls.append(sha)
    live = m.closed_evidence(b, NATIVE_273_SHA, receipt)
    assert live['state'] == m.TERMINAL
    assert calls == ['c' * 40]
    calls.clear()
    (tmp_path / 'config.retired').mkdir()
    (tmp_path / 'lib.retired').mkdir()
    assert m.closed_evidence(b, NATIVE_273_SHA, receipt, historical=True) == live
    assert calls == []
    assert before == {p.name: (p.stat().st_ino, p.read_bytes()) for p in workspace.iterdir()}
    assert not (workspace / 'completed.json').exists()
    assert not (tmp_path / m.ROOT_NAME / m.OLD_SHA).exists()


@pytest.mark.parametrize('field', ['run_id', 'run_attempt', 'build_id', 'submission_id', 'log_sha256', 'canonical_hashes', 'jobs_sha256', 'prior_jobs_sha256'])
def test_second_profile_history_rejects_resealed_cross_profile_proof(tmp_path, monkeypatch, field):
    m = load()
    b, workspace, record, receipt = completed_fixture(m, tmp_path, monkeypatch, NATIVE_273_SHA)
    intent = json.loads((record / 'intent.json').read_text())
    old = m.validate_vendor(*metadata(m))
    intent['vendor'][field] = old[field]
    reseal_fixture(m, record, intent)
    with pytest.raises(m.RetirementError, match='vendor proof differs'):
        m.closed_evidence(b, NATIVE_273_SHA, receipt, historical=True)


@pytest.mark.parametrize('mutation', ['receipt', 'lock', 'archive', 'workspace', 'canonical'])
def test_second_profile_historical_never_bypasses_integrity(tmp_path, monkeypatch, mutation):
    m = load()
    b, workspace, record, receipt = completed_fixture(m, tmp_path, monkeypatch, NATIVE_273_SHA)
    if mutation == 'receipt':
        receipt = 'f' * 64
    elif mutation == 'lock':
        b._recovery_file_identity = lambda p: {'inode': 999}
    elif mutation == 'archive':
        b._installation_evidence = lambda *args: {}
    elif mutation == 'workspace':
        (workspace / 'build.lock').write_bytes(b'changed')
    elif mutation == 'canonical':
        def bad_source(*args):
            raise m.RetirementError('canonical mismatch')
        monkeypatch.setattr(m, 'canonical_profile', bad_source)
    with pytest.raises(m.RetirementError):
        m.closed_evidence(b, NATIVE_273_SHA, receipt, historical=True)


@pytest.mark.parametrize('drift', ['none', 'log', 'jobs', 'run'])
def test_live_second_profile_fetch_binds_complete_reviewed_digests(monkeypatch, drift):
    m = load()
    run, jobs, prior, log = modern_metadata(m)
    profile = copy.deepcopy(m.profile_for(NATIVE_273_SHA))
    profile.update(log_sha256=hashlib.sha256(log).hexdigest(), jobs_sha256=m.digest(jobs))
    monkeypatch.setitem(m.PROFILES, NATIVE_273_SHA, profile)
    original_run = copy.deepcopy(run)
    if drift == 'log':
        log += b'2026-10-01T14:55:00.0000000Z changed extra output\n'
    elif drift == 'jobs':
        jobs['jobs'][0]['runner_name'] = 'changed'
    calls = []
    def read(url, token, **kwargs):
        calls.append((url, kwargs))
        assert token == 'private-test-token'
        if url.endswith('/actions/runs/36877321184'):
            if drift == 'run' and len(calls) > 1:
                return json.dumps({**original_run, 'run_attempt': 2}).encode()
            return json.dumps(run).encode()
        if url.endswith('/attempts/1/jobs?per_page=100'):
            return json.dumps(jobs).encode()
        if url.endswith('/actions/jobs/110424934683/logs'):
            assert kwargs == {'logs': True, 'native_sha': NATIVE_273_SHA}
            return log
        raise AssertionError('unreviewed evidence requested')
    monkeypatch.setattr(m, 'read_url', read)
    if drift == 'none':
        proof = m.vendor_evidence('private-test-token', NATIVE_273_SHA)
        assert proof['prior_jobs_sha256'] is None
        assert len(calls) == 4
    else:
        with pytest.raises(m.RetirementError):
            m.vendor_evidence('private-test-token', NATIVE_273_SHA)


def test_second_profile_close_writes_its_own_terminal_only(tmp_path):
    m = load()
    a = Adapter(m, tmp_path)
    a.record = tmp_path / m.ROOT_NAME / NATIVE_273_SHA
    a.evidence['old_sha'] = NATIVE_273_SHA
    inspected = m.close_transaction(a)
    assert not a.record.exists()
    completed = m.close_transaction(a, inspected['evidence_sha256'])
    assert completed['sha'] == NATIVE_273_SHA
    assert json.loads((a.record / 'completed.json').read_text())['old_sha'] == NATIVE_273_SHA
    assert not (tmp_path / m.ROOT_NAME / m.OLD_SHA).exists()


def test_redirect_host_is_bound_to_the_selected_profile():
    m = load()
    for sha, allowed, denied in [
        (m.OLD_SHA, 'productionresultssa18.blob.core.windows.net', 'productionresultssa4.blob.core.windows.net'),
        (NATIVE_273_SHA, 'productionresultssa4.blob.core.windows.net', 'productionresultssa18.blob.core.windows.net'),
    ]:
        assert m.validate_log_redirect('https://' + allowed + '/log?sig=private', sha)
        for host in (denied, allowed + '.evil.test', 'user@' + allowed):
            with pytest.raises(m.RetirementError):
                m.validate_log_redirect('https://' + host + '/log', sha)


def test_second_profile_signed_log_request_carries_no_github_credential(monkeypatch):
    from email.message import Message
    m = load()
    headers = Message()
    headers['Location'] = 'https://productionresultssa4.blob.core.windows.net/log?sig=fixture'
    requests = []
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def read(self, limit):
            return b'log fixture'
    class Client:
        def open(self, request, timeout):
            requests.append(request)
            if len(requests) == 1:
                raise m.urllib.error.HTTPError(request.full_url, 302, 'found', headers, None)
            return Response()
    monkeypatch.setattr(m, 'opener', lambda: Client())
    assert m.read_url(m.BASE + '/actions/jobs/110424934683/logs', 'private-token', logs=True,
                      native_sha=NATIVE_273_SHA) == b'log fixture'
    assert requests[0].get_header('Authorization') == 'Bearer private-token'
    assert requests[1].header_items() == []


@pytest.mark.parametrize('fault', ['authorized', 'private-key'])
def test_second_profile_inspection_preserves_installation_revocation_guard(tmp_path, monkeypatch, fault):
    # Exercise the real bootstrap installation validator against local fixtures.
    from scripts.test_bootstrap_trusted_release import fixture, PUBLIC, LOOPBACK
    m = load()
    b, _calls = fixture(monkeypatch, tmp_path)
    b.install(NATIVE_273_SHA, 200, PUBLIC)
    source = tmp_path / 'source'
    monkeypatch.setattr(b, 'canonical_source', lambda sha: source)
    monkeypatch.setattr(b, '_assert_idle', lambda: None)
    monkeypatch.setattr(b, '_recovery_process_proof', lambda: None)
    b.BUSINESS_LEASE = tmp_path / 'no-lease'
    monkeypatch.setattr(m, 'canonical_profile', lambda *args: None)
    if fault == 'authorized':
        (b.CONFIG / 'loopback.key').unlink()
    else:
        b.AUTHORIZED.write_text('unrelated-only\n')
    adapter = m.Adapter(b, source, 'b' * 40, 'never-use-token', lambda: None, 'c' * 40, NATIVE_273_SHA)
    with pytest.raises(b.BootstrapError, match='authorized|inventory'):
        adapter.inspect()
    assert not adapter.record.exists()
