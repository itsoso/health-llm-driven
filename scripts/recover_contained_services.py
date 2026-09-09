"""One-shot operator recovery of unchanged services after pre-checkout containment.

Not a deployment, rollback, lease reset, or release authorization. The original
failed release and its business lease remain untouched, even after success.
"""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

UNITS = ("health-backend.socket", "health-backend.service", "celery-worker.service", "celery-beat.service")
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C"}
STATE = Path("/var/lib/reva-release")


class RecoveryError(Exception):
    """Only static diagnostics may cross the operator boundary."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RecoveryError("invalid operator arguments")


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(json.dumps(value, sort_keys=True).encode())
        stream.flush()
        os.fsync(stream.fileno())
    _sync(path.parent)


def _systemctl(action, unit):
    if action not in {"start", "stop"} or unit not in UNITS:
        raise RecoveryError("unknown service operation")
    subprocess.run(["/usr/bin/systemctl", action, unit], env=ENV,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True, timeout=60)


def _wait_ready(proof):
    deadline = time.monotonic() + 60
    previous, since = None, None
    while time.monotonic() < deadline:
        try:
            sample = proof.running_snapshot()
        except Exception:  # A startup read is not success; bounded stability is required.
            previous, since = None, None
        else:
            if sample != previous:
                previous, since = sample, time.monotonic()
            elif since is not None and time.monotonic() - since >= 7:
                return sample
        time.sleep(1)
    raise RecoveryError("service stability proof failed")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RecoveryError("health redirect rejected")


def _http_probes():
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with opener.open("http://127.0.0.1:8000/api/v1/health", timeout=5) as response:
                raw = response.read(16385)
                if response.status != 200 or len(raw) > 16384:
                    raise RecoveryError("health response rejected")
                health = json.loads(raw)
                expected = {"api": "running", "database": "connected", "redis": "connected", "celery": "connected"}
                if health.get("status") != "healthy" or health.get("services") != expected:
                    raise RecoveryError("health services not ready")
            try:
                with opener.open("http://127.0.0.1:8000/api/v1/auth/me", timeout=5):
                    raise RecoveryError("authentication boundary did not reject")
            except urllib.error.HTTPError as error:
                error.close()
                if error.code != 401:
                    raise RecoveryError("authentication boundary failed") from None
            return
        except (OSError, ValueError, RecoveryError):
            time.sleep(2)
    raise RecoveryError("health or authentication proof failed")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _context(sha, *, verify_ci=True):
    if (re.fullmatch(r"[0-9a-f]{40}", sha or "") is None
            or not sys.flags.isolated or not sys.flags.no_site
            or not sys.flags.dont_write_bytecode or os.geteuid() != 0
            or sys.executable != "/usr/bin/python3.12"
            or "SSH_ORIGINAL_COMMAND" in os.environ):
        raise RecoveryError("isolated system operator required")
    source = STATE / "bootstrap" / sha / "source"
    entry = source / "scripts/recover_contained_services.py"
    if Path(__file__).absolute() != entry:
        raise RecoveryError("canonical recovery source required")
    # Verify metadata before importing any repository helper.
    for path in [*reversed(entry.parents), entry, entry.with_name("bootstrap_trusted_release.py")]:
        info = path.lstat()
        kind = stat.S_ISREG if path in (entry, entry.with_name("bootstrap_trusted_release.py")) else stat.S_ISDIR
        if info.st_uid != 0 or info.st_mode & 0o022 or not kind(info.st_mode):
            raise RecoveryError("unsafe canonical recovery path")
        if path.is_file() and info.st_nlink != 1:
            raise RecoveryError("linked canonical recovery file")
    os.umask(0o077)
    bootstrap = _load(entry.with_name("bootstrap_trusted_release.py"), "contained_bootstrap")
    reviewed, server = bootstrap.reviewed_source(sha)
    if reviewed != source:
        raise RecoveryError("canonical source mismatch")
    if verify_ci:
        subprocess.run(["/usr/bin/python3.12", "-I", "-S", "-B", str(source / "scripts/trusted_release_gate.py"),
                        "--sha", sha, "--workflow-sha", sha], env=ENV, check=True, timeout=90,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return source, bootstrap, server


def _probe_child(production_sha, recovery_sha):
    """Read-only application checks from canonical old code, no site startup."""
    # The parent has attested exact CI before any credential read and holds the
    # original locks. This read-only child revalidates canonical local bytes;
    # an external metadata outage cannot turn a post-start probe into a new gate.
    source, bootstrap, server = _context(recovery_sha, verify_ci=False)
    reset = _load(source / "scripts/trusted_review_reset.py", "contained_probe_reset")
    reset._assert_isolated_search_path()
    old_source = bootstrap.canonical_source(production_sha)
    reset._revision_proof(production_sha, old_source, bootstrap)
    reset._validate_application_imports(old_source, server)
    reset._validate_venv(server)
    site = Path("/opt/health-app/backend/venv/lib/python3.12/site-packages")
    sys.path.append(str(site))
    environment = reset._parse_maintenance_environment(server.read_production_env())
    os.environ.clear()
    os.environ.update(environment)
    os.chdir(old_source / "backend")
    sys.path.insert(0, str(old_source / "backend"))
    with contextlib.redirect_stdout(reset._BoundedSummary()), contextlib.redirect_stderr(reset._BoundedSummary()):
        reset._validate_effective_target(old_source, environment)
        schema = _load(old_source / "backend/scripts/verify_runtime_schema_compatibility.py", "contained_schema_probe")
        schema.main()
        kb = _load(old_source / "backend/scripts/verify_runtime_only_kb_contract.py", "contained_kb_probe")
        sys.argv = [str(old_source / "backend/scripts/verify_runtime_only_kb_contract.py"), "--phase", "staged"]
        if kb.main() != 0:
            raise RecoveryError("KB serving probe failed")


def _application_probes(production_sha, recovery_sha):
    # Exact operator script; no caller-supplied commands, paths or credentials.
    code = "import runpy; m=runpy.run_path(" + repr(str(Path(__file__).absolute())) + "); m['_probe_child'](" + repr(production_sha) + "," + repr(recovery_sha) + ")"
    subprocess.run(["/usr/bin/python3.12", "-I", "-S", "-B", "-c", code], env=ENV,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, check=True, timeout=180)


def recover_services(proof, audit, recovery_sha, expected_hash=None):
    if os.path.lexists(audit):
        raise RecoveryError("recovery already attempted; retry forbidden")
    before = proof.snapshot()
    proof.stopped()
    evidence = {"recovery_sha": recovery_sha, "failed_sha": proof.failed_sha,
                "production_sha": proof.production_sha, "snapshot": before}
    digest = _digest(evidence)
    if expected_hash is not None and expected_hash != digest:
        raise RecoveryError("recovery evidence changed")
    try:
        _application_probes(proof.production_sha, recovery_sha)
        if proof.snapshot() != before:
            raise RecoveryError("application preflight changed evidence")
        proof.stopped()
    except Exception:
        raise RecoveryError("application preflight failed; no recovery consumed") from None
    if expected_hash is None:
        return {"state": "INSPECTED", "evidence_sha256": digest}
    audit.mkdir(mode=0o700)
    _sync(audit.parent)
    _write(audit / "intent.json", {**evidence, "evidence_sha256": digest})
    started = False
    try:
        if proof.snapshot() != before:
            raise RecoveryError("pre-start evidence changed")
        proof.stopped()
        started = True
        for unit in UNITS:
            _systemctl("start", unit)
        _wait_ready(proof)
        _application_probes(proof.production_sha, recovery_sha)
        _http_probes()
        stable = _wait_ready(proof)
        if proof.snapshot() != before:
            raise RecoveryError("post-start evidence changed")
        result = {"state": "RESTORED_PREVIOUS_SERVICES", "recovery_sha": recovery_sha,
                  "failed_sha": proof.failed_sha, "production_sha": proof.production_sha,
                  "evidence_sha256": digest, "stable_services": stable,
                  "original_release_and_lease_preserved": True}
        _write(audit / "completed.json", result)
        return result
    except BaseException:
        if started:
            failures = []
            for unit in UNITS:
                try:
                    _systemctl("stop", unit)
                except BaseException:
                    failures.append(unit)
            try:
                proof.stopped()
            except BaseException:
                failures.append("containment")
            if failures:
                raise RecoveryError("recovery and containment unproven; preserve all evidence") from None
        raise RecoveryError("recovery incomplete; preserve intent and original lease") from None


def _check_original_build_lock(bootstrap, failed_sha, fd):
    path = bootstrap.STATE / failed_sha / "build.lock"
    if fd is None:
        if os.path.lexists(path):
            raise RecoveryError("previously absent build lock appeared")
    else:
        bootstrap._assert_original_lock(path, fd)


def main():
    try:
        parser = _Parser(description=__doc__, allow_abbrev=False)
        parser.add_argument("--sha", required=True)
        parser.add_argument("--failed-sha", required=True)
        parser.add_argument("--production-sha", required=True)
        parser.add_argument("--lease-token-stdin", required=True, action="store_true")
        parser.add_argument("--evidence-sha256")
        parser.add_argument("--retire-restored", action="store_true",
                            help="Separately close an already restored failed release; never redeploy")
        args = parser.parse_args()
        for sha in (args.sha, args.failed_sha, args.production_sha):
            if re.fullmatch(r"[0-9a-f]{40}", sha) is None:
                raise RecoveryError("exact SHA required")
        if len({args.sha, args.failed_sha, args.production_sha}) != 3:
            raise RecoveryError("distinct recovery, failed and previous SHA required")
        if args.evidence_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", args.evidence_sha256) is None:
            raise RecoveryError("exact inspection digest required")
        source, bootstrap, server = _context(args.sha)
        raw = sys.stdin.buffer.read(257)
        if re.fullmatch(rb"[A-Za-z0-9._:-]{1,255}\n", raw) is None:
            raise RecoveryError("exact original lease token required")
        token = raw[:-1].decode("ascii")
        lock = STATE / "launcher.lock"
        bootstrap.secure(lock, private=True)
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        build_fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            build_fd = bootstrap._acquire_existing_build_lock(args.failed_sha)
            bootstrap._assert_original_lock(lock, fd)
            bootstrap._recovery_process_proof()
            proof_module = _load(source / "scripts/contained_recovery_proof.py", "contained_proof")
            underlying = proof_module.RecoveryProof(source, bootstrap, server, args.failed_sha, args.production_sha, token)
            class LockedProof:
                failed_sha = args.failed_sha
                production_sha = args.production_sha

                def check(self):
                    bootstrap._assert_original_lock(lock, fd)
                    _check_original_build_lock(bootstrap, args.failed_sha, build_fd)

                def invoke(self, name):
                    self.check()
                    result = getattr(underlying, name)()
                    self.check()
                    return result

                def snapshot(self):
                    return self.invoke("snapshot")

                def stopped(self):
                    return self.invoke("stopped")

                def running_snapshot(self):
                    return self.invoke("running_snapshot")

            proof = LockedProof()
            if args.retire_restored:
                module_path = source / "scripts/contained_release_retirement.py"
                bootstrap.secure(module_path)
                closure = _load(module_path, "contained_closure")
                adapter = closure.ClosureAdapter(underlying, bootstrap, sys.modules[__name__], args.sha, proof.check)
                result = closure.close_transaction(adapter, args.evidence_sha256)
                print(json.dumps(result, sort_keys=True))
                return 0
            audit_parent = STATE / "contained-service-recoveries"
            if os.path.lexists(audit_parent):
                bootstrap.secure(audit_parent)
                if audit_parent.stat().st_mode & 0o777 != 0o700:
                    raise RecoveryError("unsafe recovery audit directory")
            elif args.evidence_sha256 is not None:
                audit_parent.mkdir(mode=0o700)
                _sync(STATE)
            result = recover_services(proof, audit_parent / args.failed_sha, args.sha, args.evidence_sha256)
            bootstrap._assert_original_lock(lock, fd)
            print(json.dumps(result, sort_keys=True))
        finally:
            if build_fd is not None:
                os.close(build_fd)
            os.close(fd)
        return 0
    except BaseException:
        print("contained recovery: blocked; preserve original release, lease and recovery evidence", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
