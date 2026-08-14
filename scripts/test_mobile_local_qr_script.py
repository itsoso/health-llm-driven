from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import plistlib
import subprocess
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/mobile-local-qr.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_external_path(tmp_path: Path) -> tuple[Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "external-called"
    for name in (
        "curl",
        "date",
        "dirname",
        "git",
        "node",
        "rsync",
        "ssh",
        "xcodebuild",
    ):
        _write_executable(
            fake_bin / name,
            f"#!/bin/sh\n: > {str(marker)!r}\nexit 97\n",
        )
    return fake_bin, marker


@pytest.mark.parametrize(
    "arguments",
    (
        (),
        ("--no-upload",),
        ("--ipa", "missing.ipa"),
        ("--ipa", "missing.ipa", "--no-upload"),
        ("--no-upload", "--ipa", "--no-upload"),
        ("--no-upload", "--ipa", "missing.ipa", "--build-id", "legacy"),
    ),
)
def test_disallowed_qr_modes_freeze_before_external_tools(
    tmp_path: Path,
    arguments: tuple[str, ...],
) -> None:
    fake_bin, marker = _fake_external_path(tmp_path)

    result = subprocess.run(
        ["/bin/bash", str(SCRIPT), *arguments],
        cwd=tmp_path,
        env={"PATH": str(fake_bin)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 78, result.stdout + result.stderr
    assert "--no-upload --ipa EXISTING" in result.stderr
    assert not marker.exists()


def _write_ipa(path: Path) -> bytes:
    info = plistlib.dumps(
        {
            "CFBundleIdentifier": "life.executor.health",
            "CFBundleShortVersionString": "1.2.3",
            "CFBundleVersion": "42",
        }
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Payload/HealthPilot.app/Info.plist", info)
        archive.writestr("Payload/HealthPilot.app/HealthPilot", b"fake-binary")
    return path.read_bytes()


def test_existing_ipa_mode_writes_offline_inspection_evidence_only(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    copied_script = scripts / SCRIPT.name
    copied_script.write_bytes(SCRIPT.read_bytes())
    copied_script.chmod(0o755)
    ipa = tmp_path / "candidate.ipa"
    ipa_bytes = _write_ipa(ipa)
    marker = tmp_path / "network-called"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for name in ("curl", "git", "rsync", "ssh", "xcodebuild"):
        _write_executable(
            fake_bin / name,
            f"#!/bin/sh\n: > {str(marker)!r}\nexit 97\n",
        )
    (repository / ".env").write_text(
        f"ssh attacker.invalid ': > {str(marker)!r}'\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "/bin/bash",
            str(copied_script),
            "--no-upload",
            "--ipa",
            str(ipa),
        ],
        cwd=repository,
        env={"PATH": f"{fake_bin}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert not marker.exists()
    digest = hashlib.sha256(ipa_bytes).hexdigest()
    output = repository / "artifacts/ios-ipa-inspection" / digest[:16]
    assert (output / ipa.name).read_bytes() == ipa_bytes
    payload = json.loads((output / "inspection.json").read_text(encoding="utf-8"))
    assert payload == {
        "build": "42",
        "bundle_id": "life.executor.health",
        "installable": False,
        "ipa_file": "candidate.ipa",
        "ipa_sha256": digest,
        "ipa_size": len(ipa_bytes),
        "purpose": "offline_ipa_inspection",
        "schema_version": 1,
        "version": "1.2.3",
    }
    report = (output / "inspection.html").read_text(encoding="utf-8")
    assert "evidence only" in report
    assert "does not install or publish" in report
    assert not (output / "manifest.plist").exists()
    assert not (output / "qr.png").exists()


def test_existing_ipa_mode_reuses_same_digest_directory_safely(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    scripts = repository / "scripts"
    scripts.mkdir(parents=True)
    copied_script = scripts / SCRIPT.name
    copied_script.write_bytes(SCRIPT.read_bytes())
    copied_script.chmod(0o755)
    ipa = tmp_path / "candidate.ipa"
    _write_ipa(ipa)

    commands = [
        ["/bin/bash", str(copied_script), "--no-upload", "--ipa", str(ipa)],
    ] * 2
    for command in commands:
        result = subprocess.run(
            command,
            cwd=repository,
            env={"PATH": "/usr/bin:/bin"},
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr


def test_mobile_local_qr_source_has_no_install_or_publish_implementation() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

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
