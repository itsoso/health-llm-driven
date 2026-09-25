"""Read-only proof for native-only continuation of an already deployed tree.

No credentials, deployment, source checkout, account maintenance, or receipt
creation. Invoke only from the fixed root-owned canonical bootstrap staging.
"""

import argparse
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

STATE = Path("/var/lib/reva-release")
PRODUCTION = Path("/opt/health-app")
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C",
       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
       "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1"}
# This is a continuation, not permission to ship undeployed runtime changes.
PUBLISHER_FILES = frozenset({
    ".github/workflows/trusted-release.yml", ".github/workflows/ci.yml",
    "scripts/trusted_release_server.py", "scripts/trusted_testflight_preflight.py",
    "scripts/test_testflight_only.py", "scripts/test_trusted_release_workflow.py",
    "docs/governance/deploy.md",
})


class PreflightError(Exception):
    """Fixed sanitized failure, never raw command output or health data."""


def validate_changed_paths(paths):
    for path in paths:
        if path in PUBLISHER_FILES:
            continue
        if (path.startswith("docs/dossiers/") and path.endswith(".md")
                and "/" not in path[len("docs/dossiers/"):] and ".." not in path):
            continue
        raise PreflightError("native-only candidate contains undeployed runtime or unknown changes")


def validate_receipt(sha, receipt):
    if not re.fullmatch(r"[0-9a-f]{40}", sha) or receipt != {"sha": sha, "state": "SUCCEEDED"}:
        raise PreflightError("exact successful production backend receipt required")


def validate_health(payload):
    expected = {"api": "running", "database": "connected", "redis": "connected", "celery": "connected"}
    if (not isinstance(payload, dict) or payload.get("status") != "healthy"
            or not isinstance(payload.get("services"), dict)
            or any(payload["services"].get(key) != value for key, value in expected.items())):
        raise PreflightError("production health is not fully healthy")


def run(args):
    return subprocess.run(args, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL, check=True, timeout=90).stdout


def git(source, *args):
    return run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                "-C", str(source), *args])


def load_module(source, sha, name, filename):
    path = source / "scripts" / filename
    for item in [*reversed(path.parents), path]:
        info = item.lstat()
        expected_type = stat.S_ISREG if item == path else stat.S_ISDIR
        if info.st_uid != 0 or info.st_mode & 0o022 or not expected_type(info.st_mode):
            raise PreflightError("unsafe canonical helper")
    if path.read_bytes() != git(source, "show", f"{sha}:scripts/{filename}"):
        raise PreflightError("canonical helper content differs")
    if os.path.lexists(path.parent / "__pycache__"):
        raise PreflightError("cached helper code forbidden")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prove(sha, lease):
    source = STATE / "bootstrap" / sha / "source"
    if Path(__file__).absolute() != source / "scripts/trusted_testflight_preflight.py":
        raise PreflightError("fixed canonical staging required")
    bootstrap = load_module(source, sha, "native_bootstrap", "bootstrap_trusted_release.py")
    checked_source, server = bootstrap.reviewed_source(sha)
    if source != checked_source:
        raise PreflightError("candidate source differs")
    helper = load_module(source, sha, "native_revision", "trusted_review_reset.py")
    gate = load_module(source, sha, "native_ci", "trusted_release_gate.py")
    gate.verify_release(sha, sha)
    live = git(PRODUCTION, "rev-parse", "HEAD").decode().strip()
    if re.fullmatch(r"[0-9a-f]{40}", live) is None:
        raise PreflightError("invalid production revision")
    helper._revision_proof(live, source, bootstrap)
    validate_receipt(live, bootstrap._read_json(STATE / live / "completed.json"))
    gate._latest(gate._get_json, live)
    helper._assert_previous_resets(bootstrap, server)
    server.assert_frontend_rebuild_history()
    server._assert_testflight_lease(lease, STATE / sha)
    # Compare object inventories, not diffs: no rename heuristics, external diff
    # drivers or caller-selected revision/path. All runtime entries must match.
    def inventory(repo, revision):
        rows = git(repo, "ls-tree", "-r", "-z", "--full-tree", revision)
        result = {}
        for row in rows.split(b"\0"):
            if row:
                metadata, path = row.split(b"\t", 1)
                result[path.decode("utf-8", errors="strict")] = metadata
        return result
    target, deployed = inventory(source, sha), inventory(PRODUCTION, live)
    validate_changed_paths([path for path in target.keys() | deployed.keys()
                            if target.get(path) != deployed.get(path)])
    for unit in ("health-backend", "celery-worker", "celery-beat", "reva-laya"):
        values = dict(line.split("=", 1) for line in run([
            "/usr/bin/systemctl", "show", unit,
            "--property=ActiveState,SubState,MainPID",
        ]).decode().splitlines())
        if (values.get("ActiveState") != "active" or values.get("SubState") != "running"
                or int(values.get("MainPID", "0")) <= 0):
            raise PreflightError("production service is not running")
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise PreflightError("health redirect rejected")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open("http://127.0.0.1:8000/api/v1/health", timeout=10) as response:
        raw = response.read(65537)
        if response.status != 200 or len(raw) > 65536:
            raise PreflightError("health response unavailable")
        validate_health(json.loads(raw))
    if git(PRODUCTION, "rev-parse", "HEAD").decode().strip() != live:
        raise PreflightError("production revision changed")
    server._assert_testflight_lease(lease, STATE / sha)
    return {"sha": sha, "production_sha": live, "state": "COMPATIBLE"}


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        if (not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
                or os.geteuid() != 0 or re.fullmatch(r"[0-9a-f]{40}", args.sha) is None):
            raise PreflightError("isolated privileged proof required")
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise PreflightError("invalid lease proof input")
        lease = json.loads(raw)
        result = prove(args.sha, lease)
    except Exception:  # noqa: BLE001 -- Never expose health payloads or helper errors.
        print("TestFlight backend compatibility proof failed", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
