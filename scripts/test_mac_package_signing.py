"""Exercise the real packaging script with isolated signing/build commands."""

import os
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "apps/mac/scripts/package-app.sh"
IDENTITY = "A" * 40


@pytest.fixture
def package(tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    commands = {
        "security": '#!/bin/bash\nprintf "%s\\n" "$TEST_IDENTITIES"\nexit "${TEST_SECURITY_STATUS:-0}"\n',
        "swift": '''#!/bin/bash
if [[ "$*" == *--show-bin-path* ]]; then
  printf '%s\\n' "$TEST_BIN"
else
  mkdir -p "$TEST_BIN"
  printf '#!/bin/bash\\nexit 0\\n' > "$TEST_BIN/HealthAgentMac"
  chmod +x "$TEST_BIN/HealthAgentMac"
fi
''',
        "codesign": '#!/bin/bash\nprintf "%s\\n" "$@" >> "$TEST_SIGN_LOG"\nif [[ "$1" == "--verify" ]]; then exit "${TEST_VERIFY_STATUS:-0}"; fi\nexit "${TEST_SIGN_STATUS:-0}"\n',
    }
    for name, body in commands.items():
        path = tools / name
        path.write_text(body)
        path.chmod(0o755)

    def run(identities="", *, identity="", security_status=0, sign_status=0, verify_status=0, args=()):
        env = dict(os.environ, PATH=f"{tools}:/usr/bin:/bin:/usr/sbin:/sbin")
        env.update(
            HEALTH_MAC_SIGN_IDENTITY=identity,
            TEST_IDENTITIES=identities,
            TEST_BIN=str(tmp_path / "bin"),
            TEST_SIGN_LOG=str(tmp_path / "sign.log"),
            TEST_SECURITY_STATUS=str(security_status),
            TEST_SIGN_STATUS=str(sign_status),
            TEST_VERIFY_STATUS=str(verify_status),
        )
        result = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--output", str(tmp_path / "dist"), *args],
            env=env, capture_output=True, text=True, timeout=20,
        )
        log = tmp_path / "sign.log"
        return result, log.read_text().splitlines() if log.exists() else []

    return run


def test_default_uses_unique_apple_identity(package):
    result, calls = package(f'  1) {IDENTITY} "Apple Development: Example (TEAM)"\n  1 valid identities found')
    assert result.returncode == 0, result.stderr
    assert calls[calls.index("--sign") + 1] == IDENTITY
    assert "--verify" in calls


@pytest.mark.parametrize("identities", [
    "  0 valid identities found",
    f'  1) {IDENTITY} "Apple Development: One (TEAM)"\n  2) {"B" * 40} "Apple Development: Two (OTHER)"',
    f'  1) {IDENTITY} "Unrelated local certificate"',
])
def test_missing_or_ambiguous_identity_never_falls_back_to_adhoc(package, identities):
    result, calls = package(identities)
    assert result.returncode != 0
    assert "HEALTH_MAC_SIGN_IDENTITY" in result.stderr
    assert calls == []


def test_explicit_identity_is_preserved(package):
    result, calls = package(identity=IDENTITY)
    assert result.returncode == 0, result.stderr
    assert calls[calls.index("--sign") + 1] == IDENTITY


def test_security_lookup_failure_is_not_hidden(package):
    result, calls = package(security_status=1)
    assert result.returncode != 0
    assert calls == []


def test_codesign_failure_prevents_success(package):
    result, _ = package(identity=IDENTITY, sign_status=1)
    assert result.returncode != 0
    assert "Packaged" not in result.stdout


def test_adhoc_pseudo_identity_is_rejected(package):
    result, calls = package(identity="-")
    assert result.returncode != 0
    assert calls == []


def test_verification_failure_prevents_success(package):
    result, calls = package(identity=IDENTITY, verify_status=1)
    assert result.returncode != 0
    assert "--verify" in calls
    assert "Packaged" not in result.stdout


def test_explicit_unsigned_build_does_not_require_a_certificate(package):
    result, calls = package(args=("--no-sign",))
    assert result.returncode == 0, result.stderr
    assert calls == []
