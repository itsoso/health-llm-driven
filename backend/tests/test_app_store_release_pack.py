import os
import json
import struct
import subprocess
import sys
import zlib
from pathlib import Path

from scripts.check_app_store_release_pack import (
    REQUIRED_FILES,
    validate_app_review_redlines,
    validate_app_store_privacy_publication,
    validate_demo_review_credentials,
    validate_demo_account_live,
    validate_final_submission_material_state,
    validate_privacy_policy_copy,
    validate_real_device_evidence,
    validate_regulated_medical_device_declaration,
    validate_release_narrative,
)


def test_release_pack_requires_dependency_risk_review():
    assert "docs/release/app-store/dependency-risk-review.md" in REQUIRED_FILES

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


def _write_manifest(
    directory: Path,
    *,
    privacy_status: str = "demo",
    build_id: str | None = None,
) -> None:
    screens = []
    for name in REQUIRED_SCREENSHOT_NAMES:
        _write_png(directory / f"{name}.png")
        screens.append({"name": name, "file": f"{name}.png", "route": "/"})

    manifest = {
        "captured_at": "2026-06-28T16:30:00Z",
        "privacy_status": privacy_status,
        "app_store_ready": privacy_status in {"demo", "sanitized"},
        "screens": screens,
    }
    if build_id is not None:
        manifest["build_id"] = build_id

    (directory / "manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def _real_device_evidence(*, build_id: str = "235") -> dict:
    return {
        "build_id": build_id,
        "app_version": "1.3.2",
        "build_profile": "production",
        "eas_build_id": "d6b5f7de-1208-488d-8799-4b6f8a76b011",
        "git_commit_hash": "371dacc60ba3f218edec4b367ea61472798904a2",
        "device_model": "iPhone 15 Pro",
        "ios_version": "18.5",
        "tested_at": "2026-07-23T12:00:00Z",
        "tester": "release-owner",
        "checks": {
            "demo_account_login": True,
            "today_briefing_expand_collapse": True,
            "agent_text_conversation": True,
            "streaming_markdown_rendering": True,
            "realtime_dictation_toggle": True,
            "hold_to_talk_send_cancel_text": True,
            "voice_interrupts_external_audio": True,
            "camera_photo_persistence": True,
            "image_save_and_share": True,
            "wechat_share_handoff": True,
            "xiaohongshu_share_handoff": True,
            "generated_video_playback_no_regeneration": True,
            "confirmed_database_write": True,
            "write_correction_delete_idempotency": True,
            "foreground_stream_recovery": True,
            "draft_preserved_across_background": True,
            "conversation_opens_at_latest_message": True,
            "personal_center_privacy_policy": True,
            "optional_permission_denial_text_chat": True,
            "account_deletion_status": True,
        },
    }


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


def test_privacy_policy_copy_rejects_stale_brand_and_missing_controls():
    failures = validate_privacy_policy_copy(
        "隐私政策 | 健康助理\n最近更新: 2026-06-28\nHealthKit",
        "HealthKit 数据摘要",
    )

    joined = "\n".join(failures)
    assert "stale privacy-policy brand" in joined
    assert "2026-07-14" in joined
    assert "精确位置" in joined
    assert "删除请求编号" in joined


def test_privacy_policy_copy_accepts_current_web_and_mobile_contract():
    required = (
        "小巴 睿为健康 2026-07-14 HealthKit AI 模型服务 精确位置 "
        "删除账号与数据 删除请求编号 7 天 support@executor.life 广告 营销 不提供诊断 处方 药物剂量调整"
    )

    assert validate_privacy_policy_copy(required, required) == []


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
    assert "final submit requires real-device acceptance evidence" in result.stderr
    assert "APP_STORE_PRIVACY_RESPONSES_PUBLISHED=1" in result.stderr
    assert "APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS=no" in result.stderr


def test_app_store_release_pack_final_submit_rejects_screenshots_from_another_build(
    tmp_path: Path,
):
    root = Path(__file__).resolve().parents[2]
    screenshot_dir = tmp_path / "screens"
    screenshot_dir.mkdir()
    _write_manifest(screenshot_dir, privacy_status="demo", build_id="225")

    evidence = tmp_path / "real-device.json"
    evidence.write_text(json.dumps(_real_device_evidence(build_id="226")), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/check_app_store_release_pack.py",
            "--final-submit",
            "--screenshot-dir",
            str(screenshot_dir),
            "--real-device-evidence",
            str(evidence),
            "--build-id",
            "226",
        ],
        cwd=root,
        env={
            **os.environ,
            "APP_STORE_REVIEW_DEMO_ACCOUNT": "app-review@example.com",
            "APP_STORE_REVIEW_DEMO_PASSWORD": "review-password",
            "APP_STORE_REVIEW_CONTACT_PHONE": "+8613800138000",
            "APP_STORE_REVIEW_API_BASE": "http://127.0.0.1:1",
            "ASC_KEY_ID": "test-key",
            "ASC_ISSUER_ID": "test-issuer",
            "ASC_PRIVATE_KEY_BASE64": "test-private-key",
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 1
    assert "manifest build_id must match expected build" in result.stderr


def test_real_device_evidence_requires_current_build_and_all_core_flows(tmp_path: Path):
    evidence = tmp_path / "real-device.json"
    payload = _real_device_evidence(build_id="226")
    payload["checks"]["xiaohongshu_share_handoff"] = False
    evidence.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    failures = validate_real_device_evidence(evidence, expected_build_id="226")

    assert "xiaohongshu_share_handoff" in "\n".join(failures)


def test_real_device_evidence_accepts_complete_matching_build(tmp_path: Path):
    evidence = tmp_path / "real-device.json"
    evidence.write_text(
        json.dumps(_real_device_evidence(build_id="226"), ensure_ascii=False),
        encoding="utf-8",
    )

    assert validate_real_device_evidence(evidence, expected_build_id="226") == []


def test_real_device_evidence_rejects_untraceable_build_metadata(tmp_path: Path):
    evidence = tmp_path / "real-device.json"
    payload = _real_device_evidence()
    payload.update(
        {
            "app_version": "",
            "build_profile": "watch-production",
            "eas_build_id": "not-an-eas-id",
            "git_commit_hash": "not-a-commit",
        }
    )
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    failures = validate_real_device_evidence(evidence, expected_build_id="235")
    joined = "\n".join(failures)

    assert "missing app_version" in joined
    assert "build_profile must be production" in joined
    assert "invalid eas_build_id" in joined
    assert "invalid git_commit_hash" in joined


def test_real_device_evidence_requires_named_tester_and_reviewer_paths(tmp_path: Path):
    evidence = tmp_path / "real-device.json"
    evidence.write_text(
        json.dumps(
            {
                "build_id": "226",
                "device_model": "iPhone 15 Pro",
                "ios_version": "18.5",
                "tested_at": "2026-07-14T12:00:00Z",
                "checks": {},
            }
        ),
        encoding="utf-8",
    )

    failures = validate_real_device_evidence(evidence, expected_build_id="226")
    joined = "\n".join(failures)

    assert "missing tester" in joined
    assert "demo_account_login" in joined
    assert "today_briefing_expand_collapse" in joined
    assert "agent_text_conversation" in joined
    assert "personal_center_privacy_policy" in joined
    assert "optional_permission_denial_text_chat" in joined


def test_final_submission_material_state_rejects_drafts():
    failures = validate_final_submission_material_state(
        submission_pack="Status: draft for the next App Store submission.",
        review_notes="# App Store Review Notes Draft",
    )

    joined = "\n".join(failures)
    assert "submission pack is not marked ready" in joined
    assert "review notes are still marked Draft" in joined


def test_final_submission_material_state_accepts_ready_materials():
    assert validate_final_submission_material_state(
        submission_pack="Status: ready for App Store submission.",
        review_notes="# App Store Review Notes",
    ) == []


def test_regulated_medical_device_declaration_is_required_for_final_submit():
    failures = validate_regulated_medical_device_declaration(
        final_submit=True,
        env={},
    )

    assert "APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS=no" in "\n".join(failures)


def test_regulated_medical_device_declaration_accepts_not_regulated_status():
    assert validate_regulated_medical_device_declaration(
        final_submit=True,
        env={"APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS": "no"},
    ) == []


def test_regulated_medical_device_declaration_rejects_regulated_status_for_this_release():
    failures = validate_regulated_medical_device_declaration(
        final_submit=True,
        env={"APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS": "yes"},
    )

    assert "release scope declares the app is not a regulated medical device" in "\n".join(failures)


def test_regulated_medical_device_declaration_is_not_required_for_draft_checks():
    assert validate_regulated_medical_device_declaration(
        final_submit=False,
        env={},
    ) == []


def test_app_store_privacy_publication_is_required_for_final_submit():
    failures = validate_app_store_privacy_publication(
        final_submit=True,
        env={},
    )

    assert "APP_STORE_PRIVACY_RESPONSES_PUBLISHED=1" in "\n".join(failures)


def test_app_store_privacy_publication_accepts_explicit_confirmation():
    assert validate_app_store_privacy_publication(
        final_submit=True,
        env={"APP_STORE_PRIVACY_RESPONSES_PUBLISHED": "1"},
    ) == []


def test_app_store_privacy_publication_is_not_required_for_draft_checks():
    assert validate_app_store_privacy_publication(
        final_submit=False,
        env={},
    ) == []


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


def test_live_demo_account_gate_proves_login_identity_and_seeded_review_surfaces(monkeypatch):
    calls: list[tuple[str, str]] = []

    def fake_request(url, *, method="GET", token=None, payload=None, timeout=10):
        calls.append((method, url))
        if url.endswith("/auth/login/json"):
            assert payload == {"username": "reviewer@example.com", "password": "private-password"}
            return {"access_token": "token", "user": {"id": 17}}
        assert token == "token"
        if url.endswith("/auth/me"):
            return {"id": 17}
        if url.endswith("/daily-plan/me"):
            return {"actions": [{"title": "今日重点"}]}
        if url.endswith("/daily-artifact/me"):
            return {"top_action": {"title": "晨起记录"}}
        raise AssertionError(url)

    monkeypatch.setattr(
        "scripts.check_app_store_release_pack._request_json",
        fake_request,
    )

    failures = validate_demo_account_live(
        "reviewer@example.com",
        "private-password",
        api_base="https://health.example.test/api/v1",
    )

    assert failures == []
    assert calls == [
        ("POST", "https://health.example.test/api/v1/auth/login/json"),
        ("GET", "https://health.example.test/api/v1/auth/me"),
        ("GET", "https://health.example.test/api/v1/daily-plan/me"),
        ("GET", "https://health.example.test/api/v1/daily-artifact/me"),
    ]


def test_live_demo_account_gate_fails_closed_when_login_is_rejected(monkeypatch):
    def reject_login(*_args, **_kwargs):
        raise RuntimeError("HTTP 403")

    monkeypatch.setattr(
        "scripts.check_app_store_release_pack._request_json",
        reject_login,
    )

    failures = validate_demo_account_live(
        "reviewer@example.com",
        "wrong-password",
        api_base="https://health.example.test/api/v1",
    )

    assert "live demo account check failed" in "\n".join(failures)


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
            "本版本重构了移动端核心动线: 今日、小巴、记录、我。"
            "旧版入口是今日、私教、记录、我的。"
        ),
        review_notes="Go to `私教` and ask a question.",
        screenshot_runbook="Bottom navigation labels are `今日 / 小巴 / 记录 / 我`.",
    )

    assert "release text contains stale user-visible term: Reva" in failures
    assert "release text contains stale user-visible term: 健康助理" in failures
    assert "release text contains stale user-visible term: 私教" in failures
    assert "release text contains stale user-visible term: 阿衡" in failures  # 2026-07-05 改名小巴
    assert "release text contains stale user-visible term: 健康守护者" in failures  # 2026-07-05 定位语终裁回参谋家族
    assert "release text contains stale user-visible term: 今日 / 小巴 / 记录 / 我" in failures
    assert "release text contains stale user-visible term: 今日、小巴、记录、我" in failures
    assert "release text must describe current agent-native entry: 打开即进入小巴" in failures
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


def test_app_review_redlines_reject_legacy_healthpilot_brand_in_permission_copy():
    failures = validate_app_review_redlines(
        {"mobile/hooks/useMediaPicker.ts": "请在系统设置中允许 HealthPilot 访问相册"}
    )

    assert "legacy app brand" in "\n".join(failures)


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
