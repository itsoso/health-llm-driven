from __future__ import annotations

import importlib.util
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "arguments",
    (
        ("server",),
        ("server-under-lock", "secret-token"),
        ("mobile",),
        ("mobile", "1.3.3"),
    ),
)
def test_network_cli_modes_freeze_before_imports_tokens_paths_or_tools(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    isolated = tmp_path / "scripts"
    isolated.mkdir()
    script = isolated / "release_production_state.py"
    script.write_bytes((ROOT / "scripts/release_production_state.py").read_bytes())
    marker = tmp_path / "import-called"
    (isolated / "atexit.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('called')\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=tmp_path,
        env={**os.environ, "EXPO_TOKEN": "must-not-leak"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert "external trusted Gate" in completed.stderr
    assert "must-not-leak" not in completed.stdout + completed.stderr
    assert "secret-token" not in completed.stdout + completed.stderr
    assert not marker.exists()


@pytest.mark.parametrize("mode", ("server", "server-under-lock", "mobile"))
def test_programmatic_network_cli_modes_freeze_before_probe(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
) -> None:
    module = _module()
    monkeypatch.setattr(
        module,
        "probe_server_surfaces",
        lambda *_args, **_kwargs: pytest.fail("network probe must not run"),
    )
    argv = ["release_production_state.py", mode]
    if mode == "server-under-lock":
        argv.append("secret-token")

    assert module._main(argv) == 78


def _module():
    path = ROOT / "scripts/release_production_state.py"
    spec = importlib.util.spec_from_file_location("release_production_state", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _remote_contract_namespace(module) -> dict[str, object]:
    probe = module._REMOTE_PROBE
    source = "SHA_RE =" + probe.split("SHA_RE =", 1)[1].split(
        "MAC_MAX_ARTIFACT_BYTES", 1
    )[0]
    namespace: dict[str, object] = {"re": re}
    exec(source, namespace)
    return namespace


def _remote_hash_function(module):
    probe = module._REMOTE_PROBE
    source = "def hash_root_file(" + probe.split("def hash_root_file(", 1)[1].split(
        "\n\ndef valid_utc_timestamp", 1
    )[0]

    class ProbeFailure(RuntimeError):
        pass

    def fail(message: str):
        raise ProbeFailure(message)

    namespace: dict[str, object] = {
        "hashlib": hashlib,
        "os": os,
        "stat": stat,
        "FILE_FLAGS": os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0),
        "fail": fail,
    }
    exec(source, namespace)
    return namespace["hash_root_file"], ProbeFailure


def _remote_quiescence_function(module, *, lock_path: Path):
    probe = module._REMOTE_PROBE
    source = "def assert_mac_release_quiescent(" + probe.split(
        "def assert_mac_release_quiescent(", 1
    )[1].split("\n\ndef root_file_identity", 1)[0]

    class ProbeFailure(RuntimeError):
        pass

    def fail(message: str):
        raise ProbeFailure(message)

    namespace: dict[str, object] = {
        "os": os,
        "MAC_JOURNAL": "mac-release.transaction.json",
        "STATE_ROOT": str(lock_path.parent),
        "REMOTE_RELEASE_LOCK_PATH": str(lock_path),
        "fail": fail,
    }
    exec(source, namespace)
    return namespace["assert_mac_release_quiescent"], ProbeFailure


def _remote_expected_lock_function(module, *, lock_path: Path, token: str):
    probe = module._REMOTE_PROBE
    source = "def valid_utc_timestamp(" + probe.split(
        "def valid_utc_timestamp(", 1
    )[1].split("\n\ndef root_file_identity", 1)[0]
    source = source.replace(
        "metadata.st_uid != 0", "metadata.st_uid != os.geteuid()"
    ).replace(
        "metadata.st_gid != 0", "metadata.st_gid != os.getegid()"
    )

    class ProbeFailure(RuntimeError):
        pass

    def fail(message: str):
        raise ProbeFailure(message)

    def read_root_file(directory_fd, name, *, mode, maximum):
        descriptor = os.open(name, os.O_RDONLY, dir_fd=directory_fd)
        try:
            metadata = os.fstat(descriptor)
            if stat.S_IMODE(metadata.st_mode) != mode:
                fail("unsafe expected unified remote release lease")
            raw = os.read(descriptor, maximum + 1)
            return raw, metadata
        finally:
            os.close(descriptor)

    namespace: dict[str, object] = {
        "datetime": __import__("datetime").datetime,
        "timezone": __import__("datetime").timezone,
        "os": os,
        "stat": stat,
        "re": re,
        "DIR_FLAGS": os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        "MAC_JOURNAL": "mac-release.transaction.json",
        "STATE_ROOT": str(lock_path.parent),
        "REMOTE_RELEASE_LOCK_PATH": str(lock_path),
        "EXPECTED_RELEASE_LOCK_TOKEN": token,
        "SHA_RE": re.compile(r"[0-9a-f]{40}"),
        "HEX64_RE": re.compile(r"[0-9a-f]{64}"),
        "read_root_file": read_root_file,
        "fail": fail,
    }
    exec(source, namespace)
    return namespace["assert_expected_release_lock"], ProbeFailure


def _write_v2_remote_lock(path: Path, *, token: str) -> None:
    path.mkdir(mode=0o700)
    values = {
        "schema": "2",
        "token": token,
        "label": "coordinator:mobile:forward",
        "stage": f"/tmp/health-app-backup-preflight-{token}",
        "started_at": "2026-08-12T00:00:00Z",
        "source_sha": "a" * 40,
        "source_tree": "b" * 40,
        "state": "sealed",
        "surface": "mobile",
        "operation": "forward",
        "channel": "production",
        "transaction_id": "c" * 32,
        "baseline_digest": "d" * 64,
        "request_digest": "e" * 64,
        "terminal_digest": "-",
    }
    for name, value in values.items():
        target = path / name
        target.write_text(value + "\n", encoding="ascii")
        target.chmod(0o600)


def _remote_public_function(module, name: str, next_name: str, payload: bytes):
    probe = module._REMOTE_PROBE
    source = f"def {name}(" + probe.split(f"def {name}(", 1)[1].split(
        f"\n\ndef {next_name}", 1
    )[0]

    class ProbeFailure(RuntimeError):
        pass

    class Process:
        def __init__(self) -> None:
            self.stdout = io.BytesIO(payload)

        def wait(self, timeout=None):
            del timeout
            return 0

        def kill(self):
            return None

    def fail(message: str):
        raise ProbeFailure(message)

    namespace: dict[str, object] = {
        "hashlib": hashlib,
        "re": re,
        "subprocess": subprocess,
        "PUBLIC_HEADER_TIMEOUT_SECONDS": 15,
        "PUBLIC_MANIFEST_TIMEOUT_SECONDS": 30,
        "PUBLIC_ARTIFACT_TIMEOUT_SECONDS": 60,
        "public_process": lambda *_args, **_kwargs: Process(),
        "fail": fail,
    }
    exec(source, namespace)
    return namespace[name], ProbeFailure


def _remote_health_function(module, run):
    probe = module._REMOTE_PROBE
    source = "def assert_local_health(" + probe.split(
        "def assert_local_health(", 1
    )[1].split("\n\ninitial_checkout_identity", 1)[0]
    class ProbeFailure(RuntimeError):
        pass

    def fail(message: str):
        raise ProbeFailure(message)

    namespace: dict[str, object] = {"run": run, "fail": fail}
    exec(source, namespace)
    return namespace["assert_local_health"], ProbeFailure


def _remote_run_function(module):
    probe = module._REMOTE_PROBE
    source = "def run(" + probe.split("def run(", 1)[1].split(
        "\n\ndef json_value", 1
    )[0]

    class ProbeFailure(RuntimeError):
        pass

    def fail(message: str):
        raise ProbeFailure(message)

    namespace: dict[str, object] = {
        "os": os,
        "selectors": __import__("selectors"),
        "signal": __import__("signal"),
        "subprocess": subprocess,
        "time": time,
        "SAFE_ENV": {"PATH": os.environ.get("PATH", "")},
        "COMMAND_OUTPUT_CAP": 64 * 1024,
        "fail": fail,
    }
    exec(source, namespace)
    return namespace["run"], ProbeFailure


def _server_stdout(
    sha: str = "a" * 40,
    *,
    frontend_sha: str | None = "c" * 40,
    frontend_proof_id: str | None = "d" * 64,
    mac_sha: str | None = "f" * 40,
    mac_artifact_sha256: str | None = "1" * 64,
    mac_receipt_id: str | None = "2" * 64,
) -> str:
    return json.dumps(
        {
            "schema_version": 3,
            "checkout_revision": sha,
            "repository_clean": True,
            "backend_revision": sha,
            "backend_proof_id": "e" * 64,
            "backend_service": "active",
            "backend_health": "ok",
            "frontend_pm2": "online",
            "frontend_health": "ok",
            "frontend_revision": frontend_sha,
            "frontend_proof_id": frontend_proof_id,
            "mac_revision": mac_sha,
            "mac_artifact_sha256": mac_artifact_sha256,
            "mac_receipt_id": mac_receipt_id,
        }
    )


def _channel_stdout(
    sha: str = "b" * 40,
    *,
    branches: int = 1,
    groups: int = 1,
    dirty: bool = False,
    environment: str = "production",
    channel_updated_at: str = "2026-08-12T12:34:56.000Z",
) -> str:
    update = {
        "id": "019ff3c7-5803-7464-8614-a63dd5a60684",
        "group": "691fe316-da6b-404e-8d24-53b755c0df18",
        "runtimeVersion": "1.3.3",
        "platform": "ios",
        "gitCommitHash": sha,
        "isGitWorkingTreeDirty": dirty,
        "environment": environment,
    }
    group_values = [[dict(update)] for _ in range(groups)]
    branch = {
        "id": "12345678-1234-4234-8234-123456789abc",
        "name": "production",
        "updateGroups": group_values,
    }
    return json.dumps(
        {
            "currentPage": {
                "id": "019dd201-1503-7ec9-a7b8-ed264891a7c5",
                "isPaused": False,
                "name": "production",
                "updatedAt": channel_updated_at,
                "branchMapping": json.dumps(
                    {
                        "version": 0,
                        "data": [
                            {
                                "branchId": "12345678-1234-4234-8234-123456789abc",
                                "branchMappingLogic": "true",
                            }
                        ],
                    },
                    separators=(",", ":"),
                ),
                "updateBranches": [dict(branch) for _ in range(branches)],
            }
        }
    )


def test_probe_uses_fixed_read_only_commands_scrubbed_env_and_returns_surfaces(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module = _module()
    mobile = tmp_path / "mobile"
    mobile.mkdir()
    observed: list[tuple[list[str], dict[str, object]]] = []
    monkeypatch.setenv("NODE_OPTIONS", "--require=/tmp/inject")
    monkeypatch.setenv("OTA_EAS_RUNNER", "/tmp/fake-eas")
    monkeypatch.setenv("EAS_NO_VCS", "1")

    def runner(command, **kwargs):
        observed.append((list(command), kwargs))
        stdout = _server_stdout() if command[0] == "/usr/bin/ssh" else _channel_stdout()
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    result = module.probe_production_surfaces(tmp_path, mobile_dir=mobile, runner=runner)

    assert result.backend_sha == "a" * 40
    assert result.backend_proof_id == "e" * 64
    assert result.frontend_sha == "c" * 40
    assert result.frontend_proof_id == "d" * 64
    assert result.mac_sha == "f" * 40
    assert result.mac_artifact_sha256 == "1" * 64
    assert result.mac_receipt_id == "2" * 64
    assert result.server_sha == result.backend_sha
    assert result.mobile_ota_sha == "b" * 40
    assert result.mobile_group_id == "691fe316-da6b-404e-8d24-53b755c0df18"
    assert result.mobile_update_id == "019ff3c7-5803-7464-8614-a63dd5a60684"
    assert result.mobile_runtime == "1.3.3"
    assert result.mobile_channel_id == "019dd201-1503-7ec9-a7b8-ed264891a7c5"
    assert result.mobile_channel_updated_at == "2026-08-12T12:34:56.000Z"
    assert result.mobile_branch_id == "12345678-1234-4234-8234-123456789abc"
    assert re.fullmatch(r"[0-9a-f]{64}", result.mobile_identity_digest)
    ssh_command, ssh_kwargs = observed[0]
    assert ssh_command[0] == "/usr/bin/ssh"
    assert ssh_command[1:3] == ["-F", "/dev/null"]
    assert "StrictHostKeyChecking=yes" in ssh_command
    assert "UserKnownHostsFile=/dev/null" in ssh_command
    assert sum("UserKnownHostsFile=" in item for item in ssh_command) == 1
    known_hosts_commands = [
        item for item in ssh_command if item.startswith("KnownHostsCommand=")
    ]
    assert len(known_hosts_commands) == 1
    assert known_hosts_commands[0].startswith(
        "KnownHostsCommand=/usr/bin/printf 39.98.206.178\\ ssh-ed25519\\ "
    )
    assert "/dev/fd/" not in " ".join(ssh_command)
    assert ssh_kwargs["timeout"] == module.PROBE_TIMEOUT_SECONDS
    assert "pass_fds" not in ssh_kwargs
    eas_command, eas_kwargs = observed[1]
    assert eas_command[0] == str(
        ROOT / "scripts/eas-cli-tool/node_modules/.bin/eas"
    )
    assert eas_command[1:] == [
        "channel:view",
        "production",
        "--json",
        "--non-interactive",
    ]
    assert eas_kwargs["cwd"] == mobile
    for name in ("NODE_OPTIONS", "OTA_EAS_RUNNER", "EAS_NO_VCS"):
        assert name not in eas_kwargs["env"]


def test_production_probe_under_release_lock_uses_exact_token_for_server_sample(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    mobile = tmp_path / "mobile"
    mobile.mkdir()
    server_identity = (
        "a" * 40,
        "b" * 64,
        "c" * 40,
        "d" * 64,
        "e" * 40,
        "f" * 64,
        "1" * 64,
    )
    lock_tokens: list[str | None] = []

    def server_probe(_repo, *, expected_lock_token, runner):
        del runner
        lock_tokens.append(expected_lock_token)
        return server_identity

    monkeypatch.setattr(module, "_probe_server_surfaces", server_probe)
    monkeypatch.setattr(module, "_expected_mobile_runtime", lambda: "1.3.3")
    monkeypatch.setattr(
        module,
        "_run_probe",
        lambda *_args, **_kwargs: _channel_stdout("2" * 40),
    )

    surfaces = module.probe_production_surfaces_under_release_lock(
        tmp_path,
        mobile_dir=mobile,
        expected_lock_token="durable-owner-token",
        runner=lambda *_args, **_kwargs: None,
    )

    assert lock_tokens == ["durable-owner-token"]
    assert surfaces.backend_sha == "a" * 40
    assert surfaces.mobile_ota_sha == "2" * 40


def test_mobile_identity_digest_detects_channel_aba_even_when_update_returns_to_a():
    module = _module()
    first = module._parse_mobile_evidence(
        _channel_stdout(channel_updated_at="2026-08-12T12:34:56.000Z"),
        expected_runtime="1.3.3",
    )
    returned_to_a = module._parse_mobile_evidence(
        _channel_stdout(channel_updated_at="2026-08-12T12:35:01.000Z"),
        expected_runtime="1.3.3",
    )

    assert first.group_id == returned_to_a.group_id
    assert first.update_id == returned_to_a.update_id
    assert first.digest != returned_to_a.digest


@pytest.mark.parametrize(
    ("field", "message"),
    (
        ("updatedAt", "updated"),
        ("branchMapping", "mapping"),
    ),
)
def test_mobile_identity_rejects_missing_channel_cas_fields(
    field: str,
    message: str,
):
    module = _module()
    payload = json.loads(_channel_stdout())
    del payload["currentPage"][field]

    with pytest.raises(module.ProductionProbeError, match=message):
        module._parse_mobile_evidence(
            json.dumps(payload),
            expected_runtime="1.3.3",
        )


def test_server_only_probe_binds_exact_remote_lease_token_and_skips_eas(
    tmp_path: Path,
) -> None:
    module = _module()
    observed: list[list[str]] = []

    def runner(command, **kwargs):
        del kwargs
        observed.append(list(command))
        return subprocess.CompletedProcess(
            command, 0, stdout=_server_stdout(), stderr=""
        )

    result = module.probe_server_surfaces_under_release_lock(
        tmp_path,
        expected_lock_token="exact-owner-token",
        runner=runner,
    )

    assert result == (
        "a" * 40,
        "e" * 64,
        "c" * 40,
        "d" * 64,
        "f" * 40,
        "1" * 64,
        "2" * 64,
    )
    assert len(observed) == 1
    assert observed[0][0] == "/usr/bin/ssh"
    assert observed[0][-2] == "root@39.98.206.178"
    assert "exec /usr/bin/python3 - exact-owner-token" in observed[0][-1]


@pytest.mark.parametrize("token", ("", "bad token", "x" * 129))
def test_server_only_probe_rejects_unsafe_expected_lease_token_before_ssh(
    tmp_path: Path,
    token: str,
) -> None:
    module = _module()
    calls: list[object] = []

    with pytest.raises(module.ProductionProbeError, match="lease token"):
        module.probe_server_surfaces_under_release_lock(
            tmp_path,
            expected_lock_token=token,
            runner=lambda *args, **kwargs: calls.append((args, kwargs)),
        )

    assert calls == []


@pytest.mark.parametrize(
    ("server_payload", "message"),
    [
        ({}, "missing or unexpected"),
        ({"checkout_revision": "not-a-sha"}, "missing or unexpected"),
        (
            json.loads(_server_stdout()) | {"repository_clean": False},
            "tracked and untracked clean",
        ),
        (
            json.loads(_server_stdout()) | {"backend_revision": "b" * 40},
            "backend runtime revision",
        ),
        (
            json.loads(_server_stdout()) | {"backend_proof_id": "invalid"},
            "backend runtime proof",
        ),
        (
            json.loads(_server_stdout()) | {"backend_health": "failed"},
            "backend health",
        ),
        (
            json.loads(_server_stdout()) | {"frontend_pm2": "stopped"},
            "frontend",
        ),
    ],
)
def test_server_probe_fails_closed_on_incomplete_or_unhealthy_evidence(
    tmp_path: Path, server_payload: dict[str, object], message: str
):
    module = _module()

    def runner(command, **kwargs):
        del kwargs
        stdout = json.dumps(server_payload) if command[0] == "/usr/bin/ssh" else _channel_stdout()
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with pytest.raises(module.ProductionProbeError, match=message):
        module.probe_production_surfaces(tmp_path, mobile_dir=tmp_path, runner=runner)


def test_server_probe_keeps_missing_frontend_receipt_explicitly_unknown(
    tmp_path: Path,
):
    module = _module()

    def runner(command, **kwargs):
        del kwargs
        stdout = (
            _server_stdout(frontend_sha=None, frontend_proof_id=None)
            if command[0] == "/usr/bin/ssh"
            else _channel_stdout()
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    result = module.probe_production_surfaces(
        tmp_path, mobile_dir=tmp_path, runner=runner
    )

    assert result.frontend_sha is None
    assert result.frontend_proof_id is None
    assert result.server_sha == "a" * 40


def test_server_probe_keeps_missing_mac_receipt_explicitly_unknown(tmp_path: Path):
    module = _module()

    def runner(command, **kwargs):
        del kwargs
        stdout = (
            _server_stdout(
                mac_sha=None,
                mac_artifact_sha256=None,
                mac_receipt_id=None,
            )
            if command[0] == "/usr/bin/ssh"
            else _channel_stdout()
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    result = module.probe_production_surfaces(
        tmp_path, mobile_dir=tmp_path, runner=runner
    )

    assert result.mac_sha is None
    assert result.mac_artifact_sha256 is None
    assert result.mac_receipt_id is None


@pytest.mark.parametrize(
    "server_payload",
    [
        json.loads(_server_stdout()) | {"frontend_revision": None},
        json.loads(_server_stdout()) | {"frontend_proof_id": None},
        json.loads(_server_stdout()) | {"frontend_proof_id": "invalid"},
    ],
)
def test_server_probe_rejects_partial_or_malformed_frontend_receipt_evidence(
    tmp_path: Path, server_payload: dict[str, object]
):
    module = _module()

    def runner(command, **kwargs):
        del kwargs
        stdout = (
            json.dumps(server_payload)
            if command[0] == "/usr/bin/ssh"
            else _channel_stdout()
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with pytest.raises(module.ProductionProbeError, match="frontend runtime proof"):
        module.probe_production_surfaces(
            tmp_path, mobile_dir=tmp_path, runner=runner
        )


@pytest.mark.parametrize(
    "server_payload",
    [
        json.loads(_server_stdout()) | {"mac_revision": None},
        json.loads(_server_stdout()) | {"mac_artifact_sha256": None},
        json.loads(_server_stdout()) | {"mac_receipt_id": None},
        json.loads(_server_stdout()) | {"mac_artifact_sha256": "invalid"},
    ],
)
def test_server_probe_rejects_partial_or_malformed_mac_receipt_evidence(
    tmp_path: Path, server_payload: dict[str, object]
):
    module = _module()

    def runner(command, **kwargs):
        del kwargs
        stdout = (
            json.dumps(server_payload)
            if command[0] == "/usr/bin/ssh"
            else _channel_stdout()
        )
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with pytest.raises(module.ProductionProbeError, match="Mac runtime proof"):
        module.probe_production_surfaces(
            tmp_path, mobile_dir=tmp_path, runner=runner
        )


def test_remote_probe_contract_binds_runtime_artifacts_and_uses_isolated_git():
    module = _module()
    probe = module._REMOTE_PROBE

    assert "--untracked-files=all" in probe
    assert "GIT_CONFIG_NOSYSTEM" in probe
    assert "GIT_CONFIG_GLOBAL" in probe
    assert "core.fsmonitor=false" in probe
    assert "core.hooksPath=/dev/null" in probe
    assert "/var/lib/health-app/release-state/runtime-state-terminal.json" in probe
    assert "health-backend.service" in probe
    assert "celery-worker.service" in probe
    assert "celery-beat.service" in probe
    assert '"MainPID"' in probe
    assert "/proc" in probe
    assert '"/opt/health-app/backend"' in probe
    assert "/var/lib/health-app/release-state/frontend-runtime.json" in probe
    assert '"pm_uptime"' in probe
    assert '"PM2_HOME": "/root/.pm2"' in probe
    assert '".next/BUILD_ID"' in probe
    assert "/var/lib/health-app/release-state/mac-runtime.json" in probe
    assert "/opt/health-app-shared/assets/mac/current.json" in probe
    assert "/opt/health-app-shared/assets/mac/releases" in probe
    assert "artifact_sha256" in probe
    assert "notary_status" in probe
    assert "stapled" in probe
    assert "O_NOFOLLOW" in probe
    assert "st_nlink" in probe


def test_remote_mac_receipt_accepts_only_stable_numeric_versions():
    module = _module()
    probe = module._REMOTE_PROBE
    version_re = _remote_contract_namespace(module)["VERSION_RE"]

    assert isinstance(version_re, re.Pattern)
    for value in ("1.0", "1.2.3", "1.2.3.4"):
        assert version_re.fullmatch(value) is not None
    for value in ("1", "v1.2", "1.2-beta", "1.2+42"):
        assert version_re.fullmatch(value) is None
    assert 'VERSION_RE.fullmatch(mac_receipt["version"]) is None' in probe


def test_remote_mac_receipt_accepts_only_numeric_bundle_builds():
    module = _module()
    probe = module._REMOTE_PROBE
    build_re = _remote_contract_namespace(module)["MAC_BUILD_RE"]

    assert isinstance(build_re, re.Pattern)
    for value in ("1", "2", "42", "1.2", "1.2.3"):
        assert build_re.fullmatch(value) is not None
    for value in ("", "v2", "2-beta", "2+7", "1.2.3.4"):
        assert build_re.fullmatch(value) is None
    assert 'MAC_BUILD_RE.fullmatch(mac_receipt["build"]) is None' in probe


def test_remote_mac_receipt_requires_a_strict_notary_uuid():
    module = _module()
    probe = module._REMOTE_PROBE
    uuid_re = _remote_contract_namespace(module)["UUID_RE"]

    assert isinstance(uuid_re, re.Pattern)
    assert uuid_re.fullmatch("123e4567-e89b-42d3-a456-426614174000") is not None
    assert uuid_re.fullmatch("00000000-0000-0000-0000-000000000000") is None
    assert uuid_re.fullmatch("123e4567e89b42d3a456426614174000") is None
    assert (
        'UUID_RE.fullmatch(mac_receipt["notary_submission_id"]) is None'
        in probe
    )


def test_remote_mac_receipt_restricts_architectures_to_supported_values():
    module = _module()
    probe = module._REMOTE_PROBE
    architectures = _remote_contract_namespace(module)["ARCHITECTURES"]

    assert architectures == {"arm64", "x86_64"}
    assert "item not in ARCHITECTURES" in probe


def test_remote_mac_receipt_requires_product_bundle_and_team_identity():
    module = _module()
    probe = module._REMOTE_PROBE
    namespace = _remote_contract_namespace(module)

    assert namespace["MAC_BUNDLE_ID"] == "life.executor.health.mac"
    assert namespace["MAC_TEAM_ID"] == "QA2U724DAN"
    assert 'mac_receipt.get("bundle_id") != MAC_BUNDLE_ID' in probe
    assert 'mac_receipt.get("team_id") != MAC_TEAM_ID' in probe


def test_remote_root_file_read_rechecks_descriptor_and_directory_entry_identity():
    module = _module()
    function = module._REMOTE_PROBE.split("def read_root_file(", 1)[1].split(
        "\n\ndef hash_root_file", 1
    )[0]

    assert "after = os.fstat(descriptor)" in function
    assert (
        "current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)"
        in function
    )
    assert "after.st_mtime_ns" in function
    assert "current.st_mtime_ns" in function
    assert "root file changed during verification" in function


def test_remote_probe_requires_exact_public_mac_manifest_projection():
    module = _module()
    probe = module._REMOTE_PROBE

    expected_public_fields = {
        "schema_version",
        "source_sha",
        "source_tree",
        "artifact_sha256",
        "artifact_size",
        "bundle_id",
        "version",
        "build",
        "architectures",
        "min_os",
        "artifact_url",
        "published_at",
    }
    namespace: dict[str, object] = {}
    public_fields_source = probe.split("public_fields = {", 1)[1].split("}\n", 1)[0]
    exec("value = {" + public_fields_source + "}", {}, namespace)

    assert namespace["value"] == expected_public_fields
    assert "set(current) != public_fields" in probe
    assert "current != expected_current" in probe
    for private_field in (
        "artifact_path",
        "team_id",
        "cdhash",
        "notary_submission_id",
        "notary_status",
        "stapled",
    ):
        assert private_field not in expected_public_fields


def test_remote_mac_probe_binds_the_stable_download_to_the_receipt_artifact():
    module = _module()
    probe = module._REMOTE_PROBE

    assert (
        'MAC_STABLE_PATH = "/opt/health-app-shared/assets/xiaoba-mac.dmg"'
        in probe
    )
    stable_block = probe.split("stable_root_fd = open_root_directory(", 1)[1].split(
        "mac_receipt_id =", 1
    )[0]
    assert "os.path.dirname(MAC_STABLE_PATH), mode=0o755" in stable_block
    assert "proved_stable = hash_root_file(" in stable_block
    assert "os.path.basename(MAC_STABLE_PATH)" in stable_block
    assert "mode=0o644" in stable_block
    assert "expected_size=artifact_size" in stable_block
    assert "if proved_stable != mac_artifact_sha256:" in stable_block
    assert "Mac stable artifact digest does not match runtime receipt" in stable_block


def test_remote_mac_probe_requires_bounded_public_https_route_proof():
    module = _module()
    probe = module._REMOTE_PROBE

    assert 'PUBLIC_MAC_BASE = "https://health.executor.life"' in probe
    assert "def read_public_bytes(" in probe
    assert "def public_artifact_marker(" in probe
    assert '"--proto", "=https"' in probe
    assert '"--tlsv1.2"' in probe
    assert '"--max-redirs", "0"' in probe
    assert "maximum + 1" in probe
    assert 'public_artifact_marker("/mac/current.json")' in probe
    assert '!= "mac-current-manifest"' in probe
    assert "public current manifest does not match runtime receipt" in probe
    assert "public immutable Mac artifact digest does not match runtime receipt" in probe
    assert "public stable Mac artifact digest does not match runtime receipt" in probe
    assert 'public_artifact_marker("/xiaoba-mac.dmg")' in probe
    assert '!= "xiaoba-mac-dmg"' in probe


def test_remote_mac_probe_rejects_pending_transaction_or_remote_lease_before_and_after_proof():
    module = _module()
    probe = module._REMOTE_PROBE

    assert (
        'MAC_JOURNAL_PATH = "/var/lib/health-app/release-state/mac-release.transaction.json"'
        in probe
    )
    assert (
        'REMOTE_RELEASE_LOCK_PATH = "/var/lib/health-app/release-state/deploy.lock"'
        in probe
    )
    assert "os.listdir(state_fd)" in probe
    assert "def assert_mac_release_quiescent(state_fd):" in probe
    assert "mac release transaction is still in progress" in probe.lower()
    assert "unified remote release lease is still held" in probe.lower()
    assert probe.count("assert_mac_release_quiescent(state_fd)") >= 2
    assert "EXPECTED_RELEASE_LOCK_TOKEN = sys.argv[1]" in probe
    assert "def assert_expected_release_lock(state_fd):" in probe
    assert "release lock ownership changed during production proof" in probe

    first_guard = probe.index("assert_mac_release_quiescent(state_fd)")
    receipt_read = probe.index("mac_receipt_value = read_root_file(")
    public_proof = probe.index('public_artifact_marker("/mac/current.json")')
    last_guard = probe.rindex("assert_mac_release_quiescent(state_fd)")
    result_emit = probe.index('"mac_revision": mac_revision')
    assert first_guard < receipt_read < public_proof < last_guard < result_emit


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (None, None),
        ("extra", "unsafe"),
        ("missing", "unsafe"),
        ("invalid-operation", "unsafe"),
    ),
)
def test_remote_probe_strictly_validates_generic_v2_release_lease(
    tmp_path: Path,
    mutation: str | None,
    message: str | None,
) -> None:
    module = _module()
    state_root = tmp_path / "state"
    state_root.mkdir(mode=0o700)
    token = "a" * 64
    lock_path = state_root / "deploy.lock"
    _write_v2_remote_lock(lock_path, token=token)
    if mutation == "extra":
        extra = lock_path / "unexpected"
        extra.write_text("x\n", encoding="ascii")
        extra.chmod(0o600)
    elif mutation == "missing":
        (lock_path / "request_digest").unlink()
    elif mutation == "invalid-operation":
        (lock_path / "operation").write_text("rollback\n", encoding="ascii")
        (lock_path / "operation").chmod(0o600)
    verifier, probe_failure = _remote_expected_lock_function(
        module,
        lock_path=lock_path,
        token=token,
    )
    state_fd = os.open(state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        if message is None:
            identity = verifier(state_fd)
            assert len(identity) == 3
        else:
            with pytest.raises(probe_failure, match=message):
                verifier(state_fd)
    finally:
        os.close(state_fd)


def test_remote_probe_resamples_all_server_identities_after_slow_public_proof():
    module = _module()
    probe = module._REMOTE_PROBE

    for helper in (
        "def checkout_identity():",
        "def backend_process_identity(marker_metadata):",
        "def frontend_process_identity():",
        "def root_file_identity(value):",
    ):
        assert helper in probe

    assert "initial_checkout_identity = checkout_identity()" in probe
    assert "confirmed_checkout_identity = checkout_identity()" in probe
    assert "initial_terminal_identity = root_file_identity(" in probe
    assert "confirmed_terminal_identity = root_file_identity(" in probe
    assert "initial_backend_process_identity = backend_process_identity(" in probe
    assert "confirmed_backend_process_identity = backend_process_identity(" in probe
    assert "initial_frontend_process_identity = frontend_process_identity()" in probe
    assert "confirmed_frontend_process_identity = frontend_process_identity()" in probe
    assert "initial_frontend_receipt_identity = root_file_identity(" in probe
    assert "confirmed_frontend_receipt_identity = root_file_identity(" in probe
    assert "initial_build_id_identity = root_file_identity(" in probe
    assert "confirmed_build_id_identity = root_file_identity(" in probe
    assert "production server identity changed during proof" in probe

    public_proof = probe.index('public_artifact_marker("/mac/current.json")')
    confirmed_checkout = probe.rindex("confirmed_checkout_identity = checkout_identity()")
    result_emit = probe.index('"mac_revision": mac_revision')
    assert public_proof < confirmed_checkout < result_emit


def test_public_mac_probe_timeouts_fit_inside_outer_ssh_budget():
    module = _module()
    probe = module._REMOTE_PROBE

    values: dict[str, int] = {}
    for name in (
        "PUBLIC_HEADER_TIMEOUT_SECONDS",
        "PUBLIC_MANIFEST_TIMEOUT_SECONDS",
        "PUBLIC_ARTIFACT_TIMEOUT_SECONDS",
    ):
        match = re.search(rf"^{name} = ([0-9]+)$", probe, re.MULTILINE)
        assert match is not None
        values[name] = int(match.group(1))

    maximum_public_seconds = (
        3 * values["PUBLIC_HEADER_TIMEOUT_SECONDS"]
        + values["PUBLIC_MANIFEST_TIMEOUT_SECONDS"]
        + 2 * values["PUBLIC_ARTIFACT_TIMEOUT_SECONDS"]
    )
    assert module.PROBE_TIMEOUT_SECONDS >= maximum_public_seconds + 60
    assert '"--max-time", str(max_time)' in probe
    assert '"--write-out", "%{http_code}"' in probe
    assert "public Mac response was not exact HTTP 200" in probe
    assert "public Mac header probe was not exact HTTP 200" in probe
    assert "public Mac artifact was not exact HTTP 200" in probe


@pytest.mark.parametrize(
    ("name", "next_name", "payload", "arguments"),
    (
        ("read_public_bytes", "public_artifact_marker", b"body302", ("/x",)),
        (
            "public_artifact_marker",
            "hash_public_artifact",
            b"HTTP/1.1 302 Found\r\nx-reva-artifact: marker\r\n\r\n302",
            ("/x",),
        ),
        (
            "hash_public_artifact",
            "valid_utc_timestamp",
            b"body302",
            ("/x",),
        ),
    ),
)
def test_public_mac_probe_dynamically_rejects_http_302(
    name: str,
    next_name: str,
    payload: bytes,
    arguments: tuple[str, ...],
) -> None:
    module = _module()
    function, probe_failure = _remote_public_function(
        module, name, next_name, payload
    )

    with pytest.raises(probe_failure, match="HTTP 200"):
        if name == "read_public_bytes":
            function(*arguments, maximum=16)
        elif name == "hash_public_artifact":
            function(*arguments, expected_size=4, maximum=16)
        else:
            function(*arguments)


def test_remote_probe_resamples_health_after_public_proof_before_quiescence():
    module = _module()
    probe = module._REMOTE_PROBE

    assert probe.count("assert_local_health()") == 3  # definition plus two calls
    public_proof = probe.index('public_artifact_marker("/mac/current.json")')
    second_health = probe.rindex("assert_local_health()")
    final_quiescence = max(
        probe.rindex("assert_mac_release_quiescent(state_fd)"),
        probe.rindex("assert_expected_release_lock(state_fd)"),
    )
    assert public_proof < second_health < final_quiescence


def test_remote_probe_fails_when_second_health_sample_returns_500():
    module = _module()
    calls: list[str] = []

    def run(argv, **_kwargs):
        url = argv[-1]
        calls.append(url)
        if len(calls) == 3:
            return "500"
        return "200"

    health, probe_failure = _remote_health_function(module, run)
    health()
    with pytest.raises(probe_failure, match="HTTP 200"):
        health()

    assert calls == [
        "http://127.0.0.1:8000/api/v1/health",
        "http://127.0.0.1:3000/",
        "http://127.0.0.1:8000/api/v1/health",
    ]


@pytest.mark.parametrize("redirect_call", (1, 2), ids=("backend", "frontend"))
def test_remote_probe_rejects_local_health_http_302(redirect_call: int):
    module = _module()
    calls: list[list[str]] = []

    def run(argv, **_kwargs):
        calls.append(list(argv))
        return "302" if len(calls) == redirect_call else "200"

    health, probe_failure = _remote_health_function(module, run)
    with pytest.raises(probe_failure, match="HTTP 200"):
        health()

    assert calls[-1][-1] in {
        "http://127.0.0.1:8000/api/v1/health",
        "http://127.0.0.1:3000/",
    }
    assert "--max-redirs" in calls[-1]
    assert "--write-out" in calls[-1]


def test_bounded_local_probe_kills_unbounded_combined_output(tmp_path: Path):
    module = _module()
    producer = tmp_path / "producer.py"
    producer.write_text(
        "import os\n"
        "chunk = b'x' * 16384\n"
        "while True:\n"
        "    os.write(1, chunk)\n"
        "    os.write(2, chunk)\n",
        encoding="utf-8",
    )
    started = time.monotonic()

    with pytest.raises(module.ProductionProbeError, match="output exceeds"):
        module._run_probe(
            subprocess.run,
            [sys.executable, str(producer)],
            label="unbounded probe",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )

    assert time.monotonic() - started < 5


def test_bounded_remote_probe_kills_unbounded_combined_output(tmp_path: Path):
    module = _module()
    remote_run, probe_failure = _remote_run_function(module)
    producer = tmp_path / "remote-producer.py"
    producer.write_text(
        "import os\n"
        "chunk = b'x' * 16384\n"
        "while True:\n"
        "    os.write(1, chunk)\n"
        "    os.write(2, chunk)\n",
        encoding="utf-8",
    )
    started = time.monotonic()

    with pytest.raises(probe_failure, match="output exceeds"):
        remote_run([sys.executable, str(producer)])

    assert time.monotonic() - started < 5


@pytest.mark.parametrize(
    "lease_name",
    (
        "deploy.lock",
        ".deploy.lock.released-foreign-token",
        ".deploy.lock.alloc-foreign-token",
        ".deploy.lock.state-foreign-token",
        ".deploy.lock.mac-creating-foreign-token",
        ".deploy.lock.mac-phase-foreign-token",
        ".deploy.lock.mac-releasing-foreign-token",
    ),
)
def test_remote_mac_quiescence_guard_rejects_canonical_and_partial_foreign_leases(
    tmp_path: Path, lease_name: str
):
    module = _module()
    state_root = tmp_path / "state"
    state_root.mkdir()
    lock_path = state_root / "deploy.lock"
    guard, probe_failure = _remote_quiescence_function(module, lock_path=lock_path)
    state_fd = os.open(state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        guard(state_fd)
        (state_root / lease_name).mkdir()
        with pytest.raises(probe_failure, match="lease is still held"):
            guard(state_fd)
    finally:
        os.close(state_fd)


def test_remote_mac_quiescence_guard_rejects_pending_formal_journal(tmp_path: Path):
    module = _module()
    state_root = tmp_path / "state"
    state_root.mkdir()
    guard, probe_failure = _remote_quiescence_function(
        module, lock_path=state_root / "deploy.lock"
    )
    (state_root / "mac-release.transaction.json").write_text(
        "pending\n", encoding="utf-8"
    )
    state_fd = os.open(state_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        with pytest.raises(probe_failure, match="transaction is still in progress"):
            guard(state_fd)
    finally:
        os.close(state_fd)


def test_remote_artifact_hash_contract_rejects_missing_tampered_and_wrong_mode(
    tmp_path: Path,
):
    module = _module()
    hash_root_file, probe_failure = _remote_hash_function(module)
    directory = tmp_path / "assets"
    directory.mkdir(mode=0o755)
    root_fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        with pytest.raises(FileNotFoundError):
            hash_root_file(
                root_fd,
                "xiaoba-mac.dmg",
                mode=0o644,
                expected_size=4,
                maximum=1024,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
            )

        stable = directory / "xiaoba-mac.dmg"
        stable.write_bytes(b"good")
        stable.chmod(0o644)
        expected = hashlib.sha256(b"good").hexdigest()
        assert (
            hash_root_file(
                root_fd,
                stable.name,
                mode=0o644,
                expected_size=4,
                maximum=1024,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
            )
            == expected
        )

        stable.write_bytes(b"evil")
        actual = hash_root_file(
            root_fd,
            stable.name,
            mode=0o644,
            expected_size=4,
            maximum=1024,
            expected_uid=os.geteuid(),
            expected_gid=os.getegid(),
        )
        assert actual != expected

        stable.chmod(0o600)
        with pytest.raises(probe_failure, match="unsafe root artifact"):
            hash_root_file(
                root_fd,
                stable.name,
                mode=0o644,
                expected_size=4,
                maximum=1024,
                expected_uid=os.geteuid(),
                expected_gid=os.getegid(),
            )
    finally:
        os.close(root_fd)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (_channel_stdout(branches=2), "single active branch"),
        (_channel_stdout(groups=2), "single active group"),
        (_channel_stdout(dirty=True), "dirty"),
        (_channel_stdout().replace('"ios"', '"android"'), "iOS"),
        (_channel_stdout(environment="preview"), "production"),
    ],
)
def test_ota_probe_fails_closed_on_rollout_or_contradictory_identity(
    tmp_path: Path, payload: str, message: str
):
    module = _module()

    def runner(command, **kwargs):
        del kwargs
        stdout = _server_stdout() if command[0] == "/usr/bin/ssh" else payload
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    with pytest.raises(module.ProductionProbeError, match=message):
        module.probe_production_surfaces(tmp_path, mobile_dir=tmp_path, runner=runner)


def test_production_probe_records_live_runtime_without_assuming_target_runtime(
    tmp_path: Path,
) -> None:
    module = _module()
    live_payload = _channel_stdout().replace('"1.3.3"', '"9.9.9"')

    def runner(command, **kwargs):
        del kwargs
        stdout = _server_stdout() if command[0] == "/usr/bin/ssh" else live_payload
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    surfaces = module.probe_production_surfaces(
        tmp_path,
        mobile_dir=tmp_path,
        runner=runner,
    )
    assert surfaces.mobile_runtime == "9.9.9"

    with pytest.raises(module.ProductionProbeError, match="source runtime"):
        module._parse_mobile_evidence(
            live_payload,
            expected_runtime="1.3.3",
        )


def test_probe_rejects_nonzero_oversize_and_non_utf8_output(tmp_path: Path):
    module = _module()

    for completed in (
        subprocess.CompletedProcess([], 7, stdout="", stderr="denied"),
        subprocess.CompletedProcess([], 0, stdout="x" * (module.MAX_PROBE_BYTES + 1), stderr=""),
        subprocess.CompletedProcess([], 0, stdout=b"\xff", stderr=b""),
    ):
        with pytest.raises(module.ProductionProbeError):
            module._checked_output(completed, label="probe")
