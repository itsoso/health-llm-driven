import json
import os
import stat
import sys
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/scripts"))

import runtime_state_release_transaction as runtime_transaction  # noqa: E402
from runtime_state_release_transaction import (  # noqa: E402
    BOOT_GATE_UNITS,
    CandidatePaths,
    Layout,
    ReleaseTransaction,
    TransactionError,
    UNITS,
    parse_cli,
    production_layout,
)


def test_runtime_state_release_artifacts_exist() -> None:
    assert (ROOT / "backend/scripts/runtime_state_release_transaction.py").is_file()
    for name in (
        "health-backend-runtime-state.conf",
        "celery-worker-runtime-state.conf",
        "celery-beat-runtime-state.conf",
    ):
        assert (ROOT / "infra/systemd/dropins" / name).is_file()


class FakeSystemd:
    def __init__(
        self,
        layout: Layout,
        *,
        old_schedule: Path,
        enablement: dict[str, str] | None = None,
        old_upload_authority: str = "legacy",
    ) -> None:
        self.layout = layout
        self.old_schedule = old_schedule
        self.events: list[str] = []
        self.active_state = "inactive"
        self.active_states: dict[str, str] = {}
        self.candidate_beat_extra_runtime = False
        self.old_upload_authority = old_upload_authority
        self.enablement = enablement or {
            "health-backend.socket": "enabled",
            "health-backend.service": "enabled",
            "celery-worker.service": "enabled",
            "celery-beat.service": "enabled",
        }
        self.exec_start_queries = 0
        self.flip_schedule_on_query: int | None = None
        self.clear_exec_runtime_metadata_on_disable = False
        self.exec_runtime_metadata_cleared = False
        self.extra_candidate_exec_record_unit: str | None = None
        self.changed_candidate_exec_unit: str | None = None
        self.static_exec_change_on_disable: str | None = None

    def daemon_reload(self) -> None:
        self.events.append("daemon-reload")

    def is_enabled(self, unit: str) -> str:
        self.events.append(f"is-enabled:{unit}")
        return self.enablement[unit]

    def disable(self, unit: str) -> None:
        self.events.append(f"disable:{unit}")
        if self.enablement[unit] == "enabled":
            self.enablement[unit] = "disabled"
        if self.clear_exec_runtime_metadata_on_disable:
            self.exec_runtime_metadata_cleared = True

    def enable(self, unit: str) -> None:
        self.events.append(f"enable:{unit}")
        if self.enablement[unit] == "disabled":
            self.enablement[unit] = "enabled"

    def show(self, unit: str, prop: str) -> str:
        if prop == "ActiveState":
            return self.active_states.get(unit, self.active_state)
        live = self.layout.live_dropins[unit]
        candidate_installed = (
            live.is_file()
            and live.read_bytes() == self.layout.candidate_dropins[unit].read_bytes()
        )
        if prop == "DropInPaths":
            return str(live) if live.exists() else ""
        if prop == "FragmentPath":
            return str(self.layout.base_units[unit])
        if prop == "ExecStart":
            if unit == "celery-beat.service":
                self.exec_start_queries += 1
            schedule = (
                self.layout.current_shelf_base
                if (
                    candidate_installed
                    or self.exec_start_queries == self.flip_schedule_on_query
                )
                and unit == "celery-beat.service"
                else self.old_schedule
            )
            if unit == "celery-beat.service":
                command = (
                    "/opt/health-app/backend/venv/bin/celery "
                    "-A app.celery_app:celery_app beat --loglevel=info "
                    f"--schedule={schedule}"
                )
            elif unit == "health-backend.service" and candidate_installed:
                command = runtime_transaction.BACKEND_EXEC_START_ARGV
            else:
                command = f"/opt/health-app/{unit}"
            path = command.split()[0]
            ignore_errors = "no"
            if self.exec_runtime_metadata_cleared:
                if self.static_exec_change_on_disable == "path":
                    changed = f"{path}.changed"
                    command = changed + command[len(path) :]
                    path = changed
                elif self.static_exec_change_on_disable == "argv":
                    command += " --unexpected-static-change=true"
                elif self.static_exec_change_on_disable == "ignore_errors":
                    ignore_errors = "yes"
            if candidate_installed and unit == self.changed_candidate_exec_unit:
                command += " --unexpected-candidate-change=true"
            if self.exec_runtime_metadata_cleared:
                runtime = (
                    "start_time=[n/a] ; stop_time=[n/a] ; pid=0 ; "
                    "code=(null) ; status=0/0"
                )
            else:
                runtime = (
                    "start_time=[Thu 2026-07-30 22:15:44 CST] ; "
                    "stop_time=[Thu 2026-07-30 22:15:55 CST] ; "
                    "pid=523354 ; code=exited ; status=0"
                )
            record = (
                f"{{ path={path} ; argv[]={command} ; "
                f"ignore_errors={ignore_errors} ; "
                f"{runtime} }}"
            )
            if candidate_installed and unit == self.extra_candidate_exec_record_unit:
                extra = (
                    "{ path=/bin/true ; argv[]=/bin/true ; "
                    "ignore_errors=no ; start_time=[n/a] ; "
                    "stop_time=[n/a] ; pid=0 ; code=(null) ; status=0/0 }"
                )
                return f"{record} {extra}"
            return record
        if prop == "ReadWritePaths":
            if candidate_installed:
                if unit == "celery-beat.service":
                    value = str(self.layout.beat_state_dir)
                    if self.candidate_beat_extra_runtime:
                        value += f" {self.layout.runtime_root}"
                    return value
                if unit == "health-backend.service":
                    return (
                        f"{self.layout.uploads_root} "
                        f"{self.layout.skills_cache_root} "
                        f"{self.layout.runtime_root} "
                        f"{self.layout.dedao_container}"
                    )
                return f"{self.layout.uploads_root} {self.layout.dedao_container}"
            if unit in {"health-backend.service", "celery-worker.service"}:
                upload_root = (
                    self.layout.uploads_root
                    if self.old_upload_authority == "external"
                    else self.layout.legacy_uploads
                )
                return f"{upload_root} {self.layout.backend_data}"
            return str(self.layout.backend_data)
        raise AssertionError((unit, prop))


def _copy_candidates(stage: Path) -> CandidatePaths:
    stage.mkdir(parents=True)
    stage.chmod(0o700)
    names = {
        "health-backend.service": "health-backend-runtime-state.conf",
        "celery-worker.service": "celery-worker-runtime-state.conf",
        "celery-beat.service": "celery-beat-runtime-state.conf",
    }
    paths = {}
    for unit, name in names.items():
        target = stage / name
        target.write_bytes(runtime_transaction._expected_candidate(unit))
        target.chmod(0o600)
        paths[unit] = target
    return CandidatePaths(paths)


def _layout(tmp_path: Path) -> Layout:
    repo = tmp_path / "opt/health-app"
    backend_data = repo / "backend/data"
    backend_data.mkdir(parents=True)
    backend_data.chmod(0o700)
    stage = tmp_path / "stage"
    candidates = _copy_candidates(stage)
    systemd_root = tmp_path / "etc/systemd/system"
    systemd_root.mkdir(parents=True)
    for unit in (
        "health-backend.socket",
        "health-backend.service",
        "celery-worker.service",
        "celery-beat.service",
    ):
        base_unit = systemd_root / unit
        base_unit.write_text(f"[Service]\n# {unit}\n")
        base_unit.chmod(0o644)
    var_lib = tmp_path / "var/lib/health-app"
    var_lib.mkdir(parents=True)
    var_cache = tmp_path / "var/cache"
    var_cache.mkdir(parents=True)
    (var_lib / "dedao-kbase-review").mkdir(mode=0o755)
    release_state = var_lib / "release-state"
    release_state.mkdir(mode=0o700)
    return Layout(
        repo_root=repo,
        runtime_root=var_lib / "runtime",
        skills_cache_root=var_cache / "health-app/skills-hub",
        beat_state_dir=var_lib / "celery-beat",
        dedao_legacy_root=var_lib / "dedao-kbase-review",
        dedao_container=var_lib / "dedao-kbase",
        systemd_root=systemd_root,
        release_stage=stage,
        transaction_root=release_state / "runtime-state-transaction",
        candidate_dropins=candidates,
        health_uid=os.getuid(),
        health_gid=os.getgid(),
        root_uid=os.getuid(),
        root_gid=os.getgid(),
        require_root=False,
    )


def _replacement_stage(tmp_path: Path, layout: Layout) -> Layout:
    stage = tmp_path / "replacement-stage"
    return replace(
        layout,
        release_stage=stage,
        candidate_dropins=_copy_candidates(stage),
    )


def _lock(
    tmp_path: Path,
    *,
    stage: Path | None = None,
) -> tuple[Path, str]:
    lock_dir = tmp_path / "release.lock"
    lock_dir.mkdir(mode=0o700)
    token = "release-owner"
    (lock_dir / "token").write_text(token + "\n", encoding="utf-8")
    (lock_dir / "token").chmod(0o600)
    (lock_dir / "stage").write_text(
        str(stage or (tmp_path / "stage")) + "\n",
        encoding="utf-8",
    )
    (lock_dir / "stage").chmod(0o600)
    return lock_dir, token


def _bind_lock_stage(lock_dir: Path, stage: Path) -> None:
    (lock_dir / "stage").write_text(str(stage) + "\n", encoding="utf-8")
    (lock_dir / "stage").chmod(0o600)


def _write_shelf(base: Path, suffix: str, value: bytes) -> Path:
    base.parent.mkdir(parents=True, exist_ok=True)
    target = Path(f"{base}{suffix}")
    target.write_bytes(value)
    target.chmod(0o600)
    return target


def _journal(layout: Layout) -> dict:
    return json.loads(
        (layout.transaction_root / "journal.json").read_text(encoding="utf-8")
    )


def _terminal_marker(layout: Layout) -> dict:
    return json.loads(
        (layout.transaction_root.parent / "runtime-state-terminal.json").read_text(
            encoding="utf-8"
        )
    )


def _tree_state(path: Path):
    current = path.lstat()
    metadata = (
        current.st_uid,
        current.st_gid,
        stat.S_IMODE(current.st_mode),
    )
    if path.is_file():
        return ("file", metadata, path.read_bytes())
    return (
        "dir",
        metadata,
        {
            child.name: _tree_state(child)
            for child in sorted(path.iterdir(), key=lambda item: item.name)
        },
    )


def _mark_boot_gate_active(transaction: ReleaseTransaction) -> None:
    transaction.systemd.active_state = "active"


def _transaction(
    tmp_path: Path,
    *,
    layout: Layout | None = None,
    old_schedule: Path | None = None,
    event_sink=None,
    fault_hook=None,
    enablement: dict[str, str] | None = None,
    old_upload_authority: str = "legacy",
) -> tuple[ReleaseTransaction, Layout, Path, str]:
    layout = layout or _layout(tmp_path)
    systemd = FakeSystemd(
        layout,
        old_schedule=old_schedule or layout.legacy_shelf_base,
        enablement=enablement,
        old_upload_authority=old_upload_authority,
    )
    lock_dir, token = _lock(tmp_path, stage=layout.release_stage)
    return (
        ReleaseTransaction(
            layout,
            systemd,
            event_sink=event_sink,
            fault_hook=fault_hook,
        ),
        layout,
        lock_dir,
        token,
    )


def test_production_layout_and_cli_do_not_accept_path_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "runtime_state_release_transaction.pwd.getpwnam",
        lambda _name: SimpleNamespace(pw_uid=123),
    )
    monkeypatch.setattr(
        "runtime_state_release_transaction.grp.getgrnam",
        lambda _name: SimpleNamespace(gr_gid=456),
    )
    stage = Path("/tmp/health-app-backup-preflight-123-456")
    layout = production_layout(stage)

    assert layout.repo_root == Path("/opt/health-app")
    assert layout.runtime_root == Path("/var/lib/health-app/runtime")
    assert layout.legacy_uploads == Path("/opt/health-app/backend/uploads")
    assert layout.uploads_root == Path("/var/lib/health-app/uploads")
    assert layout.skills_cache_root == Path("/var/cache/health-app/skills-hub")
    assert layout.beat_state_dir == Path("/var/lib/health-app/celery-beat")
    assert layout.dedao_legacy_root == Path("/var/lib/health-app/dedao-kbase-review")
    assert layout.dedao_workspace == Path("/var/lib/health-app/dedao-kbase/workspace")
    assert layout.release_stage == stage
    assert layout.transaction_root == Path(
        "/var/lib/health-app/release-state/runtime-state-transaction"
    )
    assert layout.transaction_root.parent == Path("/var/lib/health-app/release-state")
    assert layout.live_dropins["celery-beat.service"] == Path(
        "/etc/systemd/system/celery-beat.service.d/90-runtime-state.conf"
    )
    with pytest.raises(TransactionError, match="release stage"):
        production_layout(Path("/tmp/operator-controlled"))
    with pytest.raises(TransactionError):
        parse_cli(
            [
                "preflight",
                "a" * 40,
                "b" * 40,
                str(tmp_path),
                "valid-token",
                "/tmp/injected",
            ]
        )
    with pytest.raises(TransactionError):
        parse_cli(
            [
                "preflight",
                "a" * 40,
                "b" * 40,
                str(tmp_path),
                "bad';touch-/tmp/pwn",
            ]
        )
    status = parse_cli(["status", str(tmp_path), "valid-token"])
    assert status.command == "status"
    assert status.first_sha is None
    for command in ("release-gate", "finalize"):
        arguments = parse_cli([command, "a" * 40, str(tmp_path), "valid-token"])
        assert arguments.command == command
        assert arguments.first_sha == "a" * 40


def test_subprocess_systemd_enablement_uses_fixed_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict]] = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[1] == "is-enabled":
            return SimpleNamespace(returncode=1, stdout="disabled\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(runtime_transaction.subprocess, "run", fake_run)
    systemd = runtime_transaction.SubprocessSystemd()

    assert systemd.is_enabled("health-backend.socket") == "disabled"
    systemd.disable("health-backend.socket")
    systemd.enable("health-backend.socket")

    assert [call[0] for call in calls] == [
        ["/usr/bin/systemctl", "is-enabled", "health-backend.socket"],
        ["/usr/bin/systemctl", "disable", "health-backend.socket"],
        ["/usr/bin/systemctl", "enable", "health-backend.socket"],
    ]
    assert all("shell" not in kwargs for _, kwargs in calls)


def test_prepare_rejects_effective_authority_change_before_journal(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.systemd.flip_schedule_on_query = 2

    with pytest.raises(TransactionError, match="effective config changed"):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    assert not layout.transaction_root.exists()


def test_prepare_ignores_execstart_runtime_metadata_reset_after_boot_gate(
    tmp_path: Path,
) -> None:
    transaction, _layout, lock_dir, token = _transaction(tmp_path)
    transaction.systemd.clear_exec_runtime_metadata_on_disable = True

    assert transaction.prepare(
        "a" * 40,
        "b" * 40,
        lock_dir,
        token,
    ) == "PREPARED"


@pytest.mark.parametrize("change", ("path", "argv", "ignore_errors"))
def test_prepare_rejects_static_execstart_change_after_boot_gate(
    tmp_path: Path,
    change: str,
) -> None:
    transaction, _layout, lock_dir, token = _transaction(tmp_path)
    transaction.systemd.clear_exec_runtime_metadata_on_disable = True
    transaction.systemd.static_exec_change_on_disable = change

    with pytest.raises(TransactionError, match="effective config changed"):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)


def test_prepare_canonicalizes_legacy_raw_arming_journal_after_boot_gate(
    tmp_path: Path,
) -> None:
    def fail_after_gate(point: str) -> None:
        if point == "prepare:after-gate":
            raise OSError("simulated old-runner interruption")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=fail_after_gate,
    )
    raw_exec_start = {
        unit: transaction.systemd.show(unit, "ExecStart")
        for unit in UNITS
    }
    transaction.systemd.clear_exec_runtime_metadata_on_disable = True

    with pytest.raises(OSError, match="old-runner interruption"):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    journal = _journal(layout)
    assert journal["phase"] == "ARMING"
    assert journal["boot_gate_armed"] is True
    for unit in UNITS:
        journal["old_effective"][unit]["ExecStart"] = raw_exec_start[unit]
    journal_path = layout.transaction_root / "journal.json"
    journal_path.write_text(
        json.dumps(journal, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    journal_path.chmod(0o600)
    transaction._fault_hook = lambda _point: None

    assert transaction.prepare(
        "a" * 40,
        "b" * 40,
        lock_dir,
        token,
    ) == "PREPARED"
    persisted = _journal(layout)
    assert persisted["phase"] == "PREPARED"
    for unit in UNITS:
        assert persisted["old_effective"][unit]["ExecStart"].startswith("path=")


def test_execstart_stability_parser_rejects_multiple_command_records(
    tmp_path: Path,
) -> None:
    transaction, _layout, _lock_dir, _token = _transaction(tmp_path)
    command = transaction.systemd.show("health-backend.service", "ExecStart")

    with pytest.raises(TransactionError, match="unsupported systemd ExecStart shape"):
        transaction._stable_exec_start(f"{command} {command}")


def test_execstart_stability_parser_rejects_unknown_fields(
    tmp_path: Path,
) -> None:
    transaction, _layout, _lock_dir, _token = _transaction(tmp_path)
    command = transaction.systemd.show("health-backend.service", "ExecStart")
    command_with_unknown = command.replace(
        " ; ignore_errors=",
        " ; unknown=surprise ; ignore_errors=",
        1,
    )

    with pytest.raises(TransactionError, match="unsupported systemd ExecStart shape"):
        transaction._stable_exec_start(command_with_unknown)

    stable = transaction._stable_exec_start(command)
    stable_with_unknown = stable.replace(
        "\nignore_errors=",
        " ; unknown=surprise\nignore_errors=",
        1,
    )
    with pytest.raises(TransactionError, match="unsupported systemd ExecStart shape"):
        transaction._stable_exec_start(stable_with_unknown)


def test_execstart_stability_parser_accepts_systemd_v249_realtime_signal_status(
    tmp_path: Path,
) -> None:
    transaction, _layout, _lock_dir, _token = _transaction(tmp_path)
    command = transaction.systemd.show("health-backend.service", "ExecStart")
    realtime_signal = command.replace(
        "code=exited ; status=0",
        "code=killed ; status=35/RTMIN+1",
        1,
    )

    assert transaction._stable_exec_start(realtime_signal) == (
        transaction._stable_exec_start(command)
    )


def test_malformed_old_effective_is_rejected_before_restore_mutation(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = _write_shelf(layout.legacy_shelf_base, ".db", b"before")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    legacy.write_bytes(b"after")
    journal = _journal(layout)
    journal["old_effective"]["health-backend.service"]["ExecStart"] = (
        journal["old_effective"]["health-backend.service"]["ExecStart"].replace(
            "\nignore_errors=",
            " ; unknown=surprise\nignore_errors=",
            1,
        )
    )
    journal_path = layout.transaction_root / "journal.json"
    journal_path.write_text(
        json.dumps(journal, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    journal_path.chmod(0o600)

    with pytest.raises(TransactionError, match="unsupported systemd ExecStart shape"):
        transaction.restore("a" * 40, lock_dir, token)

    assert legacy.read_bytes() == b"after"


@pytest.mark.parametrize(
    "corruption",
    (
        "metadata-missing-key",
        "metadata-required-none",
        "metadata-bool-uid",
        "metadata-unsafe-mode",
        "metadata-runtime-root-cross-field",
        "metadata-beat-state-cross-field",
        "snapshot-missing-top-level",
        "snapshot-missing-record-field",
        "snapshot-bool-gid",
        "snapshot-unsafe-mode",
    ),
)
def test_malformed_restore_schema_is_rejected_before_any_restore_mutation(
    tmp_path: Path,
    corruption: str,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = _write_shelf(layout.legacy_shelf_base, ".db", b"before")
    if corruption == "metadata-runtime-root-cross-field":
        layout.runtime_root.mkdir(mode=0o700)
        runtime_gene = layout.runtime_root / "gene_knowledge.json"
        runtime_gene.write_text("runtime-before", encoding="utf-8")
        runtime_gene.chmod(0o600)
    if corruption == "metadata-beat-state-cross-field":
        _write_shelf(layout.current_shelf_base, ".db", b"current-before")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    legacy.write_bytes(b"after")
    journal = _journal(layout)
    if corruption == "metadata-missing-key":
        del journal["metadata"]["runtime_root"]
    elif corruption == "metadata-required-none":
        journal["metadata"]["backend_data"] = None
    elif corruption == "metadata-bool-uid":
        journal["metadata"]["backend_data"]["uid"] = True
    elif corruption == "metadata-unsafe-mode":
        journal["metadata"]["backend_data"]["mode"] = 0o777
    elif corruption == "metadata-runtime-root-cross-field":
        journal["metadata"]["runtime_root"] = None
    elif corruption == "metadata-beat-state-cross-field":
        journal["metadata"]["beat_state_dir"] = None
    elif corruption == "snapshot-missing-top-level":
        del journal["snapshots"]["runtime_current"]
    else:
        record = journal["snapshots"]["shelf"]["legacy"][".db"]
        if corruption == "snapshot-missing-record-field":
            del record["uid"]
        elif corruption == "snapshot-bool-gid":
            record["gid"] = False
        elif corruption == "snapshot-unsafe-mode":
            record["mode"] = 0o666
        else:  # pragma: no cover - parameter list is exhaustive
            raise AssertionError(corruption)
    journal_path = layout.transaction_root / "journal.json"
    journal_path.write_text(
        json.dumps(journal, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    journal_path.chmod(0o600)

    with pytest.raises(TransactionError):
        transaction.restore("a" * 40, lock_dir, token)

    assert legacy.read_bytes() == b"after"
    assert _journal(layout)["phase"] == "PREPARED"


def test_prepare_crash_after_snapshot_publish_rebuilds_snapshot_on_reentry(
    tmp_path: Path,
) -> None:
    def crash_after_snapshot_publish(point: str) -> None:
        if point == "prepare:after-snapshot-publish":
            raise OSError("simulated snapshot publish interruption")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_after_snapshot_publish,
    )
    legacy_gene = layout.backend_data / "gene_knowledge.json"
    legacy_gene.write_text("before-interruption", encoding="utf-8")

    with pytest.raises(OSError, match="snapshot publish interruption"):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    interrupted = _journal(layout)
    assert interrupted["phase"] == "ARMING"
    assert interrupted["boot_gate_armed"] is True
    assert "snapshots" not in interrupted
    assert (layout.transaction_root / "snapshots").is_dir()
    legacy_gene.write_text("after-interruption", encoding="utf-8")
    transaction._fault_hook = lambda _point: None

    assert transaction.prepare(
        "a" * 40,
        "b" * 40,
        lock_dir,
        token,
    ) == "PREPARED"
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    assert (layout.runtime_root / "gene_knowledge.json").read_text(
        encoding="utf-8"
    ) == "after-interruption"


@pytest.mark.parametrize("unit", UNITS)
def test_candidate_effective_rejects_additional_execstart_record(
    tmp_path: Path,
    unit: str,
) -> None:
    transaction, _layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.systemd.extra_candidate_exec_record_unit = unit

    with pytest.raises(TransactionError, match="unsupported systemd ExecStart shape"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)


def test_candidate_effective_installs_single_worker_backend_execstart(
    tmp_path: Path,
) -> None:
    transaction, _layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    assert transaction.install("a" * 40, "b" * 40, lock_dir, token) == "INSTALLED"
    effective = transaction.systemd.show("health-backend.service", "ExecStart")
    assert "--workers 1" in effective
    assert "--workers 2" not in effective


@pytest.mark.parametrize("unit", UNITS)
def test_candidate_effective_rejects_changed_static_execstart(
    tmp_path: Path,
    unit: str,
) -> None:
    transaction, _layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.systemd.changed_candidate_exec_unit = unit

    with pytest.raises(TransactionError, match="candidate ExecStart mismatch"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)


def test_prepare_arms_exact_boot_gate_and_reentry_repairs_it(
    tmp_path: Path,
) -> None:
    enablement = {
        "health-backend.socket": "enabled",
        "health-backend.service": "static",
        "celery-worker.service": "disabled",
        "celery-beat.service": "enabled",
    }
    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        enablement=enablement,
    )

    assert transaction.prepare("a" * 40, "b" * 40, lock_dir, token) == "PREPARED"

    journal = _journal(layout)
    assert journal["original_enablement"] == {
        "health-backend.socket": "enabled",
        "health-backend.service": "static",
        "celery-worker.service": "disabled",
        "celery-beat.service": "enabled",
    }
    assert journal["boot_gate_armed"] is True
    assert journal["boot_gate_released"] is False
    assert enablement == {
        "health-backend.socket": "disabled",
        "health-backend.service": "static",
        "celery-worker.service": "disabled",
        "celery-beat.service": "disabled",
    }
    assert [
        event for event in transaction.systemd.events if event.startswith("disable:")
    ] == [
        "disable:health-backend.socket",
        "disable:celery-beat.service",
    ]

    enablement["health-backend.socket"] = "enabled"
    assert transaction.prepare("a" * 40, "b" * 40, lock_dir, token) == "PREPARED"
    assert enablement["health-backend.socket"] == "disabled"


def test_prepare_crash_after_persistent_journal_can_rearm_on_reentry(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_after_persist(point: str) -> None:
        nonlocal crashed
        if not crashed and point == "prepare:after-intent":
            crashed = True
            raise OSError("simulated power loss")

    enablement = {
        unit: "enabled"
        for unit in (
            "health-backend.socket",
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        )
    }
    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        enablement=enablement,
        fault_hook=crash_after_persist,
    )
    legacy_gene = layout.backend_data / "gene_knowledge.json"
    legacy_gene.write_text("before-reboot", encoding="utf-8")

    with pytest.raises(OSError, match="simulated power loss"):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    assert layout.transaction_root.is_dir()
    assert _journal(layout)["phase"] == "ARMING"
    assert _journal(layout)["boot_gate_armed"] is False
    assert "snapshots" not in _journal(layout)
    assert set(enablement.values()) == {"enabled"}
    legacy_gene.write_text("after-reboot", encoding="utf-8")

    resumed = ReleaseTransaction(
        layout,
        FakeSystemd(
            layout,
            old_schedule=layout.legacy_shelf_base,
            enablement=enablement,
        ),
    )
    assert resumed.prepare("a" * 40, "b" * 40, lock_dir, token) == "PREPARED"
    assert _journal(layout)["boot_gate_armed"] is True
    assert set(enablement.values()) == {"disabled"}
    resumed.install("a" * 40, "b" * 40, lock_dir, token)
    assert (layout.runtime_root / "gene_knowledge.json").read_text(
        encoding="utf-8"
    ) == "after-reboot"


def test_prepare_publish_crash_recovers_exact_sibling_and_blocks_other_release(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_before_publish(point: str) -> None:
        nonlocal crashed
        if not crashed and point == "prepare:before-intent-publish":
            crashed = True
            raise OSError("simulated intent publish crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_before_publish,
    )
    with pytest.raises(OSError, match="intent publish crash"):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    preparing = layout.transaction_root.parent / (
        ".runtime-state-transaction.preparing"
    )
    assert preparing.is_dir()
    assert not layout.transaction_root.exists()

    other_lock_parent = tmp_path / "other-preparing-owner"
    other_lock_parent.mkdir()
    replacement = _replacement_stage(tmp_path, layout)
    other_lock_dir, other_token = _lock(
        other_lock_parent,
        stage=replacement.release_stage,
    )
    blocked = ReleaseTransaction(
        replacement,
        FakeSystemd(
            replacement,
            old_schedule=replacement.legacy_shelf_base,
            enablement=transaction.systemd.enablement,
        ),
    )
    with pytest.raises(TransactionError, match="different release"):
        blocked.prepare(
            "c" * 40,
            "d" * 40,
            other_lock_dir,
            other_token,
        )
    assert preparing.is_dir()

    assert (
        blocked.prepare(
            "a" * 40,
            "b" * 40,
            other_lock_dir,
            other_token,
        )
        == "PREPARED"
    )
    assert not preparing.exists()
    assert layout.transaction_root.is_dir()


def test_preflight_provisions_exact_secure_persistent_parent(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    layout.transaction_root.parent.rmdir()
    transaction, _, lock_dir, token = _transaction(
        tmp_path,
        layout=layout,
    )

    assert transaction.preflight("a" * 40, "b" * 40, lock_dir, token) == "legacy"
    parent = layout.transaction_root.parent
    assert parent.is_dir()
    assert stat.S_IMODE(parent.stat().st_mode) == 0o700
    assert parent.stat().st_uid == layout.root_uid
    assert parent.stat().st_gid == layout.root_gid


def test_release_lock_binds_exact_stage_before_any_transaction_mutation(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    replacement = _replacement_stage(tmp_path, layout)
    wrong_stage = ReleaseTransaction(
        replacement,
        FakeSystemd(
            replacement,
            old_schedule=replacement.legacy_shelf_base,
        ),
    )

    with pytest.raises(TransactionError, match="release lock stage"):
        wrong_stage.preflight("a" * 40, "b" * 40, lock_dir, token)

    assert not layout.transaction_root.exists()
    assert transaction.status(lock_dir, token).startswith("phase=NONE ")


def test_legacy_old_preflight_rejects_unproven_external_upload_content(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = layout.legacy_uploads / "chat/7/current.jpg"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"authoritative")
    unproven = layout.uploads_root / "chat/7/deleted-private.jpg"
    unproven.parent.mkdir(parents=True)
    unproven.write_bytes(b"stale-external")

    with pytest.raises(
        TransactionError,
        match="old legacy upload authority has unproven external content",
    ):
        transaction.preflight("a" * 40, "b" * 40, lock_dir, token)

    assert unproven.read_bytes() == b"stale-external"
    assert legacy.read_bytes() == b"authoritative"
    assert not layout.transaction_root.exists()


def test_install_fails_if_any_boot_gate_entry_is_not_armed(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.systemd.enablement["celery-worker.service"] = "enabled"

    with pytest.raises(TransactionError, match="boot gate"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert not layout.runtime_root.exists()


def test_prepare_rejects_unknown_enablement_state_before_intent(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.systemd.enablement["celery-beat.service"] = "indirect"

    with pytest.raises(TransactionError, match="unsupported is-enabled"):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    assert not layout.transaction_root.exists()


def test_reboot_after_install_crash_uses_persistent_journal_and_new_stage(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_during_install(point: str) -> None:
        nonlocal crashed
        if not crashed and point.endswith("celerybeat-schedule.db:after-rename"):
            crashed = True
            raise OSError("simulated install power loss")

    enablement = {
        unit: "enabled"
        for unit in (
            "health-backend.socket",
            "health-backend.service",
            "celery-worker.service",
            "celery-beat.service",
        )
    }
    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        enablement=enablement,
        fault_hook=crash_during_install,
    )
    _write_shelf(layout.legacy_shelf_base, ".db", b"legacy")
    _write_shelf(layout.current_shelf_base, ".db", b"old-current")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    with pytest.raises(OSError, match="simulated install power loss"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    replacement = _replacement_stage(tmp_path, layout)
    _bind_lock_stage(lock_dir, replacement.release_stage)
    resumed = ReleaseTransaction(
        replacement,
        FakeSystemd(
            replacement,
            old_schedule=replacement.legacy_shelf_base,
            enablement=enablement,
        ),
    )
    assert resumed.prepare("a" * 40, "b" * 40, lock_dir, token) == "PREPARED"
    assert replacement.transaction_root == layout.transaction_root
    assert _journal(replacement)["boot_gate_armed"] is True
    assert set(enablement.values()) == {"disabled"}

    other_lock_parent = tmp_path / "other-owner"
    other_lock_parent.mkdir()
    other_lock_dir, other_token = _lock(
        other_lock_parent,
        stage=replacement.release_stage,
    )
    with pytest.raises(TransactionError, match="different release"):
        resumed.prepare(
            "c" * 40,
            "d" * 40,
            other_lock_dir,
            other_token,
        )

    assert resumed.restore("a" * 40, lock_dir, token) == "restored"
    assert set(enablement.values()) == {"disabled"}


def test_status_recovers_authoritative_shas_with_new_lock_owner(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    replacement = _replacement_stage(tmp_path, layout)
    new_lock_parent = tmp_path / "reboot-owner"
    new_lock_parent.mkdir()
    new_lock_dir, new_token = _lock(
        new_lock_parent,
        stage=replacement.release_stage,
    )
    resumed = ReleaseTransaction(
        replacement,
        FakeSystemd(
            replacement,
            old_schedule=replacement.legacy_shelf_base,
            enablement=transaction.systemd.enablement,
        ),
    )

    assert resumed.status(new_lock_dir, new_token) == (
        f"phase=PREPARED old_sha={'a' * 40} "
        f"candidate_sha={'b' * 40} gate_armed=true "
        "gate_released=false release_target=none "
        "next_action=install state_source=journal"
    )
    assert (
        resumed.prepare(
            "a" * 40,
            "b" * 40,
            new_lock_dir,
            new_token,
        )
        == "PREPARED"
    )


def test_status_reports_explicit_none_before_first_transaction(
    tmp_path: Path,
) -> None:
    transaction, _, lock_dir, token = _transaction(tmp_path)

    assert transaction.status(lock_dir, token) == (
        "phase=NONE old_sha=none candidate_sha=none "
        "gate_armed=false gate_released=false "
        "release_target=none next_action=preflight state_source=none"
    )


def test_old_restore_stays_gated_until_idempotent_release_gate(
    tmp_path: Path,
) -> None:
    enablement = {
        "health-backend.socket": "enabled",
        "health-backend.service": "static",
        "celery-worker.service": "disabled",
        "celery-beat.service": "enabled",
    }
    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        enablement=enablement,
    )
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert transaction.restore("a" * 40, lock_dir, token) == "restored"
    assert enablement == {
        "health-backend.socket": "disabled",
        "health-backend.service": "static",
        "celery-worker.service": "disabled",
        "celery-beat.service": "disabled",
    }
    assert _journal(layout)["phase"] == "RESTORED"
    assert _journal(layout)["boot_gate_released"] is False

    _mark_boot_gate_active(transaction)
    assert transaction.release_gate("a" * 40, lock_dir, token) == "RESTORE_FINALIZED"
    assert enablement == {
        "health-backend.socket": "enabled",
        "health-backend.service": "static",
        "celery-worker.service": "disabled",
        "celery-beat.service": "enabled",
    }
    assert not layout.transaction_root.exists()
    assert _terminal_marker(layout)["phase"] == "RESTORE_FINALIZED"
    assert _terminal_marker(layout)["terminal_sha"] == "a" * 40
    enable_events = [
        event for event in transaction.systemd.events if event.startswith("enable:")
    ]
    assert transaction.release_gate("a" * 40, lock_dir, token) == ("RESTORE_FINALIZED")
    assert [
        event for event in transaction.systemd.events if event.startswith("enable:")
    ] == enable_events


def test_release_intent_blocks_opposite_restore_after_partial_enable(
    tmp_path: Path,
) -> None:
    failed = False

    def fail_after_first_enable(point: str) -> None:
        nonlocal failed
        if not failed and point.endswith("health-backend.socket:after-enable"):
            failed = True
            raise OSError("simulated reboot during release")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=fail_after_first_enable,
    )
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    transaction.restore("a" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)

    with pytest.raises(OSError, match="simulated reboot during release"):
        transaction.release_gate("a" * 40, lock_dir, token)

    assert _journal(layout)["release_target"] == "old"
    assert _journal(layout)["boot_gate_released"] is False
    with pytest.raises(TransactionError, match="irrevocable"):
        transaction.restore("b" * 40, lock_dir, token)

    resumed = ReleaseTransaction(
        layout,
        FakeSystemd(
            layout,
            old_schedule=layout.legacy_shelf_base,
            enablement=transaction.systemd.enablement,
        ),
    )
    _mark_boot_gate_active(resumed)
    assert resumed.release_gate("a" * 40, lock_dir, token) == "RESTORE_FINALIZED"
    assert not layout.transaction_root.exists()


def test_release_gate_revalidates_old_effective_after_durable_intent(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_after_old_intent(point: str) -> None:
        nonlocal crashed
        if not crashed and point == "release-gate:after-release-intent":
            crashed = True
            raise OSError("simulated reboot after old release intent")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_after_old_intent,
    )
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    transaction.restore("a" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)

    with pytest.raises(OSError, match="old release intent"):
        transaction.release_gate("a" * 40, lock_dir, token)

    transaction.systemd.old_schedule = layout.current_shelf_base
    with pytest.raises(TransactionError, match="old effective config mismatch"):
        transaction.release_gate("a" * 40, lock_dir, token)

    assert _journal(layout)["release_target"] == "old"
    assert _journal(layout)["boot_gate_released"] is False
    assert set(transaction.systemd.enablement.values()) == {"disabled"}


@pytest.mark.parametrize("inactive_unit", BOOT_GATE_UNITS)
def test_old_release_gate_requires_every_boot_gated_unit_active(
    tmp_path: Path,
    inactive_unit: str,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    transaction.restore("a" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)
    transaction.systemd.active_states[inactive_unit] = "inactive"

    with pytest.raises(TransactionError, match="must be active"):
        transaction.release_gate("a" * 40, lock_dir, token)

    assert _journal(layout)["release_target"] is None
    assert set(transaction.systemd.enablement.values()) == {"disabled"}


def test_commit_releases_only_originals_and_finalize_cleans_exact_root(
    tmp_path: Path,
) -> None:
    enablement = {
        "health-backend.socket": "enabled",
        "health-backend.service": "static",
        "celery-worker.service": "disabled",
        "celery-beat.service": "enabled",
    }
    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        enablement=enablement,
    )
    stage_sentinel = layout.release_stage / "keep-stage"
    stage_sentinel.write_text("keep", encoding="utf-8")
    parent_sentinel = layout.transaction_root.parent / "keep-parent"
    parent_sentinel.write_text("keep", encoding="utf-8")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)

    assert transaction.commit("b" * 40, lock_dir, token) == "COMMITTED"
    assert enablement == {
        "health-backend.socket": "enabled",
        "health-backend.service": "static",
        "celery-worker.service": "disabled",
        "celery-beat.service": "enabled",
    }
    assert _journal(layout)["boot_gate_released"] is True
    assert _journal(layout)["release_target"] == "candidate"
    assert [
        event for event in transaction.systemd.events if event.startswith("enable:")
    ] == [
        "enable:health-backend.socket",
        "enable:celery-beat.service",
    ]

    assert transaction.finalize("b" * 40, lock_dir, token) == "finalized"
    assert not layout.transaction_root.exists()
    assert stage_sentinel.read_text(encoding="utf-8") == "keep"
    assert parent_sentinel.read_text(encoding="utf-8") == "keep"
    assert _terminal_marker(layout)["phase"] == "COMMITTED"
    assert _terminal_marker(layout)["terminal_sha"] == "b" * 40
    assert transaction.status(lock_dir, token) == (
        f"phase=COMMITTED old_sha={'a' * 40} "
        f"candidate_sha={'b' * 40} gate_armed=false "
        "gate_released=true release_target=candidate "
        "next_action=none state_source=terminal"
    )
    assert transaction.finalize("b" * 40, lock_dir, token) == "finalized"
    with pytest.raises(TransactionError, match="terminal SHA"):
        transaction.finalize("c" * 40, lock_dir, token)


def test_commit_intent_is_candidate_floor_and_reboots_resume_release(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_after_candidate_intent(point: str) -> None:
        nonlocal crashed
        if not crashed and point == "commit:after-release-intent":
            crashed = True
            raise OSError("simulated candidate release reboot")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_after_candidate_intent,
    )
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)

    with pytest.raises(OSError, match="candidate release reboot"):
        transaction.commit("b" * 40, lock_dir, token)

    assert _journal(layout)["phase"] == "COMMITTED"
    assert _journal(layout)["release_target"] == "candidate"
    assert transaction.status(lock_dir, token) == (
        f"phase=COMMITTED old_sha={'a' * 40} "
        f"candidate_sha={'b' * 40} gate_armed=true "
        "gate_released=false release_target=candidate "
        "next_action=commit state_source=journal"
    )
    with pytest.raises(TransactionError, match="irrevocable"):
        transaction.restore("a" * 40, lock_dir, token)

    resumed = ReleaseTransaction(
        layout,
        FakeSystemd(
            layout,
            old_schedule=layout.legacy_shelf_base,
            enablement=transaction.systemd.enablement,
        ),
    )
    _mark_boot_gate_active(resumed)
    assert resumed.commit("b" * 40, lock_dir, token) == "COMMITTED"
    assert _journal(layout)["boot_gate_released"] is True


@pytest.mark.parametrize("inactive_unit", BOOT_GATE_UNITS)
def test_candidate_commit_requires_every_boot_gated_unit_active(
    tmp_path: Path,
    inactive_unit: str,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)
    transaction.systemd.active_states[inactive_unit] = "inactive"

    with pytest.raises(TransactionError, match="must be active"):
        transaction.commit("b" * 40, lock_dir, token)

    assert _journal(layout)["release_target"] is None
    assert set(transaction.systemd.enablement.values()) == {"disabled"}


def test_candidate_retention_has_commit_and_finalize_terminal_path(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert transaction.restore("b" * 40, lock_dir, token) == "candidate-retained"
    _mark_boot_gate_active(transaction)
    assert transaction.commit("b" * 40, lock_dir, token) == "COMMITTED"
    assert transaction.restore("b" * 40, lock_dir, token) == "candidate-retained"
    with pytest.raises(TransactionError, match="irrevocable"):
        transaction.restore("a" * 40, lock_dir, token)
    assert transaction.finalize("b" * 40, lock_dir, token) == "finalized"
    assert not layout.transaction_root.exists()


def test_candidate_retention_reproves_actual_boot_gate_when_unreleased(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    transaction.systemd.enablement["celery-worker.service"] = "enabled"

    with pytest.raises(TransactionError, match="boot gate is not armed"):
        transaction.restore("b" * 40, lock_dir, token)

    assert _journal(layout)["phase"] == "INSTALLED"


def test_terminal_rename_crash_recovers_with_new_token_and_blocks_other_sha(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_after_terminal_rename(point: str) -> None:
        nonlocal crashed
        if not crashed and point == "terminal:after-rename":
            crashed = True
            raise OSError("simulated terminal rename crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_after_terminal_rename,
    )
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    transaction.restore("a" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)

    with pytest.raises(OSError, match="terminal rename crash"):
        transaction.release_gate("a" * 40, lock_dir, token)

    marker = _terminal_marker(layout)
    reap = layout.transaction_root.parent / marker["reap_name"]
    assert not layout.transaction_root.exists()
    assert reap.is_dir()

    new_lock_parent = tmp_path / "terminal-owner"
    new_lock_parent.mkdir()
    new_lock_dir, new_token = _lock(
        new_lock_parent,
        stage=layout.release_stage,
    )
    resumed = ReleaseTransaction(
        layout,
        FakeSystemd(
            layout,
            old_schedule=layout.legacy_shelf_base,
            enablement=transaction.systemd.enablement,
        ),
    )
    with pytest.raises(TransactionError, match="terminal SHA"):
        resumed.release_gate("c" * 40, new_lock_dir, new_token)
    assert reap.is_dir()
    with pytest.raises(TransactionError, match="terminal cleanup pending"):
        resumed.preflight(
            "c" * 40,
            "d" * 40,
            new_lock_dir,
            new_token,
        )
    assert reap.is_dir()

    assert (
        resumed.release_gate("a" * 40, new_lock_dir, new_token) == "RESTORE_FINALIZED"
    )
    assert not reap.exists()


def test_terminal_marker_crash_before_rename_is_reentrant(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_after_terminal_marker(point: str) -> None:
        nonlocal crashed
        if not crashed and point == "terminal:after-marker":
            crashed = True
            raise OSError("simulated terminal marker crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_after_terminal_marker,
    )
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    transaction.restore("a" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)

    with pytest.raises(OSError, match="terminal marker crash"):
        transaction.release_gate("a" * 40, lock_dir, token)

    marker = _terminal_marker(layout)
    reap = layout.transaction_root.parent / marker["reap_name"]
    assert layout.transaction_root.is_dir()
    assert not reap.exists()

    resumed = ReleaseTransaction(
        layout,
        FakeSystemd(
            layout,
            old_schedule=layout.legacy_shelf_base,
            enablement=transaction.systemd.enablement,
        ),
    )
    _mark_boot_gate_active(resumed)
    assert resumed.release_gate("a" * 40, lock_dir, token) == "RESTORE_FINALIZED"
    assert not layout.transaction_root.exists()
    assert not reap.exists()


def test_terminal_marker_rejects_inconsistent_target_contract(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)
    transaction.commit("b" * 40, lock_dir, token)
    transaction.finalize("b" * 40, lock_dir, token)
    marker_path = layout.transaction_root.parent / "runtime-state-terminal.json"
    marker = _terminal_marker(layout)
    marker["target"] = "old"
    marker_path.write_text(json.dumps(marker), encoding="utf-8")

    with pytest.raises(TransactionError, match="terminal marker contract"):
        transaction.status(lock_dir, token)


def test_restore_removes_only_journal_scoped_sigkill_temps(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction_id = _journal(layout)["transaction_id"]
    layout.beat_state_dir.mkdir(mode=0o700)
    beat_orphan = layout.beat_state_dir / (
        f".celerybeat-schedule.db.runtime-state-{transaction_id}.tmp"
    )
    beat_orphan.write_bytes(b"partial")
    layout.runtime_root.mkdir(mode=0o700)
    runtime_orphan = layout.runtime_root / (
        f".knowledge_base.runtime-state-{transaction_id}.tmp"
    )
    runtime_orphan.mkdir()
    (runtime_orphan / "partial").write_bytes(b"partial")

    resumed = ReleaseTransaction(
        layout,
        FakeSystemd(
            layout,
            old_schedule=layout.legacy_shelf_base,
            enablement=transaction.systemd.enablement,
        ),
    )
    assert resumed.restore("a" * 40, lock_dir, token) == "restored"
    assert not beat_orphan.exists()
    assert not runtime_orphan.exists()


def test_restore_rejects_and_preserves_unrelated_hidden_sentinel(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    layout.beat_state_dir.mkdir(mode=0o700)
    sentinel = layout.beat_state_dir / ".operator-sentinel"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(TransactionError, match="unknown beat state entry"):
        transaction.restore("a" * 40, lock_dir, token)

    assert sentinel.read_text(encoding="utf-8") == "preserve"


def test_dropins_enforce_minimal_external_writable_boundaries() -> None:
    dropins = ROOT / "infra/systemd/dropins"
    backend = (dropins / "health-backend-runtime-state.conf").read_text(
        encoding="utf-8"
    )
    assert backend == (
        "[Service]\n"
        "# The runtime-state drop-in is the transactionally installed production\n"
        "# artifact. Reset any older base unit command so process-local Garmin MFA\n"
        "# challenges remain pinned to the worker that created them.\n"
        "ExecStart=\n"
        "ExecStart=/opt/health-app/backend/venv/bin/uvicorn main:app --fd 3 "
        "--workers 1 --limit-concurrency 100 --proxy-headers "
        "--forwarded-allow-ips=127.0.0.1 --no-access-log\n"
        "ReadWritePaths=\n"
        "ReadWritePaths=/var/lib/health-app/uploads "
        "/var/cache/health-app/skills-hub "
        "/var/lib/health-app/runtime "
        "/var/lib/health-app/dedao-kbase\n"
    )
    assert backend.encode() == runtime_transaction._expected_candidate(
        "health-backend.service"
    )
    worker = (dropins / "celery-worker-runtime-state.conf").read_text(encoding="utf-8")
    assert worker == (
        "[Service]\n"
        "ReadWritePaths=\n"
        "ReadWritePaths=/var/lib/health-app/uploads "
        "/var/lib/health-app/dedao-kbase\n"
    )

    beat = (dropins / "celery-beat-runtime-state.conf").read_text(encoding="utf-8")
    assert beat == (
        "[Service]\n"
        "StateDirectory=health-app/celery-beat\n"
        "StateDirectoryMode=0700\n"
        "ReadWritePaths=\n"
        "ReadWritePaths=/var/lib/health-app/celery-beat\n"
        "ExecStart=\n"
        "ExecStart=/opt/health-app/backend/venv/bin/celery "
        "-A app.celery_app:celery_app beat --loglevel=info "
        "--schedule=/var/lib/health-app/celery-beat/celerybeat-schedule\n"
    )


def test_install_provisions_external_skills_cache_without_migrating_checkout(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy_cache = layout.repo_root / ".health-skills-cache"
    legacy_cache.mkdir()
    (legacy_cache / "legacy.json").write_text("checkout-cache")

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    assert "skills_cache" not in _journal(layout)["snapshots"]
    assert not layout.skills_cache_root.exists()
    assert (
        transaction.install(
            "a" * 40,
            "b" * 40,
            lock_dir,
            token,
        )
        == "INSTALLED"
    )

    cache = layout.skills_cache_root
    assert cache.is_dir()
    assert stat.S_IMODE(cache.stat().st_mode) == 0o700
    assert cache.stat().st_uid == layout.health_uid
    assert cache.stat().st_gid == layout.health_gid
    assert list(cache.iterdir()) == []
    assert (legacy_cache / "legacy.json").read_text() == "checkout-cache"


def test_prepare_rejects_unsafe_external_skills_cache_root(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    layout.skills_cache_root.parent.mkdir(parents=True)
    target = tmp_path / "cache-target"
    target.mkdir()
    layout.skills_cache_root.symlink_to(target)

    with pytest.raises(TransactionError, match="symlink"):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    assert not layout.transaction_root.exists()


def test_install_bootstraps_dedao_workspace_and_old_restore_removes_it(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    layout.dedao_legacy_root.mkdir(mode=0o755, exist_ok=True)
    payload = layout.dedao_legacy_root / "keep.json"
    payload.write_text("immutable-content")

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert stat.S_IMODE(layout.dedao_container.stat().st_mode) == 0o700
    assert stat.S_IMODE(layout.dedao_workspace.stat().st_mode) == 0o700
    assert payload.read_text() == "immutable-content"
    assert (layout.dedao_workspace / "keep.json").read_text() == "immutable-content"

    transaction.restore("a" * 40, lock_dir, token)

    assert not layout.dedao_container.exists()
    assert payload.read_text() == "immutable-content"


def test_preflight_rejects_unknown_runtime_entries_without_mutation(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    layout.runtime_root.mkdir(mode=0o700)
    (layout.runtime_root / "unexpected").write_text("do not touch")
    before = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }

    with pytest.raises(TransactionError, match="unknown runtime entry"):
        transaction.preflight("a" * 40, "b" * 40, lock_dir, token)

    after = {
        path.relative_to(tmp_path): path.read_bytes()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before
    assert not layout.transaction_root.exists()


def test_prepare_refuses_to_snapshot_while_a_writer_is_active(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.systemd.active_state = "active"

    with pytest.raises(TransactionError, match="must be inactive"):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    assert not layout.transaction_root.exists()


@pytest.mark.parametrize("kind", ("file", "directory"))
def test_metadata_application_does_not_require_path_chmod_follow_symlinks(
    tmp_path: Path,
    monkeypatch,
    kind: str,
) -> None:
    transaction, layout, _, _ = _transaction(tmp_path)
    target = tmp_path / "metadata-target"
    if kind == "file":
        target.write_text("state", encoding="utf-8")
        expected_mode = 0o600
    else:
        target.mkdir()
        expected_mode = 0o700

    def unsupported_path_chmod(*args, **kwargs):
        raise NotImplementedError("follow_symlinks=False unsupported")

    monkeypatch.setattr(runtime_transaction.os, "chmod", unsupported_path_chmod)
    transaction._apply_metadata(
        target,
        uid=os.getuid(),
        gid=os.getgid(),
        mode=expected_mode,
    )

    assert stat.S_IMODE(target.stat().st_mode) == expected_mode


def test_prepare_rejects_symlink_and_hardlink_collisions(tmp_path: Path) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = layout.backend_data / "gene_knowledge.json"
    legacy.write_text("gene")
    collision = layout.backend_data / "gene-hardlink"
    os.link(legacy, collision)

    with pytest.raises(TransactionError, match="hard link"):
        transaction.preflight("a" * 40, "b" * 40, lock_dir, token)

    collision.unlink()
    layout.runtime_root.mkdir(mode=0o700)
    (layout.runtime_root / "gene_knowledge.json").symlink_to(legacy)
    with pytest.raises(TransactionError, match="symlink"):
        transaction.preflight("a" * 40, "b" * 40, lock_dir, token)
    assert not layout.transaction_root.exists()

    (layout.runtime_root / "gene_knowledge.json").unlink()
    base_unit = layout.base_units["celery-beat.service"]
    base_unit.unlink()
    base_unit.symlink_to(layout.base_units["celery-worker.service"])
    with pytest.raises(TransactionError, match="symlink"):
        transaction.preflight("a" * 40, "b" * 40, lock_dir, token)


def test_preflight_rejects_candidate_outside_root_only_stage(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    outsider = tmp_path / "celery-beat-runtime-state.conf"
    outsider.write_bytes(layout.candidate_dropins["celery-beat.service"].read_bytes())
    outsider.chmod(0o600)
    paths = dict(layout.candidate_dropins.paths)
    paths["celery-beat.service"] = outsider
    unsafe_layout = replace(
        layout,
        candidate_dropins=CandidatePaths(paths),
    )
    transaction, _, lock_dir, token = _transaction(
        tmp_path,
        layout=unsafe_layout,
    )

    with pytest.raises(TransactionError, match="release stage"):
        transaction.preflight("a" * 40, "b" * 40, lock_dir, token)


def test_legacy_authority_install_and_old_restore_are_exact(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    transaction, layout, lock_dir, token = _transaction(
        tmp_path, event_sink=events.append
    )
    legacy = _write_shelf(layout.legacy_shelf_base, ".db", b"legacy")
    current = _write_shelf(layout.current_shelf_base, ".db", b"stale-current")
    old_dropin = layout.live_dropins["health-backend.service"]
    old_dropin.parent.mkdir(parents=True)
    old_dropin.write_text("[Service]\nEnvironment=OLD=1\n", encoding="utf-8")
    old_dropin.chmod(0o640)
    original_data = layout.backend_data.stat()

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    journal = json.loads(
        (layout.transaction_root / "journal.json").read_text(encoding="utf-8")
    )
    assert journal["beat_authority"] == "legacy"

    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    assert current.read_bytes() == b"legacy"
    assert legacy.read_bytes() == b"legacy"
    assert (
        old_dropin.read_bytes()
        == layout.candidate_dropins["health-backend.service"].read_bytes()
    )
    shelf_prefix = f"copy:{current}:"
    shelf_events = [event for event in events if event.startswith(shelf_prefix)]
    assert [event.rsplit(":", 1)[-1] for event in shelf_events] == [
        "temp",
        "file-fsync",
        "hash",
        "rename",
        "dir-fsync",
    ]

    current.write_bytes(b"candidate-mutated")
    layout.backend_data.chmod(0o755)
    result = transaction.restore("a" * 40, lock_dir, token)

    assert result == "restored"
    assert current.read_bytes() == b"stale-current"
    assert legacy.read_bytes() == b"legacy"
    assert old_dropin.read_text(encoding="utf-8") == ("[Service]\nEnvironment=OLD=1\n")
    assert stat.S_IMODE(old_dropin.stat().st_mode) == 0o640
    restored_data = layout.backend_data.stat()
    assert restored_data.st_uid == original_data.st_uid
    assert restored_data.st_gid == original_data.st_gid
    assert stat.S_IMODE(restored_data.st_mode) == stat.S_IMODE(original_data.st_mode)


def test_current_authority_is_retained_and_candidate_restore_is_noop(
    tmp_path: Path,
) -> None:
    layout = _layout(tmp_path)
    live_beat = layout.live_dropins["celery-beat.service"]
    live_beat.parent.mkdir(parents=True)
    live_beat.write_bytes(layout.candidate_dropins["celery-beat.service"].read_bytes())
    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        layout=layout,
        old_schedule=layout.current_shelf_base,
    )
    _write_shelf(layout.legacy_shelf_base, ".db", b"legacy")
    current = _write_shelf(layout.current_shelf_base, ".db", b"current")

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert current.read_bytes() == b"current"
    current.write_bytes(b"candidate-progress")
    result = transaction.restore("b" * 40, lock_dir, token)

    assert result == "candidate-retained"
    assert current.read_bytes() == b"candidate-progress"


def test_runtime_allowlist_bootstraps_missing_and_preserves_current(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    (layout.backend_data / "gene_knowledge.json").write_text("legacy-gene")
    legacy_chroma = layout.backend_data / "knowledge_chromadb/nested"
    legacy_chroma.mkdir(parents=True)
    (legacy_chroma / "index.bin").write_bytes(b"chroma")
    legacy_base = layout.backend_data / "knowledge_base"
    legacy_base.mkdir()
    (legacy_base / "vectors.bin").write_bytes(b"vectors")
    layout.runtime_root.mkdir(mode=0o700)
    (layout.runtime_root / "gene_knowledge.json").write_text("current-gene")

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert (layout.runtime_root / "gene_knowledge.json").read_text() == "current-gene"
    assert (
        stat.S_IMODE((layout.runtime_root / "gene_knowledge.json").stat().st_mode)
        == 0o600
    )
    assert (
        layout.runtime_root / "knowledge_chromadb/nested/index.bin"
    ).read_bytes() == b"chroma"
    assert (
        layout.runtime_root / "knowledge_base/vectors.bin"
    ).read_bytes() == b"vectors"

    transaction.restore("a" * 40, lock_dir, token)
    assert (layout.runtime_root / "gene_knowledge.json").read_text() == "current-gene"
    assert not (layout.runtime_root / "knowledge_chromadb").exists()
    assert not (layout.runtime_root / "knowledge_base").exists()


def test_install_migrates_legacy_uploads_into_empty_external_authority(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = layout.repo_root / "backend/uploads/medical/7/report.pdf"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy-report")
    layout.uploads_root.mkdir(mode=0o700)

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    journal = _journal(layout)
    assert journal["snapshots"]["uploads_legacy"]["exists"] is True
    assert journal["snapshots"]["uploads_current"]["exists"] is True
    assert journal["snapshots"]["uploads_current"]["children"] == {}
    assert (
        layout.transaction_root / "snapshots/uploads-legacy/medical/7/report.pdf"
    ).read_bytes() == b"legacy-report"

    assert (
        transaction.install(
            "a" * 40,
            "b" * 40,
            lock_dir,
            token,
        )
        == "INSTALLED"
    )

    migrated = layout.runtime_root.parent / "uploads/medical/7/report.pdf"
    assert migrated.read_bytes() == b"legacy-report"
    assert not layout.legacy_uploads.exists()
    assert (
        layout.transaction_root / "snapshots/uploads-legacy/medical/7/report.pdf"
    ).read_bytes() == b"legacy-report"
    assert stat.S_IMODE(migrated.stat().st_mode) == 0o600
    assert stat.S_IMODE(migrated.parent.stat().st_mode) == 0o700
    assert migrated.stat().st_nlink == 1
    assert not transaction._temporary_path(layout.uploads_root).exists()


def test_install_rejects_legacy_upload_change_after_snapshot_without_retiring_source(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = layout.legacy_uploads / "medical/7/report.pdf"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"snapshot-version")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    legacy.write_bytes(b"changed-after-snapshot")

    with pytest.raises(TransactionError, match="legacy uploads changed"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert legacy.read_bytes() == b"changed-after-snapshot"
    assert not (layout.uploads_root / "medical/7/report.pdf").exists()
    assert _journal(layout)["phase"] == "PREPARED"


def test_install_accepts_identical_upload_conflict_idempotently(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = layout.repo_root / "backend/uploads/avatar/7/photo.jpg"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"same-photo")
    sibling = legacy.parent / "new-photo.jpg"
    sibling.write_bytes(b"new-photo")

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    current = layout.runtime_root.parent / "uploads/avatar/7/photo.jpg"
    current.parent.mkdir(parents=True)
    current.write_bytes(b"same-photo")

    assert (
        transaction.install(
            "a" * 40,
            "b" * 40,
            lock_dir,
            token,
        )
        == "INSTALLED"
    )
    assert (
        transaction.install(
            "a" * 40,
            "b" * 40,
            lock_dir,
            token,
        )
        == "INSTALLED"
    )
    assert current.read_bytes() == b"same-photo"
    assert (current.parent / "new-photo.jpg").read_bytes() == b"new-photo"


def test_install_rejects_different_upload_conflict_without_overwriting(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy_root = layout.repo_root / "backend/uploads"
    legacy_root.mkdir()
    (legacy_root / "a-new.txt").write_bytes(b"must-not-partially-copy")
    (legacy_root / "z-conflict.txt").write_bytes(b"legacy")

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    current_root = layout.runtime_root.parent / "uploads"
    current_root.mkdir()
    conflict = current_root / "z-conflict.txt"
    conflict.write_bytes(b"current")

    with pytest.raises(
        TransactionError,
        match="external upload partial is not a sealed subset",
    ):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert conflict.read_bytes() == b"current"
    assert not (current_root / "a-new.txt").exists()
    assert _journal(layout)["phase"] == "PREPARED"


def test_install_rejects_external_only_content_created_after_prepare(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = layout.legacy_uploads / "chat/7/current.jpg"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"authoritative")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    unproven = layout.uploads_root / "chat/7/deleted-private.jpg"
    unproven.parent.mkdir(parents=True)
    unproven.write_bytes(b"stale-external")

    with pytest.raises(
        TransactionError,
        match="external upload partial is not a sealed subset",
    ):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert unproven.read_bytes() == b"stale-external"
    assert legacy.read_bytes() == b"authoritative"
    assert _journal(layout)["upload_authority"] == "mixed"


def test_install_upload_copy_crash_reenters_without_stage_or_hardlink(
    tmp_path: Path,
) -> None:
    crashed = False
    transaction: ReleaseTransaction

    def crash_after_upload_publish(point: str) -> None:
        nonlocal crashed
        if not crashed and point.endswith("/uploads/report.pdf:after-rename"):
            crashed = True
            raise OSError("simulated upload publish crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_after_upload_publish,
    )
    legacy = layout.legacy_uploads / "report.pdf"
    legacy.parent.mkdir()
    legacy.write_bytes(b"report")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    with pytest.raises(OSError, match="upload publish crash"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    current = layout.uploads_root / "report.pdf"
    assert current.read_bytes() == b"report"
    assert current.stat().st_nlink == 1
    assert not transaction._temporary_path(layout.uploads_root).exists()
    assert _journal(layout)["phase"] == "PREPARED"

    assert (
        transaction.install(
            "a" * 40,
            "b" * 40,
            lock_dir,
            token,
        )
        == "INSTALLED"
    )
    assert current.read_bytes() == b"report"
    assert current.stat().st_nlink == 1


def test_install_recovers_orphaned_upload_stage_hardlink(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = layout.legacy_uploads / "report.pdf"
    legacy.parent.mkdir()
    legacy.write_bytes(b"report")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    layout.uploads_root.mkdir(mode=0o700)
    stage = transaction._temporary_path(layout.uploads_root)
    stage.mkdir(mode=0o700)
    staged = stage / ("0" * 64)
    staged.write_bytes(b"report")
    current = layout.uploads_root / "report.pdf"
    os.link(staged, current)
    assert staged.stat().st_nlink == 2
    assert current.stat().st_nlink == 2

    assert (
        transaction.install(
            "a" * 40,
            "b" * 40,
            lock_dir,
            token,
        )
        == "INSTALLED"
    )

    assert not stage.exists()
    assert current.read_bytes() == b"report"
    assert current.stat().st_nlink == 1


def test_old_restore_preserves_candidate_window_uploads_in_legacy_authority(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = layout.repo_root / "backend/uploads/medical/7/original.pdf"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"original")

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    candidate_upload = (
        layout.runtime_root.parent / "uploads/medical/7/candidate-window.pdf"
    )
    candidate_upload.write_bytes(b"candidate-window")

    assert transaction.restore("a" * 40, lock_dir, token) == "restored"

    restored_candidate = (
        layout.repo_root / "backend/uploads/medical/7/candidate-window.pdf"
    )
    assert restored_candidate.read_bytes() == b"candidate-window"
    assert not layout.uploads_root.exists()
    assert legacy.read_bytes() == b"original"
    assert transaction.restore("a" * 40, lock_dir, token) == "restored"


def test_old_restore_propagates_candidate_window_upload_deletions(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    deleted = layout.legacy_uploads / "chat/7/deleted.jpg"
    retained = layout.legacy_uploads / "chat/7/retained.jpg"
    deleted.parent.mkdir(parents=True)
    deleted.write_bytes(b"delete-me")
    retained.write_bytes(b"keep-me")

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    (layout.uploads_root / "chat/7/deleted.jpg").unlink()
    candidate_upload = layout.uploads_root / "chat/7/candidate-window.jpg"
    candidate_upload.write_bytes(b"candidate-window")

    assert transaction.restore("a" * 40, lock_dir, token) == "restored"

    assert not deleted.exists()
    assert retained.read_bytes() == b"keep-me"
    assert (
        layout.legacy_uploads / "chat/7/candidate-window.jpg"
    ).read_bytes() == b"candidate-window"
    assert not layout.uploads_root.exists()


def test_external_old_release_rollback_keeps_external_upload_authority(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        old_upload_authority="external",
    )
    deleted = layout.uploads_root / "chat/7/deleted.jpg"
    retained = layout.uploads_root / "chat/7/retained.jpg"
    deleted.parent.mkdir(parents=True)
    deleted.write_bytes(b"delete-me")
    retained.write_bytes(b"keep-me")

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    deleted.unlink()
    candidate = layout.uploads_root / "chat/7/candidate-window.jpg"
    candidate.write_bytes(b"candidate-window")

    assert transaction.restore("a" * 40, lock_dir, token) == "restored"

    assert not deleted.exists()
    assert retained.read_bytes() == b"keep-me"
    assert candidate.read_bytes() == b"candidate-window"
    assert not layout.legacy_uploads.exists()
    assert _journal(layout)["old_upload_authority"] == "external"
    assert _journal(layout)["upload_authority"] == "external"
    _mark_boot_gate_active(transaction)
    assert (
        transaction.release_gate("a" * 40, lock_dir, token)
        == "RESTORE_FINALIZED"
    )
    assert layout.uploads_root.exists()
    assert not layout.legacy_uploads.exists()


def test_install_upload_authority_retirement_crash_reenters_without_data_loss(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_during_legacy_retirement(point: str) -> None:
        nonlocal crashed
        if not crashed and point.startswith("uploads:install-retire:"):
            crashed = True
            raise OSError("simulated legacy upload retirement crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_during_legacy_retirement,
    )
    first = layout.legacy_uploads / "medical/7/first.pdf"
    second = layout.legacy_uploads / "medical/7/second.pdf"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    with pytest.raises(OSError, match="legacy upload retirement crash"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert (layout.uploads_root / "medical/7/first.pdf").read_bytes() == b"first"
    assert (layout.uploads_root / "medical/7/second.pdf").read_bytes() == b"second"
    assert _journal(layout)["upload_authority"] == "external-retiring-legacy"

    assert (
        transaction.install("a" * 40, "b" * 40, lock_dir, token)
        == "INSTALLED"
    )
    assert not layout.legacy_uploads.exists()
    assert (layout.uploads_root / "medical/7/first.pdf").read_bytes() == b"first"
    assert (layout.uploads_root / "medical/7/second.pdf").read_bytes() == b"second"
    assert _journal(layout)["upload_authority"] == "external"


def test_restore_upload_authority_retirement_crash_reenters_without_data_loss(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_during_external_retirement(point: str) -> None:
        nonlocal crashed
        if not crashed and point.startswith("uploads:restore-retire:"):
            crashed = True
            raise OSError("simulated external upload retirement crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_during_external_retirement,
    )
    original = layout.legacy_uploads / "medical/7/original.pdf"
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    candidate = layout.uploads_root / "medical/7/candidate.pdf"
    candidate.write_bytes(b"candidate")

    with pytest.raises(OSError, match="external upload retirement crash"):
        transaction.restore("a" * 40, lock_dir, token)

    assert original.read_bytes() == b"original"
    assert (
        layout.legacy_uploads / "medical/7/candidate.pdf"
    ).read_bytes() == b"candidate"
    assert _journal(layout)["upload_authority"] == "legacy-retiring-external"

    assert transaction.restore("a" * 40, lock_dir, token) == "restored"
    assert not layout.uploads_root.exists()
    assert original.read_bytes() == b"original"
    assert (
        layout.legacy_uploads / "medical/7/candidate.pdf"
    ).read_bytes() == b"candidate"
    assert _journal(layout)["upload_authority"] == "legacy"


@pytest.mark.parametrize(
    "mutation",
    ("new", "modified", "type-changed", "permission-changed"),
)
def test_install_retirement_reentry_rejects_divergent_legacy_source(
    tmp_path: Path,
    mutation: str,
) -> None:
    crashed = False

    def crash_during_legacy_retirement(point: str) -> None:
        nonlocal crashed
        if not crashed and point.startswith("uploads:install-retire:"):
            crashed = True
            raise OSError("simulated legacy upload retirement crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_during_legacy_retirement,
    )
    retired = layout.legacy_uploads / "a-retired.txt"
    survivor = layout.legacy_uploads / "z-survivor.txt"
    retired.parent.mkdir(parents=True)
    retired.write_bytes(b"retired")
    survivor.write_bytes(b"sealed")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    with pytest.raises(OSError, match="legacy upload retirement crash"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    if mutation == "new":
        divergent = layout.legacy_uploads / "late.txt"
        divergent.write_bytes(b"unsealed")
    elif mutation == "modified":
        divergent = survivor
        divergent.write_bytes(b"changed")
    elif mutation == "type-changed":
        survivor.unlink()
        survivor.mkdir(mode=0o700)
        divergent = survivor
    else:
        survivor.chmod(0o400)
        divergent = survivor

    with pytest.raises(
        TransactionError,
        match="retiring legacy upload source is not a sealed subset",
    ):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert divergent.exists()
    assert _journal(layout)["upload_authority"] == "external-retiring-legacy"


@pytest.mark.parametrize(
    "mutation",
    ("new", "modified", "type-changed", "permission-changed"),
)
def test_restore_retirement_reentry_rejects_divergent_external_source(
    tmp_path: Path,
    mutation: str,
) -> None:
    crashed = False

    def crash_during_external_retirement(point: str) -> None:
        nonlocal crashed
        if not crashed and point.startswith("uploads:restore-retire:"):
            crashed = True
            raise OSError("simulated external upload retirement crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_during_external_retirement,
    )
    retired = layout.legacy_uploads / "a-retired.txt"
    survivor = layout.legacy_uploads / "z-survivor.txt"
    retired.parent.mkdir(parents=True)
    retired.write_bytes(b"retired")
    survivor.write_bytes(b"sealed")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    with pytest.raises(OSError, match="external upload retirement crash"):
        transaction.restore("a" * 40, lock_dir, token)

    external_survivor = layout.uploads_root / "z-survivor.txt"
    if mutation == "new":
        divergent = layout.uploads_root / "late.txt"
        divergent.write_bytes(b"unsealed")
    elif mutation == "modified":
        divergent = external_survivor
        divergent.write_bytes(b"changed")
    elif mutation == "type-changed":
        external_survivor.unlink()
        external_survivor.mkdir(mode=0o700)
        divergent = external_survivor
    else:
        external_survivor.chmod(0o400)
        divergent = external_survivor

    with pytest.raises(
        TransactionError,
        match="retiring external upload source is not a sealed subset",
    ):
        transaction.restore("a" * 40, lock_dir, token)

    assert divergent.exists()
    assert _journal(layout)["upload_authority"] == "legacy-retiring-external"


def test_old_restore_reenters_interrupted_initial_upload_authority_switch(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_during_initial_retirement(point: str) -> None:
        nonlocal crashed
        if not crashed and point.startswith("uploads:install-retire:"):
            crashed = True
            raise OSError("simulated initial upload authority crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_during_initial_retirement,
    )
    first = layout.legacy_uploads / "medical/7/first.pdf"
    second = layout.legacy_uploads / "medical/7/second.pdf"
    first.parent.mkdir(parents=True)
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    with pytest.raises(OSError, match="initial upload authority crash"):
        transaction.restore("a" * 40, lock_dir, token)

    assert _journal(layout)["upload_authority"] == "external-retiring-legacy"
    assert transaction.restore("a" * 40, lock_dir, token) == "restored"
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"
    assert not layout.uploads_root.exists()
    assert _journal(layout)["upload_authority"] == "legacy"


def test_candidate_finalize_does_not_leave_a_legacy_private_upload_copy(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = layout.legacy_uploads / "chat/7/private.jpg"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"private")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    migrated = layout.uploads_root / "chat/7/private.jpg"
    assert migrated.read_bytes() == b"private"
    assert not layout.legacy_uploads.exists()
    migrated.unlink()
    _mark_boot_gate_active(transaction)
    transaction.commit("b" * 40, lock_dir, token)
    assert transaction.finalize("b" * 40, lock_dir, token) == "finalized"

    assert not migrated.exists()
    assert not layout.legacy_uploads.exists()
    assert not layout.transaction_root.exists()


def test_candidate_finalize_rejects_reintroduced_legacy_upload_authority(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    _mark_boot_gate_active(transaction)
    transaction.commit("b" * 40, lock_dir, token)
    legacy = layout.legacy_uploads / "chat/7/private.jpg"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"private")

    with pytest.raises(TransactionError, match="candidate upload authority"):
        transaction.finalize("b" * 40, lock_dir, token)

    assert legacy.read_bytes() == b"private"
    assert layout.transaction_root.exists()


def test_candidate_retention_rejects_reintroduced_legacy_upload_authority(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    legacy = layout.legacy_uploads / "chat/7/private.jpg"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"private")

    with pytest.raises(TransactionError, match="candidate upload authority"):
        transaction.restore("b" * 40, lock_dir, token)

    assert legacy.read_bytes() == b"private"
    assert layout.transaction_root.exists()


def test_old_release_gate_rejects_reintroduced_external_upload_authority(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    transaction.restore("a" * 40, lock_dir, token)
    external = layout.uploads_root / "chat/7/private.jpg"
    external.parent.mkdir(parents=True)
    external.write_bytes(b"private")
    _mark_boot_gate_active(transaction)

    with pytest.raises(TransactionError, match="old upload authority"):
        transaction.release_gate("a" * 40, lock_dir, token)

    assert external.read_bytes() == b"private"
    assert layout.transaction_root.exists()


def test_old_restore_rejects_unexpected_legacy_tree_without_copy(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    new_external = layout.uploads_root / "a-new.pdf"
    new_external.write_bytes(b"candidate-new")
    external_conflict = layout.uploads_root / "z-conflict.pdf"
    external_conflict.write_bytes(b"candidate-conflict")
    layout.legacy_uploads.mkdir()
    legacy_conflict = layout.legacy_uploads / "z-conflict.pdf"
    legacy_conflict.write_bytes(b"restored-old")
    external_before = {
        path.name: (path.read_bytes(), path.stat().st_ino)
        for path in (new_external, external_conflict)
    }

    with pytest.raises(
        TransactionError,
        match="legacy upload tree exists before rollback copy",
    ):
        transaction.restore("a" * 40, lock_dir, token)

    assert not (layout.legacy_uploads / "a-new.pdf").exists()
    assert legacy_conflict.read_bytes() == b"restored-old"
    assert {
        path.name: (path.read_bytes(), path.stat().st_ino)
        for path in (new_external, external_conflict)
    } == external_before
    assert _journal(layout)["phase"] == "INSTALLED"


def test_old_restore_upload_copy_crash_reenters_without_mutating_external(
    tmp_path: Path,
) -> None:
    crashed = False

    def crash_after_legacy_publish(point: str) -> None:
        nonlocal crashed
        if not crashed and point.endswith(
            "/backend/uploads/candidate-window.pdf:after-rename"
        ):
            crashed = True
            raise OSError("simulated rollback upload crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path,
        fault_hook=crash_after_legacy_publish,
    )
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)
    external = layout.uploads_root / "candidate-window.pdf"
    external.write_bytes(b"candidate-window")
    before = external.lstat()
    external_before = (
        external.read_bytes(),
        before.st_dev,
        before.st_ino,
        before.st_uid,
        before.st_gid,
        before.st_mtime_ns,
    )

    with pytest.raises(OSError, match="rollback upload crash"):
        transaction.restore("a" * 40, lock_dir, token)

    copied = layout.legacy_uploads / "candidate-window.pdf"
    assert copied.read_bytes() == b"candidate-window"
    assert copied.stat().st_nlink == 1
    assert not transaction._temporary_path(layout.legacy_uploads).exists()
    assert _journal(layout)["phase"] == "INSTALLED"
    after_copy_crash = external.lstat()
    assert (
        external.read_bytes(),
        after_copy_crash.st_dev,
        after_copy_crash.st_ino,
        after_copy_crash.st_uid,
        after_copy_crash.st_gid,
        after_copy_crash.st_mtime_ns,
    ) == external_before
    assert stat.S_IMODE(after_copy_crash.st_mode) == 0o600

    assert transaction.restore("a" * 40, lock_dir, token) == "restored"
    assert not external.exists()
    assert copied.read_bytes() == b"candidate-window"


@pytest.mark.parametrize(
    "unsafe_kind,unsafe_tree",
    (
        ("symlink", "legacy"),
        ("hardlink", "legacy"),
        ("fifo", "current"),
    ),
)
def test_prepare_rejects_unsafe_upload_entries_without_snapshot(
    tmp_path: Path,
    unsafe_kind: str,
    unsafe_tree: str,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    roots = {
        "legacy": layout.repo_root / "backend/uploads",
        "current": layout.runtime_root.parent / "uploads",
    }
    root = roots[unsafe_tree]
    root.mkdir()
    safe = root / "safe.txt"
    safe.write_bytes(b"safe")
    unsafe = root / "unsafe"
    if unsafe_kind == "symlink":
        unsafe.symlink_to(safe)
    elif unsafe_kind == "hardlink":
        os.link(safe, unsafe)
    else:
        os.mkfifo(unsafe)

    with pytest.raises(
        TransactionError,
        match="symlink|hard link|special file",
    ):
        transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    assert not layout.transaction_root.exists()


def test_old_restore_recovers_exact_legacy_runtime_allowlist(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy_gene = layout.backend_data / "gene_knowledge.json"
    legacy_gene.write_bytes(b"live-gene")
    legacy_gene.chmod(0o640)
    legacy_chroma = layout.backend_data / "knowledge_chromadb"
    chroma_nested = legacy_chroma / "nested"
    chroma_nested.mkdir(parents=True)
    legacy_chroma.chmod(0o710)
    chroma_nested.chmod(0o750)
    chroma_index = chroma_nested / "index.bin"
    chroma_index.write_bytes(b"live-chroma")
    chroma_index.chmod(0o640)
    legacy_base = layout.backend_data / "knowledge_base"
    legacy_base.mkdir(mode=0o750)
    legacy_vectors = legacy_base / "vectors.bin"
    legacy_vectors.write_bytes(b"live-vectors")
    legacy_vectors.chmod(0o600)
    expected = {
        name: _tree_state(layout.backend_data / name)
        for name in (
            "gene_knowledge.json",
            "knowledge_chromadb",
            "knowledge_base",
        )
    }

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    legacy_gene.write_bytes(b"checkout-gene")
    legacy_gene.chmod(0o600)
    chroma_index.unlink()
    chroma_nested.rmdir()
    legacy_chroma.rmdir()
    legacy_vectors.unlink()
    (legacy_base / "checkout-only.bin").write_bytes(b"checkout")

    transaction.restore("a" * 40, lock_dir, token)

    assert {
        name: _tree_state(layout.backend_data / name)
        for name in (
            "gene_knowledge.json",
            "knowledge_chromadb",
            "knowledge_base",
        )
    } == expected


def test_existing_dedao_workspace_is_authoritative_and_old_restore_is_exact(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    (layout.dedao_legacy_root / "release.json").write_text("legacy")
    layout.dedao_workspace.mkdir(parents=True, mode=0o755)
    current = layout.dedao_workspace / "release.json"
    current.write_text("current")
    original_mode = stat.S_IMODE(layout.dedao_container.stat().st_mode)

    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    assert current.read_text() == "current"
    assert stat.S_IMODE(current.stat().st_mode) == 0o600
    current.write_text("candidate")
    transaction.restore("a" * 40, lock_dir, token)

    assert current.read_text() == "current"
    assert stat.S_IMODE(layout.dedao_container.stat().st_mode) == original_mode


def test_install_failure_can_restore_complete_preimage(tmp_path: Path) -> None:
    failed = False

    def fail_after_first_shelf_replace(point: str) -> None:
        nonlocal failed
        if not failed and point.endswith("celerybeat-schedule.db:after-rename"):
            failed = True
            raise OSError("injected crash")

    transaction, layout, lock_dir, token = _transaction(
        tmp_path, fault_hook=fail_after_first_shelf_replace
    )
    _write_shelf(layout.legacy_shelf_base, ".db", b"legacy")
    current = _write_shelf(layout.current_shelf_base, ".db", b"old-current")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)

    with pytest.raises(OSError, match="injected crash"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)
    assert current.read_bytes() == b"legacy"

    assert transaction.restore("a" * 40, lock_dir, token) == "restored"
    assert current.read_bytes() == b"old-current"
    assert not any(path.exists() for path in layout.live_dropins.values())


def test_effective_candidate_boundary_failure_restores_old_dropins_and_state(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy = _write_shelf(layout.legacy_shelf_base, ".db", b"legacy")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.systemd.candidate_beat_extra_runtime = True

    with pytest.raises(TransactionError, match="state boundary"):
        transaction.install("a" * 40, "b" * 40, lock_dir, token)

    transaction.systemd.candidate_beat_extra_runtime = False
    assert transaction.restore("a" * 40, lock_dir, token) == "restored"
    assert legacy.read_bytes() == b"legacy"
    assert not layout.current_shelf_base.with_suffix(".db").exists()
    assert not any(path.exists() for path in layout.live_dropins.values())


def test_prepare_collision_with_other_release_fails_closed(tmp_path: Path) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    before = (layout.transaction_root / "journal.json").read_bytes()

    with pytest.raises(TransactionError, match="different release"):
        transaction.prepare("c" * 40, "d" * 40, lock_dir, token)

    assert (layout.transaction_root / "journal.json").read_bytes() == before


def test_commit_requires_candidate_and_removes_only_legacy_shelf(
    tmp_path: Path,
) -> None:
    transaction, layout, lock_dir, token = _transaction(tmp_path)
    legacy_shelf = _write_shelf(layout.legacy_shelf_base, ".db", b"legacy-shelf")
    legacy_gene = layout.backend_data / "gene_knowledge.json"
    legacy_gene.write_text("tracked-gene")
    unrelated = layout.backend_data / "unrelated.keep"
    unrelated.write_text("keep")
    transaction.prepare("a" * 40, "b" * 40, lock_dir, token)
    transaction.install("a" * 40, "b" * 40, lock_dir, token)

    with pytest.raises(TransactionError, match="candidate SHA"):
        transaction.commit("a" * 40, lock_dir, token)
    assert legacy_shelf.exists()

    _mark_boot_gate_active(transaction)
    transaction.commit("b" * 40, lock_dir, token)

    assert not legacy_shelf.exists()
    assert legacy_gene.read_text() == "tracked-gene"
    assert unrelated.read_text() == "keep"
    assert (
        json.loads((layout.transaction_root / "journal.json").read_text())["phase"]
        == "COMMITTED"
    )
