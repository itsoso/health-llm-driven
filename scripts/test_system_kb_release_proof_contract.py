from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backend_deploy_defaults_whole_kb_proof_to_shadow_mode():
    deploy = (ROOT / "deploy.sh").read_text(encoding="utf-8")

    marker = 'SYSTEM_KB_IMPORT_PROOF_MODE="\\${SYSTEM_KB_IMPORT_PROOF_MODE:-shadow}"'
    marker_index = deploy.index(marker)

    assert deploy.index("python scripts/seed_system_kb_phase0.py") < marker_index
    assert deploy.index("python scripts/import_system_kb_v2_artifacts.py") > marker_index
    assert deploy.find("verify_runtime_only_kb_contract \"staged\"", marker_index) > marker_index
