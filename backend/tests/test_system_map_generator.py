from __future__ import annotations

import builtins
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_doc_drift as cdd  # noqa: E402


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
