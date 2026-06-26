"""Health Agenda contract: statuses, source refs, events, surfaces, and Smart Agenda metadata."""


def test_agenda_contract_normalizes_statuses_and_terminals():
    from app.services import agenda_contract as contract

    assert contract.canonical_item_status("done") == "completed"
    assert contract.canonical_item_status("verified") == "completed"
    assert contract.canonical_item_status("scheduled") == "pending"
    assert contract.canonical_item_status("overdue") == "overdue"

    assert contract.is_terminal_item_status("done") is True
    assert contract.is_terminal_item_status("completed") is True
    assert contract.is_terminal_item_status("auto_observed") is True
    assert contract.is_terminal_item_status("expired") is True
    assert contract.is_terminal_item_status("pending") is False
    assert contract.is_terminal_item_status("due") is False
    assert contract.is_terminal_item_status("info") is False


def test_execution_event_statuses_map_to_item_statuses():
    from app.services import agenda_contract as contract

    assert contract.EXECUTION_EVENT_STATUSES == (
        "done",
        "skipped",
        "snoozed",
        "adjusted",
        "auto_observed",
        "confirmed",
        "failed",
    )
    assert contract.execution_event_to_item_status("done") == "completed"
    assert contract.execution_event_to_item_status("confirmed") == "completed"
    assert contract.execution_event_to_item_status("failed") == "blocked"


def test_source_ref_contract_accepts_known_sources_and_rejects_unknown():
    from app.services import agenda_contract as contract

    ref = contract.source_ref("health_protocol", 7)
    assert ref == {"object_type": "health_protocol", "object_id": 7}
    assert contract.is_known_source_ref(ref) is True
    assert contract.is_known_source_ref({"object_type": "review_schedule", "object_id": "abc"}) is True
    assert contract.is_known_source_ref({"object_type": "random_tool", "object_id": 1}) is False


def test_surface_contract_uses_backend_owned_routing_rules():
    from app.services import agenda_contract as contract

    assert contract.surface_contract_for_item({"type": "movement"}) == {
        "primary": "watch",
        "alternates": ["mobile", "rokid"],
    }
    assert contract.surface_contract_for_item({"type": "diet"}) == {
        "primary": "mobile",
        "alternates": ["rokid", "watch"],
    }
    assert contract.surface_contract_for_item({
        "type": "checkup",
        "source": {"object_type": "review_schedule", "object_id": 3},
    }) == {
        "primary": "mobile",
        "alternates": ["mac", "watch"],
    }


def test_smart_item_carries_contract_metadata_and_keeps_voice_gate():
    from app.services import agenda_contract as contract
    from app.services import agenda_service

    med_item = {
        "type": "hydration",
        "title": "drifted medical writer",
        "status": "pending",
        "source_model": "medication_logs",
        "source": {"object_type": "health_protocol", "object_id": 9},
    }
    smart = agenda_service._to_smart_item(med_item, fallback_verification=None)

    assert smart["contract"]["version"] == contract.CONTRACT_VERSION
    assert smart["status_canonical"] == "pending"
    assert smart["is_terminal"] is False
    assert smart["contract"]["source_known"] is True
    assert smart["contract"]["execution_event_statuses"] == list(contract.EXECUTION_EVENT_STATUSES)
    assert smart["voice_actionable"] is False

    done = agenda_service._to_smart_item({**med_item, "status": "done"}, fallback_verification=None)
    assert done["status"] == "done"
    assert done["status_canonical"] == "completed"
    assert done["is_terminal"] is True


def test_regular_agenda_items_carry_contract_metadata(client, auth_user_and_headers):
    _, headers = auth_user_and_headers
    client.post("/api/v1/protocols/seed/water-cup", headers=headers)

    items = client.get("/api/v1/agenda/today", headers=headers).json()["items"]
    water = next(item for item in items if item["type"] == "hydration")

    assert water["status"] == "pending"
    assert water["status_canonical"] == "pending"
    assert water["is_terminal"] is False
    assert water["surface"] == {"primary": "watch", "alternates": ["mobile"]}
    assert water["contract"]["version"] == "health_agenda_contract_v1"
    assert water["contract"]["source_known"] is True
