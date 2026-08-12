from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts/ios-real-device-acceptance/generate_project.rb"
RUNNER = ROOT / "scripts/run_ios_real_device_acceptance.sh"
UI_TEST_SOURCE = (
    ROOT / "scripts/ios-real-device-acceptance/XiaobaAcceptanceUITests.swift"
)
README = ROOT / "scripts/ios-real-device-acceptance/README.md"
RESULT_VERIFIER = ROOT / "scripts/verify_ios_acceptance_result.py"


def _generate(
    tmp_path: Path,
    *,
    account: str = "",
    password: str = "",
    expected_city: str = "",
) -> str:
    env = os.environ.copy()
    env["APP_STORE_REVIEW_DEMO_ACCOUNT"] = account
    env["APP_STORE_REVIEW_DEMO_PASSWORD"] = password
    env["REVA_ACCEPTANCE_EXPECTED_CITY"] = expected_city
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


def test_generator_persists_expected_city_in_xcode_scheme(tmp_path: Path) -> None:
    scheme = _generate(tmp_path, expected_city="杭州")

    assert "REVA_ACCEPTANCE_EXPECTED_CITY" in scheme
    assert "杭州" in scheme


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


def test_runner_documents_simulator_location_options() -> None:
    result = subprocess.run(
        ["bash", str(RUNNER), "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "--location <lat,lon>" in result.stdout
    assert "--expected-city <city>" in result.stdout
    assert "Simulator-only" in result.stdout


def test_runner_manages_simulator_location_and_cleans_it_in_a_trap() -> None:
    runner = RUNNER.read_text(encoding="utf-8")

    assert 'xcrun simctl privacy "${DEVICE_ID}" grant location "${APP_BUNDLE_ID}"' in runner
    assert 'xcrun simctl location "${DEVICE_ID}" set "${SIMULATED_LOCATION}"' in runner
    assert 'xcrun simctl location "${DEVICE_ID}" clear' in runner
    assert "cleanup()" in runner
    assert "trap cleanup EXIT INT TERM" in runner
    assert "REVA_ACCEPTANCE_EXPECTED_CITY" in runner
    assert "verify_ios_acceptance_result.py" in runner


def test_result_verifier_rejects_skipped_authenticated_acceptance(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    tests = tmp_path / "tests.json"
    summary.write_text(
        '{"result":"Passed","failedTests":0,"passedTests":1,"skippedTests":1,"totalTestCount":2}',
        encoding="utf-8",
    )
    tests.write_text(
        '{"testNodes":[{"children":['
        '{"name":"testInstalledBuildLaunchesExpectedEntrySurface()","nodeType":"Test Case","result":"Passed"},'
        '{"name":"testProductionSettingsEntriesOpenAndReturn()","nodeType":"Test Case","result":"Skipped"}'
        ']}]}',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(RESULT_VERIFIER),
            "--summary",
            str(summary),
            "--tests",
            str(tests),
            "--allow-skip",
            "testTodayContextCanOpenAndDismiss()",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "skipped" in result.stderr.lower()


def test_result_verifier_accepts_complete_green_summary(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    tests = tmp_path / "tests.json"
    summary.write_text(
        '{"result":"Passed","failedTests":0,"passedTests":8,"skippedTests":0,"totalTestCount":8}',
        encoding="utf-8",
    )
    tests.write_text(
        '{"testNodes":[{"children":['
        + ",".join(
            f'{{"name":"test{index}()","nodeType":"Test Case","result":"Passed"}}'
            for index in range(8)
        )
        + ']}]}',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(RESULT_VERIFIER),
            "--summary",
            str(summary),
            "--tests",
            str(tests),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "8 passed" in result.stdout


def test_result_verifier_accepts_only_an_explicitly_allowlisted_skip(tmp_path: Path) -> None:
    summary = tmp_path / "summary.json"
    tests = tmp_path / "tests.json"
    summary.write_text(
        '{"result":"Passed","failedTests":0,"passedTests":1,"skippedTests":1,"totalTestCount":2}',
        encoding="utf-8",
    )
    tests.write_text(
        '{"testNodes":[{"children":['
        '{"name":"testInstalledBuildLaunchesExpectedEntrySurface()","nodeType":"Test Case","result":"Passed"},'
        '{"name":"testTodayContextCanOpenAndDismiss()","nodeType":"Test Case","result":"Skipped"}'
        ']}]}',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(RESULT_VERIFIER),
            "--summary",
            str(summary),
            "--tests",
            str(tests),
            "--allow-skip",
            "testTodayContextCanOpenAndDismiss()",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "1 allowed skip" in result.stdout


def test_runner_rejects_location_options_for_physical_devices() -> None:
    result = subprocess.run(
        [
            "bash",
            str(RUNNER),
            "--platform",
            "iOS",
            "--location",
            "30.2741,120.1551",
            "--expected-city",
            "杭州",
            "not-a-real-device",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "Simulator-only" in result.stderr


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


def test_readme_requires_manual_pre_authentication_without_sourcing_credentials() -> None:
    readme = README.read_text(encoding="utf-8")

    assert "manually pre-authenticated" in readme
    assert "source /secure/path/to/release.env" not in readme
    assert "copied\nonly into the temporary generated Xcode scheme" not in readme
    assert "<physical-device-udid>" in readme
    assert "<simulator-udid>" in readme
    assert re.search(r"\b[0-9A-F]{8}-[0-9A-F-]{20,}\b", readme, re.IGNORECASE) is None


def test_composer_selector_accepts_ios_placeholder_augmented_label() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert 'label BEGINSWITH %@", "消息输入框"' in source


def test_each_device_acceptance_starts_in_portrait() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    setup = source[source.index("override func setUpWithError"):source.index("private func attachScreenshot")]
    assert "XCUIDevice.shared.orientation = .portrait" in setup


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
    assert "app.swipeDown()" in source


def test_settings_acceptance_can_dismiss_modal_routes_before_falling_back_to_gesture_back() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert "app.swipeDown()" in source
    assert '"Could not return to Settings"' in source


def test_simulator_acceptance_checks_gps_city_and_ready_state() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert "testGPSAutoRefreshPublishesCityAndReadyState" in source
    assert 'ProcessInfo.processInfo.environment["REVA_ACCEPTANCE_EXPECTED_CITY"]' in source
    assert 'app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "GPS / 城市定位"))' in source
    assert 'label CONTAINS %@' in source
    assert '"GPS 自动"' in source


def test_settings_smoke_classifies_safe_and_never_automated_actions() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert "testProductionSettingsEntriesOpenAndReturn" in source
    assert "safeSettingsEntries" in source
    assert 'SettingsEntry(label: "隐私政策", target: "隐私政策")' in source
    assert 'SettingsEntry(label: "用药管理", target: "用药管理")' in source
    assert "assertOnlySettingsEntries" in source
    assert '"Garmin"' in source
    assert '"Apple Health"' in source
    assert '"删除账号与数据"' in source
    assert '"退出登录"' in source
    assert "never tap destructive or third-party Settings actions" in source


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
    assert 'label CONTAINS %@' in source
    assert '"今天优先完成两件事"' in source
    assert 'assistantSurface.label.contains("今天优先完成两件事")' in source


def test_runner_disables_interactive_device_diagnostics() -> None:
    runner = RUNNER.read_text(encoding="utf-8")

    assert "-collect-test-diagnostics never" in runner


def test_today_context_acceptance_matches_the_current_agent_native_surface() -> None:
    source = UI_TEST_SOURCE.read_text(encoding="utf-8")

    assert "testTodayContextCanOpenAndDismiss" in source
    assert 'app.buttons["打开今日计划"]' in source
    assert 'app.buttons["返回小巴"]' in source
    assert 'app.buttons["关闭当前提示"]' in source
    assert "testBriefingCanExpandAndCollapse" not in source
    assert '"今日简报："' not in source
