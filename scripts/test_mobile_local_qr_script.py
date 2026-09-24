import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_mobile_local_qr_upload_updates_stable_latest_install_alias():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")

    assert 'LATEST_PUBLIC_BASE_URL="${PUBLIC_ROOT_URL}/latest"' in script
    assert "REMOTE_LATEST_DIR" in script
    assert "Latest install page:" in script
    assert "mv -Tf" in script
    assert "--delete" not in script


def test_mobile_local_qr_reuses_existing_output_ipa_without_copying_it_onto_itself():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")

    assert 'cmp -s "${IPA_INPUT}" "${IPA_PATH}"' in script


def test_local_qr_resolves_inherited_update_channel_from_selected_profile():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")
    resolver = script.split("<<'NODE'\n", 1)[1].split("\nNODE", 1)[0]
    for profile, channel in [
        ("production", "production"),
        ("preview", "preview"),
        ("rokid-adhoc", "rokid-production"),
    ]:
        result = subprocess.run(
            ["node", "-", str(ROOT / "mobile" / "eas.json"), profile],
            input=resolver,
            text=True,
            capture_output=True,
            check=True,
        )
        assert f"REVA_LOCAL_UPDATES_CHANNEL\t{channel}" in result.stdout


@pytest.mark.parametrize("channel", [None, "", "production\npreview", "$(echo unsafe)"])
def test_local_qr_rejects_missing_or_invalid_channel_before_exporting_env(
    tmp_path, channel
):
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")
    resolver = script.split("<<'NODE'\n", 1)[1].split("\nNODE", 1)[0]
    config = tmp_path / "eas.json"
    config.write_text(
        json.dumps(
            {
                "build": {
                    "production": {
                        "channel": channel,
                        "env": {"APP_VARIANT": "production"},
                    }
                }
            }
        )
    )
    result = subprocess.run(
        ["node", "-", str(config), "production"],
        input=resolver,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert result.stdout == ""
    # The assignment propagates Node failure; eval "$(node ...)" would hide it.
    assert 'PROFILE_EXPORTS="$(' in script
    assert 'eval "${PROFILE_EXPORTS}"' not in script


def test_local_qr_does_not_execute_dotenv_or_development_fallback():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text()
    assert 'source "${ENV_FILE}"' not in script
    assert "retry development export" not in script
    assert "env -i" in script
    assert "EXPO_NO_DOTENV=1" in script


def test_local_qr_validates_existing_ipa_before_uploading_only_public_files():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text()
    assert "verify-ios-ipa" in script
    assert "--require-receipt" in script
    assert '"${OUTPUT_DIR}/" "${DEPLOY_SERVER}' not in script
    assert '"${PUBLIC_DIR}/" "${DEPLOY_SERVER}' in script
    assert script.index("verify-ios-ipa") < script.index("rsync ")


@pytest.fixture
def qr_checkout(tmp_path):
    root = tmp_path / "source"
    (root / "scripts").mkdir(parents=True)
    (root / "mobile").mkdir()
    shutil.copyfile(
        ROOT / "scripts/mobile-local-qr.sh", root / "scripts/mobile-local-qr.sh"
    )
    shutil.copyfile(
        ROOT / "scripts/mobile_local_qr_safety.py",
        root / "scripts/mobile_local_qr_safety.py",
    )
    (root / "mobile/eas.json").write_text(
        json.dumps(
            {
                "build": {
                    "production": {
                        "channel": "production",
                        "env": {"APP_VARIANT": "production"},
                    }
                }
            }
        )
    )
    (root / "mobile/app.json").write_text(json.dumps({"expo": {"version": "1.3.4"}}))
    (root / ".gitignore").write_text("artifacts/\n.env\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(
        ["git", "-C", str(root), "add", "scripts", "mobile", ".gitignore"], check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    return root


def test_shell_does_not_execute_dotenv_and_rejects_unproven_ipa(qr_checkout, tmp_path):
    marker = tmp_path / "dotenv-was-executed"
    (qr_checkout / ".env").write_text(f"touch '{marker}'\n")
    ipa = tmp_path / "unproven.ipa"
    ipa.write_bytes(b"not-a-real-ipa")
    result = subprocess.run(
        [
            "bash",
            str(qr_checkout / "scripts/mobile-local-qr.sh"),
            "--profile",
            "production",
            "--ipa",
            str(ipa),
            "--no-upload",
            "--build-id",
            "fixture-unproven",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "safety validation failed" in result.stderr
    assert not marker.exists()
    assert not (
        qr_checkout / "artifacts/ios-local-install/fixture-unproven/public"
    ).exists()


def test_native_subprocess_does_not_inherit_health_secrets(qr_checkout, tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    probe = tmp_path / "probe.json"
    (binary / "npx").write_text(
        f"#!/usr/bin/env python3\nimport json,os\nopen({str(probe)!r},'w').write(json.dumps(dict(os.environ)))\nraise SystemExit(47)\n"
    )
    for name in ["pod", "xcodebuild"]:
        (binary / name).write_text("#!/bin/sh\nexit 91\n")
    for entry in binary.iterdir():
        entry.chmod(0o755)
    env = dict(
        os.environ,
        PATH=f"{binary}:{os.environ['PATH']}",
        PRODUCTION_DATABASE_SECRET="synthetic-sensitive-value",
        IOS_LOCAL_QR_PROFILE_UUID="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        REVA_IOS_BUILD_NUMBER="273",
    )
    result = subprocess.run(
        [
            "bash",
            str(qr_checkout / "scripts/mobile-local-qr.sh"),
            "--profile",
            "production",
            "--no-upload",
            "--build-id",
            "fixture-env",
        ],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 47
    observed = json.loads(probe.read_text())
    assert "PRODUCTION_DATABASE_SECRET" not in observed
    assert observed["EXPO_NO_DOTENV"] == "1"
    assert observed["APP_VARIANT"] == "production"
    assert observed["REVA_LOCAL_UPDATES_CHANNEL"] == "production"


def test_shell_rejects_path_injection_before_creating_artifacts(qr_checkout):
    result = subprocess.run(
        [
            "bash",
            str(qr_checkout / "scripts/mobile-local-qr.sh"),
            "--build-id",
            "bad';echo injected;#",
            "--no-upload",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not (qr_checkout / "artifacts").exists()


@pytest.mark.parametrize(
    "server",
    ["-oProxyCommand=bad", "health;echo bad", "user@host:/other", "user@$(id)"],
)
def test_shell_rejects_ssh_destination_injection(qr_checkout, server):
    result = subprocess.run(
        [
            "bash",
            str(qr_checkout / "scripts/mobile-local-qr.sh"),
            "--build-id",
            "fixture-host",
            "--no-upload",
        ],
        env=dict(os.environ, DEPLOY_SERVER=server),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert not (qr_checkout / "artifacts").exists()


@pytest.mark.parametrize("no_latest", [True, False])
def test_upload_orchestration_can_preserve_latest_and_reads_back_unique_ipa(
    qr_checkout, tmp_path, no_latest
):
    # Stub only the cryptographic boundary (tested separately with signed metadata)
    # to exercise the real shell orchestration without signing or network writes.
    (qr_checkout / "scripts/mobile_local_qr_safety.py").write_text("""import pathlib,sys
if sys.argv[1] == 'validate-config': raise SystemExit(0)
args=dict(zip(sys.argv[2::2],sys.argv[3::2]))
assert '--require-receipt' in args
out=pathlib.Path(args['--public-dir']); out.mkdir()
(out/'app.ipa').write_bytes(b'synthetic')
for name in ['manifest.plist','install.html']: (out/name).write_text('public')
(out/'install-url.txt').write_text('itms-services://synthetic')
""")
    subprocess.run(
        ["git", "-C", str(qr_checkout), "add", "scripts/mobile_local_qr_safety.py"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(qr_checkout),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "stub cryptographic boundary",
        ],
        check=True,
    )
    binary = tmp_path / "bin"
    binary.mkdir()
    trace = tmp_path / "commands.jsonl"
    for name in ["ssh", "rsync", "curl", "qrencode"]:
        (binary / name).write_text(f"""#!/usr/bin/env python3
import json,pathlib,sys
with open({str(trace)!r},'a') as f: f.write(json.dumps([{name!r}]+sys.argv[1:])+'\\n')
if {name!r}=='qrencode': pathlib.Path(sys.argv[sys.argv.index('-o')+1]).write_bytes(b'QR')
if {name!r}=='curl' and '-fsS' in sys.argv: sys.stdout.buffer.write(b'synthetic')
""")
        (binary / name).chmod(0o755)
    ipa = tmp_path / "previous.ipa"
    ipa.write_bytes(b"synthetic")
    env = dict(os.environ, PATH=f"{binary}:{os.environ['PATH']}")
    command = [
        "bash",
        str(qr_checkout / "scripts/mobile-local-qr.sh"),
        "--profile",
        "production",
        "--ipa",
        str(ipa),
        "--build-id",
        "fixture-publish",
    ]
    if no_latest:
        command.append("--no-latest")
    result = subprocess.run(
        command, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    uploads = [c for c in calls if c[0] == "rsync"]
    assert len(uploads) == 1
    assert uploads[0][-2].endswith("/public/")
    assert "--delete" not in uploads[0]
    reads = [c for c in calls if c[0] == "curl"]
    assert any(
        "-fsS" in c and c[-1].endswith("/fixture-publish/app.ipa") for c in reads
    )
    promotions = [c for c in calls if c[0] == "ssh" and "mv -Tf" in c[-1]]
    assert len(promotions) == (0 if no_latest else 1)
    if no_latest:
        assert not any("/latest" in " ".join(c) for c in calls)
