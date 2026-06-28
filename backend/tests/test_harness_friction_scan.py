from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_scan_module():
    spec = importlib.util.spec_from_file_location(
        "harness_friction_scan", ROOT / "scripts" / "harness_friction_scan.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_friction_scan_returns_clean_for_unrelated_text(tmp_path):
    note = tmp_path / "note.md"
    note.write_text("普通实现记录,没有重复摩擦信号。\n", encoding="utf-8")
    scan = _load_scan_module()

    payload = scan.scan([note])

    assert payload == {"status": "clean", "scanned_files": 1, "suggestions": []}


def test_friction_scan_detects_repeat_correction_and_completion_pressure(tmp_path):
    transcript = tmp_path / "session.md"
    transcript.write_text(
        "\n".join(
            [
                "继续",
                "继续实现",
                "继续推进",
                "基于知识库相关规划,不是最新的规划",
                "还有没有完成? 是否全部完成了?",
            ]
        ),
        encoding="utf-8",
    )
    scan = _load_scan_module()

    payload = scan.scan([tmp_path])
    suggestions = {item["id"]: item for item in payload["suggestions"]}

    assert payload["status"] == "suggestions_found"
    assert payload["scanned_files"] == 1
    assert set(suggestions) == {
        "repeated_continue",
        "source_of_truth_correction",
        "completion_uncertainty",
    }
    assert suggestions["repeated_continue"]["count"] == 3
    assert suggestions["source_of_truth_correction"]["evidence"][0]["line"] == 4
    assert suggestions["completion_uncertainty"]["evidence"][0]["file"].endswith("session.md")


def test_friction_scan_cli_outputs_json_without_blocking(tmp_path, capsys):
    transcript = tmp_path / "session.log"
    transcript.write_text("继续\n继续\n继续\n", encoding="utf-8")
    scan = _load_scan_module()

    assert scan.main(["--input", str(transcript), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "suggestions_found"
    assert [item["id"] for item in payload["suggestions"]] == ["repeated_continue"]
