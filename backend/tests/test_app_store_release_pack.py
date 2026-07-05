import os
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from scripts.check_app_store_release_pack import (
    validate_app_review_redlines,
    validate_demo_review_credentials,
    validate_release_narrative,
)

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


def test_demo_review_credentials_accept_env_for_final_submit_with_placeholder_notes():
    review_notes = (
        "- Demo account: `[NEEDS APP STORE REVIEW DEMO ACCOUNT]`\n"
        "- Password: `[NEEDS APP STORE REVIEW DEMO PASSWORD]`\n"
    )

    failures = validate_demo_review_credentials(
        review_notes,
        final_submit=True,
        env={
            "APP_STORE_REVIEW_DEMO_ACCOUNT": "app-review@example.com",
            "APP_STORE_REVIEW_DEMO_PASSWORD": "review-password",
            "APP_STORE_REVIEW_CONTACT_PHONE": "+8613800138000",
        },
    )

    assert failures == []


def test_demo_review_credentials_final_submit_accepts_real_values_in_notes():
    review_notes = (
        "- Demo account: `demo-reviewer@example.com`\n"
        "- Password: `real-review-password`\n"
    )

    failures = validate_demo_review_credentials(
        review_notes,
        final_submit=True,
        env={"APP_STORE_REVIEW_CONTACT_PHONE": "+8613800138000"},
    )

    assert failures == []


def test_demo_review_credentials_final_submit_fails_closed_when_lines_deleted():
    # Deleting the credential lines must fail even with env vars set: there is no
    # placeholder left to substitute, so the pasted notes would carry no credentials.
    review_notes = "## Reviewer Access\n\n- Region: China / United States compatible.\n"

    failures = validate_demo_review_credentials(
        review_notes,
        final_submit=True,
        env={
            "APP_STORE_REVIEW_DEMO_ACCOUNT": "app-review@example.com",
            "APP_STORE_REVIEW_DEMO_PASSWORD": "review-password",
            "APP_STORE_REVIEW_CONTACT_PHONE": "+8613800138000",
        },
    )

    joined = "\n".join(failures)
    assert "final submit requires a `Demo account:` line" in joined
    assert "final submit requires a `Password:` line" in joined


def test_demo_review_credentials_final_submit_fails_closed_on_blank_values():
    review_notes = "- Demo account: ``\n- Password:\n"

    failures = validate_demo_review_credentials(
        review_notes,
        final_submit=True,
        env={
            "APP_STORE_REVIEW_DEMO_ACCOUNT": "app-review@example.com",
            "APP_STORE_REVIEW_DEMO_PASSWORD": "review-password",
            "APP_STORE_REVIEW_CONTACT_PHONE": "+8613800138000",
        },
    )

    joined = "\n".join(failures)
    assert "non-empty `Demo account:` value" in joined
    assert "non-empty `Password:` value" in joined


def test_demo_review_credentials_final_submit_placeholders_without_env_fail():
    review_notes = (
        "- Demo account: `[NEEDS APP STORE REVIEW DEMO ACCOUNT]`\n"
        "- Password: `[NEEDS APP STORE REVIEW DEMO PASSWORD]`\n"
    )

    failures = validate_demo_review_credentials(
        review_notes,
        final_submit=True,
        env={"APP_STORE_REVIEW_CONTACT_PHONE": "+8613800138000"},
    )

    assert "final submit requires replacing demo account placeholders" in "\n".join(failures)


def test_demo_review_credentials_rejects_checked_in_secret_outside_final_submit():
    review_notes = "- Demo account: `app-review@example.com`\n- Password: `review-password`\n"

    failures = validate_demo_review_credentials(review_notes, final_submit=False, env={})

    assert "review notes must keep explicit demo-account placeholders" in "\n".join(failures)


def test_release_narrative_rejects_stale_public_positioning():
    failures = validate_release_narrative(
        submission=(
            "Reva 是你的健康助理。阿衡帮你管理健康。你的健康守护者。"
            "本版本重构了移动端核心动线: 今日、私教、记录、我的。"
        ),
        review_notes="Go to `私教` and ask a question.",
        screenshot_runbook="Bottom navigation labels are `今日 / 私教 / 记录 / 我的`.",
    )

    assert "release text contains stale user-visible term: Reva" in failures
    assert "release text contains stale user-visible term: 健康助理" in failures
    assert "release text contains stale user-visible term: 私教" in failures
    assert "release text contains stale user-visible term: 阿衡" in failures  # 2026-07-05 改名小巴
    assert "release text contains stale user-visible term: 健康守护者" in failures  # 2026-07-05 定位语终裁回参谋家族
    assert "release text must use current bottom navigation labels: 今日 / 小巴 / 记录 / 我" in failures
    assert "release text must include current positioning term: 健康参谋" in failures


def test_app_review_redlines_reject_high_confidence_review_risks():
    failures = validate_app_review_redlines(
        {
            "mobile/app/paywall.tsx": (
                "Android 用户请去微信支付充值会员, 也可以输入 CDKey 兑换码。"
                "必须开启通知才能继续使用。"
                "敬请期待, 页面建设中。"
                "AI 已确诊为高血压, 治疗方案如下。"
            )
        }
    )

    assert "non-iOS platform term" in "\n".join(failures)
    assert "third-party payment or redeem-code term" in "\n".join(failures)
    assert "forced permission wording" in "\n".join(failures)
    assert "unfinished or placeholder product copy" in "\n".join(failures)
    assert "unsafe medical claim wording" in "\n".join(failures)


def test_app_review_redlines_allow_current_medical_boundary_disclaimers():
    failures = validate_app_review_redlines(
        {
            "docs/release/app-store/submission-pack.md": (
                "小巴提供健康记录、趋势解读和生活方式建议,不提供诊断、急救分诊、"
                "处方、治疗方案或药物剂量调整。任何医疗决策请咨询医生。"
            )
        }
    )

    assert failures == []
