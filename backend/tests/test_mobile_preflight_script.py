from pathlib import Path
import os
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_mobile_preflight_uses_current_ios_app_target(tmp_path):
    mobile_dir = tmp_path / "mobile"
    app_dir = mobile_dir / "ios" / "app"
    app_dir.mkdir(parents=True)
    (app_dir / "Info.plist").write_text(
        "\n".join(
            f"<key>{key}</key>"
            for key in (
                "NSHealthShareUsageDescription",
                "NSCameraUsageDescription",
                "NSMicrophoneUsageDescription",
                "NSLocationWhenInUseUsageDescription",
            )
        ),
        encoding="utf-8",
    )
    (app_dir / "app.entitlements").write_text(
        "<key>com.apple.developer.healthkit</key>",
        encoding="utf-8",
    )
    (mobile_dir / "ios" / "Podfile.lock").write_text(
        "RNAppleHealthKit\nExpoSecureStore\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["MOBILE_DIR_OVERRIDE"] = str(mobile_dir)
    result = subprocess.run(
        [str(REPO_ROOT / "scripts" / "preflight-eas.sh")],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "preflight 全过" in result.stdout
