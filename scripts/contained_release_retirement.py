"""Audited closure of an unchanged, restored pre-checkout failed release.

Loaded only by the canonical isolated recovery operator or reviewed bootstrap.
No CLI, deployment, service restart, new key, or vendor operation lives here.
The root-managed host and canonical source are explicit trust prerequisites.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess

ACTIVE_LEASE = Path("/var/lock/health-app-release")
VOLATILE_ROOT = Path("/run/lock")


def _move_no_clobber(source, destination):
    subprocess.run(["/usr/bin/mv", "--no-clobber", "-T", "--", str(source), str(destination)],
                   env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C"},
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   check=True, timeout=15)

class ClosureError(Exception):
    """Static, secret-free operator failure."""


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write(path, value):
    _bytes(path, json.dumps(value, sort_keys=True).encode(), 0o600)


def _bytes(path, raw, mode):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), mode)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _sync(path.parent)


def verify_receipt(intent, receipt):
    digest = intent.get("receipt_sha256")
    if (not isinstance(receipt, str) or re.fullmatch(r"[0-9a-f]{64}", receipt) is None
            or not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or not secrets.compare_digest(hashlib.sha256(receipt.encode()).hexdigest(), digest)):
        raise ClosureError("durably issued closure receipt required")


def close_transaction(adapter, evidence_sha256=None):
    record = adapter.record
    if os.path.lexists(record):
        raise ClosureError("closure already attempted; retry forbidden")
    evidence = adapter.inspect()
    digest = _digest(evidence)
    if evidence_sha256 is None:
        return {"state": "INSPECTED_RESTORED_RELEASE", "evidence_sha256": digest}
    if evidence_sha256 != digest:
        raise ClosureError("closure inspection changed")
    if not record.parent.exists():
        record.parent.mkdir(mode=0o700)
        _sync(record.parent.parent)
    record.mkdir(mode=0o700)
    _sync(record.parent)
    receipt = secrets.token_hex(32)
    intent = {**evidence, "evidence_sha256": digest,
              "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest()}
    _write(record / "intent.json", intent)
    if adapter.inspect() != evidence:
        raise ClosureError("closure evidence drift after intent")
    adapter.archive_and_revoke(evidence)
    closed = adapter.verify_closed(evidence)
    _write(record / "completed.json", {
        "old_sha": evidence["old_sha"], "state": "CLOSED_RESTORED_RELEASE",
        "intent_sha256": _digest(intent), **closed,
    })
    # No plaintext preimage is persisted or returned before every final fsync.
    return {"sha": evidence["old_sha"], "state": "CLOSED_RESTORED_RELEASE", "receipt": receipt}


def _file(bootstrap, path):
    bootstrap.secure(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_gid != 0 or before.st_size > 16_000_000:
        raise ClosureError("invalid closure file metadata")
    with path.open("rb") as stream:
        raw = stream.read(16_000_001)
    after = path.lstat()
    fields = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_size", "st_mtime_ns", "st_nlink")
    if len(raw) > 16_000_000 or any(getattr(before, key) != getattr(after, key) for key in fields):
        raise ClosureError("closure file changed")
    return raw, {"dev": before.st_dev, "ino": before.st_ino, "uid": before.st_uid,
                 "gid": before.st_gid, "mode": stat.S_IMODE(before.st_mode),
                 "sha256": hashlib.sha256(raw).hexdigest()}


def _private_directory(bootstrap, path):
    bootstrap.secure(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700 or info.st_gid != 0:
        raise ClosureError("private closure directory required")


def _archive_inventory(bootstrap, root, expected):
    _private_directory(bootstrap, root)
    if {p.name for p in root.iterdir()} != set(expected):
        raise ClosureError("closure archive inventory differs")
    result = {}
    for name, original in expected.items():
        _, identity = _file(bootstrap, root / name)
        if any(identity[key] != original[key] for key in ("uid", "gid", "mode", "sha256")):
            raise ClosureError("closure archive differs from original")
        result[name] = identity
    return result


def _expected_archives(snapshot):
    stage = snapshot["stage"]
    lease = {name: stage[name] for name in ("token", "label", "stage", "started_at")}
    excluded = {"lease", "token", "label", "stage", "started_at", "pointer", "directory", "live_env"}
    artifacts = {("staged.sha256" if name == "manifest" else name): item
                 for name, item in stage.items() if name not in excluded}
    return {"lease": lease, "stage": artifacts}


def _archives(bootstrap, record, snapshot):
    return {name: _archive_inventory(bootstrap, record / name, items)
            for name, items in _expected_archives(snapshot).items()}


def _workspace_unchanged(bootstrap, sha, expected):
    workspace = bootstrap.STATE / sha
    _private_directory(bootstrap, workspace)
    info = workspace.lstat()
    directory = {"dev": info.st_dev, "ino": info.st_ino, "uid": info.st_uid,
                 "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}
    if directory != expected["directory"] or sorted(p.name for p in workspace.iterdir()) != expected["inventory"]:
        raise ClosureError("original failed workspace changed")
    for name, identity in expected.items():
        if name in {"directory", "inventory", "policy", "executor"}:
            continue
        if _file(bootstrap, workspace / name)[1] != identity:
            raise ClosureError("original failed receipt or log changed")


def _locks(bootstrap, sha, snapshot):
    # Backend-only releases never claim a native build. Preserve that proven
    # absence under the original launcher lock; never manufacture a build lock.
    build = bootstrap.STATE / sha / "build.lock"
    expected = "build.lock" in snapshot["workspace"]["inventory"]
    if os.path.lexists(build) != expected:
        raise ClosureError("build lock differs from original restoration inventory")
    return {"launcher": bootstrap._recovery_file_identity(bootstrap.STATE / "launcher.lock"),
            "build": bootstrap._recovery_file_identity(build) if expected else None}


def _restoration(bootstrap, sha):
    root = bootstrap.STATE / "contained-service-recoveries" / sha
    inventory = bootstrap._inventory(root, {"intent.json", "completed.json"})
    intent, completed = (bootstrap._read_json(root / name) for name in ("intent.json", "completed.json"))
    if (not isinstance(intent, dict) or set(intent) != {
            "recovery_sha", "failed_sha", "production_sha", "snapshot", "evidence_sha256"}
            or intent["failed_sha"] != sha
            or any(not isinstance(intent[k], str) or re.fullmatch(r"[0-9a-f]{40}", intent[k]) is None
                   for k in ("recovery_sha", "failed_sha", "production_sha"))
            or len({intent[k] for k in ("recovery_sha", "failed_sha", "production_sha")}) != 3
            or intent["evidence_sha256"] != _digest({k: v for k, v in intent.items() if k != "evidence_sha256"})
            or not isinstance(completed, dict) or set(completed) != {
                "state", "recovery_sha", "failed_sha", "production_sha", "evidence_sha256",
                "stable_services", "original_release_and_lease_preserved"}
            or completed["state"] != "RESTORED_PREVIOUS_SERVICES"
            or completed["original_release_and_lease_preserved"] is not True
            or any(completed[k] != intent[k] for k in ("recovery_sha", "failed_sha", "production_sha", "evidence_sha256"))
            or not isinstance(completed["stable_services"], dict)):
        raise ClosureError("restoration audit does not prove completed recovery")
    bootstrap.canonical_source(intent["recovery_sha"])
    return intent, completed, inventory


class ClosureAdapter:
    def __init__(self, proof, bootstrap, recovery, closing_sha, check_locks):
        self.proof, self.b, self.r = proof, bootstrap, recovery
        self.sha, self.check = closing_sha, check_locks
        self.record = bootstrap.STATE / "contained-release-closures" / proof.failed_sha
        self.volatile = VOLATILE_ROOT / ("health-app-release.retired-" + proof.failed_sha)

    def inspect(self):
        b, p = self.b, self.proof
        self.check()
        if os.path.lexists(self.record.parent):
            _private_directory(b, self.record.parent)
        else:
            b.secure(self.record.parent.parent)
        b._recovery_process_proof()
        restored, completed, audit = _restoration(b, p.failed_sha)
        snapshot = p.snapshot()
        if (restored["production_sha"] != p.production_sha or restored["snapshot"] != snapshot
                or self.sha in {restored["recovery_sha"], p.failed_sha, p.production_sha}):
            raise ClosureError("restored original state changed")
        if os.path.lexists(self.volatile):
            raise ClosureError("original lease archive already exists")
        if p.lease != ACTIVE_LEASE:
            raise ClosureError("fixed original business lease required")
        history = b._retired_history()
        b._assert_known_activity(history, p.failed_sha)
        if p.failed_sha in history or any(os.path.lexists(path) for path in b._archives(p.failed_sha)):
            raise ClosureError("failed release already retired")
        config = b._inventory(b.CONFIG, {"known_hosts", "loopback.conf", "authorized-release.json",
                                         "loopback.pub", "cloud.pub", "loopback.key"})
        library = b._inventory(b.INSTALLED.parent, {b.INSTALLED.name})
        policy = b._read_json(b.CONFIG / "authorized-release.json")
        public = [(b.CONFIG / name).read_text().strip() for name in ("cloud.pub", "loopback.pub")]
        for key in public:
            b.validate_install(p.failed_sha, 1, key, now=0)
        if public[0] == public[1]:
            raise ClosureError("release identities must differ")
        expected = b.key_lines(policy["expires_at"], *public)
        b.secure(b.AUTHORIZED, private=True)
        lines = b.AUTHORIZED.read_text().splitlines()
        if any([line for line in lines if key.split()[1] in line] != [exact] for key, exact in zip(public, expected)):
            raise ClosureError("original release authorization changed")
        self.r._application_probes(p.production_sha, self.sha)
        self.r._http_probes()
        stable = self.r._wait_ready(p)
        if stable != completed["stable_services"] or p.snapshot() != snapshot:
            raise ClosureError("restored services or original evidence changed")
        b._recovery_process_proof()
        self.check()
        return {"old_sha": p.failed_sha, "closing_sha": self.sha, "production_sha": p.production_sha,
                "restoration": audit, "snapshot": snapshot, "config": config, "library": library,
                "authorized": b._recovery_file_identity(b.AUTHORIZED), "services": stable,
                "locks": _locks(b, p.failed_sha, snapshot)}

    def archive_and_revoke(self, evidence):
        b, p = self.b, self.proof
        # Durable copies precede revocation and removal from the active lease
        # name. The original lease inode is retained on its original filesystem.
        for name, expected in _expected_archives(evidence["snapshot"]).items():
            target = self.record / name
            target.mkdir(mode=0o700)
            _sync(self.record)
            source = p.lease if name == "lease" else p.stage
            for filename, identity in expected.items():
                raw, actual = p._file(source / filename)
                if actual != identity:
                    raise ClosureError("original archival input changed")
                _bytes(target / filename, raw, identity["mode"])
        _archives(b, self.record, evidence["snapshot"])
        self.check()
        if p.snapshot() != evidence["snapshot"] or _locks(b, p.failed_sha, evidence["snapshot"]) != evidence["locks"]:
            raise ClosureError("original evidence changed before revocation")
        if b._recovery_file_identity(b.AUTHORIZED) != evidence["authorized"]:
            raise ClosureError("authorization changed before revocation")
        policy = b._read_json(b.CONFIG / "authorized-release.json")
        public = [(b.CONFIG / name).read_text().strip() for name in ("cloud.pub", "loopback.pub")]
        expected = b.key_lines(policy["expires_at"], *public)
        retained = b"".join(line for line in b.AUTHORIZED.read_bytes().splitlines(keepends=True)
                            if line.decode().rstrip("\r\n") not in expected)
        b._replace_authorized(retained)
        if b.AUTHORIZED.read_bytes() != retained:
            raise ClosureError("revocation postcondition failed")
        if b._inventory(b.CONFIG, evidence["config"].keys() - {"."}) != evidence["config"]:
            raise ClosureError("installation drift before private key removal")
        (b.CONFIG / "loopback.key").unlink()
        _sync(b.CONFIG)
        b._installation_evidence(p.failed_sha, b.CONFIG, b.INSTALLED.parent)
        b._recovery_process_proof()
        self.check()
        if p.snapshot() != evidence["snapshot"] or self.r._wait_ready(p) != evidence["services"]:
            raise ClosureError("restored state changed before lease archival")
        if os.path.lexists(self.volatile):
            raise ClosureError("lease archive appeared")
        # _lease_snapshot has validated the fixed alias and sticky parent.
        # No delete/reset: rename on /run/lock preserves the original inode.
        b.secure(Path("/usr/bin/mv"))
        if p.lease.lstat().st_dev != VOLATILE_ROOT.lstat().st_dev:
            raise ClosureError("lease archival must remain on the same filesystem")
        _move_no_clobber(p.lease, self.volatile)
        _sync(VOLATILE_ROOT)
        self._verify_original_lease_archive(evidence)

    def _verify_original_lease_archive(self, evidence):
        expected = evidence["snapshot"]["stage"]
        if os.path.lexists(self.proof.lease):
            raise ClosureError("active business lease remains")
        info = self.volatile.lstat()
        actual = {"dev": info.st_dev, "ino": info.st_ino, "uid": info.st_uid,
                  "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}
        if not stat.S_ISDIR(info.st_mode) or actual != expected["lease"]:
            raise ClosureError("original lease inode not preserved")
        if {p.name for p in self.volatile.iterdir()} != {"token", "label", "stage", "started_at"}:
            raise ClosureError("original lease archive inventory changed")
        for name in ("token", "label", "stage", "started_at"):
            path = self.volatile / name
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != 0
                    or info.st_gid != 0 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
                raise ClosureError("original lease archive file changed")
            identity = {"dev": info.st_dev, "ino": info.st_ino, "uid": info.st_uid,
                        "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            if identity != expected[name]:
                raise ClosureError("original lease archive file identity changed")

    def verify_closed(self, evidence):
        b, p = self.b, self.proof
        self.check()
        self._verify_original_lease_archive(evidence)
        b._assert_idle()
        b._recovery_process_proof()
        _workspace_unchanged(b, p.failed_sha, evidence["snapshot"]["workspace"])
        _, _, restoration = _restoration(b, p.failed_sha)
        if restoration != evidence["restoration"] or _locks(b, p.failed_sha, evidence["snapshot"]) != evidence["locks"]:
            raise ClosureError("original restoration or lock evidence changed")
        self.r._application_probes(p.production_sha, self.sha)
        self.r._http_probes()
        class Services:
            def running_snapshot(self):
                return p.running_services_snapshot()
        if self.r._wait_ready(Services()) != evidence["services"]:
            raise ClosureError("services changed during closure")
        installation = b._installation_evidence(p.failed_sha, b.CONFIG, b.INSTALLED.parent)
        if installation != {"config": {k: v for k, v in evidence["config"].items() if k != "loopback.key"},
                            "library": evidence["library"]}:
            raise ClosureError("closed installation differs")
        self._verify_original_lease_archive(evidence)
        self.check()
        return {"installation": installation, "archives": _archives(b, self.record, evidence["snapshot"])}


def closed_evidence(bootstrap, sha, receipt):
    """Rotation/history proof. Never uses live service state as historical truth."""
    root = bootstrap.STATE / "contained-release-closures" / sha
    _private_directory(bootstrap, root)
    if {p.name for p in root.iterdir()} != {"intent.json", "completed.json", "lease", "stage"}:
        raise ClosureError("closure audit incomplete")
    for name in ("intent.json", "completed.json"):
        bootstrap.secure(root / name, private=True)
    intent, completed = (bootstrap._read_json(root / name) for name in ("intent.json", "completed.json"))
    keys = {"old_sha", "closing_sha", "production_sha", "restoration", "snapshot", "config", "library",
            "authorized", "services", "locks", "evidence_sha256", "receipt_sha256"}
    if (not isinstance(intent, dict) or set(intent) != keys or intent["old_sha"] != sha
            or any(not isinstance(intent[k], str) or re.fullmatch(r"[0-9a-f]{40}", intent[k]) is None
                   for k in ("old_sha", "closing_sha", "production_sha"))
            or len({intent[k] for k in ("old_sha", "closing_sha", "production_sha")}) != 3
            or intent["evidence_sha256"] != _digest({k: v for k, v in intent.items() if k not in {"evidence_sha256", "receipt_sha256"}})
            or not isinstance(completed, dict) or set(completed) != {"old_sha", "state", "intent_sha256", "installation", "archives"}
            or completed["old_sha"] != sha or completed["state"] != "CLOSED_RESTORED_RELEASE"
            or completed["intent_sha256"] != _digest(intent)):
        raise ClosureError("closure audit binding invalid")
    verify_receipt(intent, receipt)
    bootstrap.canonical_source(intent["closing_sha"])
    restored, _, restoration = _restoration(bootstrap, sha)
    if (restoration != intent["restoration"] or restored["snapshot"] != intent["snapshot"]
            or restored["production_sha"] != intent["production_sha"]):
        raise ClosureError("restoration evidence changed after closure")
    _workspace_unchanged(bootstrap, sha, intent["snapshot"]["workspace"])
    if completed["archives"] != _archives(bootstrap, root, intent["snapshot"]):
        raise ClosureError("durable lease or stage archive changed")
    if intent["locks"] != _locks(bootstrap, sha, intent["snapshot"]):
        raise ClosureError("original launcher or build lock changed")
    config, library = bootstrap._archives(sha)
    if not os.path.lexists(config) and not os.path.lexists(library):
        config, library = bootstrap.CONFIG, bootstrap.INSTALLED.parent
    expected = {"config": {k: v for k, v in intent["config"].items() if k != "loopback.key"}, "library": intent["library"]}
    if completed["installation"] != expected or bootstrap._installation_evidence(sha, config, library) != expected:
        raise ClosureError("closed installation or authorization changed")
    return {"state": "CLOSED_RESTORED_RELEASE", "closure": _digest(completed),
            "workspace": intent["snapshot"]["workspace"]}
