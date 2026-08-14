import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROKID_ROOT = ROOT / "apps" / "rokid-pushup-glasses"
POSIX_WRAPPER = ROKID_ROOT / "gradlew"
WINDOWS_WRAPPER = ROKID_ROOT / "gradlew.bat"


def test_rokid_gradle_wrapper_freezes_before_java_or_gradle(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "external-tool-called"
    for name in ("adb", "dirname", "java", "uname"):
        tool = fake_bin / name
        tool.write_text(
            f'#!/bin/sh\nprintf "%s\\n" "{name}" >> "{marker}"\nexit 91\n',
            encoding="utf-8",
        )
        tool.chmod(0o755)

    result = subprocess.run(
        ["/bin/sh", str(POSIX_WRAPPER), "assembleRelease"],
        cwd=ROKID_ROOT,
        env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78
    assert "frozen" in result.stderr.lower()
    assert not marker.exists()


def test_windows_rokid_wrapper_has_an_early_unconditional_freeze() -> None:
    meaningful = [
        line.strip().lower()
        for line in WINDOWS_WRAPPER.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().lower().startswith("@rem")
    ]

    assert meaningful[0].startswith("@echo rokid native build/sign/install entrypoint is frozen")
    assert meaningful[1] == "@exit /b 78"


def test_rokid_readme_does_not_offer_copyable_build_or_install_commands() -> None:
    readme = (ROKID_ROOT / "README.md").read_text(encoding="utf-8")

    assert "./gradlew assembleRelease" not in readme
    assert "adb install" not in readme
    assert "manual external Gate" in readme
