from __future__ import annotations

import builtins
import importlib
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_doc_drift as cdd  # noqa: E402
import dump_system_map as dsm  # noqa: E402


def _reject_backend_runtime_imports(monkeypatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "app" or name.startswith("app."):
            raise AssertionError(f"system-map scanner imported backend runtime module: {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


def test_specialist_roster_is_derived_without_backend_runtime_imports(monkeypatch) -> None:
    _reject_backend_runtime_imports(monkeypatch)

    roster = cdd.specialist_roster()

    assert "SafetyGuardianSpecialist" in roster
    assert "CrossSourceValidatorSpecialist" in roster
    assert roster == sorted(roster)
    assert cdd.count_specialists() == len(roster)


def test_twin_partition_roster_is_derived_without_backend_runtime_imports(monkeypatch) -> None:
    _reject_backend_runtime_imports(monkeypatch)

    roster = cdd.twin_partition_roster()

    assert "physiological" in roster
    assert "freshness" in roster
    assert "meta" not in roster
    assert "gene_config" not in roster
    assert roster == sorted(roster)
    assert cdd.count_twin_partitions() == len(roster)


def _contract_module():
    try:
        return importlib.import_module("system_map_contract")
    except ModuleNotFoundError:
        pytest.fail("scripts/system_map_contract.py is required for System Map v2")


def _minimal_graph() -> dict:
    return {
        "_note": "test",
        "schema_version": "2.0",
        "entities": [
            {
                "id": "component.mobile",
                "kind": "component",
                "name": "Mobile",
                "coverage": "declaration",
                "source": {
                    "type": "declaration",
                    "path": "fixture.json",
                },
            }
        ],
        "relations": [],
        "coverage": {},
        "counts": {},
        "safety_rules_by_category": {},
        "specialists_roster": [],
        "twin_partitions_roster": [],
    }


def test_build_map_emits_sorted_v2_graph() -> None:
    contract = _contract_module()

    result = dsm.build_map()

    assert result["schema_version"] == "2.0"
    assert result["entities"] == sorted(result["entities"], key=lambda item: item["id"])
    assert result["relations"] == sorted(
        result["relations"], key=lambda item: (item["from"], item["type"], item["to"])
    )
    contract.validate_system_map(result)


def test_contract_rejects_dangling_relation() -> None:
    contract = _contract_module()
    graph = _minimal_graph()
    graph["relations"].append(
        {
            "from": "component.mobile",
            "type": "dependsOn",
            "to": "resource.missing",
            "coverage": "declaration",
            "source": {"type": "declaration", "path": "fixture.json"},
        }
    )

    with pytest.raises(contract.SystemMapContractError, match="unknown target"):
        contract.validate_system_map(graph)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda graph: graph["entities"].append(dict(graph["entities"][0])), "duplicate entity"),
        (lambda graph: graph["entities"][0].update(kind="unknown"), "unknown entity kind"),
        (
            lambda graph: graph["entities"][0].update(source={"type": "code"}),
            "source.path",
        ),
    ],
)
def test_contract_rejects_invalid_entities(mutation, message: str) -> None:
    contract = _contract_module()
    graph = _minimal_graph()
    mutation(graph)

    with pytest.raises(contract.SystemMapContractError, match=message):
        contract.validate_system_map(graph)
