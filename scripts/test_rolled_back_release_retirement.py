"""Synthetic evidence only: validation never authorizes or settles a release."""
import copy
import hashlib
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "rolled_back_evidence_test", Path(__file__).with_name("rolled_back_release_retirement.py")
)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def observation():
    old, failed, closing = "a" * 40, "b" * 40, "c" * 40
    transaction = hashlib.sha256(f"{old}:{failed}".encode()).hexdigest()[:32]
    return {
        "version": 1,
        "context": {"production_sha": old, "failed_sha": failed, "closing_sha": closing},
        "backend_terminal": {"sha": failed, "state": "NEEDS_OPERATOR"},
        "runtime_terminal": {"version": 1, "old_sha": old, "candidate_sha": failed,
            "terminal_sha": old, "target": "old", "phase": "RESTORE_FINALIZED",
            "result": "RESTORE_FINALIZED", "transaction_id": transaction,
            "reap_name": "runtime-state-transaction.reap-" + transaction},
        "runtime_inventory": ["runtime-state-terminal.json"],
        "deployment_window": {"started_at": "2026-10-10T06:00:00+00:00",
                              "completed_at": "2026-10-10T06:10:00+00:00"},
        "deployment_log": ("guard failed\nROLLBACK_OK commit=" + old
            + " kb_quarantine=passed schema_probe=passed auth_probe=passed services=active"
              " process_flag=false runtime_state=restored\n"),
        "kb": {"state": "ROLLBACK_QUARANTINED", "old_sha": old, "candidate_sha": failed,
            "actor": "rollback:" + old[:12], "audit_count": 1,
            "audit_at": "2026-10-10T06:05:00+00:00", "expected_pack_sha256": "d" * 64,
            "sealed_pack_sha256": "d" * 64, "expected_count": 3,
            "target_count": 3, "matched_count": 3, "archived_count": 3,
            "all_archived": True, "metadata_matches": True,
            "generic_serving_count": 0, "runtime_serving_count": 0},
        "environment": {"live_sha256": "e" * 64, "rollback_sha256": "e" * 64,
            "candidate_sha256": "f" * 64, "process_flag": False, "schema_compatible": True},
        "processes": {"inventory_complete": True, "unknown_count": 0, "active_release_count": 0},
        "control": {"production_sha": old, "production_clean": True,
            "lease_exists": False, "transaction_exists": False, "reap_exists": False,
            "activation_exists": False, "workflow_terminal": True,
            "original_workspace_preserved": True, "launcher_identity_matches": True,
            "services_stable": True, "health_status": 200, "unauthenticated_status": 401},
    }


def test_valid_observation_is_not_authorization_or_closure():
    value = observation()
    original = copy.deepcopy(value)
    assert m.validate_observation(value) is None
    result = m.inspect_readonly(value)
    assert result["authorized"] is False
    assert "CLOSED" not in result["state"] and "receipt" not in result
    assert value == original


@pytest.mark.parametrize("section,field,bad", [
    (None, "version", True), (None, "extra", "unknown"),
    ("context", "failed_sha", "short"), ("context", "closing_sha", "b" * 40),
    ("context", "production_sha", "b" * 40),
    ("backend_terminal", "sha", "a" * 40), ("backend_terminal", "state", "SUCCEEDED"),
    ("runtime_terminal", "version", True), ("runtime_terminal", "version", 2),
    ("runtime_terminal", "old_sha", "d" * 40), ("runtime_terminal", "candidate_sha", "d" * 40),
    ("runtime_terminal", "terminal_sha", "b" * 40), ("runtime_terminal", "target", "candidate"),
    ("runtime_terminal", "phase", "COMMITTED"), ("runtime_terminal", "result", "finalized"),
    ("runtime_terminal", "transaction_id", "0" * 32), ("runtime_terminal", "reap_name", "other"),
    ("runtime_terminal", "extra", True),
    ("kb", "actor", "rollback:" + "b" * 12), ("kb", "old_sha", "b" * 40),
    ("kb", "candidate_sha", "a" * 40), ("kb", "audit_count", 0),
    ("kb", "audit_count", 2), ("kb", "audit_count", True),
    ("kb", "audit_at", "2026-10-10T06:20:00+00:00"),
    ("kb", "sealed_pack_sha256", "0" * 64), ("kb", "matched_count", 2),
    ("kb", "target_count", 2), ("kb", "archived_count", 4),
    ("kb", "all_archived", False), ("kb", "metadata_matches", False),
    ("kb", "generic_serving_count", 1), ("kb", "runtime_serving_count", 1),
    ("environment", "live_sha256", "0" * 64), ("environment", "process_flag", True),
    ("environment", "schema_compatible", False),
    ("processes", "inventory_complete", False), ("processes", "unknown_count", 1),
    ("processes", "active_release_count", 1),
    ("control", "production_sha", "b" * 40), ("control", "production_clean", False),
    ("control", "transaction_exists", True), ("control", "reap_exists", True),
    ("control", "lease_exists", True), ("control", "activation_exists", True),
    ("control", "workflow_terminal", False), ("control", "original_workspace_preserved", False),
    ("control", "launcher_identity_matches", False), ("control", "services_stable", False),
    ("control", "health_status", 500), ("control", "unauthenticated_status", 200),
])
def test_invalid_evidence_is_blocked(section, field, bad):
    value = observation()
    (value if section is None else value[section])[field] = bad
    with pytest.raises(m.EvidenceError):
        m.inspect_readonly(value)


@pytest.mark.parametrize("missing", list(observation()))
def test_every_missing_section_blocks_even_with_absent_lease(missing):
    value = observation()
    del value[missing]
    with pytest.raises(m.EvidenceError):
        m.inspect_readonly(value)


@pytest.mark.parametrize("name", ["runtime-state-transaction", ".runtime-state-transaction.tmp",
    "runtime-state-transaction.reap-other", "../runtime-state-terminal.json"])
def test_transaction_or_reap_inventory_never_hides(name):
    value = observation()
    value["runtime_inventory"].append(name)
    with pytest.raises(m.EvidenceError):
        m.validate_observation(value)


@pytest.mark.parametrize("mode", ["missing", "duplicate", "wrong_old", "candidate_retained", "suffix"])
def test_rollback_log_requires_exact_unique_old_success(mode):
    value = observation()
    line = value["deployment_log"].splitlines()[1]
    value["deployment_log"] = {
        "missing": "guard failed\n", "duplicate": line + "\n" + line,
        "wrong_old": line.replace("a" * 40, "b" * 40),
        "candidate_retained": line.replace("runtime_state=restored", "runtime_state=candidate-retained"),
        "suffix": line + " ignored",
    }[mode]
    with pytest.raises(m.EvidenceError):
        m.validate_observation(value)


def test_old_quarantine_can_be_idempotently_archived_zero_times():
    value = observation()
    value["kb"]["archived_count"] = 0
    m.validate_observation(value)


def test_error_does_not_echo_untrusted_input():
    value = observation()
    value["context"]["failed_sha"] = "sensitive-untrusted-value"
    with pytest.raises(m.EvidenceError) as failure:
        m.validate_observation(value)
    assert "sensitive-untrusted-value" not in str(failure.value)


@pytest.mark.parametrize("section", [key for key, value in observation().items() if isinstance(value, dict)])
@pytest.mark.parametrize("change", ["missing", "extra"])
def test_nested_schemas_are_closed(section, change):
    value = observation()
    if change == "missing":
        del value[section][next(iter(value[section]))]
    else:
        value[section]["unexpected"] = "unknown"
    with pytest.raises(m.EvidenceError):
        m.validate_observation(value)


@pytest.mark.parametrize("section,field,bad", [
    ("deployment_window", "started_at", "2026-10-10T06:00:00"),
    ("deployment_window", "started_at", "2026-10-10T07:00:00+00:00"),
    ("kb", "expected_count", True), ("kb", "archived_count", -1),
    ("kb", "expected_count", 0), ("kb", "generic_serving_count", False),
    ("kb", "audit_at", "2026-10-10T06:05:00"),
    ("processes", "unknown_count", False),
    ("environment", "process_flag", 0), ("control", "lease_exists", 0),
    ("control", "health_status", True),
])
def test_types_and_time_are_not_coerced(section, field, bad):
    value = observation()
    value[section][field] = bad
    with pytest.raises(m.EvidenceError):
        m.validate_observation(value)


def test_no_caller_claim_can_authorize_or_settle_run():
    value = observation()
    value["run_resolution"] = {"state": "NO_EFFECT", "ack_generation": 8}
    with pytest.raises(m.EvidenceError):
        m.inspect_readonly(value)
    result = m.inspect_readonly(observation())
    assert result == {"state": "EVIDENCE_ONLY", "authorized": False, "trusted_chain_verified": False}
