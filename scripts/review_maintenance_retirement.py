"""Explicitly accepted UNKNOWN review maintenance: isolated administrative closure.

Not a reset, deployment, successful recovery, or proof of historical no-write.
Only the canonical root operator can execute; original receipts never change.
"""
import argparse
import contextlib
import fcntl
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys

STATE = Path("/var/lib/reva-release")
ENV = {"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C"}
TERMINAL = "CLOSED_UNKNOWN_REVIEW_MAINTENANCE"
DIRECT_TABLES = (
    "user_profiles", "garmin_data", "weight_records", "water_intakes",
    "blood_pressure_records", "sleep_records", "workout_records",
    "workout_analysis_results", "medical_exams", "daily_operating_plans",
    "intervention_events", "agent_conversations", "health_problems", "health_programs",
)
CHILD_TABLES = {
    "medical_exam_items": ("exam_id", "medical_exams"),
    "workout_hr_zones": ("workout_id", "workout_records"),
    "agent_messages": ("conversation_id", "agent_conversations"),
}
CANONICAL_FILES = {"deploy.sh", "scripts/bootstrap_trusted_release.py", "scripts/trusted_release_server.py",
                   "scripts/trusted_review_reset.py", "backend/scripts/seed_demo_account.py"}


class ClosureError(Exception):
    """Static diagnostics only."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_bytes(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def write_json(path, value):
    write_bytes(path, json.dumps(value, sort_keys=True).encode())


def close_transaction(adapter, *, accept_unknown=False, evidence_sha256=None):
    if accept_unknown is not True:
        raise ClosureError("explicit unknown review write acceptance required")
    if os.path.lexists(adapter.record):
        raise ClosureError("closure already attempted; retry forbidden")
    evidence = adapter.inspect()
    fingerprint = digest(evidence)
    if evidence_sha256 is None:
        return {"state": "INSPECTED_UNKNOWN_REVIEW_MAINTENANCE", "evidence_sha256": fingerprint}
    if fingerprint != evidence_sha256:
        raise ClosureError("inspection evidence changed")
    if not adapter.record.parent.exists():
        adapter.record.parent.mkdir(mode=0o700)
        sync(adapter.record.parent.parent)
    adapter.record.mkdir(mode=0o700)
    sync(adapter.record.parent)
    receipt = secrets.token_hex(32)
    intent = {**evidence, "accept_unknown_review_writes": True, "evidence_sha256": fingerprint,
              "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest()}
    write_json(adapter.record / "intent.json", intent)
    if adapter.inspect() != evidence:
        raise ClosureError("evidence changed after durable intent")
    isolation = adapter.isolate(evidence)
    write_json(adapter.record / "isolation.json", isolation)
    account = adapter.inspect_account()
    write_json(adapter.record / "account.json", account)
    adapter.archive(evidence)
    closed = adapter.verify_closed(evidence, isolation, account)
    write_json(adapter.record / "completed.json", {
        "state": TERMINAL, "old_sha": evidence["old_sha"], "original_outcome": "UNKNOWN",
        "intent_sha256": digest(intent), "isolation_sha256": digest(isolation),
        "account_sha256": digest(account), **closed,
    })
    return {"state": TERMINAL, "sha": evidence["old_sha"], "receipt": receipt}


def inspect_account_rows(connection, email, key, database):
    """Hard read-only, fixed scoped queries; keyed row fingerprints, no raw output."""
    from sqlalchemy import bindparam, column, func, literal_column, select, table
    if connection.dialect.name != "postgresql" or not isinstance(key, bytes) or len(key) != 32 or not database:
        raise ClosureError("PostgreSQL and private fingerprint key required")
    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
    connection.exec_driver_sql("SET LOCAL statement_timeout = '5000ms'")
    if (connection.exec_driver_sql("SHOW transaction_read_only").scalar_one() != "on"
            or connection.exec_driver_sql("SHOW transaction_isolation").scalar_one() != "repeatable read"
            or connection.exec_driver_sql("SELECT current_database()").scalar_one() != database):
        raise ClosureError("database snapshot is not strictly read only")
    fields = ("id", "email", "name", "birth_date", "gender", "onboarding_completed", "is_active", "is_approved", "is_admin")
    users = table("users", *(column(k) for k in fields))
    rows = connection.execute(select(*(users.c[k] for k in fields if k != "email"))
        .where(users.c.email == bindparam("email")).limit(2), {"email": email}).mappings().all()
    if (len(rows) != 1 or type(rows[0]["id"]) is not int or rows[0]["id"] < 1
            or rows[0]["is_active"] is not True or rows[0]["is_approved"] is not True
            or rows[0]["is_admin"] is not False):
        raise ClosureError("unique active non-admin review account required")
    user_id = rows[0]["id"]
    key_digest = hmac.new(key, json.dumps([email, dict(rows[0])], sort_keys=True, default=str).encode(), hashlib.sha256).hexdigest()
    tables, total = {}, 0
    for name in (*DIRECT_TABLES, *CHILD_TABLES):
        columns = [column("id"), column("user_id")]
        if name in CHILD_TABLES:
            columns.append(column(CHILD_TABLES[name][0]))
        target = table(name, *columns)
        owner = target.c.user_id == bindparam("user_id")
        if name in CHILD_TABLES:
            fk, parent_name = CHILD_TABLES[name]
            parent = table(parent_name, column("id"), column("user_id"))
            owner = target.c[fk].in_(select(parent.c.id).where(parent.c.user_id == bindparam("user_id")))
        query = select(func.to_jsonb(literal_column(name)).label("row")).select_from(target).where(owner).order_by(target.c.id).limit(10001)
        fingerprints = []
        for row in connection.execute(query, {"user_id": user_id}):
            raw = json.dumps(row[0], sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
            total += len(raw)
            if total > 16_000_000 or len(fingerprints) >= 10000:
                raise ClosureError("account snapshot exceeds bound")
            fingerprints.append(hmac.new(key, name.encode() + b"\0" + raw, hashlib.sha256).hexdigest())
        tables[name] = {"count": len(fingerprints), "rows_hmac_sha256": hmac.new(key, json.dumps(fingerprints).encode(), hashlib.sha256).hexdigest()}
    if tables["user_profiles"]["count"] != 1:
        raise ClosureError("review profile identity unavailable")
    return {"verification": "CURRENT_ACCOUNT_ONLY_NOT_RESET", "account_hmac_sha256": key_digest, "tables": tables}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def context(sha, *, verify_ci=True):
    if (not isinstance(sha, str) or re.fullmatch(r"[a-f0-9]{40}", sha) is None
            or not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
            or os.geteuid() != 0 or sys.executable != "/usr/bin/python3.12"
            or "SSH_ORIGINAL_COMMAND" in os.environ):
        raise ClosureError("isolated canonical root operator required")
    source = STATE / "bootstrap" / sha / "source"
    entry = source / "scripts/review_maintenance_retirement.py"
    if Path(__file__).absolute() != entry:
        raise ClosureError("canonical closing entry required")
    for path in [*reversed(entry.parents), entry, entry.with_name("bootstrap_trusted_release.py")]:
        info = path.lstat()
        file = path in (entry, entry.with_name("bootstrap_trusted_release.py"))
        if (info.st_uid != 0 or info.st_mode & 0o022
                or not (stat.S_ISREG(info.st_mode) if file else stat.S_ISDIR(info.st_mode))
                or (file and info.st_nlink != 1)):
            raise ClosureError("canonical closing metadata invalid")
    os.umask(0o077)
    b = load(entry.with_name("bootstrap_trusted_release.py"), "review_closing_bootstrap")
    reviewed, server = b.reviewed_source(sha)
    if source != reviewed:
        raise ClosureError("canonical source mismatch")
    if verify_ci:
        subprocess.run(["/usr/bin/python3.12", "-I", "-S", "-B", str(source / "scripts/trusted_release_gate.py"),
                        "--sha", sha, "--workflow-sha", sha], env=ENV, check=True, timeout=90,
                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return source, b, server


def assert_no_other_ssh_sessions(proc=Path("/proc")):
    """Fail, never kill unrelated sessions. Current operator ancestors alone are allowed."""
    ancestors, pid = set(), os.getpid()
    while pid > 1:
        if pid in ancestors or len(ancestors) > 64:
            raise ClosureError("operator ancestry uncertain")
        ancestors.add(pid)
        fields = (proc / str(pid) / "stat").read_bytes().rsplit(b")", 1)[-1].split()
        pid = int(fields[1])
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) in ancestors:
            continue
        try:
            argv = (entry / "cmdline").read_bytes()
        except FileNotFoundError:
            raise ClosureError("session inventory changed") from None
        if argv.startswith((b"sshd:", b"sshd-session:")):
            raise ClosureError("other SSH session must finish before closure")


def account_child(sha, old_sha, record):
    source, b, server = context(sha, verify_ci=False)
    expected = STATE / "review-maintenance-closures" / old_sha
    if record != expected:
        raise ClosureError("fixed account audit directory required")
    intent = b._read_json(record / "intent.json")
    isolation = b._read_json(record / "isolation.json")
    if (intent.get("old_sha") != old_sha or intent.get("closing_sha") != sha
            or intent.get("accept_unknown_review_writes") is not True
            or isolation.get("state") != "OLD_IDENTITIES_REVOKED_EXECUTION_QUIESCENT"
            or b._installation_evidence(old_sha, b.CONFIG, b.INSTALLED.parent) != isolation.get("installation")):
        raise ClosureError("isolated account probe authorization invalid")
    b.secure(record / "account-hmac.key", private=True)
    reset = load(source / "scripts/trusted_review_reset.py", "review_closing_reset")
    reset._assert_isolated_search_path()
    reset._validate_production(old_sha, source, b, server)
    site = Path("/opt/health-app/backend/venv/lib/python3.12/site-packages")
    sys.path.append(str(site))
    environment = reset._parse_maintenance_environment(server.read_production_env())
    os.environ.clear()
    os.environ.update(environment)
    os.chdir(source / "backend")
    sys.path.insert(0, str(source / "backend"))
    with contextlib.redirect_stdout(reset._BoundedSummary()), contextlib.redirect_stderr(reset._BoundedSummary()):
        reset._validate_effective_target(source, environment)
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        url = make_url(environment["DATABASE_URL"])
        if not url.database:
            raise ClosureError("explicit production database name required")
        engine = create_engine(url, isolation_level="REPEATABLE READ", connect_args={"connect_timeout": 5})
        try:
            with engine.connect() as connection, connection.begin():
                result = inspect_account_rows(connection, environment["APP_STORE_REVIEW_DEMO_ACCOUNT"], (record / "account-hmac.key").read_bytes(), url.database)
        finally:
            engine.dispose()
    return result


def original_workspace(b, old_sha, operation_id):
    """Original receipts remain immutable; accepting risk never edits their state."""
    root = b.STATE / old_sha
    b.secure(root)
    allowed_dirs = {"source", "home", "bin", "review-resets", "clone-attempts"}
    allowed_files = {"started.json", "completed.json", "build-started.json", "native-started.json",
                     "build.lock", "deployment.env", "preparation.log", "deployment.log",
                     "preparation-started.json", "prepared.json", "deployment-started.json"}
    names = {p.name for p in root.iterdir()}
    if not names <= allowed_dirs | allowed_files or not {"started.json", "completed.json", "review-resets"} <= names:
        raise ClosureError("unexpected original workspace inventory")
    phases = {"preparation-started.json", "prepared.json", "deployment-started.json"}
    if names & phases and not phases <= names:
        raise ClosureError("incomplete original release phases")
    result = {}
    for p in [root, *(root / n for n in sorted(names))]:
        directory = p == root or p.name in allowed_dirs
        b.secure(p, private=not directory)
        info = p.lstat()
        if directory and (not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700):
            raise ClosureError("private original directory required")
        if not directory and info.st_size > 16_000_000:
            raise ClosureError("original evidence file exceeds bound")
        result[p.name if p != root else "."] = {
            "device": info.st_dev, "inode": info.st_ino, "mode": stat.S_IMODE(info.st_mode),
            "uid": info.st_uid, "gid": info.st_gid,
            "sha256": None if directory else hashlib.sha256(p.read_bytes()).hexdigest(),
        }
    states = {"started.json": "STARTED", "completed.json": "SUCCEEDED", "build-started.json": "STARTED",
              "native-started.json": "STARTED", "preparation-started.json": "PREPARING", "prepared.json": "PREPARED", "deployment-started.json": "DEPLOYING"}
    for name in names & states.keys():
        expected = {"sha": old_sha, "state": states[name]}
        if name == "preparation-started.json":
            expected["executor_sha256"] = hashlib.sha256((b.canonical_source(old_sha) / "scripts/trusted_release_server.py").read_bytes()).hexdigest()
        if b._read_json(root / name) != expected:
            raise ClosureError("successful backend release required")
    reset_root = root / "review-resets"
    operations = list(reset_root.iterdir())
    if not 1 <= len(operations) <= 1000:
        raise ClosureError("review operation inventory exceeds bound")
    result["operations"] = {}
    found = False
    for operation in operations:
        if re.fullmatch(r"[0-9a-f]{32}", operation.name) is None:
            raise ClosureError("invalid original operation")
        result["operations"][operation.name] = b._inventory(operation, {"started.json", "completed.json"})
        expected = "NEEDS_OPERATOR" if operation.name == operation_id else "SUCCEEDED"
        found |= operation.name == operation_id
        for name, state in (("started.json", "STARTED"), ("completed.json", expected)):
            if b._read_json(operation / name) != {"sha": old_sha, "operation_id": operation.name, "state": state}:
                raise ClosureError("unaccepted or incomplete review operation")
    if not found:
        raise ClosureError("accepted unknown operation missing")
    return result


class Adapter:
    def __init__(self, source, b, server, sha, old_sha, operation_id, token, check_locks):
        self.source, self.b, self.server = source, b, server
        self.sha, self.old_sha, self.operation_id = sha, old_sha, operation_id
        self.token, self.check = token, check_locks
        self.record = b.STATE / "review-maintenance-closures" / old_sha
        self.volatile = Path("/run/lock/health-app-release.review-retired-" + old_sha)
        for filename in ("contained_release_retirement.py", "contained_recovery_proof.py",
                         "recover_contained_services.py", "trusted_review_reset.py"):
            b.secure(source / "scripts" / filename)
        self.c = load(source / "scripts/contained_release_retirement.py", "review_archive_helpers")
        self.r = load(source / "scripts/recover_contained_services.py", "review_health_helpers")
        self.reset = load(source / "scripts/trusted_review_reset.py", "review_snapshot_helpers")
        proof = load(source / "scripts/contained_recovery_proof.py", "review_service_helpers")
        # Reuse ONLY fixed OS file/service readers, not backend-failure recovery.
        self.p = proof.RecoveryProof(source, b, server, sha, old_sha, token)

    def _quiescent(self):
        self.check()
        self.b._recovery_process_proof()
        assert_no_other_ssh_sessions()
        self.b._recovery_process_proof()
        self.check()

    def _lease(self):
        p = self.p
        result = {"directory": p._directory(p.lease)}
        if {v.name for v in p.lease.iterdir()} != {"token", "label", "stage", "started_at"}:
            raise ClosureError("unexpected maintenance lease inventory")
        raw = {}
        for name in ("token", "label", "stage", "started_at"):
            raw[name], result[name] = p._file(p.lease / name, 0o600)
        if (raw["token"] != (self.token + "\n").encode() or raw["label"] != b"deploy:app-store-review-reset\n"
                or re.fullmatch(rb"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\n", raw["started_at"]) is None
                or re.fullmatch(rb"/tmp/health-app-backup-preflight-[1-9][0-9]*-[1-9][0-9]*\n", raw["stage"]) is None):
            raise ClosureError("original maintenance lease binding differs")
        # -R does not create a backup stage. A populated/linked stage means a
        # different transaction may be involved; never adopt or clean it here.
        if os.path.lexists(Path(raw["stage"].decode().strip())):
            raise ClosureError("unexpected maintenance stage exists")
        return result

    def _services(self):
        reader = type("Reader", (), {"running_snapshot": lambda _: self.p.running_services_snapshot()})()
        return self.r._wait_ready(reader)

    def _base(self):
        b = self.b
        self.check()
        old_source = b.canonical_source(self.old_sha)
        self.reset._revision_proof(self.old_sha, self.source, b)
        original = original_workspace(b, self.old_sha, self.operation_id)
        code = {}
        for name in sorted(CANONICAL_FILES):
            code[name] = self.c._file(b, old_source / name)[1]
        return {"workspace": original, "canonical": code,
                "locks": {"launcher": b._recovery_file_identity(b.STATE / "launcher.lock"),
                          "build": b._recovery_file_identity(b.STATE / self.old_sha / "build.lock")
                          if os.path.lexists(b.STATE / self.old_sha / "build.lock") else None}}

    def inspect(self):
        b = self.b
        self._quiescent()
        if self.record.parent.exists():
            self.c._private_directory(b, self.record.parent)
        if os.path.lexists(self.volatile):
            raise ClosureError("maintenance lease already archived")
        history = b._retired_history()
        b._assert_known_activity(history, self.old_sha)
        if self.old_sha in history or any(os.path.lexists(p) for p in b._archives(self.old_sha)):
            raise ClosureError("release already retired")
        base = self._base()
        config = b._inventory(b.CONFIG, {"known_hosts", "loopback.conf", "authorized-release.json", "cloud.pub", "loopback.pub", "loopback.key"})
        library = b._inventory(b.INSTALLED.parent, {b.INSTALLED.name})
        policy = self.server.validate_policy(b._read_json(b.CONFIG / "authorized-release.json"), now=0)
        expected_digest = base["canonical"]["scripts/trusted_release_server.py"]["sha256"]
        if policy["sha"] != self.old_sha or policy["executor_sha256"] != expected_digest or library[b.INSTALLED.name]["sha256"] != expected_digest:
            raise ClosureError("old installed executor binding differs")
        public = [(b.CONFIG / name).read_text().strip() for name in ("cloud.pub", "loopback.pub")]
        for key in public:
            b.validate_install(self.old_sha, 1, key, now=0)
        if public[0] == public[1]:
            raise ClosureError("old keys must differ")
        expected = b.key_lines(policy["expires_at"], *public)
        b.secure(b.AUTHORIZED, private=True)
        lines = b.AUTHORIZED.read_text().splitlines()
        if any([v for v in lines if key.split()[1] in v] != [line] for key, line in zip(public, expected)):
            raise ClosureError("old key authorization changed")
        self.r._http_probes()
        services = self._services()
        lease = self._lease()
        self._quiescent()
        if self._base() != base:
            raise ClosureError("original evidence changed during inspection")
        return {"old_sha": self.old_sha, "closing_sha": self.sha, "operation_id": self.operation_id,
                "original_outcome": "UNKNOWN", "original": base, "lease": lease, "services": services,
                "config": config, "library": library, "authorized": b._recovery_file_identity(b.AUTHORIZED)}

    def isolate(self, evidence):
        b = self.b
        self._quiescent()
        if self._base() != evidence["original"] or self._lease() != evidence["lease"]:
            raise ClosureError("original evidence changed before revocation")
        if (b._inventory(b.CONFIG, evidence["config"].keys() - {"."}) != evidence["config"]
                or b._recovery_file_identity(b.AUTHORIZED) != evidence["authorized"]):
            raise ClosureError("authorization changed before revocation")
        # /run is volatile. Preserve both lease and original operation bytes
        # durably BEFORE removing any authorization or moving the live lease.
        self._copy_archives(evidence)
        policy = b._read_json(b.CONFIG / "authorized-release.json")
        public = [(b.CONFIG / name).read_text().strip() for name in ("cloud.pub", "loopback.pub")]
        expected = b.key_lines(policy["expires_at"], *public)
        retained = b"".join(line for line in b.AUTHORIZED.read_bytes().splitlines(keepends=True)
                            if line.decode().rstrip("\r\n") not in expected)
        b._replace_authorized(retained)
        if b.AUTHORIZED.read_bytes() != retained:
            raise ClosureError("precise revocation verification failed")
        if b._inventory(b.CONFIG, evidence["config"].keys() - {"."}) != evidence["config"]:
            raise ClosureError("private key identity changed")
        (b.CONFIG / "loopback.key").unlink()
        sync(b.CONFIG)
        installation = b._installation_evidence(self.old_sha, b.CONFIG, b.INSTALLED.parent)
        # Revocation alone does not terminate an authenticated session. Both
        # process and session checks must pass after revocation, before reads.
        self._quiescent()
        write_bytes(self.record / "account-hmac.key", secrets.token_bytes(32))
        return {"state": "OLD_IDENTITIES_REVOKED_EXECUTION_QUIESCENT", "installation": installation,
                "authorized": b._recovery_file_identity(b.AUTHORIZED)}

    def inspect_account(self):
        key = self.record / "account-hmac.key"
        self.b.secure(key, private=True)
        self._quiescent()
        result = subprocess.run(["/usr/bin/python3.12", "-I", "-S", "-B", str(self.source / "scripts/review_maintenance_retirement.py"),
                                 "--sha", self.sha, "--release-sha", self.old_sha, "--account-probe"],
                                env=ENV, check=True, timeout=180, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        if len(result.stdout) > 16384:
            raise ClosureError("account proof output exceeds bound")
        account = json.loads(result.stdout)
        validate_account_summary(account)
        self._quiescent()
        return account

    def _copy_archives(self, evidence):
        for name, expected, source in (
                ("lease", {k: v for k, v in evidence["lease"].items() if k != "directory"}, self.p.lease),
                ("operation", {k: v for k, v in evidence["original"]["workspace"]["operations"][self.operation_id].items() if k != "."}, self.b.STATE / self.old_sha / "review-resets" / self.operation_id)):
            target = self.record / name
            target.mkdir(mode=0o700)
            sync(self.record)
            for filename, identity in expected.items():
                raw, actual = self.p._file(source / filename, 0o600)
                if (any(actual[k] != identity[k] for k in ("uid", "gid", "mode", "sha256"))
                        or actual["dev"] != identity.get("dev", identity.get("device"))
                        or actual["ino"] != identity.get("ino", identity.get("inode"))):
                    raise ClosureError("archive input changed")
                write_bytes(target / filename, raw)
        archive_evidence(self.b, self.record, evidence)

    def archive(self, evidence):
        archive_evidence(self.b, self.record, evidence)
        self._quiescent()
        if self._base() != evidence["original"] or self._lease() != evidence["lease"] or self._services() != evidence["services"]:
            raise ClosureError("evidence changed before lease archival")
        if os.path.lexists(self.volatile) or self.p.lease.lstat().st_dev != self.volatile.parent.lstat().st_dev:
            raise ClosureError("same filesystem unused lease archive required")
        self.b.secure(Path("/usr/bin/mv"))
        self.c._move_no_clobber(self.p.lease, self.volatile)
        sync(self.volatile.parent)
        self.verify_volatile(evidence)

    def verify_volatile(self, evidence):
        info = self.volatile.lstat()
        identity = {"dev": info.st_dev, "ino": info.st_ino, "mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid}
        if (os.path.lexists(self.p.lease) or not stat.S_ISDIR(info.st_mode)
                or identity != evidence["lease"]["directory"]
                or {p.name for p in self.volatile.iterdir()} != {"token", "label", "stage", "started_at"}):
            raise ClosureError("original lease inode not preserved")
        for name in ("token", "label", "stage", "started_at"):
            path = self.volatile / name
            info = path.lstat()
            expected = evidence["lease"][name]
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 4096
                    or info.st_uid != identity["uid"] or info.st_gid != identity["gid"]
                    or stat.S_IMODE(info.st_mode) != 0o600
                    or (info.st_dev, info.st_ino) != (expected["dev"], expected["ino"])
                    or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]):
                raise ClosureError("original archived lease file changed")

    def verify_closed(self, evidence, isolation, account):
        self._quiescent()
        self.verify_volatile(evidence)
        self.b._assert_idle()
        if self._base() != evidence["original"] or self._services() != evidence["services"]:
            raise ClosureError("original state changed during closure")
        self.r._http_probes()
        if self.inspect_account() != account:
            raise ClosureError("review account changed during closure")
        installation = self.b._installation_evidence(self.old_sha, self.b.CONFIG, self.b.INSTALLED.parent)
        if installation != isolation["installation"]:
            raise ClosureError("revoked installation changed")
        if self.b._recovery_file_identity(self.b.AUTHORIZED) != isolation["authorized"]:
            raise ClosureError("authorization drift during closure")
        self._quiescent()
        return {"installation": installation, "archives": archive_evidence(self.b, self.record, evidence),
                "account_key": self.b._recovery_file_identity(self.record / "account-hmac.key")}


def archive_evidence(b, record, evidence):
    result = {}
    expected_sets = {"lease": evidence["lease"], "operation": evidence["original"]["workspace"]["operations"][evidence["operation_id"]]}
    for name, expected in expected_sets.items():
        inventory = b._inventory(record / name, expected.keys() - {".", "directory"})
        for filename in inventory.keys() - {"."}:
            if any(inventory[filename][k] != expected[filename][k] for k in ("uid", "gid", "mode", "sha256")):
                raise ClosureError("durable original evidence archive changed")
        result[name] = inventory
    return result


def closed_evidence(b, old_sha, receipt):
    record = b.STATE / "review-maintenance-closures" / old_sha
    b.secure(record)
    expected = {"intent.json", "isolation.json", "account.json", "account-hmac.key", "completed.json", "lease", "operation"}
    if not record.is_dir() or stat.S_IMODE(record.lstat().st_mode) != 0o700 or {p.name for p in record.iterdir()} != expected:
        raise ClosureError("unknown maintenance closure incomplete")
    intent, completed, isolation, account = (b._read_json(record / name) for name in ("intent.json", "completed.json", "isolation.json", "account.json"))
    intent_keys = {"old_sha", "closing_sha", "operation_id", "original_outcome", "original", "lease", "services", "config", "library", "authorized", "accept_unknown_review_writes", "evidence_sha256", "receipt_sha256"}
    completed_keys = {"state", "old_sha", "original_outcome", "intent_sha256", "isolation_sha256", "account_sha256", "installation", "archives", "account_key"}
    if (not all(isinstance(v, dict) for v in (intent, completed, isolation, account))
            or set(intent) != intent_keys or set(completed) != completed_keys
            or set(isolation) != {"state", "installation", "authorized"}
            or set(intent.get("original", {})) != {"workspace", "canonical", "locks"}
            or set(intent["original"].get("canonical", {})) != CANONICAL_FILES
            or intent.get("old_sha") != old_sha or intent.get("original_outcome") != "UNKNOWN"
            or intent.get("accept_unknown_review_writes") is not True
            or re.fullmatch(r"[0-9a-f]{40}", intent.get("closing_sha", "")) is None
            or intent["closing_sha"] == old_sha or re.fullmatch(r"[0-9a-f]{32}", intent.get("operation_id", "")) is None
            or intent.get("evidence_sha256") != digest({k: v for k, v in intent.items() if k not in {"accept_unknown_review_writes", "evidence_sha256", "receipt_sha256"}})
            or completed.get("state") != TERMINAL or completed.get("old_sha") != old_sha
            or completed.get("original_outcome") != "UNKNOWN" or completed.get("intent_sha256") != digest(intent)
            or completed.get("isolation_sha256") != digest(isolation) or completed.get("account_sha256") != digest(account)):
        raise ClosureError("unknown maintenance closure binding invalid")
    validate_account_summary(account)
    if (not isinstance(receipt, str) or re.fullmatch(r"[0-9a-f]{64}", receipt) is None
            or not secrets.compare_digest(hashlib.sha256(receipt.encode()).hexdigest(), intent.get("receipt_sha256", ""))):
        raise ClosureError("durably delivered closure receipt required")
    b.canonical_source(intent["closing_sha"])
    if original_workspace(b, old_sha, intent["operation_id"]) != intent["original"]["workspace"]:
        raise ClosureError("original unknown operation changed")
    b.secure(record / "account-hmac.key", private=True)
    if ((record / "account-hmac.key").stat().st_size != 32
            or b._recovery_file_identity(record / "account-hmac.key") != completed["account_key"]):
        raise ClosureError("private account fingerprint key invalid")
    if archive_evidence(b, record, intent) != completed["archives"]:
        raise ClosureError("original durable archive changed")
    old_source = b.canonical_source(old_sha)
    helper_path = Path(__file__).with_name("contained_release_retirement.py")
    b.secure(helper_path)
    helpers = load(helper_path, "review_history_file_helpers")
    for name, expected_file in intent["original"]["canonical"].items():
        if helpers._file(b, old_source / name)[1] != expected_file:
            raise ClosureError("old canonical source evidence changed")
    locks = {"launcher": b._recovery_file_identity(b.STATE / "launcher.lock"),
             "build": b._recovery_file_identity(b.STATE / old_sha / "build.lock")
             if os.path.lexists(b.STATE / old_sha / "build.lock") else None}
    if locks != intent["original"]["locks"]:
        raise ClosureError("original lock identity changed")
    config, library = b._archives(old_sha)
    if not os.path.lexists(config) and not os.path.lexists(library):
        config, library = b.CONFIG, b.INSTALLED.parent
    expected_installation = {"config": {k: v for k, v in intent["config"].items() if k != "loopback.key"}, "library": intent["library"]}
    if (completed["installation"] != expected_installation or isolation.get("installation") != expected_installation
            or isolation.get("state") != "OLD_IDENTITIES_REVOKED_EXECUTION_QUIESCENT"
            or b._installation_evidence(old_sha, config, library) != expected_installation):
        raise ClosureError("closed old authorization changed")
    return {"state": TERMINAL, "operation_id": intent["operation_id"], "original_outcome": "UNKNOWN", "closure": digest(completed)}


def validate_account_summary(account):
    if (not isinstance(account, dict) or set(account) != {"verification", "account_hmac_sha256", "tables"}
            or account["verification"] != "CURRENT_ACCOUNT_ONLY_NOT_RESET"
            or not isinstance(account["account_hmac_sha256"], str)
            or re.fullmatch(r"[0-9a-f]{64}", account["account_hmac_sha256"]) is None
            or not isinstance(account["tables"], dict)
            or set(account["tables"]) != set(DIRECT_TABLES) | CHILD_TABLES.keys()):
        raise ClosureError("invalid current account proof")
    for value in account["tables"].values():
        if (not isinstance(value, dict) or set(value) != {"count", "rows_hmac_sha256"}
                or type(value["count"]) is not int or not 0 <= value["count"] <= 10000
                or not isinstance(value["rows_hmac_sha256"], str)
                or re.fullmatch(r"[0-9a-f]{64}", value["rows_hmac_sha256"]) is None):
            raise ClosureError("invalid current account table proof")
    if account["tables"]["user_profiles"]["count"] != 1:
        raise ClosureError("unique review profile proof required")


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ClosureError("invalid operator arguments")


def main():
    try:
        parser = Parser(description=__doc__, allow_abbrev=False)
        parser.add_argument("--sha", required=True)
        parser.add_argument("--release-sha", required=True)
        parser.add_argument("--operation-id")
        parser.add_argument("--accept-unknown-review-writes", action="store_true")
        parser.add_argument("--evidence-sha256")
        parser.add_argument("--account-probe", action="store_true", help=argparse.SUPPRESS)
        args = parser.parse_args()
        if re.fullmatch(r"[0-9a-f]{40}", args.release_sha) is None or args.sha == args.release_sha:
            raise ClosureError("distinct exact release and closing SHA required")
        if args.account_probe:
            if args.operation_id or args.evidence_sha256 or args.accept_unknown_review_writes:
                raise ClosureError("invalid fixed read-only probe arguments")
            print(json.dumps(account_child(args.sha, args.release_sha, STATE / "review-maintenance-closures" / args.release_sha), sort_keys=True))
            return 0
        if not args.accept_unknown_review_writes or re.fullmatch(r"[0-9a-f]{32}", args.operation_id or "") is None:
            raise ClosureError("explicit exact unknown maintenance acceptance required")
        if args.evidence_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", args.evidence_sha256) is None:
            raise ClosureError("invalid evidence digest")
        raw_token = sys.stdin.read(258)
        token = raw_token.removesuffix("\n")
        if len(raw_token) > 257 or re.fullmatch(r"[A-Za-z0-9._:-]{1,256}", token) is None:
            raise ClosureError("original lease token required via protected stdin")
        source, b, server = context(args.sha)
        lock = b.STATE / "launcher.lock"
        b.secure(lock, private=True)
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        build_fd = None
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            build = b.STATE / args.release_sha / "build.lock"
            exists = os.path.lexists(build)
            build_fd = b._acquire_existing_build_lock(args.release_sha)
            def check():
                b._assert_original_lock(lock, fd)
                if os.path.lexists(build) != exists:
                    raise ClosureError("original build lock presence changed")
                if build_fd is not None:
                    b._assert_original_lock(build, build_fd)
            adapter = Adapter(source, b, server, args.sha, args.release_sha, args.operation_id, token, check)
            result = close_transaction(adapter, accept_unknown=True, evidence_sha256=args.evidence_sha256)
            print(json.dumps(result, sort_keys=True))
            return 0
        finally:
            if build_fd is not None:
                os.close(build_fd)
            os.close(fd)
    except (Exception, KeyboardInterrupt):
        print("review closure: rejected or incomplete; preserve all evidence; do not retry", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
