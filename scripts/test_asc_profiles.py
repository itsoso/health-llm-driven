from pathlib import Path
import subprocess
import sys


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / ".claude/skills/mobile-testflight-release/scripts/asc_profiles.py"
)
def test_legacy_asc_profile_writer_is_a_fail_closed_compatibility_shim() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(MODULE_PATH), "life.executor.health"],
        text=True,
        capture_output=True,
        env={"PATH": "/usr/bin:/bin"},
        check=False,
    )

    assert result.returncode == 2
    assert "已禁用" in result.stderr
    assert "production 原生构建当前也已冻结" in result.stderr
    assert "不得绕过" in result.stderr
    assert "人工 Gate" in result.stderr
    for forbidden in (
        "APP_STORE_CONNECT_API_KEY",
        "APP_STORE_CONNECT_ISSUER_ID",
        "urllib",
        "jwt",
        '"POST"',
        '"DELETE"',
    ):
        assert forbidden not in source
