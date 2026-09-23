from pathlib import Path
import json
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_mobile_local_qr_upload_updates_stable_latest_install_alias():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")

    assert 'LATEST_PUBLIC_BASE_URL="${IOS_LOCAL_QR_LATEST_PUBLIC_BASE_URL:-${PUBLIC_ROOT_URL}/latest}"' in script
    assert "REMOTE_LATEST_DIR" in script
    assert "Latest install page:" in script


def test_mobile_local_qr_reuses_existing_output_ipa_without_copying_it_onto_itself():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")

    assert 'cmp -s "${IPA_INPUT}" "${IPA_PATH}"' in script


def test_local_qr_resolves_inherited_update_channel_from_selected_profile():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")
    resolver = script.split("<<'NODE'\n", 1)[1].split("\nNODE", 1)[0]
    for profile, channel in [("production", "production"), ("preview", "preview"), ("rokid-adhoc", "rokid-production")]:
        result = subprocess.run(
            ["node", "-", str(ROOT / "mobile" / "eas.json"), profile],
            input=resolver, text=True, capture_output=True, check=True,
        )
        assert f"export REVA_LOCAL_UPDATES_CHANNEL={json.dumps(channel)}" in result.stdout


@pytest.mark.parametrize("channel", [None, "", "production\npreview", '$(echo unsafe)'])
def test_local_qr_rejects_missing_or_invalid_channel_before_exporting_env(tmp_path, channel):
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")
    resolver = script.split("<<'NODE'\n", 1)[1].split("\nNODE", 1)[0]
    config = tmp_path / "eas.json"
    config.write_text(json.dumps({"build": {"production": {"channel": channel, "env": {"APP_VARIANT": "production"}}}}))
    result = subprocess.run(["node", "-", str(config), "production"], input=resolver, text=True, capture_output=True)
    assert result.returncode != 0
    assert result.stdout == ""
    # The assignment propagates Node failure; eval "$(node ...)" would hide it.
    assert 'PROFILE_EXPORTS="$(' in script
    assert 'eval "${PROFILE_EXPORTS}"' in script
