from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/ios-real-device-acceptance/generate_project.rb"
RUNNER = ROOT / "scripts/run_ios_real_device_acceptance.sh"
UI_TEST_SOURCE = (
    ROOT / "scripts/ios-real-device-acceptance/XiaobaAcceptanceUITests.swift"
)


def _generate(tmp_path: Path, *, account: str = "", password: str = "") -> str:
    env = os.environ.copy()
    env["APP_STORE_REVIEW_DEMO_ACCOUNT"] = account
    env["APP_STORE_REVIEW_DEMO_PASSWORD"] = password
    subprocess.run(
        ["ruby", str(GENERATOR), str(tmp_path)],
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    return (
        tmp_path
        / "XiaobaAcceptance.xcodeproj"
        / "xcshareddata"
        / "xcschemes"
        / "XiaobaAcceptanceUITests.xcscheme"
    ).read_text(encoding="utf-8")


def test_generator_omits_review_credentials_when_not_configured(tmp_path: Path) -> None:
    scheme = _generate(tmp_path)

    assert "APP_STORE_REVIEW_DEMO_ACCOUNT" not in scheme
    assert "APP_STORE_REVIEW_DEMO_PASSWORD" not in scheme


def test_generator_refuses_review_credentials_in_xcode_scheme(tmp_path: Path) -> None:
    env = os.environ.copy()
    env["APP_STORE_REVIEW_DEMO_ACCOUNT"] = "review@example.test"
    env["APP_STORE_REVIEW_DEMO_PASSWORD"] = "private-password"

    result = subprocess.run(
        ["ruby", str(GENERATOR), str(tmp_path)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "credentials" in result.stderr.lower()
    assert "private-password" not in result.stdout + result.stderr


def test_runner_accepts_simulator_destination_platform() -> None:
    result = subprocess.run(
        ["bash", str(RUNNER), "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--platform" in result.stdout
    assert "iOS Simulator" in result.stdout
    assert "pre-authenticated" in result.stdout
    assert "APP_STORE_REVIEW_DEMO_PASSWORD" not in result.stdout


def test_runner_refuses_review_credentials_before_invoking_xcodebuild() -> None:
    env = os.environ.copy()
    env["APP_STORE_REVIEW_DEMO_ACCOUNT"] = "review@example.test"
    env["APP_STORE_REVIEW_DEMO_PASSWORD"] = "private-password"

    result = subprocess.run(
        ["bash", str(RUNNER), "not-a-real-device"],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "pre-authenticated" in result.stderr
    assert "private-password" not in result.stdout + result.stderr


def test_composer_selector_accepts_ios_placeholder_augmented_label() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert 'label BEGINSWITH %@", "消息输入框"' in source


def test_draft_replacement_selects_all_without_tapping_an_offscreen_key() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert "selectAllText(" in source
    assert "replaceDraft(" in source
    assert "XCUIKeyboardKey.delete.rawValue" in source
    assert 'app.keys["delete"]' not in source


def test_settings_acceptance_uses_accessible_buttons_and_scrolls_them_visible() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert 'app.buttons["隐私政策"]' in source
    assert 'app.buttons["删除账号与数据"]' in source
    assert "scrollToElement(" in source


def test_automated_acceptance_requires_pre_authenticated_session_without_typing_secrets() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert "test00AuthenticatedSessionPersistsAcrossTwoColdLaunches" in source
    assert "requireAuthenticatedChat()" in source
    assert "reviewCredentials" not in source
    assert "APP_STORE_REVIEW_DEMO_PASSWORD" not in source
    assert "test01ReviewAccountCanLoginFromSignedOutState" not in source
    assert "credentials.password" not in source


def test_latest_message_acceptance_checks_seeded_markdown_at_the_bottom() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert "testConversationOpensAtLatestSeededMessage" in source
    assert '"assistant-message-surface"' in source
    assert 'assistantSurface.label.contains("## 今天优先完成两件事")' in source


def test_today_context_acceptance_matches_the_current_agent_native_surface() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert "testTodayContextCanOpenAndDismiss" in source
    assert 'app.buttons["打开今日计划"]' in source
    assert 'app.buttons["返回小巴"]' in source
    assert 'app.buttons["关闭当前提示"]' in source
    assert "testBriefingCanExpandAndCollapse" not in source
    assert '"今日简报："' not in source
