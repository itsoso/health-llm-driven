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


BACKEND_GATE = load_gate()
BACKEND_JOBS = (
    'classify-changes', 'docs-quality', 'backend-quality', 'agent-runtime-postgres',
    'backend-tests', 'release-invariants', 'type-drift', 'backend-release-ready-v1',
    *(f'backend-test-balanced-{i:02d}' for i in range(1, 17)),
)


class BackendAPI(API):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.jobs = [dict(id=i + 1, name=name, run_id=42, head_sha=SHA,
                          status='completed', conclusion='success')
                     for i, name in enumerate(BACKEND_JOBS)]
        self.jobs.append(dict(id=99, name='mac-build', run_id=42, head_sha=SHA,
                              status='in_progress', conclusion=None))

    def __call__(self, url):
        if '/attempts/' in url and '/jobs?' in url:
            self.calls.append(url)
            run_id = int(url.split('/runs/')[1].split('/')[0])
            return {'total_count': len(self.jobs),
                    'jobs': [dict(job, run_id=run_id) for job in self.jobs]}
        if '/actions/runs/' in url:
            self.calls.append(url)
            run_id = int(url.rsplit('/', 1)[1])
            return next(item for item in self.runs if item['id'] == run_id)
        return super().__call__(url)


def backend_verify(api):
    return BACKEND_GATE.verify_release(SHA, SHA, target='backend-v1', _get_json=api)


def test_backend_ready_does_not_wait_for_unrelated_running_job():
    api = BackendAPI(runs=[run(status='in_progress', conclusion=None)])
    receipt = backend_verify(api)
    assert receipt == dict(sha=SHA, workflow_sha=SHA, ci_run_id=42, ci_run_attempt=1,
                           target='backend-v1', policy_version='backend-v1')
    assert sum('/attempts/1/jobs?' in url for url in api.calls) == 2


@pytest.mark.parametrize('name', BACKEND_JOBS)
@pytest.mark.parametrize('state', ['missing', 'skipped', 'queued'])
def test_backend_requires_every_concrete_job(name, state):
    api = BackendAPI()
    if state == 'missing':
        api.jobs = [job for job in api.jobs if job['name'] != name]
    else:
        for job in api.jobs:
            if job['name'] == name:
                job.update(status='queued' if state == 'queued' else 'completed',
                           conclusion=None if state == 'queued' else state)
    with pytest.raises(BACKEND_GATE.GateError):
        backend_verify(api)


@pytest.mark.parametrize('changes', [
    {'id': True}, {'name': ''}, {'head_sha': OTHER},
    {'status': 'completed', 'conclusion': 'failure'},
    {'status': 'completed', 'conclusion': 'cancelled'},
    {'status': 'in_progress', 'conclusion': 'success'},
    {'status': 'mystery', 'conclusion': None},
])
def test_backend_rejects_malformed_or_failed_unrelated_job(changes):
    api = BackendAPI()
    api.jobs[-1].update(changes)
    with pytest.raises(BACKEND_GATE.GateError, match='CI|job|Job'):
        backend_verify(api)


@pytest.mark.parametrize('change', ['duplicate', 'truncated', 'wrong_run', 'boolean_count'])
def test_backend_jobs_inventory_fails_closed(change):
    api = BackendAPI()
    def altered(url):
        value = api(url)
        if '/jobs?' in url:
            if change == 'duplicate':
                value['jobs'][-1] = dict(value['jobs'][0])
            elif change == 'truncated':
                value['total_count'] += 1
            elif change == 'boolean_count':
                value['total_count'] = True
            else:
                value['jobs'][0]['run_id'] = 999
        return value
    with pytest.raises(BACKEND_GATE.GateError, match='CI|job|Job'):
        backend_verify(altered)


@pytest.mark.parametrize('change', ['rerun', 'new_run', 'job_failure', 'job_replaced', 'main'])
def test_backend_control_plane_races_fail_closed(change):
    api = BackendAPI()
    count = 0
    def racing(url):
        nonlocal count
        if '/jobs?' in url:
            count += 1
            if count == 2:
                if change == 'job_failure':
                    api.jobs[-1].update(status='completed', conclusion='failure')
                elif change == 'job_replaced':
                    api.jobs[0]['id'] = 101
        if count >= 1:
            if change == 'rerun':
                api.runs[0]['run_attempt'] = 2
            elif change == 'new_run':
                api.runs = [run(), run(43)]
            elif change == 'main':
                api.main = OTHER
        return api(url)
    with pytest.raises(BACKEND_GATE.GateError, match='CI|job|Job|Main|main'):
        backend_verify(racing)


def test_backend_checks_older_run_current_attempt_instead_of_choosing_newer_green():
    api = BackendAPI(runs=[run(41, run_attempt=2, status='queued', conclusion=None), run()])
    with pytest.raises(BACKEND_GATE.GateError, match='CI'):
        backend_verify(api)


@pytest.mark.parametrize('target', ['', None, 'backend', 'full\n', [], 'backend-v2'])
def test_unknown_target_rejected_before_network(target):
    api = API()
    with pytest.raises(BACKEND_GATE.GateError):
        BACKEND_GATE.verify_release(SHA, SHA, target=target, _get_json=api)
    assert api.calls == []


def test_backend_cannot_hide_failed_job_in_older_current_attempt():
    api = BackendAPI(runs=[run(41, run_attempt=2), run()])
    def older_failed(url):
        result = api(url)
        if '/runs/41/attempts/2/jobs?' in url:
            result['jobs'][-1].update(status='completed', conclusion='failure')
        return result
    with pytest.raises(BACKEND_GATE.GateError):
        backend_verify(older_failed)


def test_backend_checks_every_run_and_allows_safe_optional_completion():
    api = BackendAPI(runs=[run(41, run_attempt=2), run(status='in_progress', conclusion=None)])
    count = 0
    def completing(url):
        nonlocal count
        if '/jobs?' in url:
            count += 1
            if count > 2:
                api.jobs[-1].update(status='completed', conclusion='success')
        return api(url)
    assert backend_verify(completing)['ci_run_id'] == 42
    assert count == 4


@pytest.mark.parametrize('field,value', [('repository', {'full_name': 'evil/repo'}),
                                        ('head_repository', {'full_name': 'evil/repo'}),
                                        ('workflow_id', 1), ('head_sha', OTHER),
                                        ('event', 'pull_request'), ('head_branch', 'feature'),
                                        ('run_attempt', True)])
def test_backend_preserves_canonical_run_identity_checks(field, value):
    with pytest.raises(BACKEND_GATE.GateError):
        backend_verify(BackendAPI(runs=[run(**{field: value})]))


def test_backend_requires_current_main_not_documentation_exception():
    with pytest.raises(BACKEND_GATE.GateError, match='current main'):
        backend_verify(BackendAPI(main=OTHER))


def test_target_cli_is_strict_and_defaults_to_full(monkeypatch, capsys):
    from types import SimpleNamespace
    gate = load_gate()
    seen = []
    monkeypatch.setattr(gate.sys, 'flags', SimpleNamespace(isolated=1))
    monkeypatch.setattr(gate, 'verify_release', lambda *args, **kwargs: seen.append(kwargs) or {})
    monkeypatch.setattr(gate.sys, 'argv', ['gate', '--sha', SHA, '--workflow-sha', SHA])
    assert gate.main() == 0
    assert seen[-1]['target'] == 'full'
    monkeypatch.setattr(gate.sys, 'argv', ['gate', '--sha', SHA, '--workflow-sha', SHA, '--target', 'backend-v1'])
    assert gate.main() == 0
    assert seen[-1]['target'] == 'backend-v1'
    monkeypatch.setattr(gate.sys, 'argv', ['gate', '--sha', SHA, '--workflow-sha', SHA, '--target', 'backend'])
    with pytest.raises(SystemExit):
        gate.main()
    capsys.readouterr()
