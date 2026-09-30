"""Post-verification finalization is a new proof, never a rewritten old outcome."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest


SHA = "d" * 40
PUBLISHER = "a" * 40
OPERATION = "7" * 32
TREE = "c" * 40


def load():
    spec = importlib.util.spec_from_file_location(
        "tested_frontend_finalization",
        Path(__file__).with_name("frontend_verified_finalization.py"),
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def receipts(m):
    intent = {
        "kind": "frontend-rebuild",
        "publisher_sha": SHA,
        "production_sha": SHA,
        "operation_id": OPERATION,
        "frontend_tree": TREE,
        "state": "FRONTEND_STARTED",
        "artifact_digest": None,
    }
    values = {
        "intent.json": intent,
        "failed.json": {**intent, "state": "FRONTEND_NEEDS_OPERATOR"},
        "install-started.json": {
            **intent,
            "state": "FRONTEND_INSTALLING",
            "artifact_digest": m.EXPECTED_ARTIFACT,
        },
        "verified.json": {
            **intent,
            "state": "FRONTEND_VERIFIED",
            "artifact_digest": m.EXPECTED_ARTIFACT,
        },
        "before.json": {
            k: intent[k]
            for k in (
                "publisher_sha",
                "production_sha",
                "operation_id",
                "frontend_tree",
            )
        },
    }
    values["before.json"].update(
        snapshot={"services": {}, "configuration": {}},
        frontend_env={},
        frontend_process={},
        public_build_env={},
        toolchain={"node": "v22.13.0", "npm": "10.9.2"},
    )
    return values


def test_original_profile_requires_both_matching_install_and_verified_receipts():
    m = load()
    values = receipts(m)
    result = m.validate_original_records(values, OPERATION)
    assert result["artifact_digest"] == m.EXPECTED_ARTIFACT
    assert result["operation_id"] == OPERATION
    assert values["failed.json"]["state"] == "FRONTEND_NEEDS_OPERATOR"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_verified",
        "fake_completed",
        "extra",
        "operation",
        "install_hash",
        "verified_hash",
        "before_sha",
        "failed_state",
        "intent_digest",
    ],
)
def test_unknown_or_cross_bound_original_records_are_rejected(mutation):
    m = load()
    values = receipts(m)
    if mutation == "missing_verified":
        values.pop("verified.json")
    elif mutation == "fake_completed":
        values["completed.json"] = values["verified.json"]
    elif mutation == "extra":
        values["verified.json"]["retry"] = True
    elif mutation == "operation":
        values["verified.json"]["operation_id"] = "8" * 32
    elif mutation == "install_hash":
        values["install-started.json"]["artifact_digest"] = "f" * 64
    elif mutation == "verified_hash":
        values["verified.json"]["artifact_digest"] = "f" * 64
    elif mutation == "before_sha":
        values["before.json"]["production_sha"] = "e" * 40
    elif mutation == "failed_state":
        values["failed.json"]["state"] = "FRONTEND_SUCCEEDED"
    elif mutation == "intent_digest":
        values["intent.json"]["artifact_digest"] = m.EXPECTED_ARTIFACT
    with pytest.raises(m.FinalizationError):
        m.validate_original_records(values, OPERATION)


def unit(collected=True):
    return {
        "MainPID": "0",
        "ControlPID": "0",
        "Result": "success",
        "ExecMainCode": "0" if collected else "1",
        "ExecMainStatus": "0",
        "ControlGroup": "",
        "LoadState": "not-found" if collected else "loaded",
        "ActiveState": "inactive",
        "SubState": "dead",
    }


def test_collected_builder_requires_verified_known_profile_and_no_cgroup():
    m = load()
    assert (
        m.validate_builder(unit(), profile_verified=True, cgroup_present=False)
        == "COLLECTED_AFTER_VERIFIED_SUCCESS"
    )
    assert (
        m.validate_builder(unit(False), profile_verified=True, cgroup_present=False)
        == "EXITED_SUCCESSFULLY"
    )
    with pytest.raises(m.FinalizationError):
        m.validate_builder(unit(), profile_verified=False, cgroup_present=False)
    with pytest.raises(m.FinalizationError):
        m.validate_builder(unit(), profile_verified=True, cgroup_present=True)


@pytest.mark.parametrize(
    "field,value",
    [
        ("MainPID", "123"),
        ("Result", "exit-code"),
        ("ExecMainStatus", "1"),
        ("ActiveState", "active"),
        ("LoadState", "error"),
        ("ControlGroup", "/unexpected"),
    ],
)
def test_nonterminal_or_uncertain_builder_blocks(field, value):
    m = load()
    values = unit()
    values[field] = value
    with pytest.raises(m.FinalizationError):
        m.validate_builder(values, profile_verified=True, cgroup_present=False)


class Server:
    def _sync_business_lease_parent(self):
        # Explicit protocol stub: tests never fsync a real host lease parent.
        self.sync_calls = getattr(self, "sync_calls", 0) + 1

    def secure_path(self, path, **kwargs):
        assert not Path(path).is_symlink()

    def validate_metadata(self, *args, **kwargs):
        pass


def fixture_original(m, tmp_path, monkeypatch):
    from types import SimpleNamespace

    # Synthetic archive files belong to the unprivileged test user. Substitute
    # only root ownership at this protocol seam; real inode/link/mode/hash data
    # and all actual os.link operations remain untouched. Ownership rejection
    # is separately exercised against the unpatched production validator.
    archive_validator = m.archive_file_metadata
    monkeypatch.setattr(
        m,
        "archive_file_metadata",
        lambda info: archive_validator(
            SimpleNamespace(**{**m.metadata(info), "st_uid": 0, "st_gid": 0})
        ),
    )
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(m, "STATE", state)
    root = state / "frontend-rebuilds"
    root.mkdir(mode=0o700)
    audit = root / OPERATION
    audit.mkdir(mode=0o700)
    for name, value in receipts(m).items():
        (audit / name).write_text(json.dumps(value))
        (audit / name).chmod(0o600)
    (audit / "build.log").write_text("successful build log")
    (audit / "build.log").chmod(0o600)
    for name in ("previous-next", "previous-node-modules"):
        (audit / name).mkdir()
        (audit / name / "file").write_text("original backup")
    old = state / "bootstrap" / SHA / "source/scripts"
    old.mkdir(parents=True)
    (old / "trusted_frontend_rebuild.py").write_text("audited original publisher")
    monkeypatch.setattr(
        m,
        "AUDITED_PUBLISHER_SHA256",
        m.hashlib.sha256(b"audited original publisher").hexdigest(),
    )
    return state, audit, Server()


def test_original_evidence_retains_file_and_backup_inodes(tmp_path, monkeypatch):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    original = m.original_evidence(server, OPERATION, state=state)
    assert original["artifact_digest"] == m.EXPECTED_ARTIFACT
    (audit / "previous-next/file").write_text("tampered backup")
    assert m.original_evidence(server, OPERATION, state=state) != original


@pytest.mark.parametrize(
    "mutation", ["completed", "unknown", "closure", "profile", "missing_backup"]
)
def test_original_inventory_rejects_other_failure_profiles(
    tmp_path, monkeypatch, mutation
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    if mutation == "completed":
        (audit / "completed.json").write_text("{}")
    elif mutation == "unknown":
        (audit / "unknown").write_text("")
    elif mutation == "closure":
        (state / "frontend-rebuild-closures" / OPERATION).mkdir(parents=True)
    elif mutation == "profile":
        (
            state / "bootstrap" / SHA / "source/scripts/trusted_frontend_rebuild.py"
        ).write_text("different control flow")
    elif mutation == "missing_backup":
        (audit / "previous-next/file").unlink()
        (audit / "previous-next").rmdir()
    with pytest.raises(m.FinalizationError):
        m.original_evidence(server, OPERATION, state=state)


def plan(m, state, original):
    finalizer = (
        state
        / "bootstrap"
        / PUBLISHER
        / "source/scripts/frontend_verified_finalization.py"
    )
    finalizer.parent.mkdir(parents=True, exist_ok=True)
    finalizer.write_text("canonical reviewed finalizer")
    return {
        "kind": "frontend-verified-finalization",
        "publisher_sha": PUBLISHER,
        "production_sha": SHA,
        "operation_id": OPERATION,
        "original": original,
        "artifact_digest": m.EXPECTED_ARTIFACT,
        "launcher": {"inode": 1},
        "build_lock": None,
        "backend_receipt": {"sha": SHA, "state": "SUCCEEDED"},
        "unit": unit(),
        "unit_proof": "COLLECTED_AFTER_VERIFIED_SUCCESS",
        "frontend_runtime": {"pid": 2},
        "finalizer_sha256": m.hashlib.sha256(
            b"canonical reviewed finalizer"
        ).hexdigest(),
    }


def test_inspect_is_read_only_then_finalize_preserves_original_failure(
    tmp_path, monkeypatch
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    p = plan(m, state, m.original_evidence(server, OPERATION, state=state))
    before = {
        name: (audit / name).stat().st_ino for name in ("failed.json", "verified.json")
    }
    preflight = m.finalize(p, lambda: copy.deepcopy(p), server, state=state)
    assert not (state / "frontend-finalizations").exists()
    complete = m.finalize(
        p,
        lambda: copy.deepcopy(p),
        server,
        evidence_sha256=preflight["evidence_sha256"],
        state=state,
    )
    assert complete["state"] == "FRONTEND_SUCCEEDED"
    assert complete["recovery"]["state"] == m.TERMINAL
    assert before == {name: (audit / name).stat().st_ino for name in before}
    assert not (audit / "completed.json").exists()
    with pytest.raises(m.FinalizationError, match="retry"):
        m.finalize(p, lambda: p, server, state=state)


def test_interrupted_finalization_never_retries_or_creates_success(
    tmp_path, monkeypatch
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    p = plan(m, state, m.original_evidence(server, OPERATION, state=state))
    with pytest.raises(m.FinalizationError):
        m.finalize(
            p,
            lambda: {**p, "drift": True},
            server,
            evidence_sha256=m.digest(p),
            state=state,
        )
    record = state / "frontend-finalizations" / OPERATION
    assert (record / "intent.json").exists() and not (
        record / "completed.json"
    ).exists()
    with pytest.raises(m.FinalizationError):
        m.finalize(p, lambda: p, server, state=state)
    with pytest.raises(m.FinalizationError):
        m.history_evidence(server, OPERATION, state=state)


def test_history_depends_on_immutable_original_evidence_not_future_live_production(
    tmp_path, monkeypatch
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    p = plan(m, state, m.original_evidence(server, OPERATION, state=state))
    complete = m.finalize(
        p, lambda: p, server, evidence_sha256=m.digest(p), state=state
    )
    assert m.history_evidence(server, OPERATION, state=state) == complete
    assert m.history_evidence(server, OPERATION, state=state)["production_sha"] == SHA
    (audit / "failed.json").write_text("{}")
    with pytest.raises(m.FinalizationError):
        m.history_evidence(server, OPERATION, state=state)


@pytest.mark.parametrize(
    "mutation", ["terminal", "intent", "unknown", "operation_swap", "partial"]
)
def test_history_rejects_tampered_or_replayed_finalization(
    tmp_path, monkeypatch, mutation
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    p = plan(m, state, m.original_evidence(server, OPERATION, state=state))
    m.finalize(p, lambda: p, server, evidence_sha256=m.digest(p), state=state)
    record = state / "frontend-finalizations" / OPERATION
    if mutation == "terminal":
        (record / "completed.json").write_text("{}")
    elif mutation == "intent":
        (record / "intent.json").write_text("{}")
    elif mutation == "unknown":
        (record / "retry.json").write_text("{}")
    elif mutation == "operation_swap":
        record.rename(record.with_name("8" * 32))
    elif mutation == "partial":
        (record / "completed.json").unlink()
    with pytest.raises((m.FinalizationError, FileNotFoundError)):
        m.history_evidence(server, OPERATION, state=state)


def inspect_fixture(m, tmp_path, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        m,
        "EXPECTED_ARTIFACT",
        m.hashlib.sha256(("1" * 64 + "2" * 64).encode()).hexdigest(),
    )
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    original = m.original_evidence(server, OPERATION, state=state)
    plan(m, state, original)
    source = state / "bootstrap" / PUBLISHER / "source"
    production = tmp_path / "production"
    (production / "frontend/.next").mkdir(parents=True)
    (production / "frontend/node_modules").mkdir()
    monkeypatch.setattr(m, "STATE", state)
    monkeypatch.setattr(m, "PRODUCTION", production)
    monkeypatch.setattr(m, "LEASE", tmp_path / "lease")
    monkeypatch.setattr(m, "CGROUPS", tmp_path / "cgroups")
    monkeypatch.setattr(
        m, "__file__", str(source / "scripts/frontend_verified_finalization.py")
    )
    events = []
    fail = {"value": None}

    def guard(event):
        events.append(event)
        if fail["value"] == event:
            raise m.FinalizationError("synthetic " + event)

    def run(args):
        if args[0] == "/usr/bin/systemctl":
            return "\n".join(k + "=" + v for k, v in unit().items())
        assert args == ["/usr/bin/pm2", "jlist"]
        return json.dumps(
            [
                {
                    "name": "health-frontend",
                    "pid": 100,
                    "pm2_env": {
                        "status": "online",
                        "restart_time": 0,
                        "pm_uptime": 123,
                    },
                }
            ]
        )

    def binding(publisher, production_sha, expected, actual, backend, live_sha):
        if (
            expected != actual
            or backend != {"sha": SHA, "state": "SUCCEEDED"}
            or live_sha != SHA
        ):
            raise m.FinalizationError("bad production binding")

    frontend = SimpleNamespace(
        validate_binding=binding,
        git=lambda root, *args: TREE if args[-1] == "HEAD:frontend" else SHA,
        assert_unchanged=lambda *args: guard("snapshot"),
        run=run,
        artifact_digest=lambda p: (
            "changed"
            if fail["value"] == "artifact"
            else ("1" * 64 if p.name == ".next" else "2" * 64)
        ),
        verify_pages=lambda: guard("pages"),
        data_fingerprint=lambda p: ({"inode": 1}, b""),
    )
    bootstrap = SimpleNamespace(
        canonical_source=lambda sha: state / "bootstrap" / sha / "source",
        _read_json=lambda p: {"sha": SHA, "state": "SUCCEEDED"},
        _recovery_process_proof=lambda: guard("processes"),
    )
    gate = SimpleNamespace(
        verify_release=lambda *a: guard("main-ci"),
        _latest=lambda *a: guard("historical-ci"),
        _get_json=None,
    )
    args = (PUBLISHER, SHA, OPERATION, source, None, bootstrap, server, gate, frontend)
    keywords = {
        "check_locks": lambda: guard("locks"),
        "assert_other_history": lambda: guard("other-history"),
    }
    return state, audit, server, args, keywords, events, fail


def test_fresh_inspection_binds_live_proof_and_pending_intent_exactly(
    tmp_path, monkeypatch
):
    m = load()
    state, audit, server, args, kwargs, events, fail = inspect_fixture(
        m, tmp_path, monkeypatch
    )
    p = m.inspect_finalization(*args, **kwargs)
    assert p["build_lock"] is None and p["artifact_digest"] == m.EXPECTED_ARTIFACT
    assert (
        events.count("pages") == 1
        and events.count("snapshot") == 2
        and events.count("processes") == 2
    )
    complete = m.finalize(
        p,
        lambda: m.inspect_finalization(*args, **kwargs),
        server,
        evidence_sha256=m.digest(p),
        state=state,
    )
    assert complete["recovery"]["state"] == m.TERMINAL
    # The historical proof deliberately needs none of the live inspector helpers.
    for name in ("artifact_digest", "verify_pages", "run", "assert_unchanged"):
        setattr(
            args[-1],
            name,
            lambda *a: pytest.fail("historical evidence read live runtime"),
        )
    assert m.history_evidence(server, OPERATION, state=state) == complete


@pytest.mark.parametrize(
    "failure",
    [
        "main-ci",
        "historical-ci",
        "snapshot",
        "pages",
        "processes",
        "locks",
        "other-history",
        "artifact",
        "lease",
        "cgroup",
    ],
)
def test_inspection_blocks_every_unproven_live_boundary(tmp_path, monkeypatch, failure):
    m = load()
    state, audit, server, args, kwargs, events, fail = inspect_fixture(
        m, tmp_path, monkeypatch
    )
    if failure == "lease":
        m.LEASE.mkdir()
    elif failure == "cgroup":
        (m.CGROUPS / f"reva-frontend-build-{OPERATION}.service").mkdir(parents=True)
    else:
        fail["value"] = failure
    with pytest.raises(m.FinalizationError):
        m.inspect_finalization(*args, **kwargs)
    assert not (state / "frontend-finalizations").exists()


def test_post_intent_tampering_cannot_return_a_success_receipt(tmp_path, monkeypatch):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    p = plan(m, state, m.original_evidence(server, OPERATION, state=state))

    def tamper():
        record = state / "frontend-finalizations" / OPERATION
        (record / "intent.json").write_text("{}")
        return p

    with pytest.raises(m.FinalizationError):
        m.finalize(p, tamper, server, evidence_sha256=m.digest(p), state=state)
    assert not (
        state / "frontend-finalizations" / OPERATION / "completed.json"
    ).exists()


def test_pending_intent_cannot_change_operation_or_hash_while_inspecting(
    tmp_path, monkeypatch
):
    m = load()
    state, audit, server, args, kwargs, events, fail = inspect_fixture(
        m, tmp_path, monkeypatch
    )
    p = m.inspect_finalization(*args, **kwargs)
    record = state / "frontend-finalizations" / OPERATION
    record.mkdir(parents=True, mode=0o700)
    record.parent.chmod(0o700)
    value = {**p, "artifact_digest": "f" * 64, "evidence_sha256": m.digest(p)}
    (record / "intent.json").write_text(json.dumps(value))
    (record / "intent.json").chmod(0o600)
    with pytest.raises(m.FinalizationError):
        m.inspect_finalization(*args, **kwargs)
    with pytest.raises(m.FinalizationError, match="retry"):
        m.finalize(p, lambda: p, server, evidence_sha256=m.digest(p), state=state)


def test_live_digest_does_not_ignore_unsafe_descendant_ownership_or_modes(tmp_path):
    import stat

    m = load()
    root = tmp_path / "artifact"
    root.mkdir()
    (root / "nested").mkdir()
    (root / "nested/file").write_text("same bytes")
    (root / "nested/file").chmod(0o666)
    server = Server()

    def validate(info, **kwargs):
        if info.st_mode & 0o022 or not (
            stat.S_ISDIR(info.st_mode)
            if kwargs.get("directory")
            else stat.S_ISREG(info.st_mode)
        ):
            raise m.FinalizationError("unsafe metadata")

    server.validate_metadata = validate
    with pytest.raises(m.FinalizationError):
        m.secure_live_artifact(server, root)


def test_only_execute_completes_missed_parent_fsync_history_never_replays_it(
    tmp_path, monkeypatch
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    p = plan(m, state, m.original_evidence(server, OPERATION, state=state))
    m.finalize(p, lambda: p, server, state=state)
    assert getattr(server, "sync_calls", 0) == 0
    m.finalize(p, lambda: p, server, evidence_sha256=m.digest(p), state=state)
    assert server.sync_calls == 1
    m.history_evidence(server, OPERATION, state=state)
    assert server.sync_calls == 1


def test_parent_fsync_failure_retains_intent_and_original_failure(
    tmp_path, monkeypatch
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    p = plan(m, state, m.original_evidence(server, OPERATION, state=state))
    original = (audit / "failed.json").read_bytes()

    def reject():
        raise m.FinalizationError("strict lease alias changed")

    server._sync_business_lease_parent = reject
    with pytest.raises(m.FinalizationError):
        m.finalize(p, lambda: p, server, evidence_sha256=m.digest(p), state=state)
    record = state / "frontend-finalizations" / OPERATION
    assert (record / "intent.json").exists() and not (
        record / "completed.json"
    ).exists()
    assert (audit / "failed.json").read_bytes() == original
    with pytest.raises(m.FinalizationError):
        m.finalize(p, lambda: p, server, evidence_sha256=m.digest(p), state=state)


def test_protected_archive_accepts_group_writable_data_and_internal_hardlinks(
    tmp_path, monkeypatch
):
    import os

    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    root = audit / "previous-node-modules"
    first = root / "file"
    first.chmod(0o664)
    second = root / "esbuild-alias"
    os.link(first, second)
    proof = m.tree_evidence(server, root)
    assert proof["entries"] == 3
    assert first.stat().st_ino == second.stat().st_ino
    assert first.stat().st_nlink == 2 and first.stat().st_mode & 0o777 == 0o664


@pytest.mark.parametrize("target", ["external", "other_backup"])
def test_archive_hardlinks_must_all_be_inside_one_backup_tree(
    tmp_path, monkeypatch, target
):
    import os

    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    root = audit / "previous-node-modules"
    alias = (
        (tmp_path / "external-alias")
        if target == "external"
        else audit / "previous-next/alias"
    )
    os.link(root / "file", alias)
    with pytest.raises(m.FinalizationError):
        m.tree_evidence(server, root)


@pytest.mark.parametrize("mutation", ["audit_mode", "parent_mode", "path_name"])
def test_archive_exception_requires_exact_private_original_boundary(
    tmp_path, monkeypatch, mutation
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    root = audit / "previous-next"
    if mutation == "audit_mode":
        audit.chmod(0o755)
    elif mutation == "parent_mode":
        audit.parent.chmod(0o755)
    else:
        renamed = audit / "other-backup"
        root.rename(renamed)
        root = renamed
    with pytest.raises(m.FinalizationError):
        m.tree_evidence(server, root)


@pytest.mark.parametrize("mode", [0o666, 0o4644, 0o2644])
def test_inert_archive_does_not_accept_world_write_or_privileged_file_modes(
    tmp_path, monkeypatch, mode
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    root = audit / "previous-next"
    (root / "file").chmod(mode)
    with pytest.raises(m.FinalizationError):
        m.tree_evidence(server, root)


@pytest.mark.parametrize(
    "mutation", ["add_external_link", "replace_alias", "boundary_mode"]
)
def test_archive_rechecks_all_aliases_and_private_boundary_after_read(
    tmp_path, monkeypatch, mutation
):
    import os

    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    root = audit / "previous-node-modules"
    first = root / "file"
    second = root / "alias"
    os.link(first, second)
    (root / "z-trigger").write_bytes(b"late-trigger")
    original_hash = m.hashlib.sha256

    class Hash:
        def __init__(self, *args, **kwargs):
            self.inner = original_hash(*args, **kwargs)

        def update(self, data):
            self.inner.update(data)
            if data == b"late-trigger":
                if mutation == "add_external_link":
                    os.link(first, tmp_path / "late-alias")
                elif mutation == "replace_alias":
                    second.unlink()
                    second.write_text("original backup")
                else:
                    audit.chmod(0o755)

        def hexdigest(self):
            return self.inner.hexdigest()

    monkeypatch.setattr(m.hashlib, "sha256", Hash)
    with pytest.raises(m.FinalizationError):
        m.tree_evidence(server, root)


def test_archived_group_write_mode_remains_part_of_historical_proof(
    tmp_path, monkeypatch
):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    file = audit / "previous-next/file"
    file.chmod(0o664)
    p = plan(m, state, m.original_evidence(server, OPERATION, state=state))
    m.finalize(p, lambda: p, server, evidence_sha256=m.digest(p), state=state)
    file.chmod(0o644)
    with pytest.raises(m.FinalizationError):
        m.history_evidence(server, OPERATION, state=state)


@pytest.mark.parametrize("mutation", ["group_write", "hardlink"])
def test_live_artifact_rules_still_reject_archive_only_exceptions(
    tmp_path, monkeypatch, mutation
):
    import os
    import stat

    m = load()
    root = tmp_path / "live"
    root.mkdir()
    file = root / "file"
    file.write_text("live")
    if mutation == "group_write":
        file.chmod(0o664)
    else:
        os.link(file, root / "alias")
    server = Server()

    def strict(info, *, directory=False, **kwargs):
        if info.st_mode & 0o022 or (
            not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)
        ):
            raise m.FinalizationError("strict live metadata")

    server.validate_metadata = strict
    with pytest.raises(m.FinalizationError):
        m.secure_live_artifact(server, root)


@pytest.mark.parametrize("uid,gid", [(1, 0), (0, 1)])
def test_archive_regular_files_still_require_root_ownership(uid, gid):
    import stat
    from types import SimpleNamespace

    m = load()
    with pytest.raises(m.FinalizationError):
        m.archive_file_metadata(
            SimpleNamespace(
                st_uid=uid, st_gid=gid, st_mode=stat.S_IFREG | 0o664, st_nlink=1
            )
        )


def test_archive_directory_permissions_are_not_relaxed(tmp_path, monkeypatch):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    root = audit / "previous-next"
    child = root / "directory"
    child.mkdir()
    child.chmod(0o775)

    def strict(info, **kwargs):
        if info.st_mode & 0o022:
            raise m.FinalizationError("strict directory mode")

    server.validate_metadata = strict
    with pytest.raises(m.FinalizationError):
        m.tree_evidence(server, root)


@pytest.mark.parametrize("mutation", ["group_write", "hardlink"])
def test_original_private_receipts_do_not_get_archive_exceptions(
    tmp_path, monkeypatch, mutation
):
    import os

    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    path = audit / "verified.json"
    if mutation == "group_write":
        path.chmod(0o664)
    else:
        os.link(path, tmp_path / "outside-receipt")
    with pytest.raises(m.FinalizationError):
        m.file_evidence(server, path)


def test_archive_rejects_lookalike_path_outside_canonical_state(tmp_path, monkeypatch):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    other = tmp_path / "lookalike" / "frontend-rebuilds" / OPERATION
    other.parent.mkdir(parents=True, mode=0o700)
    audit.rename(other)
    with pytest.raises(m.FinalizationError, match="fixed original archive path"):
        m.tree_evidence(server, other / "previous-next")


@pytest.mark.parametrize("spelling", ["relative", "dotdot", "symlink_ancestor"])
def test_archive_rejects_noncanonical_path_ancestry(tmp_path, monkeypatch, spelling):
    m = load()
    state, audit, server = fixture_original(m, tmp_path, monkeypatch)
    root = audit / "previous-next"
    if spelling == "relative":
        monkeypatch.chdir(tmp_path)
        root = root.relative_to(tmp_path)
    elif spelling == "dotdot":
        root = audit / ".." / OPERATION / "previous-next"
    else:
        archive_parent = audit.parent
        saved = state / "saved-original-archive"
        archive_parent.rename(saved)
        archive_parent.symlink_to(saved, target_is_directory=True)

        def strict_path(path, **kwargs):
            # Production secure_path rejects symlinks in every ancestor. Keep
            # this protocol explicit without faking the real symlink fixture.
            if any(part.is_symlink() for part in [path, *path.parents]):
                raise m.FinalizationError("symlink ancestor")

        server.secure_path = strict_path
    with pytest.raises(m.FinalizationError):
        m.tree_evidence(server, root)
