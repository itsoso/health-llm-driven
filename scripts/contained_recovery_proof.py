"""Read-only proofs for the independently governed pre-checkout recovery.

No CLI, service mutation, cleanup or deployment authorization lives here.
The caller holds original launcher/build locks and owns durable recovery intent.
"""
import hashlib
import grp
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys


class ProofError(RuntimeError):
    """Static, secret-free proof failure."""


UNITS = ("health-backend.socket", "health-backend.service", "celery-worker.service", "celery-beat.service")
ACTIVATION = b"[Service]\nEnvironmentFile=-/var/lib/reva-health-evidence-runtime/enabled.env\n"
ARTIFACTS = {name: "backend/scripts/" + name for name in (
    "backup_db.sh", "verify_backup_restore.sh", "archive_backup_offsite.sh", "rollback_release.sh",
    "activate_health_evidence_runtime.sh", "verify_locked_requirements.py",
    "verify_runtime_schema_compatibility.py", "quarantine_runtime_only_kb.py", "runtime_state_release_transaction.py")}
ARTIFACTS.update({"review_manifest.json": "backend/data/system_kb_v2_seed/review_manifest.json"})
ARTIFACTS.update({name: "infra/systemd/dropins/" + name for name in (
    "health-backend-runtime-state.conf", "celery-worker-runtime-state.conf", "celery-beat-runtime-state.conf")})


def object_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ProofError("duplicate evidence field")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError):
        raise ProofError("invalid evidence JSON") from None
    if not isinstance(value, dict):
        raise ProofError("evidence must be an object")
    return value


def require_false(raw):
    lines = raw.splitlines()
    assignments = [line for line in lines if re.match(rb"\s*(?:export\s+)?HEALTH_EVIDENCE_RUNTIME_ENABLED\s*=", line, re.I)]
    if assignments != [b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false"]:
        raise ProofError("runtime flag must be uniquely false")


def normalized_base(raw, overridden):
    section = None
    result = []
    for line in raw.splitlines(keepends=True):
        stripped = line.strip()
        if not stripped or stripped.startswith((b"#", b";")):
            continue
        if line.rstrip().endswith(b"\\"):
            raise ProofError("continued unit configuration unsupported")
        if stripped.startswith(b"["):
            section = stripped
        key = stripped.split(b"=", 1)[0].decode("ascii") if b"=" in stripped else ""
        if section == b"[Service]" and key in overridden:
            continue
        result.append(line)
    return b"".join(result)


class RecoveryProof:
    def __init__(self, source, bootstrap, server, failed_sha, production_sha, lease_token):
        if any(re.fullmatch(r"[0-9a-f]{40}", value) is None for value in (failed_sha, production_sha)) or failed_sha == production_sha:
            raise ProofError("distinct exact revisions required")
        if not isinstance(lease_token, str) or re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", lease_token) is None:
            raise ProofError("exact original lease token required")
        self.source, self.bootstrap, self.server = Path(source), bootstrap, server
        self.failed_sha, self.production_sha, self.token = failed_sha, production_sha, lease_token
        self.lease = bootstrap.BUSINESS_LEASE
        self.production = Path("/opt/health-app")
        self.systemd_root = Path("/etc/systemd/system")
        self.proc = Path("/proc")
        self.cgroup = Path("/sys/fs/cgroup")
        self.runtime_root = Path("/var/lib/health-app/release-state")
        self.stage = None
        self.runtime = self._module("backend/scripts/runtime_state_release_transaction.py", "contained_runtime_proof")
        self.reset = self._module("scripts/trusted_review_reset.py", "contained_revision_proof")
        self.systemd = self.runtime.SubprocessSystemd()

    def _module(self, relative, name):
        path = self.source / relative
        self.bootstrap.secure(path)
        if os.path.lexists(path.parent / "__pycache__"):
            raise ProofError("cached recovery code forbidden")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def _secure_evidence(self, path):
        # Only the original lease and its exact sealed stage may cross these
        # two OS-owned shared parents. Never relax canonical code path trust.
        stage = getattr(self, "stage", None)
        lease = getattr(self, "lease", None)
        is_stage = (stage is not None and re.fullmatch(r"/tmp/health-app-backup-preflight-[A-Za-z0-9._-]+", str(stage))
                    and (path == stage or path.parent == stage))
        is_lease = lease == Path("/var/lock/health-app-release") and (path == lease or path.parent == lease)
        if not (is_stage or is_lease):
            self.bootstrap.secure(path)
            return
        entries = [*reversed(path.parents), path]
        if is_lease:
            entries += [Path("/run"), Path("/run/lock")]
        for item in entries:
            info = item.lstat()
            if item == Path("/var/lock") and is_lease:
                if (not stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                        or info.st_nlink != 1 or os.readlink(item) != "/run/lock"):
                    raise ProofError("fixed lock alias differs")
                continue
            shared = item == Path("/tmp") and is_stage or item == Path("/run/lock") and is_lease
            if shared:
                if (not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_gid != 0
                        or stat.S_IMODE(info.st_mode) != 0o1777):
                    raise ProofError("shared parent ownership or sticky mode differs")
                continue
            is_file = stat.S_ISREG(info.st_mode)
            if (info.st_uid != 0 or info.st_mode & 0o022
                    or not (is_file or stat.S_ISDIR(info.st_mode))
                    or (item != path and not stat.S_ISDIR(info.st_mode))
                    or (is_file and info.st_nlink != 1)):
                raise ProofError("unsafe recovery evidence path")

    def _file(self, path, mode=None):
        self._secure_evidence(path)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16_000_000 or (mode is not None and stat.S_IMODE(info.st_mode) != mode):
            raise ProofError("file evidence metadata invalid")
        with path.open("rb") as stream:
            raw = stream.read(16_000_001)
        if len(raw) > 16_000_000:
            raise ProofError("file evidence bound exceeded")
        after = path.lstat()
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_mode, info.st_uid, info.st_gid, info.st_nlink) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode, after.st_uid, after.st_gid, after.st_nlink):
            raise ProofError("file evidence changed")
        identity = {"dev": info.st_dev, "ino": info.st_ino, "mode": stat.S_IMODE(info.st_mode),
                    "uid": info.st_uid, "gid": info.st_gid, "sha256": hashlib.sha256(raw).hexdigest()}
        return raw, identity

    def _directory(self, path, mode=0o700):
        self._secure_evidence(path)
        info = path.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != mode or info.st_gid != 0:
            raise ProofError("directory evidence metadata invalid")
        return {"dev": info.st_dev, "ino": info.st_ino, "uid": info.st_uid, "gid": info.st_gid, "mode": mode}

    def _absent(self, *paths):
        for path in paths:
            for parent in reversed(path.parents):
                if os.path.lexists(parent):
                    self.bootstrap.secure(parent)
        if any(os.path.lexists(path) for path in paths):
            raise ProofError("conflicting transaction or authorization exists")

    def _lease_snapshot(self):
        result = {"lease": self._directory(self.lease)}
        if {path.name for path in self.lease.iterdir()} != {"token", "label", "stage", "started_at"}:
            raise ProofError("original lease inventory differs")
        contents = {}
        for name in ("token", "label", "stage", "started_at"):
            contents[name], result[name] = self._file(self.lease / name, 0o600)
        if contents["token"] != (self.token + "\n").encode() or contents["label"] != b"deploy:backend\n" or re.fullmatch(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\n", contents["started_at"]) is None:
            raise ProofError("original lease ownership differs")
        return result

    def _assert_original_lease(self):
        if self._lease_snapshot() != self._original_lease:
            raise ProofError("original lease replaced during recovery")

    def _workspace(self, failed_source):
        workspace = self.bootstrap.STATE / self.failed_sha
        result = {"directory": self._directory(workspace)}
        allowed = {"started.json", "completed.json", "build.lock", "source", "home", "bin", "deployment.env",
                   "preparation.log", "deployment.log", "preparation-started.json", "prepared.json", "deployment-started.json", "clone-attempts"}
        if not {p.name for p in workspace.iterdir()} <= allowed:
            raise ProofError("unknown or native/review workspace evidence")
        executor, _ = self._file(failed_source / "scripts/trusted_release_server.py")
        digest = hashlib.sha256(executor).hexdigest()
        for name, state in (("started.json", "STARTED"), ("completed.json", "NEEDS_OPERATOR"),
                            ("preparation-started.json", "PREPARING"), ("prepared.json", "PREPARED"), ("deployment-started.json", "DEPLOYING")):
            raw, result[name] = self._file(workspace / name, 0o600)
            expected = {"sha": self.failed_sha, "state": state}
            if state == "PREPARING":
                expected["executor_sha256"] = digest
            if object_json(raw) != expected:
                raise ProofError("failed release marker chain differs")
        raw, result["policy"] = self._file(self.bootstrap.CONFIG / "authorized-release.json", 0o600)
        policy = object_json(raw)
        if set(policy) != {"sha", "expires_at", "executor_sha256"} or policy["sha"] != self.failed_sha or type(policy["expires_at"]) is not int or policy["executor_sha256"] != digest:
            raise ProofError("installed release policy differs")
        installed, result["executor"] = self._file(self.bootstrap.INSTALLED, 0o600)
        if installed != executor:
            raise ProofError("installed executor differs")
        for name in ("deployment.log", "preparation.log"):
            _, result[name] = self._file(workspace / name, 0o600)
        result["inventory"] = sorted(p.name for p in workspace.iterdir())
        return result

    def _stage(self, failed_source):
        result = self._lease_snapshot()
        if not hasattr(self, "_original_lease"):
            self._original_lease = result.copy()
        self._assert_original_lease()
        token, result["token"] = self._file(self.lease / "token", 0o600)
        pointer, result["pointer"] = self._file(self.lease / "stage", 0o600)
        if token != (self.token + "\n").encode() or re.fullmatch(rb"/tmp/health-app-backup-preflight-[A-Za-z0-9._-]+\n", pointer) is None:
            raise ProofError("original lease binding differs")
        self.stage = Path(pointer.decode().rstrip("\n"))
        result["directory"] = self._directory(self.stage)
        expected_names = set(ARTIFACTS) | {"staged.sha256", "backend.env.rollback", "backend.env.candidate"}
        if {p.name for p in self.stage.iterdir()} != expected_names:
            raise ProofError("sealed stage inventory differs")
        manifest, result["manifest"] = self._file(self.stage / "staged.sha256", 0o400)
        hashes = {}
        for line in manifest.splitlines():
            match = re.fullmatch(rb"([0-9a-f]{64})  ([A-Za-z0-9._-]+)", line)
            if not match or match[2].decode() in hashes:
                raise ProofError("sealed manifest invalid")
            hashes[match[2].decode()] = match[1].decode()
        if set(hashes) != expected_names - {"staged.sha256"}:
            raise ProofError("sealed manifest inventory differs")
        snapshots = {}
        for name in sorted(hashes):
            raw, identity = self._file(self.stage / name, 0o400 if name.startswith("backend.env.") else None)
            if identity["gid"] != 0:
                raise ProofError("sealed artifact group differs")
            if identity["sha256"] != hashes[name]:
                raise ProofError("sealed artifact changed")
            if name in ARTIFACTS and raw != self._file(failed_source / ARTIFACTS[name])[0]:
                raise ProofError("stage artifact differs from failed canonical source")
            result[name] = identity
            if name.startswith("backend.env."):
                snapshots[name] = raw
        live, result["live_env"] = self._file(self.production / "backend/.env", 0o640)
        if result["live_env"]["gid"] != grp.getgrnam("health-app").gr_gid:
            raise ProofError("live environment group differs")
        if any(live != raw for raw in snapshots.values()):
            raise ProofError("live environment is not unchanged")
        require_false(live)
        return result

    def _units(self, old_source, transaction):
        result = {}
        for unit in UNITS:
            base, base_identity = self._file(self.systemd_root / unit, 0o644)
            old, _ = self._file(old_source / "infra/systemd" / unit)
            overrides = {"ReadWritePaths"} if unit.endswith(".service") else set()
            if unit in {"health-backend.service", "celery-beat.service"}:
                overrides.add("ExecStart")
            if unit == "celery-beat.service":
                overrides |= {"StateDirectory", "StateDirectoryMode"}
            if normalized_base(base, overrides) != normalized_base(old, overrides):
                raise ProofError("base unit differs outside overridden fields")
            if self.systemd.show(unit, "NeedDaemonReload") != "no" or self.systemd.is_enabled(unit) != "enabled":
                raise ProofError("unit reload or enablement differs")
            if self.systemd.show(unit, "FragmentPath") != str(self.systemd_root / unit):
                raise ProofError("unit fragment differs")
            entry = {"base": base_identity}
            paths = []
            if unit.endswith(".service"):
                for name, expected in (("80-reva-health-evidence-runtime.conf", ACTIVATION), ("90-runtime-state.conf", self.runtime._expected_candidate(unit))):
                    path = self.systemd_root / (unit + ".d") / name
                    raw, entry[name] = self._file(path, 0o644)
                    if raw != expected:
                        raise ProofError("effective drop-in bytes differ")
                    paths.append(str(path))
            if self.systemd.show(unit, "DropInPaths").split() != paths:
                raise ProofError("effective drop-in inventory differs")
            result[unit] = entry
        effective = transaction._old_effective()
        worker = "celery-worker.service"
        old_base = self._file(old_source / "infra/systemd" / worker)[0]
        commands = re.findall(rb"^ExecStart=(.+)$", old_base, re.M)
        if len(commands) != 1:
            raise ProofError("canonical worker command ambiguous")
        command = commands[0].decode()
        expected = f"path={command.split()[0]}\nargv[]={command}\nignore_errors=no"
        if transaction._stable_exec_start(effective[worker]["ExecStart"]) != expected:
            raise ProofError("effective worker command differs")
        transaction._validate_candidate_effective({"old_effective": effective})
        result["effective"] = transaction._stable_effective_snapshot(effective)
        return result

    def snapshot(self):
        failed_source = self.bootstrap.canonical_source(self.failed_sha)
        old_source = self.bootstrap.canonical_source(self.production_sha)
        self.reset._revision_proof(self.production_sha, self.source, self.bootstrap)
        result = {"workspace": self._workspace(failed_source), "stage": self._stage(failed_source)}
        layout = self.runtime.production_layout(self.stage)
        transaction = self.runtime.ReleaseTransaction(layout, self.systemd)
        transaction._assert_release_lock(self.lease, self.token)
        self._absent(layout.transaction_root, transaction._preparing_root())
        marker = transaction._load_terminal_marker()
        if marker["phase"] != "COMMITTED" or marker["terminal_sha"] != self.production_sha:
            raise ProofError("prior terminal does not prove current production")
        if list(self.runtime_root.glob("runtime-state-transaction.reap-*")):
            raise ProofError("terminal cleanup remains pending")
        self._absent(Path("/var/lib/reva-health-evidence-runtime/enabled.env"), Path("/run/reva-health-evidence-activation"), self.production / "backend/.env.reva-release.tmp")
        for unit in UNITS[1:]:
            self._absent(Path("/run/systemd/system") / (unit + ".d") / "90-reva-health-evidence-activation.conf")
        _, result["terminal"] = self._file(transaction._terminal_marker_path())
        result["units"] = self._units(old_source, transaction)
        return result

    def _pids(self, unit):
        group = self.systemd.show(unit, "ControlGroup")
        if not group:
            return []
        if re.fullmatch(r"/[A-Za-z0-9_.@:/\\-]+", group) is None or any(part in {".", ".."} for part in group.split("/")):
            raise ProofError("unsafe service cgroup")
        raw = (self.cgroup / group.lstrip("/") / "cgroup.procs").read_text()
        pids = raw.splitlines()
        if len(pids) > 10000 or len(pids) != len(set(pids)) or any(not pid.isdigit() or int(pid) <= 1 for pid in pids):
            raise ProofError("invalid service process inventory")
        return pids

    def stopped(self):
        self._assert_original_lease()
        self._no_jobs()
        for unit in UNITS:
            if self.systemd.show(unit, "ActiveState") != "inactive" or (unit.endswith(".service") and self.systemd.show(unit, "MainPID") != "0") or self._pids(unit):
                raise ProofError("service containment unproven")
        self._no_jobs()
        self._assert_original_lease()

    def _no_jobs(self):
        completed = subprocess.run(["/usr/bin/systemctl", "list-jobs", "--no-legend", "--plain", "--no-pager"],
                                   env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"}, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=15)
        if len(completed.stdout) > 1_000_000:
            raise ProofError("systemd jobs bound exceeded")
        for line in completed.stdout.splitlines():
            fields = line.split()
            if len(fields) != 4 or not fields[0].isdigit():
                raise ProofError("systemd job inventory malformed")
            if fields[1].decode() in UNITS:
                raise ProofError("service systemd job remains pending")

    def running_snapshot(self):
        self._assert_original_lease()
        result = self.running_services_snapshot()
        self._assert_original_lease()
        return result

    def running_services_snapshot(self):
        """Read-only readiness; callers separately prove their lease authority."""
        self._no_jobs()
        result = {}
        for unit in UNITS:
            fields = {name: self.systemd.show(unit, name) for name in ("ActiveState", "SubState", "MainPID", "NRestarts", "ActiveEnterTimestampMonotonic", "ControlGroup", "Result")}
            if fields["ActiveState"] != "active" or fields["SubState"] not in ({"listening", "running"} if unit.endswith(".socket") else {"running"}):
                raise ProofError("service readiness unproven")
            if fields["Result"] != "success":
                raise ProofError("service result unsuccessful")
            if not fields["ActiveEnterTimestampMonotonic"].isdigit() or int(fields["ActiveEnterTimestampMonotonic"]) <= 0:
                raise ProofError("service activation identity unavailable")
            if unit.endswith(".service"):
                if self.systemd.show(unit, "RestartUSec") != "5s":
                    raise ProofError("service restart window differs")
                pids = self._pids(unit)
                if fields["MainPID"] not in pids or not fields["NRestarts"].isdigit():
                    raise ProofError("main process identity unavailable")
                identities = {}
                for pid in pids:
                    process = self.proc / pid
                    before = (process / "stat").read_bytes().rsplit(b")", 1)[-1].split()
                    with (process / "environ").open("rb") as stream:
                        environment = stream.read(1_000_001)
                    if len(environment) > 1_000_000:
                        raise ProofError("process environment bound exceeded")
                    assignments = [item for item in environment.split(b"\0") if item.startswith(b"HEALTH_EVIDENCE_RUNTIME_ENABLED=")]
                    if assignments != [b"HEALTH_EVIDENCE_RUNTIME_ENABLED=false"]:
                        raise ProofError("process runtime flag differs")
                    after = (process / "stat").read_bytes().rsplit(b")", 1)[-1].split()
                    if len(before) < 20 or len(after) < 20 or before[19] != after[19]:
                        raise ProofError("process identity changed")
                    identities[pid] = before[19].decode()
                if pids != self._pids(unit):
                    raise ProofError("service process inventory changed")
                fields["processes"] = identities
            result[unit] = fields
        self._no_jobs()
        return result
