"""Behavioral tests for the read-only, fixed-origin release attestation."""

import importlib.util
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("trusted_release_gate.py")
SHA = "a" * 40
OTHER = "b" * 40
BASE = "https://api.github.com/repos/itsoso/health-llm-driven"


def load_gate():
    assert SCRIPT.exists(), "A trusted release metadata gate must exist"
    spec = importlib.util.spec_from_file_location("trusted_release_gate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(run_id=42, **overrides):
    result = {
        "id": run_id, "run_attempt": 1, "workflow_id": 251604315,
        "head_sha": SHA, "head_branch": "main", "event": "push",
        "status": "completed", "conclusion": "success",
        "repository": {"full_name": "itsoso/health-llm-driven"},
        "head_repository": {"full_name": "itsoso/health-llm-driven"},
    }
    result.update(overrides)
    return result


class API:
    def __init__(self, runs=None, main=SHA, detail=None):
        self.runs = [run()] if runs is None else runs
        self.main = main
        self.detail = detail
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        if url == BASE + "/git/ref/heads/main":
            return {"ref": "refs/heads/main", "object": {"type": "commit", "sha": self.main}}
        if url == BASE + "/actions/workflows/251604315/runs?head_sha=" + SHA + "&per_page=100":
            return {"total_count": len(self.runs), "workflow_runs": self.runs}
        if url == BASE + "/actions/runs/42":
            return self.detail or max(self.runs, key=lambda item: item["id"])
        raise AssertionError("Unexpected API destination")


def test_receipt_requires_exact_main_and_successful_latest_ci():
    gate = load_gate()
    api = API()
    assert gate.verify_release(SHA, SHA, _get_json=api) == {
        "sha": SHA, "workflow_sha": SHA, "ci_run_id": 42, "ci_run_attempt": 1,
    }
    assert all(url.startswith(BASE + "/") for url in api.calls)


@pytest.mark.parametrize("sha,workflow_sha", [(OTHER, SHA), (SHA, OTHER), ("main", "main"), ("a" * 39, SHA), ("A" * 40, "A" * 40), (SHA + "\n", SHA)])
def test_unpinned_or_mismatched_sha_is_rejected_before_http(sha, workflow_sha):
    gate = load_gate()
    api = API()
    with pytest.raises(gate.GateError):
        gate.verify_release(sha, workflow_sha, _get_json=api)
    assert not api.calls


def test_main_mismatch_blocks_release():
    gate = load_gate()
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=API(main=OTHER))


@pytest.mark.parametrize("overrides", [
    {"status": "queued", "conclusion": None}, {"conclusion": "failure"},
    {"event": "pull_request"}, {"head_branch": "other"},
    {"head_sha": OTHER}, {"workflow_id": 123},
    {"repository": {"full_name": "attacker/health-llm-driven"}},
    {"head_repository": {"full_name": "attacker/health-llm-driven"}},
    {"run_attempt": 0}, {"run_attempt": True}, {"id": "42"},
    {"workflow_id": 251604315.0},
])
def test_latest_run_cannot_be_replaced_by_older_success(overrides):
    gate = load_gate()
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=API(runs=[run(41), run(**overrides)]))


def test_empty_ci_history_blocks_release():
    gate = load_gate()
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=API(runs=[]))


def test_run_detail_detects_rerun_after_successful_list_snapshot():
    gate = load_gate()
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=API(detail=run(run_attempt=2, status="in_progress", conclusion=None)))


@pytest.mark.parametrize("overrides", [
    {"status": "queued", "conclusion": None},
    {"status": "in_progress", "conclusion": None},
    {"status": "completed", "conclusion": "failure"},
])
def test_older_run_new_attempt_cannot_be_hidden_by_larger_successful_run_id(overrides):
    gate = load_gate()
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=API(runs=[run(41, run_attempt=2, **overrides), run()]))


def test_explicitly_rerunning_failed_older_attempt_to_success_unlocks_gate():
    gate = load_gate()
    assert gate.verify_release(SHA, SHA, _get_json=API(runs=[run(41, run_attempt=2), run()]))["ci_run_id"] == 42


@pytest.mark.parametrize("change", ["main", "new_run", "rerun"])
def test_remote_changes_during_validation_block_release(change):
    gate = load_gate()
    api = API()
    def changing_api(url):
        if len(api.calls) >= 3:
            if change == "main":
                api.main = OTHER
            elif change == "new_run":
                api.runs = [run(43), run()]
            else:
                api.runs = [run(run_attempt=2, status="queued", conclusion=None)]
        return api(url)
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=changing_api)


def test_transport_failure_never_exposes_secret_or_claims_success():
    gate = load_gate()
    def unavailable(_url):
        raise OSError("network detail containing secret-token")
    with pytest.raises(gate.GateError, match="GitHub metadata unavailable") as error:
        gate.verify_release(SHA, SHA, _get_json=unavailable)
    assert "secret-token" not in str(error.value)


@pytest.mark.parametrize("args", [["--sha", SHA, "--workflow-sha", SHA, "--origin", "https://evil.test"], ["--sha", "main", "--workflow-sha", SHA]])
def test_cli_rejects_arbitrary_origin_and_unpinned_input(args):
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert not result.stdout


def test_cli_requires_isolated_python():
    result = subprocess.run([sys.executable, str(SCRIPT), "--sha", SHA, "--workflow-sha", SHA], capture_output=True, text=True, check=False)
    assert result.returncode != 0
    assert "isolated" in result.stderr


@pytest.mark.parametrize("payload", [[], {}, {"total_count": 101, "workflow_runs": [run()]}, {"total_count": 2, "workflow_runs": [run(), run()]}, {"total_count": 1, "workflow_runs": [None]}])
def test_incomplete_and_malformed_api_history_fails_closed(payload):
    gate = load_gate()
    api = API()
    def malformed(url):
        return payload if "/workflows/" in url else api(url)
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=malformed)


def test_cli_ignores_pythonpath_sitecustomize(tmp_path):
    marker = tmp_path / "injected"
    (tmp_path / "sitecustomize.py").write_text(
        f"from pathlib import Path; Path({str(marker)!r}).touch()\n", encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--sha", "main", "--workflow-sha", SHA], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 1
    assert not marker.exists()
    assert not result.stdout


def test_transport_is_get_only_bounded_and_rejects_redirects(monkeypatch):
    gate = load_gate()
    observed = {}
    class Response(io.BytesIO):
        status = 200
        def geturl(self):
            return BASE + "/git/ref/heads/main"
    class Opener:
        def open(self, request, timeout):
            observed.update(method=request.method, url=request.full_url, timeout=timeout)
            return Response(json.dumps({"ok": True}).encode())
    def build(*handlers):
        for handler in handlers:
            if isinstance(handler, gate.urllib.request.ProxyHandler):
                assert handler.proxies == {}
            if isinstance(handler, gate._NoRedirect):
                with pytest.raises(gate.GateError):
                    handler.redirect_request(None, None, 302, "", {}, "https://evil.test")
        return Opener()
    monkeypatch.setenv("HTTPS_PROXY", "https://evil.test")
    monkeypatch.setenv("SSL_CERT_FILE", "/nonexistent/untrusted.pem")
    monkeypatch.setattr(gate.urllib.request, "build_opener", build)
    assert gate._get_json(BASE + "/git/ref/heads/main") == {"ok": True}
    assert observed == {"method": "GET", "url": BASE + "/git/ref/heads/main", "timeout": 10}


def test_transport_refuses_oversize_response(monkeypatch):
    gate = load_gate()
    class Response(io.BytesIO):
        status = 200
        def geturl(self):
            return BASE + "/git/ref/heads/main"
    class Opener:
        def open(self, request, timeout):
            return Response(b" " * 2_000_001)
    monkeypatch.setattr(gate.urllib.request, "build_opener", lambda *args: Opener())
    with pytest.raises(gate.GateError, match="exceeds bound"):
        gate._get_json(BASE + "/git/ref/heads/main")


class DocumentationAPI(API):
    def __init__(self, paths=None):
        super().__init__(main=OTHER)
        self.comparison = {
            "status": "ahead", "ahead_by": 1, "behind_by": 0, "total_commits": 1,
            "base_commit": {"sha": SHA}, "merge_base_commit": {"sha": SHA},
            "commits": [{"sha": OTHER, "parents": [{"sha": SHA}]}],
            "files": [{"filename": p, "status": "modified"} for p in
                      (paths or ["docs/dossiers/2026-10-01-evidence.md"])],
        }

    def __call__(self, url):
        if url == BASE + f"/compare/{SHA}...{OTHER}":
            self.calls.append(url)
            return self.comparison
        if url == BASE + f"/actions/workflows/251604315/runs?head_sha={OTHER}&per_page=100":
            self.calls.append(url)
            return {"total_count": 1, "workflow_runs": [run(43, head_sha=OTHER)]}
        if url == BASE + "/actions/runs/43":
            self.calls.append(url)
            return run(43, head_sha=OTHER)
        return super().__call__(url)


@pytest.mark.parametrize("path", ["AGENTS.md", "docs/governance/deploy.md",
                                  "docs/ops/github-relay.md", "docs/dossiers/new.md"])
def test_green_linear_documentation_descendant_keeps_pinned_candidate(path):
    gate = load_gate()
    assert gate.verify_release(SHA, SHA, _get_json=DocumentationAPI([path]))["sha"] == SHA


@pytest.mark.parametrize("path", ["mobile/app.json", "backend/app/main.py", "backend/knowledge/a.md",
                                  "docs/prompts.md", "docs/ops/unknown.md", "docs/dossiers/../x.md",
                                  "docs/dossiers/nested/x.md", ".github/workflows/trusted-release.yml"])
def test_documentation_drift_rejects_runtime_and_unlisted_paths(path):
    gate = load_gate()
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=DocumentationAPI([path]))


@pytest.mark.parametrize("changes", [
    {"status": "diverged"}, {"behind_by": 1}, {"total_commits": 2}, {"ahead_by": True},
    {"merge_base_commit": {"sha": OTHER}}, {"base_commit": {"sha": OTHER}},
    {"commits": [{"sha": OTHER, "parents": [{"sha": SHA}, {"sha": "c" * 40}]}]},
    {"files": []}, {"files": [{"filename": "AGENTS.md", "status": "unknown"}]},
    {"files": [{"filename": "AGENTS.md", "status": "renamed", "previous_filename": "backend/main.py"}]},
    {"files": [{"filename": "AGENTS.md", "status": "modified"}] * 300},
])
def test_documentation_proof_fails_closed(changes):
    gate = load_gate()
    api = DocumentationAPI()
    api.comparison.update(changes)
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=api)


def test_documentation_head_must_have_fresh_green_ci():
    gate = load_gate()
    api = DocumentationAPI()
    def failed_head(url):
        result = api(url)
        if f"head_sha={OTHER}" in url:
            result["workflow_runs"][0]["conclusion"] = "failure"
        return result
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=failed_head)


def test_observed_git_main_must_match_api_main():
    gate = load_gate()
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, observed_main="c" * 40, _get_json=DocumentationAPI())


@pytest.mark.parametrize("hidden_code", [False, True])
def test_each_intermediate_commit_is_checked_even_when_net_delta_is_documentation(hidden_code):
    gate = load_gate()
    api = DocumentationAPI()
    middle = "c" * 40
    overall = {**api.comparison, "ahead_by": 2, "total_commits": 2,
               "commits": [{"sha": middle, "parents": [{"sha": SHA}]},
                           {"sha": OTHER, "parents": [{"sha": middle}]}]}
    calls = []
    def chain(url):
        calls.append(url)
        if url == BASE + f"/compare/{SHA}...{OTHER}":
            return overall
        for before, after in [(SHA, middle), (middle, OTHER)]:
            if url == BASE + f"/compare/{before}...{after}":
                return {**api.comparison, "base_commit": {"sha": before},
                        "merge_base_commit": {"sha": before},
                        "commits": [{"sha": after, "parents": [{"sha": before}]}],
                        "files": [{"filename": "backend/main.py" if hidden_code else "AGENTS.md",
                                   "status": "modified"}]}
        return api(url)
    if hidden_code:
        with pytest.raises(gate.GateError):
            gate.verify_release(SHA, SHA, _get_json=chain)
    else:
        assert gate.verify_release(SHA, SHA, observed_main=OTHER, _get_json=chain)["sha"] == SHA
        assert BASE + f"/compare/{middle}...{OTHER}" in calls


@pytest.mark.parametrize("change", ["head", "head_rerun", "candidate_rerun"])
def test_documentation_attestation_rechecks_both_ci_and_main(change):
    gate = load_gate()
    api = DocumentationAPI()
    def changing(url):
        result = api(url)
        if len(api.calls) >= 7:
            if change == "head" and url.endswith("/git/ref/heads/main"):
                result["object"]["sha"] = "c" * 40
            elif "/workflows/" in url and ((change == "head_rerun" and OTHER in url)
                                            or (change == "candidate_rerun" and SHA in url)):
                result["workflow_runs"][0]["run_attempt"] = 2
        return result
    with pytest.raises(gate.GateError):
        gate.verify_release(SHA, SHA, _get_json=changing)
