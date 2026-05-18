from __future__ import annotations

import json

from app.services.gene_rules_registry import GeneRulesRegistry


def test_summary_line_accepts_string_items(tmp_path):
    """Registry should tolerate legacy/string item shapes without crashing."""
    path = tmp_path / "gene_knowledge.json"
    payload = {
        "schema_id": "llm-wiki-v2-gene-knowledge",
        "version": "test",
        "compiled_at": "2026-05-19T00:00:00Z",
        "gene_rules": {
            "CYP2C19": {
                "poor": {
                    "avoid": [
                        "clopidogrel",
                        {"drug": "omeprazole", "reason": "interaction"},
                    ],
                    "substitute": [
                        {"from": "clopidogrel", "to": "prasugrel"},
                    ],
                    "monitor": [
                        "blood_pressure",
                        {"metric": "INR", "action": "check"},
                    ],
                }
            }
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    registry = GeneRulesRegistry(path=path)
    assert registry.load() is True

    line = registry.summary_line("CYP2C19", "poor")
    assert line is not None
    assert "CYP2C19" in line
    assert "避免 clopidogrel" in line
