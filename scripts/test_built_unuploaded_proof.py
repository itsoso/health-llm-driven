"""No network, credentials or production state in these closure proof tests."""
import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest


def module():
    spec = importlib.util.spec_from_file_location("built_proof", Path(__file__).with_name("built_unuploaded_proof.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def fixture(m):
    run = dict(m.RUN)
    run.update(repository={"full_name": m.REPOSITORY}, head_repository={"full_name": m.REPOSITORY})
    jobs = {"total_count": 6, "jobs": []}
    for name, conclusion in m.JOB_RESULTS.items():
        jobs["jobs"].append({"id": m.JOB_IDS[name], "name": name, "run_id": m.RUN["id"],
            "head_sha": m.RUN["head_sha"], "run_attempt": 1, "status": "completed", "conclusion": conclusion,
            "steps": [{"name": step, "status": "completed", "conclusion": result}
                      for step, result in m.STEPS.get(name, {}).items()]})
    build = copy.deepcopy(m.BUILD)
    log = ("2026-10-03T10:00:00.000Z https://expo.dev/accounts/itsoso/projects/health-pilot/builds/" + m.BUILD["id"] + "\n").encode()
    # Synthetic fixtures pin their own complete known job/log evidence.
    m.LOG_HASH = hashlib.sha256(log).hexdigest()
    m.JOBS_HASH = m.digest({j["name"]: {**{k: v for k, v in j.items() if k not in {"name", "steps"}},
                          "steps": {s["name"]: s["conclusion"] for s in j["steps"]}} for j in jobs["jobs"]})
    return run, jobs, build, log


def test_exact_terminal_proof_retains_artifact_without_upload_authority():
    m = module()
    proof = m.validate(*fixture(m))
    assert proof["profile"] == "finished-build-unuploaded-v1"
    assert proof["build_id"] == m.BUILD["id"]
    assert "token" not in str(proof)
    m.validate_history(proof, m.RUN["head_sha"])


@pytest.mark.parametrize("damage", ["run_running", "attempt", "run_sha", "repository", "job_running",
    "job_duplicate", "job_missing", "upload_success", "upload_unknown", "build_running", "build_sha",
    "build_project", "build_simulator", "build_submitted", "build_number", "build_id", "log_id"])
def test_uncertain_or_different_vendor_state_is_blocked(damage):
    m = module()
    run, jobs, build, log = fixture(m)
    if damage == "run_running": run["status"] = "in_progress"
    elif damage == "attempt": run["run_attempt"] = 2
    elif damage == "run_sha": run["head_sha"] = "0" * 40
    elif damage == "repository": run["repository"]["full_name"] = "other/repo"
    elif damage == "job_running": jobs["jobs"][0]["status"] = "in_progress"
    elif damage == "job_duplicate": jobs["jobs"][-1] = copy.deepcopy(jobs["jobs"][0])
    elif damage == "job_missing": jobs["jobs"].pop()
    elif damage.startswith("upload_"):
        job = next(j for j in jobs["jobs"] if j["name"] == "testflight")
        job["steps"][-1]["conclusion"] = "success" if damage == "upload_success" else None
    elif damage == "build_running": build["status"] = "IN_PROGRESS"
    elif damage == "build_sha": build["gitCommitHash"] = "0" * 40
    elif damage == "build_project": build["app"]["id"] = "other"
    elif damage == "build_simulator": build["isForIosSimulator"] = True
    elif damage == "build_submitted": build["submissions"] = [{"id": "prior"}]
    elif damage == "build_number": build["appBuildVersion"] = "273"
    elif damage == "build_id": build["id"] = "other"
    elif damage == "log_id": log = b"unrelated successful build"
    with pytest.raises(m.ProofError): m.validate(run, jobs, build, log)


def test_history_rejects_missing_mixed_or_wrong_binding():
    m = module()
    proof = m.validate(*fixture(m))
    for bad in ({}, {**proof, "unknown": True}, {**proof, "profile": "installed-reuse-v1"},
                {**proof, "build_id": "other"}, {**proof, "log_sha256": "invalid"}):
        with pytest.raises(m.ProofError): m.validate_history(bad, m.RUN["head_sha"])
    with pytest.raises(m.ProofError): m.validate_history(proof, "0" * 40)


@pytest.mark.parametrize("damage", [None, "run_drift", "expo_error", "log_drift", "source_drift"])
def test_collector_requires_live_unchanged_vendor_and_canonical_source(monkeypatch, tmp_path, damage):
    import json
    m = module()
    run, jobs, build, log = fixture(m)
    canonical = tmp_path / "source"
    canonical.mkdir()
    (canonical / "test").write_bytes(b"canonical")
    m.HASHES = {"test": hashlib.sha256(b"canonical").hexdigest()}
    requests = []
    def read(url, headers, **kwargs):
        requests.append((url, headers, kwargs))
        if url == m.EXPO:
            assert "Authorization" not in headers and headers["expo-session"] == "synthetic-session"
            return json.dumps({"errors": ["blocked"], "data": None} if damage == "expo_error"
                              else {"data": {"builds": {"byId": build}}}).encode()
        assert headers["Authorization"] == "Bearer synthetic-github" and "expo-session" not in headers
        if kwargs.get("log"):
            return log + b"changed" if damage == "log_drift" else log
        if "/jobs?" in url: return json.dumps(jobs).encode()
        if damage == "run_drift" and len(requests) > 1: return json.dumps({**run, "run_attempt": 2}).encode()
        return json.dumps(run).encode()
    monkeypatch.setattr(m, "read", read)
    if damage == "source_drift": (canonical / "test").write_bytes(b"changed")
    if damage:
        with pytest.raises(m.ProofError): m.collect("synthetic-github", "synthetic-session", canonical)
    else:
        result = m.collect("synthetic-github", "synthetic-session", canonical)
        assert result["build_id"] == m.BUILD["id"] and len(requests) == 5


@pytest.mark.parametrize("location,accepted", [
    ("https://productionresultssa4.blob.core.windows.net/log?sig=synthetic", True),
    ("https://evil.example/log", False),
    ("http://productionresultssa4.blob.core.windows.net/log", False),
    ("https://user@productionresultssa4.blob.core.windows.net/log", False),
    ("https://productionresultssa4.blob.core.windows.net:444/log", False),
])
def test_signed_log_redirect_never_receives_github_credential(monkeypatch, location, accepted):
    import io
    m = module()
    calls = []
    class Response(io.BytesIO):
        status = 200
    class Client:
        def open(self, request, **kwargs):
            calls.append(request)
            if len(calls) == 1:
                raise m.urllib.error.HTTPError(request.full_url, 302, "redirect", {"Location": location}, None)
            assert request.get_header("Authorization") is None
            assert request.get_header("Expo-session") is None
            return Response(b"safe log")
    monkeypatch.setattr(m.urllib.request, "build_opener", lambda *args: Client())
    if accepted:
        assert m.read(m.BASE + "/actions/jobs/1/logs", {"Authorization": "Bearer synthetic"}, log=True) == b"safe log"
        assert len(calls) == 2
    else:
        with pytest.raises(m.ProofError): m.read(m.BASE + "/actions/jobs/1/logs", {"Authorization": "Bearer synthetic"}, log=True)
        assert len(calls) == 1
