"""Pure rollback-old checks: caller observations never authorize retirement.

No filesystem/command/DB access or mutation entry point. This metadata schema
cannot establish root authenticity, settle a Run, acknowledge a circuit, or
produce a closure receipt. A later operator needs a complete trusted chain.
"""
import hashlib
import re
from datetime import datetime


class EvidenceError(ValueError):
    """Closed diagnostic without echoing untrusted evidence."""


def _require(condition):
    if not condition:
        raise EvidenceError("rollback-old evidence invalid or incomplete")


def _object(value, fields):
    _require(type(value) is dict and set(value) == set(fields.split()))
    return value


def _integer(value, minimum=0):
    _require(type(value) is int and value >= minimum)
    return value


def _hex(value, length):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value) is not None)
    return value


def _time(value):
    _require(type(value) is str and len(value) <= 64)
    try:
        parsed = datetime.fromisoformat(value)
        _require(parsed.tzinfo is not None and parsed.utcoffset() is not None)
        return parsed
    except (ValueError, OverflowError):
        raise EvidenceError("rollback-old evidence invalid or incomplete") from None


def validate_observation(value):
    """Validate a closed synthetic/collected observation, never its provenance."""
    v = _object(value, "version context backend_terminal runtime_terminal runtime_inventory deployment_window deployment_log kb environment processes control")
    _require(type(v["version"]) is int and v["version"] == 1)
    c = _object(v["context"], "production_sha failed_sha closing_sha")
    old, failed, closing = (_hex(c[k], 40) for k in ("production_sha", "failed_sha", "closing_sha"))
    _require(len({old, failed, closing}) == 3)
    b = _object(v["backend_terminal"], "sha state")
    _require(b == {"sha": failed, "state": "NEEDS_OPERATOR"})
    r = _object(v["runtime_terminal"], "version old_sha candidate_sha terminal_sha target phase result transaction_id reap_name")
    transaction = hashlib.sha256(f"{old}:{failed}".encode("ascii")).hexdigest()[:32]
    _require(type(r["version"]) is int and r == {
        "version": 1, "old_sha": old, "candidate_sha": failed, "terminal_sha": old,
        "target": "old", "phase": "RESTORE_FINALIZED", "result": "RESTORE_FINALIZED",
        "transaction_id": transaction, "reap_name": "runtime-state-transaction.reap-" + transaction,
    })
    _require(type(v["runtime_inventory"]) is list and v["runtime_inventory"] == ["runtime-state-terminal.json"])
    w = _object(v["deployment_window"], "started_at completed_at")
    start, end = _time(w["started_at"]), _time(w["completed_at"])
    _require(start <= end)
    log = v["deployment_log"]
    _require(type(log) is str and len(log) <= 16 * 1024 * 1024)
    _require(not any(ord(ch) < 32 and ch not in "\n\t" for ch in log))
    expected = (f"ROLLBACK_OK commit={old} kb_quarantine=passed schema_probe=passed "
                "auth_probe=passed services=active process_flag=false runtime_state=restored")
    markers = [line for line in log.splitlines() if "ROLLBACK_OK" in line]
    _require(markers == [expected])
    k = _object(v["kb"], "state old_sha candidate_sha actor audit_count audit_at expected_pack_sha256 sealed_pack_sha256 expected_count target_count matched_count archived_count all_archived metadata_matches generic_serving_count runtime_serving_count")
    _require(k["state"] == "ROLLBACK_QUARANTINED" and k["old_sha"] == old and k["candidate_sha"] == failed)
    _require(k["actor"] == "rollback:" + old[:12])
    _require(_integer(k["audit_count"]) == 1 and start <= _time(k["audit_at"]) <= end)
    _require(_hex(k["expected_pack_sha256"], 64) == _hex(k["sealed_pack_sha256"], 64))
    count = _integer(k["expected_count"], 1)
    _require(_integer(k["target_count"]) == count and _integer(k["matched_count"]) == count)
    _require(_integer(k["archived_count"]) <= count)
    _require(k["all_archived"] is True and k["metadata_matches"] is True)
    _require(_integer(k["generic_serving_count"]) == 0 and _integer(k["runtime_serving_count"]) == 0)
    e = _object(v["environment"], "live_sha256 rollback_sha256 candidate_sha256 process_flag schema_compatible")
    _require(_hex(e["live_sha256"], 64) == _hex(e["rollback_sha256"], 64))
    _hex(e["candidate_sha256"], 64)
    _require(e["process_flag"] is False and e["schema_compatible"] is True)
    p = _object(v["processes"], "inventory_complete unknown_count active_release_count")
    _require(p["inventory_complete"] is True and _integer(p["unknown_count"]) == 0 and _integer(p["active_release_count"]) == 0)
    control = _object(v["control"], "production_sha production_clean lease_exists transaction_exists reap_exists activation_exists workflow_terminal original_workspace_preserved launcher_identity_matches services_stable health_status unauthenticated_status")
    _require(control["production_sha"] == old)
    for field in ("production_clean", "workflow_terminal", "original_workspace_preserved", "launcher_identity_matches", "services_stable"):
        _require(control[field] is True)
    for field in ("lease_exists", "transaction_exists", "reap_exists", "activation_exists"):
        _require(control[field] is False)
    _require(_integer(control["health_status"]) == 200 and _integer(control["unauthenticated_status"]) == 401)


def inspect_readonly(value):
    """Structural evidence only; a caller cannot assert trusted provenance."""
    validate_observation(value)
    return {"state": "EVIDENCE_ONLY", "authorized": False, "trusted_chain_verified": False}
