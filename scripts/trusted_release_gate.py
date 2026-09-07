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


def _assert_main(get_json, sha):
    ref = _read(get_json, "/git/ref/heads/main")
    obj = ref.get("object")
    if (
        ref.get("ref") != "refs/heads/main"
        or not isinstance(obj, dict)
        or obj.get("type") != "commit"
        or obj.get("sha") != sha
    ):
        raise GateError("Release SHA is not current GitHub main")


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


def verify_release(sha, workflow_sha, *, _get_json=_get_json):
    """Attest fixed-origin current metadata; injection is internal test-only."""
    if (
        not isinstance(sha, str) or not isinstance(workflow_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", sha) is None
        or re.fullmatch(r"[0-9a-f]{40}", workflow_sha) is None
        or sha != workflow_sha
    ):
        raise GateError("Release and workflow must use the same exact 40-character SHA")
    _assert_main(_get_json, sha)
    receipt = _receipt(_latest(_get_json, sha), sha, workflow_sha)
    detail = _read(_get_json, f"/actions/runs/{receipt['ci_run_id']}")
    if _receipt(detail, sha, workflow_sha) != receipt:
        raise GateError("CI attempt changed during validation")
    _assert_main(_get_json, sha)
    if _receipt(_latest(_get_json, sha), sha, workflow_sha) != receipt:
        raise GateError("Latest CI changed during validation")
    return receipt


def main():
    if not sys.flags.isolated:
        print("release gate: isolated Python (-I) is required", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--workflow-sha", required=True)
    args = parser.parse_args()
    try:
        receipt = verify_release(args.sha, args.workflow_sha)
    except GateError as error:
        print(f"release gate: {error}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
