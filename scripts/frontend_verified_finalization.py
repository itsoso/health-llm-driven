"""Finalize a verified frontend install whose lease-parent fsync then failed.

Loaded only by the reviewed canonical root operator under the original release
locks. This narrow profile preserves the original failure and every old inode.
It neither rebuilds nor changes services, credentials, leases or backend status.
Historical verification uses immutable evidence only, never a later live site.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import stat

STATE = Path("/var/lib/reva-release")
PRODUCTION = Path("/opt/health-app")
LEASE = Path("/var/lock/health-app-release")
CGROUPS = Path("/sys/fs/cgroup/system.slice")
AUDITED_PUBLISHER_SHA256 = (
    "eeb78d9db11eb684397440bbd3cff2a7b56959f02b5363bd4d4bad15179200c3"
)
EXPECTED_ARTIFACT = "87dd9c3a77261bbf91396d34b90120334f7479d2bf37e10b9e26c2781edfe1ab"
TERMINAL = "FINALIZED_VERIFIED_FRONTEND_INSTALL"
RECORDS = {
    "intent.json",
    "before.json",
    "failed.json",
    "install-started.json",
    "verified.json",
}
INVENTORY = RECORDS | {"build.log", "previous-next", "previous-node-modules"}


class FinalizationError(Exception):
    """Static, secret-free operator error."""


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def checked(value, length):
    if (
        not isinstance(value, str)
        or re.fullmatch("[a-f0-9]{%d}" % length, value) is None
    ):
        raise FinalizationError("invalid exact finalization identity")
    return value


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FinalizationError("duplicate evidence field")
        result[key] = value
    return result


def metadata(info):
    return {
        name: getattr(info, name)
        for name in (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_nlink",
            "st_uid",
            "st_gid",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
    }


def private_directory(server, path):
    server.secure_path(path, directory=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o700:
        raise FinalizationError("private original audit directory required")
    return metadata(info)


def file_evidence(server, path, *, private=True, bound=16_000_000):
    server.secure_path(path, private=private)
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or before.st_size > bound
        or (private and stat.S_IMODE(before.st_mode) != 0o600)
    ):
        raise FinalizationError("invalid bounded audit file")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as stream:
        if metadata(os.fstat(stream.fileno())) != metadata(before):
            raise FinalizationError("audit file changed before read")
        raw = stream.read(bound + 1)
    if len(raw) > bound or metadata(path.lstat()) != metadata(before):
        raise FinalizationError("audit file changed during read")
    return {**metadata(before), "sha256": hashlib.sha256(raw).hexdigest()}, raw


def archive_file_metadata(info):
    """Read-only data under the private audit; never executable/live input."""
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != 0
        or info.st_mode & (stat.S_IWOTH | stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX)
        or info.st_nlink < 1
    ):
        raise FinalizationError("unsafe inert archived file metadata")


def tree_evidence(server, root, *, state=None):
    """Bind private inert backups; account for every hardlink within ONE tree."""
    root = Path(root)
    state = Path(state or STATE)
    if (
        root.name not in {"previous-next", "previous-node-modules"}
        or root.parent.parent != state / "frontend-rebuilds"
    ):
        raise FinalizationError("fixed original archive path required")
    checked(root.parent.name, 32)
    outer_identity = private_directory(server, root.parent.parent)
    audit_identity = private_directory(server, root.parent)
    server.secure_path(root, directory=True)
    pending = [root]
    hasher = hashlib.sha256()
    count = 0
    size = 0
    observed = []
    directories = set()
    hardlinks = {}
    while pending:
        path = pending.pop()
        before = path.lstat()
        count += 1
        if count > 150000:
            raise FinalizationError("backup inventory exceeds bound")
        identity = metadata(before)
        if stat.S_ISLNK(before.st_mode):
            target = os.readlink(path)
            if (
                before.st_uid != 0
                or before.st_nlink != 1
                or os.path.isabs(target)
                or not path.resolve(strict=True).is_relative_to(
                    root.resolve(strict=True)
                )
            ):
                raise FinalizationError("backup link escapes immutable archive")
            content = {"link": target}
        elif stat.S_ISDIR(before.st_mode):
            server.validate_metadata(before, directory=True)
            inode = (before.st_dev, before.st_ino)
            if inode in directories:
                raise FinalizationError("aliased archived directory")
            directories.add(inode)
            names = sorted(path.iterdir(), reverse=True)
            pending.extend(names)
            content = {"children": sorted(p.name for p in names)}
        elif stat.S_ISREG(before.st_mode):
            # The original root-owned 0700 audit prevents all non-root access.
            # Preserve group-write bits as evidence, never chmod or execute it.
            archive_file_metadata(before)
            if before.st_size > 2_000_000_000:
                raise FinalizationError("backup file exceeds bound")
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            file_hash = hashlib.sha256()
            with os.fdopen(fd, "rb") as stream:
                if metadata(os.fstat(stream.fileno())) != identity:
                    raise FinalizationError("backup file replaced")
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    size += len(chunk)
                    file_hash.update(chunk)
                    if size > 8_000_000_000:
                        raise FinalizationError("backup bytes exceed bound")
            content = {"sha256": file_hash.hexdigest()}
            inode = (before.st_dev, before.st_ino)
            group = hardlinks.setdefault(
                inode, {"identity": identity, "sha256": content["sha256"], "paths": []}
            )
            if group["identity"] != identity or group["sha256"] != content["sha256"]:
                raise FinalizationError("archived hardlink bytes or metadata differ")
            group["paths"].append(path)
        else:
            raise FinalizationError("unsupported backup object")
        if metadata(path.lstat()) != identity:
            raise FinalizationError("backup changed during inspection")
        observed.append((path, identity))
        hasher.update(
            json.dumps(
                [path.relative_to(root).as_posix(), identity, content],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
    for group in hardlinks.values():
        if len(group["paths"]) != group["identity"]["st_nlink"]:
            raise FinalizationError(
                "archived hardlink has an unaccounted external alias"
            )
    # Recheck even the paths visited early: later reads must not hide a newly
    # created external link, replaced alias, ownership/mode change or new entry.
    for path, identity in observed:
        if metadata(path.lstat()) != identity:
            raise FinalizationError("archived path changed after traversal")
    if (
        private_directory(server, root.parent.parent) != outer_identity
        or private_directory(server, root.parent) != audit_identity
    ):
        raise FinalizationError("private archive boundary changed")
    return {
        "sha256": hasher.hexdigest(),
        "entries": count,
        "bytes": size,
        "root": metadata(root.lstat()),
    }


def validate_original_records(values, operation):
    checked(operation, 32)
    if not isinstance(values, dict) or set(values) != RECORDS:
        raise FinalizationError(
            "only verified post-install failure profile is supported"
        )
    intent = values["intent.json"]
    keys = {
        "kind",
        "publisher_sha",
        "production_sha",
        "operation_id",
        "frontend_tree",
        "state",
        "artifact_digest",
    }
    if (
        not isinstance(intent, dict)
        or set(intent) != keys
        or intent["kind"] != "frontend-rebuild"
        or intent["operation_id"] != operation
        or intent["state"] != "FRONTEND_STARTED"
        or intent["artifact_digest"] is not None
    ):
        raise FinalizationError("original frontend intent differs")
    for key in ("publisher_sha", "production_sha", "frontend_tree"):
        checked(intent[key], 40)
    for name, status, value in (
        ("failed.json", "FRONTEND_NEEDS_OPERATOR", None),
        ("install-started.json", "FRONTEND_INSTALLING", EXPECTED_ARTIFACT),
        ("verified.json", "FRONTEND_VERIFIED", EXPECTED_ARTIFACT),
    ):
        if values[name] != {**intent, "state": status, "artifact_digest": value}:
            raise FinalizationError("verified installation and failure binding differ")
    before = values["before.json"]
    if (
        not isinstance(before, dict)
        or set(before)
        != {
            "publisher_sha",
            "production_sha",
            "operation_id",
            "frontend_tree",
            "snapshot",
            "frontend_env",
            "frontend_process",
            "public_build_env",
            "toolchain",
        }
        or any(
            before[key] != intent[key]
            for key in (
                "publisher_sha",
                "production_sha",
                "operation_id",
                "frontend_tree",
            )
        )
        or any(
            not isinstance(before[key], dict)
            for key in (
                "snapshot",
                "frontend_env",
                "frontend_process",
                "public_build_env",
                "toolchain",
            )
        )
    ):
        raise FinalizationError("original preflight binding differs")
    return {**intent, "artifact_digest": EXPECTED_ARTIFACT}


def original_evidence(server, operation, *, state=None):
    state = Path(state or STATE)
    checked(operation, 32)
    audit = state / "frontend-rebuilds" / operation
    private_directory(server, audit.parent)
    identity = private_directory(server, audit)
    if {p.name for p in audit.iterdir()} != INVENTORY or os.path.lexists(
        state / "frontend-rebuild-closures" / operation
    ):
        raise FinalizationError(
            "unknown or conflicting original frontend audit inventory"
        )
    files = {}
    values = {}
    for name in sorted(RECORDS | {"build.log"}):
        files[name], raw = file_evidence(server, audit / name)
        if name != "build.log":
            values[name] = json.loads(raw, object_pairs_hook=unique)
    binding = validate_original_records(values, operation)
    old_entry = (
        state
        / "bootstrap"
        / binding["publisher_sha"]
        / "source/scripts/trusted_frontend_rebuild.py"
    )
    code, _ = file_evidence(server, old_entry, private=False)
    if code["sha256"] != AUDITED_PUBLISHER_SHA256:
        raise FinalizationError(
            "original frontend publisher implementation is not audited"
        )
    backups = {
        name: tree_evidence(server, audit / name, state=state)
        for name in ("previous-next", "previous-node-modules")
    }
    if metadata(audit.lstat()) != identity:
        raise FinalizationError("original frontend audit changed during inspection")
    return {
        "binding": binding,
        "artifact_digest": EXPECTED_ARTIFACT,
        "audit": identity,
        "files": files,
        "backups": backups,
        "before": values["before.json"],
        "old_publisher_code": code,
    }


def validate_builder(values, *, profile_verified, cgroup_present):
    expected = {
        "MainPID": "0",
        "ControlPID": "0",
        "Result": "success",
        "ExecMainCode": "1",
        "ExecMainStatus": "0",
        "ControlGroup": "",
        "LoadState": "loaded",
        "ActiveState": "inactive",
        "SubState": "dead",
    }
    collected = {**expected, "LoadState": "not-found", "ExecMainCode": "0"}
    # A collected unit alone says nothing. The narrowly pinned publisher wrote
    # verified only AFTER check=True systemd-run --wait and a drained cgroup.
    if profile_verified is not True or cgroup_present:
        raise FinalizationError("verified builder profile and absent cgroup required")
    if values == expected:
        return "EXITED_SUCCESSFULLY"
    if values == collected:
        return "COLLECTED_AFTER_VERIFIED_SUCCESS"
    raise FinalizationError("builder termination is not proven")


def lock_evidence(frontend, production, check_locks):
    check_locks()
    launcher = frontend.data_fingerprint(STATE / "launcher.lock")[0]
    path = STATE / production / "build.lock"
    build = frontend.data_fingerprint(path)[0] if os.path.lexists(path) else None
    check_locks()
    return launcher, build


def secure_live_artifact(server, root):
    """The legacy content digest omits ownership; independently close that gap."""
    server.secure_path(root, directory=True)
    pending, count = [root], 0
    while pending:
        path = pending.pop()
        info = path.lstat()
        count += 1
        if count > 150000:
            raise FinalizationError("live artifact inventory exceeds bound")
        if stat.S_ISLNK(info.st_mode):
            if (
                info.st_uid != 0
                or os.path.isabs(os.readlink(path))
                or not path.resolve(strict=True).is_relative_to(
                    root.resolve(strict=True)
                )
            ):
                raise FinalizationError("unsafe live artifact link")
        elif stat.S_ISDIR(info.st_mode):
            server.validate_metadata(info, directory=True)
            pending.extend(path.iterdir())
        else:
            server.validate_metadata(info)


def inspect_finalization(
    publisher,
    production,
    operation,
    source,
    helper,
    bootstrap,
    server,
    gate,
    frontend,
    *,
    check_locks,
    assert_other_history,
):
    for sha in (publisher, production):
        checked(sha, 40)
    checked(operation, 32)
    check_locks()
    if (
        publisher == production
        or Path(__file__).absolute()
        != source / "scripts/frontend_verified_finalization.py"
    ):
        raise FinalizationError("new canonical finalizer revision required")
    gate.verify_release(publisher, publisher)
    gate._latest(gate._get_json, production)
    if bootstrap.canonical_source(publisher) != source:
        raise FinalizationError("canonical finalizer source differs")
    if os.path.lexists(LEASE):
        raise FinalizationError("business lease must remain absent")
    original = original_evidence(server, operation)
    before = original["before"]
    binding = original["binding"]
    if binding["production_sha"] != production:
        raise FinalizationError("original production revision differs")
    # Caller must independently validate every other operation; selected audit
    # is accepted only after the exact verified+failed profile above succeeds.
    assert_other_history()
    old_source = bootstrap.canonical_source(binding["publisher_sha"])
    gate._latest(gate._get_json, binding["publisher_sha"])
    backend = bootstrap._read_json(STATE / production / "completed.json")
    frontend.validate_binding(
        binding["publisher_sha"],
        production,
        binding["frontend_tree"],
        frontend.git(old_source, "rev-parse", "HEAD:frontend"),
        backend,
        live_sha=frontend.git(PRODUCTION, "rev-parse", "HEAD"),
    )
    frontend.assert_unchanged(before, source, helper, bootstrap, server)
    # Preserve current frontend process identity across inspection and execution.
    rows = [
        r
        for r in json.loads(frontend.run(["/usr/bin/pm2", "jlist"]))
        if r.get("name") == "health-frontend"
    ]
    if (
        len(rows) != 1
        or type(rows[0].get("pid")) is not int
        or rows[0]["pid"] <= 0
        or rows[0].get("pm2_env", {}).get("status") != "online"
    ):
        raise FinalizationError("frontend runtime is not uniquely active")
    runtime = {
        "pid": rows[0]["pid"],
        **{k: rows[0]["pm2_env"][k] for k in ("restart_time", "pm_uptime")},
    }
    props = "MainPID,ControlPID,Result,ExecMainCode,ExecMainStatus,ControlGroup,LoadState,ActiveState,SubState"
    raw = frontend.run(
        [
            "/usr/bin/systemctl",
            "show",
            f"reva-frontend-build-{operation}.service",
            "--property=" + props,
        ]
    )
    pairs = [line.split("=", 1) for line in raw.splitlines()]
    if any(len(p) != 2 for p in pairs) or len({p[0] for p in pairs}) != len(pairs):
        raise FinalizationError("builder metadata invalid")
    unit = dict(pairs)
    proof = validate_builder(
        unit,
        profile_verified=True,
        cgroup_present=os.path.lexists(
            CGROUPS / f"reva-frontend-build-{operation}.service"
        ),
    )
    bootstrap._recovery_process_proof()

    def live_digest():
        for name in (".next", "node_modules"):
            secure_live_artifact(server, PRODUCTION / "frontend" / name)
        return hashlib.sha256(
            "".join(
                frontend.artifact_digest(PRODUCTION / "frontend" / name)
                for name in (".next", "node_modules")
            ).encode()
        ).hexdigest()

    if live_digest() != EXPECTED_ARTIFACT:
        raise FinalizationError("live frontend artifact differs from verified install")
    frontend.verify_pages()
    frontend.assert_unchanged(before, source, helper, bootstrap, server)
    if live_digest() != EXPECTED_ARTIFACT:
        raise FinalizationError("frontend artifact changed during page verification")
    launcher, build = lock_evidence(frontend, production, check_locks)
    finalizer, _ = file_evidence(
        server, source / "scripts/frontend_verified_finalization.py", private=False
    )
    bootstrap._recovery_process_proof()
    assert_other_history()
    check_locks()
    if os.path.lexists(LEASE):
        raise FinalizationError("business lease appeared")
    plan = {
        "kind": "frontend-verified-finalization",
        "publisher_sha": publisher,
        "production_sha": production,
        "operation_id": operation,
        "original": original,
        "artifact_digest": EXPECTED_ARTIFACT,
        "launcher": launcher,
        "build_lock": build,
        "backend_receipt": backend,
        "unit": unit,
        "unit_proof": proof,
        "frontend_runtime": runtime,
        "finalizer_sha256": finalizer["sha256"],
    }
    record = STATE / "frontend-finalizations" / operation
    if os.path.lexists(record):
        private_directory(server, record.parent)
        private_directory(server, record)
        if {p.name for p in record.iterdir()} != {"intent.json"}:
            raise FinalizationError("only the current durable intent may be inspected")
        _, raw = file_evidence(server, record / "intent.json")
        if json.loads(raw, object_pairs_hook=unique) != {
            **plan,
            "evidence_sha256": digest(plan),
        }:
            raise FinalizationError("pending finalization differs from fresh evidence")
    return plan


def validate_plan(plan):
    required = {
        "kind",
        "publisher_sha",
        "production_sha",
        "operation_id",
        "original",
        "artifact_digest",
        "launcher",
        "build_lock",
        "backend_receipt",
        "unit",
        "unit_proof",
        "frontend_runtime",
        "finalizer_sha256",
    }
    if (
        not isinstance(plan, dict)
        or set(plan) != required
        or plan["kind"] != "frontend-verified-finalization"
    ):
        raise FinalizationError("invalid finalization evidence")
    for key in ("publisher_sha", "production_sha"):
        checked(plan[key], 40)
    checked(plan["operation_id"], 32)
    checked(plan["finalizer_sha256"], 64)
    original = plan["original"]
    if (
        plan["publisher_sha"] == plan["production_sha"]
        or plan["artifact_digest"] != EXPECTED_ARTIFACT
        or original["artifact_digest"] != EXPECTED_ARTIFACT
        or original["binding"]["operation_id"] != plan["operation_id"]
        or original["binding"]["production_sha"] != plan["production_sha"]
        or original["old_publisher_code"]["sha256"] != AUDITED_PUBLISHER_SHA256
        or plan["backend_receipt"]
        != {"sha": plan["production_sha"], "state": "SUCCEEDED"}
        or plan["unit_proof"]
        != validate_builder(plan["unit"], profile_verified=True, cgroup_present=False)
    ):
        raise FinalizationError("finalization evidence binding differs")


def receipt(plan, intent_digest):
    return {
        **plan["original"]["binding"],
        "state": "FRONTEND_SUCCEEDED",
        "recovery": {
            "kind": "frontend-verified-finalization",
            "state": TERMINAL,
            "publisher_sha": plan["publisher_sha"],
            "intent_sha256": intent_digest,
            "original_verified_sha256": plan["original"]["files"]["verified.json"][
                "sha256"
            ],
            "original_failed_sha256": plan["original"]["files"]["failed.json"][
                "sha256"
            ],
        },
    }


def sync(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
        stream.flush()
        os.fsync(stream.fileno())
    sync(path.parent)


def finalize(plan, inspect_again, server, *, evidence_sha256=None, state=None):
    """Caller holds original locks throughout; only this new audit is written."""
    validate_plan(plan)
    state = Path(state or STATE)
    record = state / "frontend-finalizations" / plan["operation_id"]
    if os.path.lexists(record):
        raise FinalizationError("finalization already attempted; retry forbidden")
    if os.path.lexists(record.parent):
        private_directory(server, record.parent)
    else:
        server.secure_path(state, directory=True)
    fingerprint = digest(plan)
    if evidence_sha256 is None:
        return {
            "state": "FRONTEND_FINALIZATION_PREFLIGHT",
            "operation_id": plan["operation_id"],
            "evidence_sha256": fingerprint,
        }
    if evidence_sha256 != fingerprint:
        raise FinalizationError("finalization evidence changed")
    if not record.parent.exists():
        record.parent.mkdir(mode=0o700)
        sync(state)
    private_directory(server, record.parent)
    record.mkdir(mode=0o700)
    sync(record.parent)
    private_directory(server, record)
    intent = {**plan, "evidence_sha256": fingerprint}
    write(record / "intent.json", intent)
    directory_identity = private_directory(server, record)
    intent_identity, _ = file_evidence(server, record / "intent.json")
    if inspect_again() != plan:
        raise FinalizationError("finalization evidence changed after intent")
    if original_evidence(server, plan["operation_id"], state=state) != plan["original"]:
        raise FinalizationError("original audit changed before terminal")
    current_identity, raw = file_evidence(server, record / "intent.json")
    if (
        private_directory(server, record) != directory_identity
        or {p.name for p in record.iterdir()} != {"intent.json"}
        or current_identity != intent_identity
        or json.loads(raw, object_pairs_hook=unique) != intent
    ):
        raise FinalizationError("durable finalization intent changed before terminal")
    if os.path.lexists(LEASE):
        raise FinalizationError("business lease appeared before finalization sync")
    # Complete the one missed durability boundary using the reviewed strict
    # /var/lock -> /run/lock contract, never a generic symlink resolution.
    server._sync_business_lease_parent()
    if os.path.lexists(LEASE):
        raise FinalizationError("business lease appeared during finalization sync")
    complete = receipt(plan, digest(intent))
    write(record / "completed.json", complete)
    return complete


def history_evidence(server, operation, *, state=None):
    """No service, network, current checkout or live artifact calls are permitted."""
    state = Path(state or STATE)
    checked(operation, 32)
    record = state / "frontend-finalizations" / operation
    private_directory(server, record.parent)
    private_directory(server, record)
    if {p.name for p in record.iterdir()} != {"intent.json", "completed.json"}:
        raise FinalizationError("incomplete or unknown frontend finalization")
    _, raw = file_evidence(server, record / "intent.json")
    intent = json.loads(raw, object_pairs_hook=unique)
    _, raw = file_evidence(server, record / "completed.json")
    complete = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(intent, dict) or "evidence_sha256" not in intent:
        raise FinalizationError("finalization intent missing")
    plan = {k: v for k, v in intent.items() if k != "evidence_sha256"}
    validate_plan(plan)
    if (
        plan["operation_id"] != operation
        or intent["evidence_sha256"] != digest(plan)
        or complete != receipt(plan, digest(intent))
    ):
        raise FinalizationError("finalization terminal differs")
    finalizer = (
        state
        / "bootstrap"
        / plan["publisher_sha"]
        / "source/scripts/frontend_verified_finalization.py"
    )
    code, _ = file_evidence(server, finalizer, private=False)
    if code["sha256"] != plan["finalizer_sha256"]:
        raise FinalizationError("canonical historical finalizer changed")
    if original_evidence(server, operation, state=state) != plan["original"]:
        raise FinalizationError("immutable original frontend evidence changed")
    return complete
