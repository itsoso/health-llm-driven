from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_mobile_local_qr_upload_updates_stable_latest_install_alias():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")

    assert 'LATEST_PUBLIC_BASE_URL="${IOS_LOCAL_QR_LATEST_PUBLIC_BASE_URL:-${PUBLIC_ROOT_URL}/latest}"' in script
    assert "REMOTE_LATEST_DIR" in script
    assert "Latest install page:" in script


def test_mobile_local_qr_reuses_existing_output_ipa_without_copying_it_onto_itself():
    script = (ROOT / "scripts" / "mobile-local-qr.sh").read_text(encoding="utf-8")

    assert 'cmp -s "${IPA_INPUT}" "${IPA_PATH}"' in script
