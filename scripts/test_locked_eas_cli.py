from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/locked_eas_cli.py"


@pytest.mark.parametrize(
    "arguments",
    (
        (),
        ("--help",),
        ("prepare", "--repo-root", "/must-not-resolve"),
        ("cleanup", "/must-not-resolve"),
    ),
)
def test_direct_cli_is_frozen_before_imports_paths_network_or_tokens(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    isolated = tmp_path / "scripts"
    isolated.mkdir()
    script = isolated / MODULE_PATH.name
    shutil.copyfile(MODULE_PATH, script)
    marker = tmp_path / "import-or-tool-called"
    (isolated / "argparse.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported')\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("curl", "git", "node", "npm", "npx", "ssh"):
        tool = fake_bin / name
        tool.write_text(
            f"#!/bin/sh\nprintf called >> {marker!s}\nexit 91\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)
    secret = "expo-token-must-not-leak"

    completed = subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": str(fake_bin),
            "HOME": str(tmp_path / "poison-home"),
            "EXPO_TOKEN": secret,
            "NPM_CONFIG_USERCONFIG": str(tmp_path / "must-not-read-npmrc"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 78
    assert "direct EAS CLI preparation is frozen" in completed.stderr
    assert secret not in completed.stdout + completed.stderr
    assert "/must-not-resolve" not in completed.stdout + completed.stderr
    assert not marker.exists()


def _module():
    spec = importlib.util.spec_from_file_location("locked_eas_cli", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _materializing_runner(observed: list[dict[str, object]]):
    def runner(command, **kwargs):
        observed.append({"command": list(command), **kwargs})
        tool = Path(kwargs["cwd"])
        package = tool / "node_modules/eas-cli/package.json"
        package.parent.mkdir(parents=True)
        package.write_text(json.dumps({"version": "21.8.0"}), encoding="utf-8")
        typescript = tool / "node_modules/typescript/package.json"
        typescript.parent.mkdir(parents=True)
        typescript.write_text(json.dumps({"version": "5.9.3"}), encoding="utf-8")
        executable = tool / "node_modules/eas-cli/bin/run"
        executable.parent.mkdir(parents=True)
        executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        executable.chmod(0o700)
        binary_dir = tool / "node_modules/.bin"
        binary_dir.mkdir(parents=True)
        (binary_dir / "eas").symlink_to(Path("../eas-cli/bin/run"))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    return runner


def test_fresh_checkout_without_node_modules_prepares_exact_locked_eas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    observed: list[dict[str, object]] = []
    monkeypatch.setenv("NODE_OPTIONS", "--require=/tmp/inject")
    monkeypatch.setenv("NPM_CONFIG_USERCONFIG", "/tmp/poison")
    monkeypatch.setenv("OTA_EAS_RUNNER", "/tmp/poison-eas")

    workspace, executable = module.prepare_locked_eas_cli(
        ROOT,
        runner=_materializing_runner(observed),
    )
    try:
        assert executable.is_symlink()
        assert executable.resolve().is_file()
        assert observed[0]["command"] == [
            "/usr/local/bin/npm",
            "ci",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ]
        assert observed[0]["stdout"] is subprocess.DEVNULL
        assert observed[0]["stderr"] is subprocess.DEVNULL
        environment = observed[0]["env"]
        user_config = Path(environment["NPM_CONFIG_USERCONFIG"])
        global_config = Path(environment["NPM_CONFIG_GLOBALCONFIG"])
        assert user_config != global_config
        assert user_config.read_bytes() == b""
        assert global_config.read_bytes() == b""
        assert user_config.stat().st_mode & 0o7777 == 0o400
        assert global_config.stat().st_mode & 0o7777 == 0o400
        assert environment["NPM_CONFIG_IGNORE_SCRIPTS"] == "true"
        for name in ("NODE_OPTIONS", "OTA_EAS_RUNNER"):
            assert name not in environment
        receipt = (workspace / "tool.receipt").read_text(encoding="ascii")
        assert "eas_cli=21.8.0" in receipt
        assert "lock_digest=" in receipt
    finally:
        module.cleanup_locked_eas_cli(workspace)
    assert not workspace.exists()


def test_locked_eas_install_failure_fails_closed_and_removes_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _module()
    created: list[Path] = []
    original_mkdtemp = module.tempfile.mkdtemp

    def tracked_mkdtemp(*args, **kwargs):
        path = Path(original_mkdtemp(*args, **kwargs))
        created.append(path)
        return str(path)

    monkeypatch.setattr(module.tempfile, "mkdtemp", tracked_mkdtemp)

    def failing_runner(command, **kwargs):
        del kwargs
        return subprocess.CompletedProcess(command, 17, stdout=b"", stderr=b"denied")

    with pytest.raises(module.LockedEasCliError, match="failed"):
        module.prepare_locked_eas_cli(ROOT, runner=failing_runner)

    assert len(created) == 1
    assert not created[0].exists()


@pytest.mark.parametrize("name", ["package.json", "package-lock.json"])
def test_group_writable_integrity_input_is_rejected(
    tmp_path: Path,
    name: str,
) -> None:
    module = _module()
    repo = tmp_path / "repo"
    source = repo / "scripts/eas-cli-tool"
    source.mkdir(parents=True)
    for filename in ("package.json", "package-lock.json"):
        target = source / filename
        target.write_bytes((ROOT / "scripts/eas-cli-tool" / filename).read_bytes())
        target.chmod(0o644)
    (source / name).chmod(0o664)

    with pytest.raises(module.LockedEasCliError, match="unsafe locked EAS input"):
        module.prepare_locked_eas_cli(
            repo,
            runner=_materializing_runner([]),
        )


def test_manifest_rejects_any_unpinned_root_dependency() -> None:
    module = _module()
    manifest = json.loads(
        (ROOT / "scripts/eas-cli-tool/package.json").read_text(encoding="utf-8")
    )
    lock = (ROOT / "scripts/eas-cli-tool/package-lock.json").read_bytes()
    manifest["dependencies"]["left-pad"] = "1.3.0"
    with pytest.raises(module.LockedEasCliError, match="not exact"):
        module._validate_manifests(
            json.dumps(manifest).encode("utf-8"),
            lock,
        )
