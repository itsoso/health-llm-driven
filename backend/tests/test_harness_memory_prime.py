from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_prime_module():
    spec = importlib.util.spec_from_file_location(
        "harness_memory_prime", ROOT / "scripts" / "harness_memory_prime.py"
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_memory_prime_returns_ranked_keyword_matches(tmp_path, capsys):
    memory_root = tmp_path / "memories"
    memory_root.mkdir()
    (memory_root / "MEMORY.md").write_text(
        "\n".join(
            [
                "# registry",
                "- health-llm-driven KB uses reviewed local knowledge first",
                "- unrelated trading note",
                "- health-llm-driven dedao kbase remote API integration",
                "- browser worktree note",
            ]
        ),
        encoding="utf-8",
    )
    prime = _load_prime_module()

    assert prime.main([
        "--memory-root", str(memory_root),
        "--keywords", "health-llm-driven", "kbase",
        "--limit", "2",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert [m["line"] for m in payload["matches"]] == [4, 2]
    assert payload["matches"][0]["score"] == 2
    assert "dedao kbase" in payload["matches"][0]["text"]


def test_memory_prime_can_require_all_keywords(tmp_path, capsys):
    memory_root = tmp_path / "memories"
    memory_root.mkdir()
    (memory_root / "MEMORY.md").write_text(
        "\n".join([
            "- health-llm-driven KB",
            "- health-llm-driven dedao kbase",
        ]),
        encoding="utf-8",
    )
    prime = _load_prime_module()

    assert prime.main([
        "--memory-root", str(memory_root),
        "--keywords", "health-llm-driven", "kbase",
        "--require-all",
    ]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert [m["line"] for m in payload["matches"]] == [2]


def test_memory_prime_fails_loud_when_registry_is_missing(tmp_path, capsys):
    prime = _load_prime_module()

    assert prime.main(["--memory-root", str(tmp_path), "--keywords", "health"]) == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "memory_registry_missing"
