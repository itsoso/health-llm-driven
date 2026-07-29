#!/usr/bin/env python3
"""Validate App Store release materials against mobile config."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "docs/release/app-store/submission-pack.md",
    "docs/release/app-store/privacy-nutrition-label.draft.json",
    "docs/release/app-store/review-notes.zh-CN.md",
    "docs/release/app-store/screenshot-runbook.md",
    "docs/release/app-store/adapted-review-checklist.md",
    "docs/release/app-store/account-deletion-runbook.md",
    "docs/release/app-store/dependency-risk-review.md",
    "docs/release/app-store/real-device-acceptance.template.json",
    "docs/plans/2026-06-28-app-store-mvp-release-batch2-plan.md",
    "docs/plans/2026-06-28-app-store-mvp-release-batch3-plan.md",
    "docs/plans/2026-06-28-app-store-mvp-release-batch4-plan.md",
    "docs/plans/2026-06-28-app-store-mvp-release-batch5-plan.md",
    "docs/plans/2026-06-28-app-store-mvp-release-batch6-plan.md",
    "docs/plans/2026-06-28-app-store-mvp-release-batch7-plan.md",
    "docs/plans/2026-06-29-app-store-final-submit-gate-plan.md",
    "docs/plans/2026-06-29-app-store-release-narrative-gate-plan.md",
    "frontend/src/app/privacy/page.tsx",
    "scripts/sim-build.sh",
    "scripts/mobile-sim-screenshots.sh",
    "scripts/check_app_store_screenshots.py",
    "scripts/check_ios_app_store_submission.py",
    "scripts/prepare_app_store_screenshots.py",
    "scripts/sanitize_app_store_screenshots.py",
]

REQUIRED_INFO_PLIST_KEYS = [
    "NSFaceIDUsageDescription",
    "NSPhotoLibraryUsageDescription",
    "NSCameraUsageDescription",
    "NSMicrophoneUsageDescription",
    "NSSpeechRecognitionUsageDescription",
    "NSLocationWhenInUseUsageDescription",
    "NSHealthShareUsageDescription",
]

MEDICAL_BOUNDARY_TERMS = [
    "不提供诊断",
    "处方",
    "药物剂量调整",
]

OFFICIAL_REFERENCE_URLS = [
    "https://developer.apple.com/support/offering-account-deletion-in-your-app/",
    "https://developer.apple.com/help/app-store-connect/reference/screenshot-specifications/",
    "https://developer.apple.com/help/app-store-connect/manage-app-privacy/app-privacy-details/",
    "https://developer.apple.com/help/app-store-connect/manage-app-information/declare-regulated-medical-device-status",
    "https://developer.apple.com/app-store/review/guidelines/",
]

EXPECTED_APP_NAME = "小巴"
DEMO_PLACEHOLDERS = [
    "[NEEDS APP STORE REVIEW DEMO ACCOUNT]",
    "[NEEDS APP STORE REVIEW DEMO PASSWORD]",
]
DEMO_ENV_KEYS = [
    "APP_STORE_REVIEW_DEMO_ACCOUNT",
    "APP_STORE_REVIEW_DEMO_PASSWORD",
]
DEMO_CREDENTIAL_LINES = [
    # (label of the review-notes line, placeholder token, env fallback key)
    ("Demo account", DEMO_PLACEHOLDERS[0], DEMO_ENV_KEYS[0]),
    ("Password", DEMO_PLACEHOLDERS[1], DEMO_ENV_KEYS[1]),
]
REVIEW_CONTACT_PHONE_ENV = "APP_STORE_REVIEW_CONTACT_PHONE"
REVIEW_CONTACT_PHONE_RE = re.compile(r"^\+[1-9]\d{1,14}(?:[\s-]\d+)*$")
APP_STORE_PRIVACY_RESPONSES_PUBLISHED_ENV = "APP_STORE_PRIVACY_RESPONSES_PUBLISHED"
REGULATED_MEDICAL_DEVICE_STATUS_ENV = "APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS"
REAL_DEVICE_EVIDENCE_ENV = "APP_STORE_REAL_DEVICE_EVIDENCE"
APP_STORE_BUILD_ID_ENV = "APP_STORE_BUILD_ID"
DEMO_API_BASE_ENV = "APP_STORE_REVIEW_API_BASE"
DEFAULT_DEMO_API_BASE = "https://health.executor.life/api/v1"
REAL_DEVICE_CHECKS = (
    "demo_account_login",
    "today_context_open_dismiss",
    "agent_text_conversation",
    "streaming_markdown_rendering",
    "realtime_dictation_toggle",
    "hold_to_talk_send_cancel_text",
    "voice_interrupts_external_audio",
    "camera_photo_persistence",
    "image_save_and_share",
    "wechat_share_handoff",
    "xiaohongshu_share_handoff",
    "generated_video_playback_no_regeneration",
    "confirmed_database_write",
    "write_correction_delete_idempotency",
    "foreground_stream_recovery",
    "draft_preserved_across_background",
    "conversation_opens_at_latest_message",
    "personal_center_privacy_policy",
    "optional_permission_denial_text_chat",
    "account_deletion_status",
)
CURRENT_AGENT_NATIVE_ENTRY_TERMS = [
    "打开即进入小巴",
    "今日计划",
    "记录",
    "个人中心",
]
CURRENT_POSITIONING_TERM = "健康参谋"  # 2026-07-05 定位语终裁:参谋家族("小巴,你忠实的健康参谋")
STALE_USER_VISIBLE_RELEASE_TERMS = [
    "Reva",
    "阿衡",  # 2026-07-05 改名小巴;旧人格名不得再出现在发布材料
    "复元",
    "健康助理",
    "守护神",
    "健康守护者",  # 2026-07-05 定位语终裁回参谋家族;守护者措辞不得再入发布材料
    "私教",
    "今日 / 小巴 / 记录 / 我",  # 2026-07-05 agent-native shell:不再承诺底部四 Tab
    "今日、小巴、记录、我",
]
APP_REVIEW_REDLINE_GLOBS = [
    "docs/release/app-store/*.md",
    "frontend/src/app/privacy/page.tsx",
    "mobile/app/**/*.tsx",
    "mobile/components/**/*.tsx",
    "mobile/hooks/**/*.ts",
    "mobile/hooks/**/*.tsx",
    "mobile/services/**/*.ts",
    "mobile/strings/**/*.ts",
    "mobile/utils/**/*.ts",
]
APP_REVIEW_REDLINE_EXCLUDED_PARTS = {
    "__tests__",
    "__mocks__",
    "adapted-review-checklist.md",
    "api.generated.ts",
}
APP_REVIEW_REDLINE_RULES = [
    (
        "legacy app brand",
        [r"\bHealthPilot\b"],
    ),
    (
        "non-iOS platform term",
        [
            r"\bAndroid\b",
            r"安卓",
            r"Google Play",
        ],
    ),
    (
        "third-party payment or redeem-code term",
        [
            r"微信支付",
            r"支付宝",
            r"第三方支付",
            r"兑换码",
            r"\bCDKey\b",
            r"\bcdkey\b",
            r"充值",
            r"提现",
        ],
    ),
    (
        "forced permission wording",
        [
            r"(?:必须|强制|需要|请先|不开启|未开启).{0,24}(?:通知|定位|跟踪|麦克风|相机|健康权限|HealthKit).{0,24}(?:才能继续使用|才能进入|才可继续|无法继续|无法使用本应用|不能使用本应用|不可使用本应用)",
            r"(?:通知|定位|跟踪|麦克风|相机|健康权限|HealthKit).{0,24}(?:必须|强制).{0,24}(?:开启|授权|允许).{0,24}(?:才能继续|才可继续|进入应用)",
        ],
    ),
    (
        "unfinished or placeholder product copy",
        [
            r"敬请期待",
            r"页面建设中",
            r"功能建设中",
            r"即将上线",
            r"待上线",
            r"待开放",
            r"占位页面",
            r"暂未实现",
            r"未实现",
            r"coming soon",
        ],
    ),
    (
        "unsafe medical claim wording",
        [
            r"确诊为",
            r"诊断为",
            r"治疗方案如下",
            r"处方如下",
            r"药物剂量调整为",
            r"(?:建议|可以|应|请|立刻|马上)自行(?:停药|换药|改剂量)",
        ],
    ),
]


def read_json(path: str) -> dict:
    with (ROOT / path).open(encoding="utf-8") as handle:
        return json.load(handle)


def read_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def validate_release_narrative(
    *,
    submission: str,
    review_notes: str,
    screenshot_runbook: str,
) -> list[str]:
    combined = "\n".join([submission, review_notes, screenshot_runbook])
    failures: list[str] = []

    for term in STALE_USER_VISIBLE_RELEASE_TERMS:
        if term in combined:
            failures.append(f"release text contains stale user-visible term: {term}")

    for required in CURRENT_AGENT_NATIVE_ENTRY_TERMS:
        if required not in combined:
            failures.append(f"release text must describe current agent-native entry: {required}")

    if CURRENT_POSITIONING_TERM not in combined:
        failures.append(f"release text must include current positioning term: {CURRENT_POSITIONING_TERM}")

    return failures


def validate_privacy_policy_copy(web_copy: str, mobile_copy: str) -> list[str]:
    failures: list[str] = []
    combined = "\n".join([web_copy, mobile_copy])
    for stale in ("健康助理", "Reva"):
        if stale in combined:
            failures.append(f"stale privacy-policy brand: {stale}")

    for required in (
        "小巴",
        "睿为健康",
        "2026-07-14",
        "HealthKit",
        "AI 模型服务",
        "精确位置",
        "删除账号与数据",
        "删除请求编号",
        "7 天",
        "support@executor.life",
        "广告",
        "营销",
        "不提供诊断",
        "处方",
        "药物剂量调整",
    ):
        if required not in web_copy or required not in mobile_copy:
            failures.append(f"privacy policy must contain {required!r} on web and mobile")
    return failures


def collect_app_review_redline_sources() -> dict[str, str]:
    sources: dict[str, str] = {}
    for pattern in APP_REVIEW_REDLINE_GLOBS:
        for path in ROOT.glob(pattern):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT).as_posix()
            if any(part in rel for part in APP_REVIEW_REDLINE_EXCLUDED_PARTS):
                continue
            sources[rel] = path.read_text(encoding="utf-8")
    return sources


def validate_app_review_redlines(source_texts: Mapping[str, str]) -> list[str]:
    failures: list[str] = []
    compiled_rules = [
        (category, [re.compile(pattern, re.IGNORECASE) for pattern in patterns])
        for category, patterns in APP_REVIEW_REDLINE_RULES
    ]

    for rel, text in sorted(source_texts.items()):
        for line_no, line in enumerate(text.splitlines(), start=1):
            compact = line.strip()
            if not compact:
                continue
            if compact.startswith(("//", "*")) or "Platform.OS" in compact:
                continue
            if "application/vnd.android.package-archive" in compact:
                continue
            for category, patterns in compiled_rules:
                if any(pattern.search(compact) for pattern in patterns):
                    failures.append(f"{category}: {rel}:{line_no}: {compact[:120]}")

    return failures


def _parse_demo_credential_value(review_notes: str, label: str) -> str | None:
    """Return the value on the `- <label>:` review-notes line, or None when the line is absent."""
    match = re.search(
        rf"^\s*[-*]?\s*{re.escape(label)}\s*[::]\s*(.*)$",
        review_notes,
        re.MULTILINE,
    )
    if match is None:
        return None
    return match.group(1).strip().strip("`").strip()


def validate_demo_review_credentials(
    review_notes: str,
    *,
    final_submit: bool,
    env: Mapping[str, str] = os.environ,
) -> list[str]:
    failures: list[str] = []
    missing_placeholders = [placeholder for placeholder in DEMO_PLACEHOLDERS if placeholder not in review_notes]

    if final_submit:
        # Fail closed: each credential line must be present with a real (non-placeholder,
        # non-empty) value, or keep the explicit placeholder and supply the value via env.
        # Deleting or blanking a line is never a valid final-submit state — a checker that
        # only looks for leftover placeholder tokens would pass with no credentials at all.
        unresolved_placeholders: list[str] = []
        for label, placeholder, env_key in DEMO_CREDENTIAL_LINES:
            value = _parse_demo_credential_value(review_notes, label)
            if value is None:
                failures.append(
                    f"final submit requires a `{label}:` line in review-notes.zh-CN.md; "
                    "the line is missing (deleting it does not satisfy the demo-credential gate)"
                )
                continue
            if not value:
                failures.append(
                    f"final submit requires a non-empty `{label}:` value in review-notes.zh-CN.md; "
                    "a blank credential does not satisfy the demo-credential gate"
                )
                continue
            if value in DEMO_PLACEHOLDERS and not env.get(env_key, "").strip():
                unresolved_placeholders.append(placeholder)
        if unresolved_placeholders:
            failures.append(
                "final submit requires replacing demo account placeholders in review notes "
                "or setting APP_STORE_REVIEW_DEMO_ACCOUNT and APP_STORE_REVIEW_DEMO_PASSWORD: "
                + ", ".join(unresolved_placeholders)
            )
        contact_phone = env.get(REVIEW_CONTACT_PHONE_ENV, "").strip()
        if not contact_phone:
            failures.append("final submit requires APP_STORE_REVIEW_CONTACT_PHONE for App Store Review contact")
        elif not REVIEW_CONTACT_PHONE_RE.match(contact_phone):
            failures.append(
                "APP_STORE_REVIEW_CONTACT_PHONE must use international format, for example +8613800138000"
            )
    elif missing_placeholders:
        failures.append(
            "review notes must keep explicit demo-account placeholders until final submit; "
            "use APP_STORE_REVIEW_DEMO_ACCOUNT and APP_STORE_REVIEW_DEMO_PASSWORD on the release machine"
        )

    return failures


def _resolved_demo_credentials(
    review_notes: str,
    env: Mapping[str, str],
) -> tuple[str, str] | None:
    values: list[str] = []
    for label, placeholder, env_key in DEMO_CREDENTIAL_LINES:
        value = _parse_demo_credential_value(review_notes, label)
        if value == placeholder:
            value = env.get(env_key, "").strip()
        if not value or value in DEMO_PLACEHOLDERS:
            return None
        values.append(value)
    return values[0], values[1]


def _request_json(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict | None = None,
    timeout: float = 10,
) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc


def validate_demo_account_live(
    account: str,
    password: str,
    *,
    api_base: str = DEFAULT_DEMO_API_BASE,
) -> list[str]:
    """Prove the exact reviewer credential against production read paths."""
    base = api_base.rstrip("/")
    try:
        login = _request_json(
            f"{base}/auth/login/json",
            method="POST",
            payload={"username": account, "password": password},
        )
        token = str(login.get("access_token") or "").strip()
        login_user_id = (login.get("user") or {}).get("id")
        if not token or login_user_id is None:
            return ["live demo account login response is missing access_token or user id"]

        me = _request_json(f"{base}/auth/me", token=token)
        if me.get("id") != login_user_id:
            return ["live demo account /auth/me identity does not match login response"]

        plan = _request_json(f"{base}/daily-plan/me", token=token)
        if not isinstance(plan.get("actions"), list) or not plan["actions"]:
            return ["live demo account daily plan has no reviewer-visible actions"]

        artifact = _request_json(f"{base}/daily-artifact/me", token=token)
        top_action = artifact.get("top_action")
        if not isinstance(top_action, dict) or not str(top_action.get("title") or "").strip():
            return ["live demo account daily artifact has no reviewer-visible top action"]
    except Exception as exc:
        return [f"live demo account check failed: {exc}"]
    return []


def validate_real_device_evidence(path: Path, *, expected_build_id: str) -> list[str]:
    failures: list[str] = []
    if not path.is_file():
        return [f"real-device acceptance evidence file not found: {path}"]
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid real-device acceptance evidence: {exc}"]

    if str(evidence.get("build_id") or "").strip() != str(expected_build_id).strip():
        failures.append(
            "real-device evidence build_id does not match APP_STORE_BUILD_ID: "
            f"evidence={evidence.get('build_id')!r}, expected={expected_build_id!r}"
        )
    for field in (
        "app_version",
        "eas_build_id",
        "git_commit_hash",
        "device_model",
        "ios_version",
        "tested_at",
        "tester",
    ):
        if not str(evidence.get(field) or "").strip():
            failures.append(f"real-device evidence missing {field}")
    if evidence.get("build_profile") != "production":
        failures.append("real-device evidence build_profile must be production")
    eas_build_id = str(evidence.get("eas_build_id") or "").strip()
    if eas_build_id and not re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        eas_build_id,
        re.IGNORECASE,
    ):
        failures.append("real-device evidence has invalid eas_build_id")
    git_commit_hash = str(evidence.get("git_commit_hash") or "").strip()
    if git_commit_hash and not re.fullmatch(r"[0-9a-f]{7,40}", git_commit_hash, re.IGNORECASE):
        failures.append("real-device evidence has invalid git_commit_hash")
    checks = evidence.get("checks")
    if not isinstance(checks, dict):
        return failures + ["real-device evidence missing checks object"]
    for check in REAL_DEVICE_CHECKS:
        if checks.get(check) is not True:
            failures.append(f"real-device acceptance check not passed: {check}")
    return failures


def validate_final_submission_material_state(
    *,
    submission_pack: str,
    review_notes: str,
) -> list[str]:
    failures: list[str] = []
    if "Status: ready for App Store submission." not in submission_pack:
        failures.append(
            "submission pack is not marked ready; replace the draft status only after G6 passes"
        )
    if re.search(r"^#\s+App Store Review Notes\s+Draft\s*$", review_notes, re.MULTILINE):
        failures.append("review notes are still marked Draft")
    if not re.search(r"^#\s+App Store Review Notes\s*$", review_notes, re.MULTILINE):
        failures.append("review notes are not marked final")
    return failures


def validate_app_store_privacy_publication(
    *,
    final_submit: bool,
    env: Mapping[str, str] = os.environ,
) -> list[str]:
    if not final_submit:
        return []
    if env.get(APP_STORE_PRIVACY_RESPONSES_PUBLISHED_ENV, "").strip() != "1":
        return [
            "final submit requires APP_STORE_PRIVACY_RESPONSES_PUBLISHED=1 after the "
            "App Store Connect privacy responses have been compared with "
            "privacy-nutrition-label.draft.json and published"
        ]
    return []


def validate_regulated_medical_device_declaration(
    *,
    final_submit: bool,
    env: Mapping[str, str] = os.environ,
) -> list[str]:
    if not final_submit:
        return []

    status = env.get(REGULATED_MEDICAL_DEVICE_STATUS_ENV, "").strip().lower()
    if not status:
        return [
            "final submit requires APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS=no after "
            "App Store Connect records the regulated medical device declaration"
        ]
    if status != "no":
        return [
            "release scope declares the app is not a regulated medical device; set "
            "APP_STORE_REGULATED_MEDICAL_DEVICE_STATUS=no only after selecting No in "
            "App Store Connect, or stop submission and complete a regulatory review"
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--final-submit",
        action="store_true",
        help="Require human-provided App Store submission materials: screenshots, ASC credentials, and demo credentials.",
    )
    parser.add_argument(
        "--screenshot-dir",
        help="App Store-ready screenshot directory. Overrides APP_STORE_SCREENSHOT_DIR.",
    )
    parser.add_argument(
        "--real-device-evidence",
        help="JSON evidence from the physical-iPhone acceptance run. Overrides APP_STORE_REAL_DEVICE_EVIDENCE.",
    )
    parser.add_argument(
        "--build-id",
        help="App Store build number expected in real-device evidence. Overrides APP_STORE_BUILD_ID.",
    )
    args = parser.parse_args()

    failures: list[str] = []

    for rel in REQUIRED_FILES:
        if not (ROOT / rel).exists():
            failures.append(f"missing required file: {rel}")

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1

    app = read_json("mobile/app.json")["expo"]
    ios = app.get("ios", {})
    info_plist = ios.get("infoPlist", {})
    entitlements = ios.get("entitlements", {})
    eas = read_json("mobile/eas.json")
    privacy = read_json("docs/release/app-store/privacy-nutrition-label.draft.json")
    submission = read_text("docs/release/app-store/submission-pack.md")
    review_notes = read_text("docs/release/app-store/review-notes.zh-CN.md")
    screenshot_runbook = read_text("docs/release/app-store/screenshot-runbook.md")
    privacy_page = read_text("frontend/src/app/privacy/page.tsx")
    mobile_privacy_page = read_text("mobile/app/privacy-policy.tsx")

    bundle_id = ios.get("bundleIdentifier")
    if app.get("name") != EXPECTED_APP_NAME:
        failures.append(f"Expo app name must be {EXPECTED_APP_NAME!r}, got {app.get('name')!r}")
    if info_plist.get("CFBundleDisplayName") != EXPECTED_APP_NAME:
        failures.append(
            f"CFBundleDisplayName must be {EXPECTED_APP_NAME!r}, got {info_plist.get('CFBundleDisplayName')!r}"
        )
    if f"| App name | `{EXPECTED_APP_NAME}` |" not in submission:
        failures.append(f"submission pack App name must be {EXPECTED_APP_NAME!r}")
    if bundle_id != privacy.get("bundle_id"):
        failures.append(f"bundle id mismatch: app.json={bundle_id!r}, privacy={privacy.get('bundle_id')!r}")

    if entitlements.get("com.apple.developer.healthkit") is not True:
        failures.append("missing iOS HealthKit entitlement")

    for key in REQUIRED_INFO_PLIST_KEYS:
        value = info_plist.get(key)
        if not isinstance(value, str) or len(value.strip()) < 8:
            failures.append(f"missing or weak iOS privacy usage string: {key}")

    asc_app_id = eas.get("submit", {}).get("production", {}).get("ios", {}).get("ascAppId")
    if asc_app_id != privacy.get("app_store_connect_app_id"):
        failures.append(
            f"ASC app id mismatch: eas={asc_app_id!r}, privacy={privacy.get('app_store_connect_app_id')!r}"
        )

    privacy_url = privacy.get("privacy_policy_url", "")
    if privacy_url != "https://health.executor.life/privacy":
        failures.append(f"unexpected privacy policy url: {privacy_url!r}")

    if privacy.get("tracking") is not False:
        failures.append("privacy label must declare tracking=false for this release")
    if privacy.get("healthkit_advertising_use") is not False:
        failures.append("HealthKit advertising use must remain false")

    categories = {item.get("category") for item in privacy.get("data_types", [])}
    for category in {"Health", "Fitness", "User Content", "Contact Info", "Identifiers", "Diagnostics"}:
        if category not in categories:
            failures.append(f"privacy nutrition missing category: {category}")

    combined_release_text = "\n".join([submission, review_notes, privacy_page])
    for term in MEDICAL_BOUNDARY_TERMS:
        if term not in combined_release_text:
            failures.append(f"medical boundary term missing from release text: {term}")

    for required in ["HealthKit", "删除账号与数据", "广告", "营销", "support@executor.life"]:
        if required not in combined_release_text:
            failures.append(f"release text missing required wording: {required}")

    failures.extend(validate_privacy_policy_copy(privacy_page, mobile_privacy_page))

    failures.extend(
        validate_release_narrative(
            submission=submission,
            review_notes=review_notes,
            screenshot_runbook=screenshot_runbook,
        )
    )
    failures.extend(validate_app_review_redlines(collect_app_review_redline_sources()))

    for url in OFFICIAL_REFERENCE_URLS:
        if url not in submission and url not in read_text("docs/plans/2026-06-28-app-store-mvp-release-batch2-plan.md"):
            failures.append(f"missing official reference URL: {url}")

    demo_credential_failures = validate_demo_review_credentials(
        review_notes,
        final_submit=args.final_submit,
    )
    failures.extend(demo_credential_failures)
    if args.final_submit:
        failures.extend(
            validate_final_submission_material_state(
                submission_pack=submission,
                review_notes=review_notes,
            )
        )
        failures.extend(validate_app_store_privacy_publication(final_submit=True))
        failures.extend(validate_regulated_medical_device_declaration(final_submit=True))
    if args.final_submit and not demo_credential_failures:
        credentials = _resolved_demo_credentials(review_notes, os.environ)
        if credentials is None:
            failures.append("final submit could not resolve demo credentials for live validation")
        else:
            failures.extend(
                validate_demo_account_live(
                    credentials[0],
                    credentials[1],
                    api_base=os.environ.get(DEMO_API_BASE_ENV, DEFAULT_DEMO_API_BASE),
                )
            )

    ios_preflight_args = [
        sys.executable,
        str(ROOT / "scripts/check_ios_app_store_submission.py"),
    ]
    if args.final_submit:
        ios_preflight_args.append("--require-asc-credentials")

    ios_preflight = subprocess.run(
        ios_preflight_args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if ios_preflight.stdout:
        print(ios_preflight.stdout, end="")
    if ios_preflight.returncode != 0:
        failures.append(f"iOS App Store submission preflight failed\n{ios_preflight.stderr.strip()}")

    build_id = args.build_id or os.environ.get(APP_STORE_BUILD_ID_ENV, "").strip()
    screenshot_dir = args.screenshot_dir or os.environ.get("APP_STORE_SCREENSHOT_DIR")
    if args.final_submit and not screenshot_dir:
        failures.append("final submit requires APP_STORE_SCREENSHOT_DIR or --screenshot-dir")
    if screenshot_dir:
        screenshot_args = [
            sys.executable,
            str(ROOT / "scripts/check_app_store_screenshots.py"),
            screenshot_dir,
            "--app-store-ready",
        ]
        if args.final_submit and build_id:
            screenshot_args.extend(["--build-id", build_id])
        result = subprocess.run(
            screenshot_args,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.stdout:
            print(result.stdout, end="")
        if result.returncode != 0:
            failures.append(
                "App Store screenshot set failed validation; "
                f"APP_STORE_SCREENSHOT_DIR={screenshot_dir!r}\n{result.stderr.strip()}"
            )

    if args.final_submit:
        evidence_path = args.real_device_evidence or os.environ.get(REAL_DEVICE_EVIDENCE_ENV, "").strip()
        if not evidence_path:
            failures.append(
                "final submit requires real-device acceptance evidence via "
                "--real-device-evidence or APP_STORE_REAL_DEVICE_EVIDENCE"
            )
        elif not build_id:
            failures.append("final submit requires --build-id or APP_STORE_BUILD_ID")
        else:
            failures.extend(validate_real_device_evidence(Path(evidence_path), expected_build_id=build_id))

    if failures:
        print("App Store release pack check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("App Store release pack check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
