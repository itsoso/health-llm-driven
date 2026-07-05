import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_harness_registry_manifest_lists_health_core_gates():
    manifest_path = ROOT / "harness" / "registry.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["project"]["id"] == "health-llm-driven"
    harnesses = manifest["harnesses"]
    ids = {item["id"] for item in harnesses}

    assert {
        "health-operating-validate",
        "health-llm-regression-gate",
        "health-runtime-eval",
        "health-retrieval-eval",
        "health-backend-smoke",
        "health-langbridge-smoke",
    }.issubset(ids)
    assert len(ids) == len(harnesses)
    assert all(item["command"] for item in harnesses)
    assert all(item["description"] for item in harnesses)
    assert all(item["stage"] in {"commit", "ci", "runtime", "manual", "release"} for item in harnesses)


def test_harness_registry_manifest_tags_memory_and_eval_paths():
    manifest = json.loads((ROOT / "harness" / "registry.json").read_text(encoding="utf-8"))

    memory_ids = {
        item["id"]
        for item in manifest["harnesses"]
        if "memory" in item.get("tags", [])
    }
    assert {"health-memory-prime", "health-retrieval-eval"}.issubset(memory_ids)

    for item in manifest["harnesses"]:
        for path in item.get("evidence_paths", []):
            assert not Path(path).is_absolute(), f"{item['id']} evidence path should be repo-relative"


def test_harness_registry_cli_is_project_local_and_machine_readable():
    result = subprocess.run(
        [sys.executable, "scripts/list_harnesses.py", "--json", "--tag", "memory"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads(result.stdout)
    assert payload["project"]["id"] == "health-llm-driven"
    assert payload["source_path"].endswith("harness/registry.json")
    assert {item["id"] for item in payload["harnesses"]} == {
        "health-memory-prime",
        "health-retrieval-eval",
    }
    assert all("memory" in item["tags"] for item in payload["harnesses"])


def test_harness_registry_cli_text_output_shows_stage_and_cwd():
    result = subprocess.run(
        [sys.executable, "scripts/list_harnesses.py", "--stage", "ci"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "project: health-llm-driven" in result.stdout
    assert "health-backend-smoke [ci]" in result.stdout
    assert "cwd: backend" in result.stdout
