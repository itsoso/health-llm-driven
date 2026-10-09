"""Read-only GitHub attestation for the trusted release workflow.

Invoke with isolated Python (-I). This module never reads git configuration,
executes repository commands, accepts endpoints, or authorizes a stale receipt.
The executor must run it immediately before each privileged release stage.
"""

import argparse
import json
import os
import re
import ssl
import sys
import urllib.request

_BASE = "https://api.github.com/repos/itsoso/health-llm-driven"
_REPOSITORY = "itsoso/health-llm-driven"
_WORKFLOW_ID = 251604315
_TIMEOUT = 10
_MAX_RESPONSE = 2_000_000


class GateError(Exception):
    """Sanitized, fail-closed gate rejection."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise GateError("GitHub redirect rejected")


def _get_json(url):
    # Ignore proxy and custom CA environment variables. Trust only the Python
    # installation's system CA locations, not caller-selected trust roots.
    defaults = ssl.get_default_verify_paths()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    cafile = defaults.openssl_cafile if os.path.isfile(defaults.openssl_cafile) else None
    capath = defaults.openssl_capath if os.path.isdir(defaults.openssl_capath) else None
    if not cafile and not capath:
        raise GateError("System TLS trust unavailable")
    context.load_verify_locations(cafile=cafile, capath=capath)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect(),
        urllib.request.HTTPSHandler(context=context),
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "reva-trusted-release-gate",
        "Cache-Control": "no-cache",
    }
    token = os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(url, headers=headers, method="GET")
    with opener.open(request, timeout=_TIMEOUT) as response:
        if response.status != 200 or response.geturl() != url:
            raise GateError("Unexpected GitHub response")
        raw = response.read(_MAX_RESPONSE + 1)
        if len(raw) > _MAX_RESPONSE:
            raise GateError("GitHub response exceeds bound")
        return json.loads(raw)


def _read(get_json, path):
    try:
        result = get_json(_BASE + path)
    except GateError:
        raise
    except Exception:  # noqa: BLE001 -- Transport failures must never expose tokens or response bodies.
        # Do not emit HTTP exception bodies, URLs, headers or credential data.
        raise GateError("GitHub metadata unavailable") from None
    if not isinstance(result, dict):
        raise GateError("Malformed GitHub metadata")
    return result


def _main_sha(get_json):
    ref = _read(get_json, "/git/ref/heads/main")
    obj = ref.get("object")
    if (
        ref.get("ref") != "refs/heads/main"
        or not isinstance(obj, dict)
        or obj.get("type") != "commit"
        or not isinstance(obj.get("sha"), str)
        or re.fullmatch(r"[0-9a-f]{40}", obj["sha"]) is None
    ):
        raise GateError("Malformed GitHub main ref")
    return obj["sha"]


def is_release_documentation(path):
    """Explicit non-runtime documents; never infer safety from .md alone."""
    return isinstance(path, str) and (
        path in {"AGENTS.md", "docs/governance/deploy.md", "docs/ops/github-relay.md"}
        or re.fullmatch(r"docs/dossiers/[A-Za-z0-9][A-Za-z0-9_-]*\.md", path) is not None
    )


def _documentation_files(payload):
    files = payload.get("files")
    # GitHub compare returns at most 300 files. A full page is ambiguous.
    if not isinstance(files, list) or not 0 < len(files) < 300:
        raise GateError("Incomplete documentation comparison")
    seen = set()
    for item in files:
        if (not isinstance(item, dict) or not is_release_documentation(item.get("filename"))
                or item.get("status") not in {"added", "removed", "modified", "renamed"}
                or item["filename"] in seen
                or (item.get("status") == "renamed"
                    and not is_release_documentation(item.get("previous_filename")))
                or ("previous_filename" in item
                    and not is_release_documentation(item["previous_filename"]))):
            raise GateError("Main contains runtime or unknown changes")
        seen.add(item["filename"])


def _documentation_descendant(get_json, sha, head, *, _max_commits=8):
    """Bounded linear ancestry, checking each commit (including reverted code)."""
    payload = _read(get_json, f"/compare/{sha}...{head}")
    commits = payload.get("commits")
    count = payload.get("total_commits")
    if (payload.get("status") != "ahead" or type(count) is not int or not 1 <= count <= _max_commits
            or type(payload.get("ahead_by")) is not int or payload["ahead_by"] != count
            or type(payload.get("behind_by")) is not int or payload["behind_by"] != 0
            or not isinstance(commits, list) or len(commits) != count
            or not isinstance(payload.get("base_commit"), dict)
            or payload["base_commit"].get("sha") != sha
            or not isinstance(payload.get("merge_base_commit"), dict)
            or payload["merge_base_commit"].get("sha") != sha):
        raise GateError("Unproven or oversized documentation ancestry")
    previous, seen = sha, {sha}
    for commit in commits:
        if not isinstance(commit, dict):
            raise GateError("Malformed documentation commit")
        current, parents = commit.get("sha"), commit.get("parents")
        if (not isinstance(current, str) or re.fullmatch(r"[0-9a-f]{40}", current) is None
                or current in seen or not isinstance(parents, list) or len(parents) != 1
                or not isinstance(parents[0], dict) or parents[0].get("sha") != previous):
            raise GateError("Documentation commits must be a linear descendant chain")
        # Immutable exact commit comparisons cannot conceal a code edit/revert.
        if count == 1:
            _documentation_files(payload)
        else:
            _documentation_descendant(get_json, previous, current, _max_commits=1)
        seen.add(current)
        previous = current
    if previous != head:
        raise GateError("Documentation ancestry does not reach main")


def _positive_int(value):
    return type(value) is int and value > 0


def _latest(get_json, sha):
    payload = _read(
        get_json,
        f"/actions/workflows/{_WORKFLOW_ID}/runs?head_sha={sha}&per_page=100",
    )
    runs = payload.get("workflow_runs")
    count = payload.get("total_count")
    if (
        not isinstance(runs, list) or not runs or type(count) is not int
        or count != len(runs) or count > 100
        or any(not isinstance(run, dict) or not _positive_int(run.get("id")) for run in runs)
        or len({run["id"] for run in runs}) != len(runs)
    ):
        raise GateError("Incomplete or malformed CI history")
    # Run IDs order workflow creation, not rerun attempts. A lower-ID run can
    # have a newer failed/running attempt. Conservatively require every current
    # exact-SHA attempt to be green; explicitly rerun old failures to clear them.
    for run in runs:
        _receipt(run, sha, sha)
    # Never select an older green run while the most recent run is queued/red.
    return max(runs, key=lambda run: run["id"])


def _receipt(run, sha, workflow_sha):
    if (
        not isinstance(run, dict)
        or not _positive_int(run.get("id"))
        or not _positive_int(run.get("run_attempt"))
        or type(run.get("workflow_id")) is not int
        or run.get("workflow_id") != _WORKFLOW_ID
        or run.get("head_sha") != sha
        or run.get("head_branch") != "main"
        or run.get("event") not in ("push", "workflow_dispatch")
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or any(
            not isinstance(run.get(key), dict)
            or run[key].get("full_name") != _REPOSITORY
            for key in ("repository", "head_repository")
        )
    ):
        raise GateError("Latest exact-SHA CI is not trusted completed success")
    return {
        "sha": sha, "workflow_sha": workflow_sha,
        "ci_run_id": run["id"], "ci_run_attempt": run["run_attempt"],
    }



_BACKEND_REQUIRED_JOBS = frozenset({
    "classify-changes", "docs-quality", "backend-quality", "agent-runtime-postgres",
    "backend-tests", "release-invariants", "type-drift", "backend-release-ready-v1",
    *(f"backend-test-balanced-{index:02d}" for index in range(1, 17)),
})


def _backend_run_receipt(run, sha):
    # Reuse every origin/identity check of the full gate. Only an explicitly
    # running workflow may lack a final success; queued and failed runs block.
    if not isinstance(run, dict) or (run.get("status"), run.get("conclusion")) not in (
        ("in_progress", None), ("completed", "success"),
    ):
        raise GateError("Backend CI is not running or successful")
    return _receipt(dict(run, status="completed", conclusion="success"), sha, sha)


def _backend_runs(get_json, sha):
    payload = _read(get_json, f"/actions/workflows/{_WORKFLOW_ID}/runs?head_sha={sha}&per_page=100")
    runs, count = payload.get("workflow_runs"), payload.get("total_count")
    if (not isinstance(runs, list) or not runs or type(count) is not int
            or count != len(runs) or count >= 100):
        raise GateError("Incomplete backend CI history")
    receipts = [_backend_run_receipt(run, sha) for run in runs]
    if len({receipt["ci_run_id"] for receipt in receipts}) != count:
        raise GateError("Duplicate backend CI history")
    return sorted(receipts, key=lambda receipt: receipt["ci_run_id"])


def _backend_jobs(get_json, receipt):
    run_id, attempt = receipt["ci_run_id"], receipt["ci_run_attempt"]
    payload = _read(get_json, f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100")
    jobs, count = payload.get("jobs"), payload.get("total_count")
    if (not isinstance(jobs, list) or type(count) is not int
            or count != len(jobs) or not 0 < count < 100):
        raise GateError("Incomplete backend CI jobs")
    identities, names = set(), set()
    required = {}
    for job in jobs:
        if (not isinstance(job, dict) or not _positive_int(job.get("id"))
                or type(job.get("run_id")) is not int or job["run_id"] != run_id
                or job.get("head_sha") != receipt["sha"]
                or not isinstance(job.get("name"), str) or not job["name"].strip()
                or job["id"] in identities or job["name"] in names):
            raise GateError("Malformed or duplicate backend CI job")
        identities.add(job["id"])
        names.add(job["name"])
        state = (job.get("status"), job.get("conclusion"))
        if state not in (("queued", None), ("waiting", None), ("in_progress", None),
                         ("completed", "success"), ("completed", "skipped")):
            raise GateError("Observed CI job failure or unknown state")
        if job["name"] in _BACKEND_REQUIRED_JOBS:
            if state != ("completed", "success"):
                raise GateError("Required backend CI job is not successful")
            required[job["name"]] = job["id"]
    if set(required) != _BACKEND_REQUIRED_JOBS:
        raise GateError("Required backend CI jobs are missing")
    return required


def _verify_backend(get_json, sha, observed_main):
    head = _main_sha(get_json)
    if head != sha or (observed_main is not None and head != observed_main):
        raise GateError("Backend release must use exact current main")
    receipts = _backend_runs(get_json, sha)
    jobs = {}
    for receipt in receipts:
        run_id = receipt["ci_run_id"]
        if _backend_run_receipt(_read(get_json, f"/actions/runs/{run_id}"), sha) != receipt:
            raise GateError("CI attempt changed during validation")
        jobs[run_id] = _backend_jobs(get_json, receipt)
    if _backend_runs(get_json, sha) != receipts:
        raise GateError("CI history changed during validation")
    for receipt in receipts:
        run_id = receipt["ci_run_id"]
        if _backend_jobs(get_json, receipt) != jobs[run_id]:
            raise GateError("CI job identity changed during validation")
        if _backend_run_receipt(_read(get_json, f"/actions/runs/{run_id}"), sha) != receipt:
            raise GateError("CI attempt changed during validation")
    if _backend_runs(get_json, sha) != receipts or _main_sha(get_json) != head:
        raise GateError("Main or CI history changed during validation")
    return dict(receipts[-1], target="backend-v1", policy_version="backend-v1")

def verify_release(sha, workflow_sha, *, observed_main=None, target="full", _get_json=_get_json):
    """Attest fixed-origin current metadata; injection is internal test-only."""
    if (
        not isinstance(sha, str) or not isinstance(workflow_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", sha) is None
        or re.fullmatch(r"[0-9a-f]{40}", workflow_sha) is None
        or sha != workflow_sha
        or (observed_main is not None and (
            not isinstance(observed_main, str) or re.fullmatch(r"[0-9a-f]{40}", observed_main) is None))
    ):
        raise GateError("Release and workflow must use the same exact 40-character SHA")
    if target not in ("full", "backend-v1"):
        raise GateError("Unknown release target")
    if target == "backend-v1":
        return _verify_backend(_get_json, sha, observed_main)
    head = _main_sha(_get_json)
    if observed_main is not None and head != observed_main:
        raise GateError("Git and GitHub main observations differ")
    head_receipt = None
    if head != sha:
        _documentation_descendant(_get_json, sha, head)
        head_receipt = _receipt(_latest(_get_json, head), head, head)
        detail = _read(_get_json, f"/actions/runs/{head_receipt['ci_run_id']}")
        if _receipt(detail, head, head) != head_receipt:
            raise GateError("Main CI attempt changed during validation")
    receipt = _receipt(_latest(_get_json, sha), sha, workflow_sha)
    detail = _read(_get_json, f"/actions/runs/{receipt['ci_run_id']}")
    if _receipt(detail, sha, workflow_sha) != receipt:
        raise GateError("CI attempt changed during validation")
    if _main_sha(_get_json) != head:
        raise GateError("Main changed during validation")
    if _receipt(_latest(_get_json, sha), sha, workflow_sha) != receipt:
        raise GateError("Latest CI changed during validation")
    if head_receipt is not None and _receipt(_latest(_get_json, head), head, head) != head_receipt:
        raise GateError("Main CI changed during validation")
    return receipt


def main():
    if not sys.flags.isolated:
        print("release gate: isolated Python (-I) is required", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    parser.add_argument("--observed-main")
    parser.add_argument("--target", choices=("full", "backend-v1"), default="full")
    args = parser.parse_args()
    try:
        receipt = verify_release(args.sha, args.workflow_sha, observed_main=args.observed_main, target=args.target)
    except GateError as error:
        print(f"release gate: {error}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
