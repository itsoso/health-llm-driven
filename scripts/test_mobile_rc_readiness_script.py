from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "mobile_rc_readiness.sh"


def read_script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_mobile_rc_readiness_covers_release_qr_healthkit_watch_and_phone_checks():
    script = read_script()

    assert "check_app_store_release_pack.py" in script
    assert "check_ios_app_store_submission.py" in script
    assert "mobile-install/ios/latest/install.html" in script
    assert "test_phone_auth.py" in script
    assert "test_healthkit_adapter.py" in script
    assert "test_watch_ask.py" in script
    assert "swift test --package-path" in script
    assert "useHealthKitForegroundSync.test.ts" in script
    assert "services/__tests__/auth.test.ts" in script


def test_mobile_rc_readiness_is_read_only_and_never_sends_real_sms():
    script = read_script()

    assert "/api/v1/auth/phone/code" not in script
    assert "auth/phone/code" not in script
    assert "curl -X POST" not in script
    assert "aliyun_sms_access_key_secret=" not in script


def test_mobile_rc_readiness_covers_diet_card_screenshot_share_native_deps():
    script = read_script()

    assert "react-native-view-shot" in script
    assert "expo-sharing" in script
    assert "ChatBubbleStructuredSummary.test.tsx" in script
    assert "utils/__tests__/share.test.ts" in script
    assert "services/__tests__/chatImageSave.test.ts" in script


def test_mobile_rc_readiness_runs_mobile_typecheck():
    script = read_script()

    assert "npx tsc --noEmit" in script
