from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]

# This is the complete repository inventory of shell entrypoints that advertise
# a freeze boundary or contain an exit-78 tombstone. Keep it explicit so adding
# a new frozen wrapper also requires choosing whether it is fully frozen or
# retains a narrowly scoped local-only mode.
FULLY_FROZEN_ENTRYPOINTS = (
    ".claude/skills/mobile-testflight-release/scripts/native-archive-asc.sh",
    "apps/mac/scripts/package-app.sh",
    "apps/mac/scripts/release-dmg.sh",
    "apps/rokid-pushup-glasses/gradlew",
    "deploy-remote.sh",
    "deploy.sh",
    "deploy_production.sh",
    "deploy_to_server.sh",
    "packages/mini-program/build-on-server.sh",
    "scripts/_run-mobile-tf.sh",
    "scripts/mac-release-nginx-bootstrap.sh",
    "scripts/mobile-android-frozen.sh",
    "scripts/mobile-fast-device.sh",
    "scripts/mobile-local-archive.sh",
    "scripts/mobile-local-device.sh",
    "scripts/mobile-ota-rollback.sh",
    "scripts/mobile-ota.sh",
    "scripts/release.sh",
)
LOCAL_ONLY_ENTRYPOINTS = (
    "scripts/mobile-local-qr.sh",
    "scripts/run_ios_real_device_acceptance.sh",
)
WINDOWS_FROZEN_ENTRYPOINTS = ("apps/rokid-pushup-glasses/gradlew.bat",)
ALL_FROZEN_ENTRYPOINTS = (
    *FULLY_FROZEN_ENTRYPOINTS,
    *LOCAL_ONLY_ENTRYPOINTS,
    *WINDOWS_FROZEN_ENTRYPOINTS,
)


def _repository_shell_candidates() -> set[Path]:
    candidates: set[Path] = set(ROOT.glob("*.sh"))
    for directory in (".claude", "apps", "backend", "packages", "scripts"):
        candidates.update((ROOT / directory).glob("**/*.sh"))
    candidates.update((ROOT / "apps").glob("**/gradlew"))
    candidates.update((ROOT / "apps").glob("**/gradlew.bat"))
    return {
        path
        for path in candidates
        if path.is_file()
        and not {"node_modules", ".git", ".venv", "venv"}.intersection(path.parts)
    }


def test_frozen_shell_entrypoint_inventory_is_complete() -> None:
    exit_78 = re.compile(r"(?m)^[ \t]*@?exit[ \t]+(?:/b[ \t]+)?78(?:[ \t]|$)")
    freeze_marker = re.compile(
        r"(?i)(?:\bfrozen\b|已冻结|manual (?:release |external |infrastructure )?gate)"
    )
    discovered = {
        path.relative_to(ROOT).as_posix()
        for path in _repository_shell_candidates()
        if (
            exit_78.search(source := path.read_text(encoding="utf-8"))
            or freeze_marker.search(source)
        )
    }

    assert discovered == set(ALL_FROZEN_ENTRYPOINTS)


def _write_external_tool_stubs(fake_bin: Path, marker: Path) -> None:
    fake_bin.mkdir()
    for name in (
        "base64",
        "basename",
        "bash",
        "cat",
        "chmod",
        "cmp",
        "codesign",
        "cp",
        "curl",
        "date",
        "dirname",
        "env",
        "find",
        "git",
        "head",
        "java",
        "mkdir",
        "mktemp",
        "npm",
        "npx",
        "open",
        "osascript",
        "pgrep",
        "pkill",
        "plutil",
        "pod",
        "python",
        "python3",
        "rm",
        "rsync",
        "scp",
        "sed",
        "seq",
        "shasum",
        "sleep",
        "ssh",
        "swift",
        "tr",
        "uname",
        "unzip",
        "xargs",
        "xcodebuild",
        "xcrun",
    ):
        tool = fake_bin / name
        tool.write_text(
            f"#!/bin/sh\n: > {str(marker)!r}\nexit 91\n",
            encoding="utf-8",
        )
        tool.chmod(0o755)


@pytest.mark.parametrize(
    "relative_path",
    (*FULLY_FROZEN_ENTRYPOINTS, *LOCAL_ONLY_ENTRYPOINTS),
)
def test_hostile_source_cannot_cross_a_frozen_boundary(
    tmp_path: Path,
    relative_path: str,
) -> None:
    fake_bin = tmp_path / "bin"
    external_marker = tmp_path / "external-tool-called"
    poison_marker = tmp_path / "poison-function-called"
    function_marker = tmp_path / "entrypoint-function-loaded"
    status_marker = tmp_path / "source-returned-nonzero"
    _write_external_tool_stubs(fake_bin, external_marker)

    harness = r'''
exit() { : > "$POISON_MARKER"; }
builtin() { : > "$POISON_MARKER"; }
printf() { : > "$POISON_MARKER"; }
set() { : > "$POISON_MARKER"; }
before="$(declare -F)"
source "$SCRIPT_UNDER_TEST"
source_status=$?
after="$(declare -F)"
if [[ "$before" != "$after" ]]; then
  : > "$FUNCTION_MARKER"
fi
if [[ "$source_status" -ne 0 ]]; then
  : > "$STATUS_MARKER"
fi
'''
    result = subprocess.run(
        ["/bin/bash", "--noprofile", "--norc", "-c", harness],
        cwd=tmp_path,
        env={
            "HOME": str(tmp_path),
            "PATH": str(fake_bin),
            "SCRIPT_UNDER_TEST": str(ROOT / relative_path),
            "POISON_MARKER": str(poison_marker),
            "FUNCTION_MARKER": str(function_marker),
            "STATUS_MARKER": str(status_marker),
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not poison_marker.exists(), relative_path
    assert not external_marker.exists(), relative_path
    assert not function_marker.exists(), relative_path
    assert not status_marker.exists(), relative_path


@pytest.mark.parametrize("relative_path", FULLY_FROZEN_ENTRYPOINTS)
def test_fully_frozen_entrypoint_still_returns_78_when_executed(
    tmp_path: Path,
    relative_path: str,
) -> None:
    fake_bin = tmp_path / "bin"
    external_marker = tmp_path / "external-tool-called"
    _write_external_tool_stubs(fake_bin, external_marker)
    result = subprocess.run(
        [str(ROOT / relative_path)],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )

    assert result.returncode == 78, (relative_path, result.stdout, result.stderr)
    assert not external_marker.exists(), relative_path


def test_windows_gradle_wrapper_is_a_truncated_tombstone() -> None:
    meaningful = [
        line.strip().lower()
        for line in (ROOT / WINDOWS_FROZEN_ENTRYPOINTS[0])
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip() and not line.strip().lower().startswith("@rem")
    ]

    assert meaningful == [
        "@echo rokid native build/sign/install entrypoint is frozen; use the manual external gate. 1>&2",
        "@exit /b 78",
    ]


def test_local_ipa_inspection_has_no_install_or_remote_publish_branch() -> None:
    source = (ROOT / "scripts/mobile-local-qr.sh").read_text(encoding="utf-8")

    for forbidden in (
        "DEPLOY_SERVER",
        "IOS_LOCAL_QR_PUBLIC",
        "IOS_LOCAL_QR_REMOTE",
        "REMOTE_DIR",
        "curl ",
        "health.executor.life",
        "itms-services",
        "manifest.plist",
        "qrencode",
        "rsync ",
        "ssh ",
    ):
        assert forbidden not in source


@pytest.mark.parametrize("relative_path", LOCAL_ONLY_ENTRYPOINTS)
def test_local_only_entrypoint_wraps_implementation_in_direct_execution_guard(
    relative_path: str,
) -> None:
    source = (ROOT / relative_path).read_text(encoding="utf-8")

    assert 'if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then' in source
