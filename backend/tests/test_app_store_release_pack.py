import os
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from scripts.check_app_store_release_pack import validate_release_narrative

REQUIRED_SCREENSHOT_NAMES = [
    "00-launch",
    "01-today",
    "02-chat",
    "03-record",
    "04-me",
    "05-import",
    "06-privacy",
]


def _write_png(path: Path, *, width: int = 1290, height: int = 2796) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    scanline = b"\x00" + b"\xff\xff\xff" * width
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(scanline * height, level=9))
        + chunk(b"IEND", b"")
    )


def _write_manifest(directory: Path, *, privacy_status: str = "demo") -> None:
    screens = []
    for name in REQUIRED_SCREENSHOT_NAMES:
        _write_png(directory / f"{name}.png")
        screens.append({"name": name, "file": f"{name}.png", "route": "/"})

    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "captured_at": "2026-06-28T16:30:00Z",
                "privacy_status": privacy_status,
                "app_store_ready": privacy_status in {"demo", "sanitized"},
                "screens": screens,
            }
        ),
        encoding="utf-8",
    )


def test_app_store_release_pack_checker_passes():
    root = Path(__file__).resolve().parents[2]

    result = subprocess.run(
        [sys.executable, "scripts/check_app_store_release_pack.py"],
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "iOS App Store submission preflight passed." in result.stdout
    assert "App Store release pack check passed." in result.stdout


def test_app_store_release_pack_checker_validates_optional_screenshot_dir(tmp_path: Path):
    root = Path(__file__).resolve().parents[2]
    screenshot_dir = tmp_path / "screens"
    screenshot_dir.mkdir()
    _write_manifest(screenshot_dir, privacy_status="demo")

    result = subprocess.run(
        [sys.executable, "scripts/check_app_store_release_pack.py"],
        cwd=root,
        env={**os.environ, "APP_STORE_SCREENSHOT_DIR": str(screenshot_dir)},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "App Store screenshot check passed." in result.stdout


def test_app_store_release_pack_final_submit_fails_loud_without_human_materials():
    root = Path(__file__).resolve().parents[2]
    scrubbed_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("ASC_")
        and not key.startswith("APP_STORE_CONNECT_")
        and key != "APP_STORE_SCREENSHOT_DIR"
    }

    result = subprocess.run(
        [sys.executable, "scripts/check_app_store_release_pack.py", "--final-submit"],
        cwd=root,
        env=scrubbed_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert "final submit requires APP_STORE_SCREENSHOT_DIR or --screenshot-dir" in result.stderr
    assert "final submit requires replacing demo account placeholders" in result.stderr
    assert "missing App Store Connect credentials" in result.stderr


def test_release_narrative_rejects_stale_public_positioning():
    failures = validate_release_narrative(
        submission=(
            "Reva 是你的健康助理。"
            "本版本重构了移动端核心动线: 今日、私教、记录、我的。"
        ),
        review_notes="Go to `私教` and ask a question.",
        screenshot_runbook="Bottom navigation labels are `今日 / 私教 / 记录 / 我的`.",
    )

    assert "release text contains stale user-visible term: Reva" in failures
    assert "release text contains stale user-visible term: 健康助理" in failures
    assert "release text contains stale user-visible term: 私教" in failures
    assert "release text must use current bottom navigation labels: 今日 / 阿衡 / 记录 / 我" in failures
    assert "release text must include current positioning term: 健康参谋" in failures
