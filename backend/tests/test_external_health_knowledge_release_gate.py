from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND_ROOT / "scripts" / "run_external_health_knowledge_release_gate.py"


def test_external_health_knowledge_release_gate_dry_run_lists_required_steps():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--json"],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    steps = payload["steps"]
    names = [step["name"] for step in steps]

    assert payload["dry_run"] is True
    assert names == [
        "domain_focused_tests",
        "jsonl_lint_import_eval",
        "compileall",
    ]

    domain_command = steps[0]["command"]
    assert domain_command[:4] == [sys.executable, "-m", "pytest", "--no-cov"]
    assert "tests/test_gerd_lpr_knowledge.py" in domain_command
    assert "tests/test_pgx_high_risk_knowledge.py" in domain_command
    assert "tests/test_sleep_spo2_knowledge.py" in domain_command
    assert "tests/test_supplement_safety_knowledge.py" in domain_command

    internal_step = steps[1]
    assert internal_step["kind"] == "internal"
    assert internal_step["artifact_dir"].endswith("data/system_kb_v2_seed")

    compile_command = steps[2]["command"]
    assert compile_command[:4] == [sys.executable, "-m", "compileall", "-q"]
    assert "app" in compile_command
    assert "scripts" in compile_command


def test_external_health_knowledge_release_gate_runs_isolated_jsonl_import_eval():
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--only",
            "jsonl_lint_import_eval",
            "--json",
        ],
        cwd=BACKEND_ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert [step["name"] for step in payload["steps"]] == ["jsonl_lint_import_eval"]

    detail = payload["steps"][0]["detail"]
    assert detail["lint"]["counts"]["claims.jsonl"] >= 1
    assert detail["import"]["documents"] >= detail["lint"]["counts"]["claims.jsonl"]
    assert detail["eval"]["total"] >= 1
    assert detail["eval"]["failed"] == 0
