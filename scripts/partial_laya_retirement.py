"""One narrowly pinned administrative closure; never deploy or resume an install.

The original business lease disappeared for an unknown reason. This is NOT the
unchanged-release profile and does not reconstruct the missing evidence. Only a
previous durably retired closure can attest the unchanged live baseline.
"""
import argparse
import fcntl
import grp
import hashlib
import importlib.util
import json
import os
import pwd
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path

FAILED = "a6b6e0e41b07caad138fcc66ab3aaf34660c8ca7"
BASELINE = "ba861b623059661010ad38a0c4a770393075b2c6"
PREDECESSOR = "3b0ec47d4bf12a80424a1fe655c7629f505b0d1b"
PRODUCTION = "05b6e4d396084103975c43e4a5fc4d044d8e66da"
GENERATION = "cffb5c196b9adf4ff5d698c5f5556a01b168201ce5077670190b7795a1dc33f2"
TERMINAL = "CLOSED_PARTIAL_LAYA_ORPHANED_LEASE"
LEASE_STATE = "ABSENT_CAUSE_UNKNOWN"
ROOT = Path("/var/lib/reva-release")
LAYA = Path("/var/lib/reva-laya-release")
BASE = Path("/opt/reva-laya")
OWNER = GROUP = 0
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "HOME": "/root", "LC_ALL": "C"}
LINKS = {"venv/lib64": "lib", "venv/bin/python3.12": "/usr/bin/python3.12",
         "venv/bin/python3": "python3.12", "venv/bin/python": "python3.12"}


class RetirementError(RuntimeError):
    """Static secret-free operator error."""


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(json.dumps(value, sort_keys=True).encode())
        out.flush()
        os.fsync(out.fileno())
    sync(path.parent)


def identity(info):
    return {k: getattr(info, k) for k in
            ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink", "st_size", "st_mtime_ns")}


def tree_manifest(root):
    """Bounded static opaque archive: no imports, subprocesses or link traversal."""
    result, pending, total = {}, [(root, ".")], 0
    while pending:
        path, relative = pending.pop()
        if len(result) >= 10000:
            raise RetirementError("partial tree entry bound exceeded")
        before = path.lstat()
        if before.st_uid != OWNER or before.st_gid != GROUP:
            raise RetirementError("partial tree ownership differs")
        item = identity(before)
        if stat.S_ISLNK(before.st_mode):
            if relative not in LINKS or os.readlink(path) != LINKS[relative] or before.st_nlink != 1:
                raise RetirementError("partial tree symlink differs")
            item["target"] = LINKS[relative]
        elif before.st_mode & 0o7022:
            raise RetirementError("partial tree permissions unsafe")
        elif stat.S_ISDIR(before.st_mode):
            children = sorted(path.iterdir())
            if len(children) > 10000 or any(not re.fullmatch(r"[A-Za-z0-9_.+-]+", p.name) for p in children):
                raise RetirementError("partial tree inventory unsafe")
            item["children"] = [p.name for p in children]
            pending.extend((p, p.name if relative == "." else relative + "/" + p.name) for p in children)
        elif stat.S_ISREG(before.st_mode) and before.st_nlink == 1:
            total += before.st_size
            if before.st_size > 16000000 or total > 32000000:
                raise RetirementError("partial tree byte bound exceeded")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                if identity(os.fstat(stream.fileno())) != identity(before):
                    raise RetirementError("partial tree file replaced")
                raw = stream.read(16000001)
            if len(raw) != before.st_size:
                raise RetirementError("partial tree file changed")
            item["sha256"] = hashlib.sha256(raw).hexdigest()
        else:
            raise RetirementError("partial tree type unsupported")
        if identity(path.lstat()) != identity(before):
            raise RetirementError("partial tree changed during inspection")
        result[relative] = item
    return result


def close_transaction(adapter, evidence_sha256=None):
    if os.path.lexists(adapter.record):
        raise RetirementError("closure already attempted; retry forbidden")
    evidence = adapter.inspect()
    bound = digest(evidence)
    if evidence_sha256 is None:
        return {"state": "INSPECTED_PARTIAL_LAYA_ORPHANED_LEASE", "evidence_sha256": bound}
    if evidence_sha256 != bound:
        raise RetirementError("closure evidence changed")
    if not adapter.record.parent.exists():
        adapter.record.parent.mkdir(mode=0o700)
        sync(adapter.record.parent.parent)
    adapter.record.mkdir(mode=0o700)
    sync(adapter.record.parent)
    receipt = secrets.token_hex(32)
    intent = {**evidence, "evidence_sha256": bound,
              "receipt_sha256": hashlib.sha256(receipt.encode()).hexdigest()}
    write(adapter.record / "intent.json", intent)
    if adapter.inspect() != evidence:
        raise RetirementError("closure drift after intent")
    adapter.archive_and_revoke(evidence)
    terminal = adapter.verify_closed(evidence)
    write(adapter.record / "completed.json", {"state": TERMINAL, "old_sha": FAILED,
          "intent_sha256": digest(intent), **terminal})
    return {"state": TERMINAL, "sha": FAILED, "receipt": receipt}


def load(b, source, filename):
    path = source / "scripts" / filename
    b.secure(path)
    if os.path.lexists(path.parent / "__pycache__"):
        raise RetirementError("cached operator code forbidden")
    spec = importlib.util.spec_from_file_location("partial_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def retired_binding(b, sha, next_sha):
    """Validate the relevant chain without recursive whole-history traversal."""
    root = b.STATE / "retired" / sha
    files = b._inventory(root, {"intent.json", "completed.json"})
    old = b._read_json(root / "intent.json")
    if (set(old) != {"old_sha", "new_sha", "installation", "workspace", "recovery_receipt"}
            or old["old_sha"] != sha or old["new_sha"] != next_sha
            or b._read_json(root / "completed.json") != {"old_sha": sha, "new_sha": next_sha, "state": "RETIRED"}
            or b._installation_evidence(sha, *b._archives(sha)) != old["installation"]
            or b._workspace_evidence(sha, recovery_receipt=old["recovery_receipt"], historical=True) != old["workspace"]):
        raise RetirementError("independent retired baseline unproven")
    return files


def baseline(b):
    """Prove both historical source siblings, not merely their revision names."""
    files = retired_binding(b, BASELINE, FAILED)
    predecessor = retired_binding(b, PREDECESSOR, BASELINE)
    archive = b.STATE / "unchanged-release-closures" / BASELINE
    old_intent = b._read_json(archive / "intent.json")
    if old_intent["production_sha"] != PRODUCTION or old_intent["closing_sha"] != FAILED:
        raise RetirementError("baseline revision differs")
    historical = old_intent["snapshot"]["unstarted_laya"]
    c = load(b, Path(__file__).absolute().parent.parent, "contained_release_retirement.py")
    for sha in (PREDECESSOR, BASELINE):
        path = LAYA / "sources" / sha
        c._private_directory(b, path)
        info = path.lstat()
        actual = {"dev": info.st_dev, "ino": info.st_ino, "uid": info.st_uid,
                  "gid": info.st_gid, "mode": stat.S_IMODE(info.st_mode)}
        if historical.get(str(path)) != actual:
            raise RetirementError("historical source directory differs")
        expected = {} if sha == PREDECESSOR else historical["prepared_source"]
        if {x.name for x in path.iterdir()} != set(expected):
            raise RetirementError("historical source inventory differs")
        for name, item in expected.items():
            if c._file(b, path / name)[1] != item:
                raise RetirementError("historical source bytes differ")
    return old_intent, {"retirement": files, "predecessor": predecessor,
                        "closure": b._recovery_file_identity(archive / "intent.json")}


def archive_paths():
    return (BASE / "retired" / FAILED / GENERATION, LAYA / "retired" / FAILED / "install.json")


def no_laya_process():
    entries = list(Path("/proc").iterdir())
    if len(entries) > 100000:
        raise RetirementError("process inspection bound exceeded")
    for path in entries:
        if not path.name.isdigit() or int(path.name) == os.getpid():
            continue
        before = (path / "stat").read_bytes().rsplit(b")", 1)[-1].split()
        if len(before) < 20:
            raise RetirementError("process identity malformed")
        if int(before[6]) & 0x00200000:
            continue
        values = []
        for name in ("cmdline", "environ"):
            with (path / name).open("rb") as stream:
                raw = stream.read(1000001)
            if len(raw) > 1000000:
                raise RetirementError("process inspection size exceeded")
            values.append(raw)
        values += [os.fsencode(os.readlink(path / name)) for name in ("cwd", "exe")]
        if any(needle in value for value in values for needle in (b"/opt/reva-laya", b"/var/lib/reva-laya-release")):
            raise RetirementError("Laya process remains")
        if (path / "stat").read_bytes().rsplit(b")", 1)[-1].split()[19] != before[19]:
            raise RetirementError("process changed during proof")


class Adapter:
    def __init__(self, b, source, server, sha, check):
        self.b, self.source, self.sha, self.check = b, source, sha, check
        self.record = b.STATE / "partial-laya-closures" / FAILED
        self.c = load(b, source, "contained_release_retirement.py")
        self.r = load(b, source, "recover_contained_services.py")
        module = load(b, source, "contained_recovery_proof.py")
        # Use only read-only methods that do not need lease authority. No fake
        # token and no synthetic original lease are constructed.
        p = module.RecoveryProof.__new__(module.RecoveryProof)
        p.source, p.bootstrap, p.server = source, b, server
        p.failed_sha, p.production_sha = FAILED, PRODUCTION
        p.production, p.systemd_root = Path("/opt/health-app"), Path("/etc/systemd/system")
        p.proc, p.cgroup = Path("/proc"), Path("/sys/fs/cgroup")
        p.runtime_root = Path("/var/lib/health-app/release-state")
        p.stage = None
        p.runtime = p._module("backend/scripts/runtime_state_release_transaction.py", "partial_runtime")
        p.reset = p._module("scripts/trusted_review_reset.py", "partial_revision")
        p.systemd = p.runtime.SubprocessSystemd()
        self.p, self.module = p, module

    def absent_activity(self):
        self.check()
        self.b._assert_idle()
        self.b._recovery_process_proof()
        no_laya_process()
        for root in ("recoveries", "contained-service-recoveries", "contained-release-closures",
                     "unchanged-release-closures", "review-maintenance-closures", "lost-closure-receipt-acknowledgments"):
            if os.path.lexists(self.b.STATE / root / FAILED):
                raise RetirementError("conflicting failed-release operation")
        self.p._absent(Path("/etc/reva-laya"), Path("/etc/systemd/system/reva-laya.service"),
                       Path("/etc/systemd/system/reva-laya.service.d"),
                       Path("/etc/systemd/system/multi-user.target.wants/reva-laya.service"),
                       Path("/run/systemd/system/reva-laya.service"), Path("/usr/lib/systemd/system/reva-laya.service"),
                       Path("/run/systemd/system/reva-laya.service.d"), Path("/usr/lib/systemd/system/reva-laya.service.d"))
        for lookup in (pwd.getpwnam, grp.getgrnam):
            try:
                lookup("reva-laya")
            except KeyError:
                continue
            raise RetirementError("Laya account exists")
        for name, expected in {"LoadState": "not-found", "FragmentPath": "", "DropInPaths": "", "UnitFileState": ""}.items():
            if self.p.systemd.show("reva-laya.service", name) != expected:
                raise RetirementError("Laya unit or override exists")
        for name in ("tcp", "tcp6"):
            raw = (Path("/proc/net") / name).read_bytes()
            if len(raw) > 1000000:
                raise RetirementError("socket bound exceeded")
            for line in raw.splitlines()[1:]:
                fields = line.split()
                if len(fields) < 4 or (fields[1].endswith(b":1F9C") and fields[3] == b"0A"):
                    raise RetirementError("Laya listener exists or socket proof invalid")

    def live(self):
        self.absent_activity()
        old, proof = baseline(self.b)
        p = self.p
        p.reset._revision_proof(PRODUCTION, self.source, self.b)
        if p._file(p.production / "backend/.env", 0o640)[1] != old["snapshot"]["stage"]["live_env"]:
            raise RetirementError("live environment differs from independent baseline")
        self.module.require_false(p._file(p.production / "backend/.env", 0o640)[0])
        # Fixed historical stage path is data only; it need not exist. No lease
        # method or candidate transaction is invoked from the orphan profile.
        prior_stage = self.b.STATE / "unchanged-release-closures" / BASELINE / "stage"
        tx = p.runtime.ReleaseTransaction(p.runtime.production_layout(prior_stage), p.systemd)
        p._absent(tx.layout.transaction_root, tx._preparing_root())
        if p._file(tx._terminal_marker_path())[1] != old["snapshot"]["terminal"]:
            raise RetirementError("terminal differs from independent baseline")
        marker = tx._load_terminal_marker()
        if marker["phase"] != "COMMITTED" or marker["terminal_sha"] != PRODUCTION:
            raise RetirementError("old production terminal unproven")
        if list(p.runtime_root.glob("runtime-state-transaction.reap-*")):
            raise RetirementError("transaction cleanup pending")
        p._absent(Path("/var/lib/reva-health-evidence-runtime/enabled.env"), Path("/run/reva-health-evidence-activation"), p.production / "backend/.env.reva-release.tmp")
        for unit in self.module.UNITS[1:]:
            p._absent(Path("/run/systemd/system") / (unit + ".d") / "90-reva-health-evidence-activation.conf")
        if p._units(self.b.canonical_source(PRODUCTION), tx) != old["snapshot"]["units"]:
            raise RetirementError("old units changed")
        class Services:
            def running_snapshot(_self):
                return p.running_services_snapshot()
        stable = self.r._wait_ready(Services())
        if stable != old["services"] or any(value["NRestarts"] != "0" for name, value in stable.items() if name.endswith(".service")):
            raise RetirementError("old services changed")
        self.r._application_probes(PRODUCTION, self.sha)
        self.r._http_probes()
        self.absent_activity()
        return proof

    def partial(self):
        b, p = self.b, self.p
        for path, expected in ((LAYA, {"sources", "install.json"}), (BASE, {"generations"}),
                               (BASE / "generations", {GENERATION}), (LAYA / "sources", {PREDECESSOR, BASELINE, FAILED})):
            b.secure(path)
            if not path.is_dir() or {x.name for x in path.iterdir()} != expected:
                raise RetirementError("partial installation inventory differs")
        for path in archive_paths():
            if os.path.lexists(path.parent.parent):
                raise RetirementError("partial archive already exists")
        canonical = b.canonical_source(FAILED)
        source = LAYA / "sources" / FAILED
        source_directory = p._directory(source)
        if {x.name for x in source.iterdir()} != set(self.module.LAYA_ASSETS) | {"source.json"}:
            raise RetirementError("partial source inventory differs")
        files = {}
        raw_assets = {}
        for name in self.module.LAYA_ASSETS:
            raw, item = p._file(source / name, 0o400)
            if raw != p._file(canonical / "infra/laya" / name)[0]:
                raise RetirementError("partial source bytes differ")
            files[name], raw_assets[name] = item, raw
        raw, files["source.json"] = p._file(source / "source.json", 0o400)
        if self.module.object_json(raw) != {"sha": FAILED, "old_sha": PRODUCTION, "old_has_decisions": False,
                                          "files": {name: item["sha256"] for name, item in files.items() if name != "source.json"}}:
            raise RetirementError("partial source binding differs")
        calculated = hashlib.sha256(b"".join(name.encode() + b"\0" + raw_assets[name] for name in self.module.LAYA_ASSETS)).hexdigest()
        if calculated != GENERATION:
            raise RetirementError("pinned partial generation differs")
        raw, receipt_identity = p._file(LAYA / "install.json", 0o600)
        receipt = self.module.object_json(raw)
        keys = {"generation", "unit_sha256", "env_sha256", "state", "candidate_sha", "lease"}
        unit = raw_assets["reva-laya.service.in"].replace(b"@GENERATION@", str(BASE / "generations" / GENERATION).encode())
        if (set(receipt) != keys or receipt["state"] != "PREPARING" or receipt["candidate_sha"] != FAILED
                or receipt["generation"] != GENERATION or receipt["unit_sha256"] != hashlib.sha256(unit).hexdigest()
                or any(not isinstance(receipt[k], str) or re.fullmatch(r"[0-9a-f]{64}", receipt[k]) is None for k in ("env_sha256", "lease"))):
            raise RetirementError("partial receipt binding differs")
        generation = BASE / "generations" / GENERATION
        tree = tree_manifest(generation)
        if set(tree["."]["children"]) != set(self.module.LAYA_ASSETS) | {"venv"}:
            raise RetirementError("partial generation phase differs")
        for name, raw in raw_assets.items():
            if tree[name].get("sha256") != hashlib.sha256(raw).hexdigest():
                raise RetirementError("partial generation assets differ")
        return {"source": files, "source_directory": source_directory, "receipt": receipt_identity, "tree": tree}

    def inspect(self):
        b = self.b
        for path in (self.record.parent,):
            if os.path.lexists(path):
                self.c._private_directory(b, path)
        history = b._retired_history()
        b._assert_known_activity(history, FAILED)
        if FAILED in history or any(os.path.lexists(path) for path in b._archives(FAILED)):
            raise RetirementError("failed release already retired")
        proof = self.live()
        workspace = self.p._workspace(b.canonical_source(FAILED))
        partial = self.partial()
        config = b._inventory(b.CONFIG, {"known_hosts", "loopback.conf", "authorized-release.json", "loopback.pub", "cloud.pub", "loopback.key"})
        library = b._inventory(b.INSTALLED.parent, {b.INSTALLED.name})
        policy = b._read_json(b.CONFIG / "authorized-release.json")
        public = [(b.CONFIG / name).read_text().strip() for name in ("cloud.pub", "loopback.pub")]
        for value in public:
            b.validate_install(FAILED, 1, value, now=0)
        expected = b.key_lines(policy["expires_at"], *public)
        lines = b.AUTHORIZED.read_text().splitlines()
        if public[0] == public[1] or any([line for line in lines if key.split()[1] in line] != [exact] for key, exact in zip(public, expected)):
            raise RetirementError("authorization differs")
        self.absent_activity()
        return {"old_sha": FAILED, "closing_sha": self.sha, "production_sha": PRODUCTION,
                "lease_state": LEASE_STATE, "baseline": proof, "workspace": workspace, "partial": partial,
                "config": config, "library": library, "authorized": b._recovery_file_identity(b.AUTHORIZED),
                "locks": locks(b)}

    def archive_and_revoke(self, evidence):
        b = self.b
        if self.inspect() != evidence:
            raise RetirementError("proof changed before archive")
        for source, target in zip((BASE / "generations" / GENERATION, LAYA / "install.json"), archive_paths()):
            target.parent.parent.mkdir(mode=0o700)
            sync(target.parent.parent.parent)
            target.parent.mkdir(mode=0o700)
            sync(target.parent.parent)
            if source.lstat().st_dev != target.parent.lstat().st_dev:
                raise RetirementError("archive must preserve original filesystem")
            b.secure(Path("/usr/bin/mv"))
            self.c._move_no_clobber(source, target)
            sync(source.parent)
            sync(target.parent)
            if os.path.lexists(source):
                raise RetirementError("archive move incomplete")
        verify_archives(b, self.c, evidence)
        self.live()
        if b._recovery_file_identity(b.AUTHORIZED) != evidence["authorized"]:
            raise RetirementError("authorization changed before revoke")
        if b._inventory(b.CONFIG, set(evidence["config"]) - {"."}) != evidence["config"]:
            raise RetirementError("installation changed before revoke")
        policy = b._read_json(b.CONFIG / "authorized-release.json")
        public = [(b.CONFIG / name).read_text().strip() for name in ("cloud.pub", "loopback.pub")]
        expected = b.key_lines(policy["expires_at"], *public)
        retained = b"".join(line for line in b.AUTHORIZED.read_bytes().splitlines(keepends=True) if line.decode().rstrip("\r\n") not in expected)
        b._replace_authorized(retained)
        if b.AUTHORIZED.read_bytes() != retained:
            raise RetirementError("revocation postcondition failed")
        (b.CONFIG / "loopback.key").unlink()
        sync(b.CONFIG)

    def verify_closed(self, evidence):
        self.live()
        if os.path.lexists(LAYA / "install.json") or os.path.lexists(BASE / "generations" / GENERATION):
            raise RetirementError("partial installation still active")
        verify_archives(self.b, self.c, evidence)
        self.c._workspace_unchanged(self.b, FAILED, evidence["workspace"])
        if locks(self.b) != evidence["locks"]:
            raise RetirementError("original locks changed")
        installed = self.b._installation_evidence(FAILED, self.b.CONFIG, self.b.INSTALLED.parent)
        if installed != {"config": {k: v for k, v in evidence["config"].items() if k != "loopback.key"}, "library": evidence["library"]}:
            raise RetirementError("closed installation differs")
        return {"installation": installed}


def locks(b):
    build = b.STATE / FAILED / "build.lock"
    return {"launcher": b._recovery_file_identity(b.STATE / "launcher.lock"),
            "build": b._recovery_file_identity(build) if os.path.lexists(build) else None}


def verify_archives(b, c, evidence):
    generation, receipt = archive_paths()
    for path in (generation, receipt):
        c._private_directory(b, path.parent.parent)
        c._private_directory(b, path.parent)
        if {x.name for x in path.parent.parent.iterdir()} != {FAILED} or {x.name for x in path.parent.iterdir()} != {path.name}:
            raise RetirementError("archive inventory changed")
    if tree_manifest(generation) != evidence["partial"]["tree"] or c._file(b, receipt)[1] != evidence["partial"]["receipt"]:
        raise RetirementError("original partial evidence changed")
    source = LAYA / "sources" / FAILED
    c._private_directory(b, source)
    info = source.lstat()
    if {"dev": info.st_dev, "ino": info.st_ino, "uid": info.st_uid, "gid": info.st_gid,
            "mode": stat.S_IMODE(info.st_mode)} != evidence["partial"]["source_directory"]:
        raise RetirementError("original source directory changed")
    if {x.name for x in source.iterdir()} != set(evidence["partial"]["source"]):
        raise RetirementError("original source inventory changed")
    for name, expected in evidence["partial"]["source"].items():
        if c._file(b, source / name)[1] != expected:
            raise RetirementError("original source changed")


def closed_evidence(b, sha, receipt):
    if sha != FAILED:
        raise RetirementError("unsupported partial closure revision")
    root = b.STATE / "partial-laya-closures" / sha
    for name in ("recoveries", "contained-service-recoveries", "contained-release-closures",
                 "unchanged-release-closures", "review-maintenance-closures", "lost-closure-receipt-acknowledgments"):
        if os.path.lexists(b.STATE / name / sha):
            raise RetirementError("conflicting archived partial closure")
    b._inventory(root, {"intent.json", "completed.json"})
    intent = b._read_json(root / "intent.json")
    completed = b._read_json(root / "completed.json")
    required = {"old_sha", "closing_sha", "production_sha", "lease_state", "baseline", "workspace", "partial",
                "config", "library", "authorized", "locks", "evidence_sha256", "receipt_sha256"}
    if (set(intent) != required or intent["old_sha"] != FAILED or intent["production_sha"] != PRODUCTION
            or intent["lease_state"] != LEASE_STATE or not re.fullmatch(r"[0-9a-f]{40}", intent["closing_sha"])
            or intent["closing_sha"] in {FAILED, BASELINE, PRODUCTION}
            or intent["evidence_sha256"] != digest({k: v for k, v in intent.items() if k not in {"evidence_sha256", "receipt_sha256"}})):
        raise RetirementError("partial closure intent invalid")
    source = b.canonical_source(intent["closing_sha"])
    c = load(b, source, "contained_release_retirement.py")
    c.verify_receipt(intent, receipt)
    if baseline(b)[1] != intent["baseline"] or locks(b) != intent["locks"]:
        raise RetirementError("partial baseline or locks changed")
    c._workspace_unchanged(b, FAILED, intent["workspace"])
    verify_archives(b, c, intent)
    config, library = b._archives(sha)
    if not os.path.lexists(config) and not os.path.lexists(library):
        config, library = b.CONFIG, b.INSTALLED.parent
    expected = {"config": {k: v for k, v in intent["config"].items() if k != "loopback.key"}, "library": intent["library"]}
    if b._installation_evidence(sha, config, library) != expected or completed != {
            "state": TERMINAL, "old_sha": FAILED, "intent_sha256": digest(intent), "installation": expected}:
        raise RetirementError("partial closure terminal invalid")
    return {"state": TERMINAL, "closure": digest(completed), "workspace": intent["workspace"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--accept-unknown-lease-loss", action="store_true", required=True)
    parser.add_argument("--evidence-sha256")
    args = parser.parse_args()
    if (sys.platform != "linux" or os.geteuid() != 0 or "SSH_ORIGINAL_COMMAND" in os.environ
            or not sys.flags.isolated or not sys.flags.no_site or not sys.flags.dont_write_bytecode
            or sys.executable != "/usr/bin/python3.12"
            or not re.fullmatch(r"[0-9a-f]{40}", args.sha) or args.sha in {FAILED, BASELINE, PRODUCTION}
            or (args.evidence_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", args.evidence_sha256))):
        raise RetirementError("canonical explicit operator context required")
    source = ROOT / "bootstrap" / args.sha / "source"
    entry = source / "scripts/partial_laya_retirement.py"
    if Path(__file__).absolute() != entry:
        raise RetirementError("canonical source required")
    for path in [*reversed(entry.parents), entry, entry.with_name("bootstrap_trusted_release.py")]:
        info = path.lstat()
        if info.st_uid != 0 or info.st_gid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise RetirementError("unsafe operator metadata")
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise RetirementError("linked operator source")
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location("partial_bootstrap", entry.with_name("bootstrap_trusted_release.py"))
    b = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = b
    spec.loader.exec_module(b)
    reviewed, server = b.reviewed_source(args.sha)
    if reviewed != source:
        raise RetirementError("reviewed source mismatch")
    subprocess.run(["/usr/bin/python3.12", "-I", "-S", "-B", str(source / "scripts/trusted_release_gate.py"),
                    "--sha", args.sha, "--workflow-sha", args.sha], env=ENV, check=True, timeout=90,
                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    b.secure(b.STATE / "launcher.lock", private=True)
    fd = os.open(b.STATE / "launcher.lock", os.O_RDWR | os.O_NOFOLLOW)
    build_fd = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        build_fd = b._acquire_existing_build_lock(FAILED)
        def check():
            b._assert_original_lock(b.STATE / "launcher.lock", fd)
            if build_fd is None:
                if os.path.lexists(b.STATE / FAILED / "build.lock"):
                    raise RetirementError("previously absent build lock appeared")
            else:
                b._assert_original_lock(b.STATE / FAILED / "build.lock", build_fd)
        check()
        result = close_transaction(Adapter(b, source, server, args.sha, check), args.evidence_sha256)
        check()
        print(json.dumps(result, sort_keys=True))
    finally:
        if build_fd is not None:
            os.close(build_fd)
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 — never expose imported operator errors or secret-bearing subprocess argv
        print("partial Laya retirement blocked; preserve all original evidence", file=sys.stderr)
        raise SystemExit(1) from None
