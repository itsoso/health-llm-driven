from eval.agent_trajectory_scorer import compare_candidates, score_trajectory


CASE = {
    "id": "diet_recalculate_visible_breakfast_lunch",
    "expected": {
        "goal_kind": "diet_recalculate_update",
        "domain": "diet",
        "operation": "update",
        "target_date": "2026-07-24",
        "target_meal_types": ["breakfast", "lunch"],
        "requires_lookup": True,
        "requires_verification": True,
        "prohibited_operations": ["create"],
        "clarification": False,
    },
}


def _valid_trace(candidate_id: str = "candidate-a") -> dict:
    return {
        "case_id": CASE["id"],
        "candidate_id": candidate_id,
        "client_turn_id": f"turn-{candidate_id}",
        "goal": {
            "kind": "diet_recalculate_update",
            "domain": "diet",
            "operation": "update",
            "target_date": "2026-07-24",
            "target_meal_types": ["breakfast", "lunch"],
        },
        "tool_calls": [
            {
                "name": "health_manage",
                "args": {
                    "record_type": "diet",
                    "operation": "list",
                    "date": "2026-07-24",
                },
                "result": [
                    {"id": 101, "meal_type": "breakfast"},
                    {"id": 102, "meal_type": "lunch"},
                ],
            },
            {
                "name": "health_manage",
                "args": {
                    "record_type": "diet",
                    "operation": "update",
                    "record_id": 101,
                    "data": {
                        "date": "2026-07-24",
                        "meal_type": "breakfast",
                        "calories": 410,
                    },
                },
                "receipt": {
                    "status": "verified",
                    "verified": True,
                    "record_id": 101,
                    "resource_type": "diet_record",
                    "date": "2026-07-24",
                    "meal_type": "breakfast",
                },
            },
            {
                "name": "health_manage",
                "args": {
                    "record_type": "diet",
                    "operation": "update",
                    "record_id": 102,
                    "data": {
                        "date": "2026-07-24",
                        "meal_type": "lunch",
                        "calories": 530,
                    },
                },
                "receipt": {
                    "status": "verified",
                    "verified": True,
                    "record_id": 102,
                    "resource_type": "diet_record",
                    "date": "2026-07-24",
                    "meal_type": "lunch",
                },
            },
            {
                "name": "health_manage",
                "args": {
                    "record_type": "diet",
                    "operation": "list",
                    "date": "2026-07-24",
                },
                "result": [
                    {
                        "id": 101,
                        "date": "2026-07-24",
                        "meal_type": "breakfast",
                        "calories": 410,
                    },
                    {
                        "id": 102,
                        "date": "2026-07-24",
                        "meal_type": "lunch",
                        "calories": 530,
                    },
                ],
            },
        ],
        "final": {"claims_complete": True},
        "latency_ms": 8900,
        "cost": 0.02,
    }


def test_score_trajectory_passes_verified_lookup_update_readback():
    scored = score_trajectory(CASE, _valid_trace())

    assert scored["passed"] is True
    assert scored["hard_failures"] == []
    assert scored["correctness_score"] == 100
    assert scored["dimensions"]["goal"] == 1
    assert scored["dimensions"]["lookup_before_write"] == 1
    assert scored["dimensions"]["target_updates"] == 1
    assert scored["dimensions"]["verified_receipts"] == 1
    assert scored["dimensions"]["readback"] == 1
    assert scored["dimensions"]["honest_completion"] == 1


def test_score_trajectory_hard_fails_create_and_false_completion():
    trace = _valid_trace("candidate-b")
    trace["tool_calls"] = [
        {
            "name": "health_manage",
            "args": {
                "record_type": "diet",
                "operation": "create",
                "data": {"meal_type": "breakfast"},
            },
            "result": {"id": 999},
        }
    ]

    scored = score_trajectory(CASE, trace)

    assert scored["passed"] is False
    assert scored["correctness_score"] == 0
    assert "prohibited_operation:create" in scored["hard_failures"]
    assert "write_before_lookup" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_hard_fails_when_lookup_has_ambiguous_target_records():
    trace = _valid_trace("candidate-ambiguous")
    trace["tool_calls"][0]["result"].insert(
        1,
        {"id": 111, "meal_type": "breakfast"},
    )

    scored = score_trajectory(CASE, trace)

    assert scored["passed"] is False
    assert scored["correctness_score"] == 0
    assert "ambiguous_lookup_target:breakfast" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_rejects_a_write_to_the_wrong_date():
    trace = _valid_trace("candidate-wrong-date")
    trace["goal"]["target_date"] = "2026-07-23"

    scored = score_trajectory(CASE, trace)

    assert scored["passed"] is False
    assert scored["dimensions"]["goal"] == 0
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_rejects_lookup_and_readback_for_wrong_date():
    trace = _valid_trace("candidate-wrong-tool-date")
    trace["tool_calls"][0]["args"]["date"] = "2026-07-23"
    trace["tool_calls"][-1]["args"]["date"] = "2026-07-23"

    scored = score_trajectory(CASE, trace)

    assert scored["passed"] is False
    assert "lookup_target_date_mismatch" in scored["hard_failures"]
    assert "readback_target_date_mismatch" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_rejects_explicit_write_date_that_differs_from_goal():
    trace = _simple_water_trace()
    trace["tool_calls"][0]["args"]["data"]["date"] = "2026-07-16"

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert "write_target_date_mismatch" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_rejects_receipt_identity_that_differs_from_write():
    trace = _valid_trace("candidate-wrong-receipt-id")
    trace["tool_calls"][1]["receipt"]["record_id"] = 999
    trace["tool_calls"][-1]["result"].append({
        "id": 999,
        "meal_type": "breakfast",
        "calories": 410,
    })

    scored = score_trajectory(CASE, trace)

    assert scored["passed"] is False
    assert "write_receipt_identity_mismatch" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_compare_candidates_ranks_correctness_before_latency_and_cost():
    correct = _valid_trace("candidate-slower")
    correct["latency_ms"] = 12000
    correct["cost"] = 0.08

    cheap_but_wrong = _valid_trace("candidate-fast")
    cheap_but_wrong["latency_ms"] = 1000
    cheap_but_wrong["cost"] = 0.001
    cheap_but_wrong["tool_calls"] = cheap_but_wrong["tool_calls"][1:3]

    comparison = compare_candidates([CASE], [cheap_but_wrong, correct])

    assert comparison["ranking"][0]["candidate_id"] == "candidate-slower"
    assert comparison["ranking"][0]["pass_rate"] == 1
    assert comparison["ranking"][1]["pass_rate"] == 0
    assert all("model" not in row for row in comparison["ranking"])


SIMPLE_WATER_CASE = {
    "id": "water_record_explicit_chinese_amount",
    "expected": {
        "goal_kind": "simple_health_record",
        "domain": "water",
        "operation": "create",
        "target_date": "2026-07-17",
        "target_record_type": "water",
        "target_values": {"amount_ml": "500"},
        "target_meal_types": [],
        "requires_lookup": False,
        "requires_verification": True,
        "prohibited_operations": ["update", "delete"],
        "clarification": False,
    },
}


def _simple_water_trace(*, receipt_status: str = "verified", claims_complete: bool = True) -> dict:
    return {
        "case_id": SIMPLE_WATER_CASE["id"],
        "candidate_id": "candidate-water",
        "client_turn_id": "turn-water-500",
        "goal": {
            "kind": "simple_health_record",
            "domain": "water",
            "operation": "create",
            "target_date": "2026-07-17",
            "target_meal_types": [],
        },
        "tool_calls": [
            {
                "name": "health_record",
                "args": {
                    "record_type": "water",
                    "operation": "create",
                    "data": {"amount_ml": "500", "date": "2026-07-17"},
                },
                "receipt": {
                    "status": receipt_status,
                    "verified": receipt_status == "verified",
                    "record_id": 501 if receipt_status == "verified" else None,
                    "resource_type": "water_record",
                    "date": "2026-07-17",
                },
            },
            {
                "name": "health_manage",
                "args": {"record_type": "water", "operation": "list", "date": "2026-07-17"},
                "result": [{"id": 501, "amount_ml": 500, "date": "2026-07-17"}],
            },
        ],
        "final": {"claims_complete": claims_complete},
    }


def test_score_trajectory_passes_simple_health_record_with_verified_readback():
    scored = score_trajectory(SIMPLE_WATER_CASE, _simple_water_trace())

    assert scored["passed"] is True
    assert scored["hard_failures"] == []
    assert scored["dimensions"]["target_updates"] == 1
    assert scored["dimensions"]["verified_receipts"] == 1
    assert scored["dimensions"]["readback"] == 1


def test_score_trajectory_accepts_a_production_shaped_write_receipt():
    from app.services.agent_executor import _write_receipt_from_tool_result

    trace = _simple_water_trace()
    receipt = _write_receipt_from_tool_result(
        "health_record",
        trace["tool_calls"][0]["args"],
        {
            "status": "recorded",
            "resource_type": "water_record",
            "resource_id": 501,
            "record_date": "2026-07-17",
        },
    )
    assert receipt is not None
    trace["tool_calls"][0]["receipt"] = receipt

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is True
    assert scored["hard_failures"] == []


def test_score_trajectory_rejects_conflicting_top_level_and_nested_date_aliases():
    trace = _simple_water_trace()
    trace["tool_calls"][0]["args"]["date"] = "2026-07-17"
    trace["tool_calls"][0]["args"]["data"]["date"] = "2099-01-01"

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert "conflicting_write_target_date" in scored["hard_failures"]


def test_score_trajectory_rejects_conflicting_top_level_and_nested_value_aliases():
    trace = _simple_water_trace()
    trace["tool_calls"][0]["args"]["amount_ml"] = "500"
    trace["tool_calls"][0]["args"]["data"]["amount_ml"] = "300"

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert "conflicting_write_target_value:amount_ml" in scored["hard_failures"]


def test_score_trajectory_rejects_conflicting_write_identity_aliases():
    trace = _valid_trace("candidate-conflicting-id")
    trace["tool_calls"][1]["args"]["data"]["record_id"] = 999

    scored = score_trajectory(CASE, trace)

    assert "conflicting_write_record_identity" in scored["hard_failures"]


def test_score_trajectory_rejects_conflicting_write_meal_aliases():
    trace = _valid_trace("candidate-conflicting-meal")
    trace["tool_calls"][1]["args"]["meal_type"] = "lunch"

    scored = score_trajectory(CASE, trace)

    assert "conflicting_write_meal_type" in scored["hard_failures"]


def test_score_trajectory_rejects_conflicting_receipt_resource_aliases():
    trace = _simple_water_trace()
    trace["tool_calls"][0]["receipt"]["record_type"] = "diet_record"

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert "conflicting_write_receipt_resource_type" in scored["hard_failures"]


def test_score_trajectory_rejects_conflicting_readback_aliases():
    trace = _simple_water_trace()
    trace["tool_calls"][-1]["result"][0]["record_date"] = "2099-01-01"

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert "conflicting_readback_result_date" in scored["hard_failures"]


def test_score_trajectory_rejects_conflicting_initial_lookup_date_aliases():
    trace = _valid_trace("candidate-conflicting-lookup-date")
    trace["tool_calls"][0]["args"]["record_date"] = "2099-01-01"

    scored = score_trajectory(CASE, trace)

    assert "conflicting_lookup_target_date" in scored["hard_failures"]


def test_score_trajectory_rejects_conflicting_initial_lookup_row_aliases():
    trace = _valid_trace("candidate-conflicting-lookup-row")
    trace["tool_calls"][0]["result"][0]["record_id"] = 999
    trace["tool_calls"][0]["result"][1]["data"] = {"meal_type": "dinner"}

    scored = score_trajectory(CASE, trace)

    assert "conflicting_lookup_result_identity" in scored["hard_failures"]
    assert "conflicting_lookup_result_meal_type" in scored["hard_failures"]


def test_score_trajectory_requires_explicit_verified_true_on_receipt():
    trace = _simple_water_trace()
    trace["tool_calls"][0]["receipt"].pop("verified")

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert "write_receipt_not_explicitly_verified" in scored["hard_failures"]


def test_score_trajectory_requires_write_date_for_dated_goal():
    trace = _simple_water_trace()
    trace["tool_calls"][0]["args"]["data"].pop("date")

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert "write_target_date_missing" in scored["hard_failures"]


def test_score_trajectory_binds_receipt_resource_type_and_date():
    wrong_resource = _simple_water_trace()
    wrong_resource["tool_calls"][0]["receipt"]["resource_type"] = "medication_log"
    wrong_date = _simple_water_trace()
    wrong_date["tool_calls"][0]["receipt"]["date"] = "2099-01-01"

    resource_score = score_trajectory(SIMPLE_WATER_CASE, wrong_resource)
    date_score = score_trajectory(SIMPLE_WATER_CASE, wrong_date)

    assert resource_score["passed"] is False
    assert "write_receipt_resource_type_mismatch" in resource_score["hard_failures"]
    assert date_score["passed"] is False
    assert "write_receipt_date_mismatch" in date_score["hard_failures"]


def test_score_trajectory_binds_readback_rows_to_expected_date():
    trace = _simple_water_trace()
    trace["tool_calls"][-1]["result"][0]["date"] = "2099-01-01"

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert "readback_result_date_mismatch" in scored["hard_failures"]


def test_score_trajectory_rejects_uncertain_receipt_that_claims_success():
    trace = _simple_water_trace(receipt_status="uncertain")
    trace["tool_calls"] = trace["tool_calls"][:1]

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert scored["dimensions"]["verified_receipts"] == 0
    assert scored["dimensions"]["honest_completion"] == 0
    assert "uncertain_receipt_claimed_complete" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_write_without_verified_receipt_cannot_pass_when_readback_is_optional():
    case = {
        "id": "fruit-record",
        "expected": {
            "goal_kind": "write",
            "domain": "diet",
            "operation": "create",
            "target_date": "2026-07-17",
            "target_record_type": "diet",
            "target_values": {
                "meal_type": "snack",
                "food_items": "一个水蜜桃",
            },
            "target_meal_types": [],
            "requires_lookup": False,
            "requires_verification": False,
            "prohibited_operations": [],
        },
    }
    trace = {
        "candidate_id": "candidate-fruit",
        "client_turn_id": "turn-fruit",
        "goal": {
            "kind": "write",
            "domain": "diet",
            "operation": "create",
            "target_date": "2026-07-17",
            "target_meal_types": [],
        },
        "tool_calls": [
            {
                "name": "health_record",
                "args": {
                    "record_type": "diet",
                    "operation": "create",
                    "data": {
                        "meal_type": "snack",
                        "food_items": "一个水蜜桃",
                    },
                },
            },
        ],
        "final": {"claims_complete": True},
    }

    scored = score_trajectory(case, trace)

    assert scored["passed"] is False
    assert scored["dimensions"]["verified_receipts"] == 0
    assert scored["dimensions"]["honest_completion"] == 0
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_rejects_duplicate_side_effect_for_same_client_turn_id():
    trace = _simple_water_trace()
    first_write = trace["tool_calls"][0]
    duplicate_write = {
        **first_write,
        "receipt": {
            **first_write["receipt"],
            "record_id": 502,
        },
    }
    trace["tool_calls"] = []
    trace["attempts"] = [
        {
            "client_turn_id": "turn-water-500",
            "tool_calls": [first_write],
        },
        {
            "client_turn_id": "turn-water-500",
            "tool_calls": [
                duplicate_write,
                {
                    "name": "health_manage",
                    "args": {
                        "record_type": "water",
                        "operation": "list",
                        "date": "2026-07-17",
                    },
                    "result": [
                        {
                            "id": 501,
                            "amount_ml": 500,
                            "date": "2026-07-17",
                        },
                        {
                            "id": 502,
                            "amount_ml": 500,
                            "date": "2026-07-17",
                        },
                    ],
                },
            ],
        },
    ]

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert "duplicate_side_effects:2>1" in scored["hard_failures"]


def test_score_trajectory_rejects_duplicate_write_to_same_record_id():
    trace = _valid_trace("candidate-duplicate-same-record")
    duplicate_breakfast = {
        **trace["tool_calls"][1],
        "args": {
            **trace["tool_calls"][1]["args"],
            "data": {"meal_type": "breakfast", "calories": 420},
        },
    }
    trace["tool_calls"].insert(2, duplicate_breakfast)

    scored = score_trajectory(CASE, trace)

    assert scored["passed"] is False
    assert "duplicate_side_effects:3>2" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_requires_identity_on_every_verified_write_receipt():
    trace = _valid_trace("candidate-missing-receipt-id")
    trace["tool_calls"][2]["receipt"].pop("record_id")

    scored = score_trajectory(CASE, trace)

    assert scored["passed"] is False
    assert scored["dimensions"]["verified_receipts"] == 0
    assert "write_receipt_missing_identity" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_rejects_unexpected_write_target():
    trace = _valid_trace("candidate-wrong-write-target")
    trace["tool_calls"].insert(
        3,
        {
            "name": "health_record",
            "args": {
                "record_type": "symptom",
                "operation": "update",
                "record_id": 901,
                "data": {"description": "synthetic"},
            },
            "receipt": {"status": "verified", "record_id": 901},
        },
    )

    scored = score_trajectory(CASE, trace)

    assert scored["passed"] is False
    assert "unexpected_write_target:symptom" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_rejects_any_write_for_read_only_goal():
    case = {
        "id": "water_question_remains_read_only",
        "expected": {
            "goal_kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-17",
            "target_meal_types": [],
            "target_record_type": None,
            "target_values": {},
            "requires_lookup": False,
            "requires_verification": False,
            "prohibited_operations": ["create", "update"],
        },
    }
    trace = {
        "candidate_id": "candidate-read-only-delete",
        "client_turn_id": "turn-read-only-delete",
        "goal": {
            "kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-17",
            "target_meal_types": [],
        },
        "tool_calls": [
            {
                "name": "health_manage",
                "args": {
                    "record_type": "water",
                    "operation": "delete",
                    "record_id": 902,
                },
                "receipt": {"status": "verified", "record_id": 902},
            }
        ],
        "final": {"claims_complete": True},
    }

    scored = score_trajectory(case, trace)

    assert scored["passed"] is False
    assert "unexpected_write_operation:delete" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_accepts_idempotent_replay_without_second_side_effect():
    trace = _simple_water_trace()
    write, readback = trace.pop("tool_calls")
    trace["attempts"] = [
        {
            "client_turn_id": "turn-water-500",
            "tool_calls": [write],
        },
        {
            "client_turn_id": "turn-water-500",
            "replayed": True,
            "tool_calls": [readback],
        },
    ]

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is True
    assert not any(item.startswith("duplicate_side_effects:") for item in scored["hard_failures"])


def test_score_trajectory_rejects_non_list_attempt_projection():
    trace = _simple_water_trace()
    trace["attempts"] = {
        "client_turn_id": "different-turn",
        "tool_calls": trace.pop("tool_calls"),
    }

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert "invalid_attempts_projection" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_requires_turn_id_on_root_and_every_attempt():
    trace = _simple_water_trace()
    write, readback = trace.pop("tool_calls")
    trace["attempts"] = [
        {"tool_calls": [write]},
        {
            "client_turn_id": "turn-water-500",
            "replayed": True,
            "tool_calls": [readback],
        },
    ]

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert "attempt_client_turn_id_missing" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_rejects_explicitly_unverified_success_receipt():
    trace = _simple_water_trace(receipt_status="success")
    trace["tool_calls"][0]["receipt"]["verified"] = False

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert "write_receipt_explicitly_unverified" in scored["hard_failures"]
    assert scored["dimensions"]["verified_receipts"] == 0
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_cannot_hide_top_level_write_behind_empty_attempts():
    case = {
        "id": "water_question_remains_read_only",
        "expected": {
            "goal_kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-17",
            "target_meal_types": [],
            "target_record_type": None,
            "target_values": {},
            "requires_lookup": False,
            "requires_verification": False,
            "prohibited_operations": ["create", "update", "delete"],
        },
    }
    trace = {
        "candidate_id": "candidate-hidden-delete",
        "client_turn_id": "turn-hidden-delete",
        "goal": {
            "kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-17",
            "target_meal_types": [],
        },
        "attempts": [],
        "tool_calls": [
            {
                "name": "health_manage",
                "args": {
                    "record_type": "water",
                    "operation": "delete",
                    "record_id": 902,
                },
                "receipt": {"status": "verified", "record_id": 902},
            }
        ],
        "final": {"claims_complete": True},
    }

    scored = score_trajectory(case, trace)

    assert scored["passed"] is False
    assert "prohibited_operation:delete" in scored["hard_failures"]
    assert "unexpected_write_operation:delete" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_detects_health_record_without_operation_as_write():
    case = {
        "id": "water_question_remains_read_only",
        "expected": {
            "goal_kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-17",
            "target_meal_types": [],
            "target_record_type": None,
            "target_values": {},
            "requires_lookup": False,
            "requires_verification": False,
            "prohibited_operations": ["create", "update", "delete"],
        },
    }
    trace = {
        "candidate_id": "candidate-hidden-health-record",
        "client_turn_id": "turn-hidden-health-record",
        "goal": {
            "kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-17",
            "target_meal_types": [],
        },
        "tool_calls": [
            {
                "name": "health_record",
                "args": {
                    "record_type": "water",
                    "data": {"amount_ml": 500},
                },
                "receipt": {"status": "verified", "record_id": 903},
            }
        ],
        "final": {"claims_complete": True},
    }

    scored = score_trajectory(case, trace)

    assert scored["passed"] is False
    assert "prohibited_operation:create" in scored["hard_failures"]
    assert "unexpected_write_operation:create" in scored["hard_failures"]
    assert "false_completion_claim" in scored["hard_failures"]


def test_score_trajectory_treats_health_record_as_create_despite_explicit_operation():
    case = {
        "id": "diet-update",
        "expected": {
            "goal_kind": "diet_recalculate_update",
            "domain": "diet",
            "operation": "update",
            "target_date": "2026-07-28",
            "target_meal_types": [],
            "target_record_type": "diet",
            "target_values": {},
            "requires_lookup": False,
            "requires_verification": False,
            "prohibited_operations": ["create", "delete"],
        },
    }
    trace = {
        "candidate_id": "candidate-health-record-update",
        "client_turn_id": "turn-health-record-update",
        "goal": {
            "kind": "diet_recalculate_update",
            "domain": "diet",
            "operation": "update",
            "target_date": "2026-07-28",
            "target_meal_types": [],
        },
        "tool_calls": [{
            "name": "health_record",
            "args": {
                "record_type": "diet",
                "operation": "update",
                "data": {"meal_type": "breakfast"},
            },
            "receipt": {"status": "verified", "record_id": 904},
        }],
        "final": {"claims_complete": True},
    }

    scored = score_trajectory(case, trace)

    assert scored["passed"] is False
    assert "prohibited_operation:create" in scored["hard_failures"]
    assert "unexpected_write_operation:create" in scored["hard_failures"]


def test_score_trajectory_detects_action_based_write_in_read_only_turn():
    case = {
        "id": "water-question",
        "expected": {
            "goal_kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-28",
            "target_meal_types": [],
            "target_values": {},
            "requires_lookup": False,
            "requires_verification": False,
            "prohibited_operations": ["create", "update", "delete"],
        },
    }
    trace = {
        "candidate_id": "candidate-hidden-plan-write",
        "client_turn_id": "turn-hidden-plan-write",
        "goal": {
            "kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-28",
            "target_meal_types": [],
        },
        "tool_calls": [{
            "name": "manage_plan",
            "args": {"action": "generate_weekly", "data": {}},
            "receipt": {"status": "verified", "record_id": 905},
        }],
        "final": {"claims_complete": True},
    }

    scored = score_trajectory(case, trace)

    assert scored["passed"] is False
    assert "unexpected_write_operation:generate_weekly" in scored["hard_failures"]


def test_score_trajectory_rejects_root_and_attempt_turn_id_mismatch():
    case = {
        "id": "water-question",
        "expected": {
            "goal_kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-28",
            "target_meal_types": [],
            "target_values": {},
            "requires_lookup": False,
            "requires_verification": False,
            "prohibited_operations": ["create", "update", "delete"],
        },
    }
    trace = {
        "candidate_id": "candidate-turn-mismatch",
        "client_turn_id": "turn-root",
        "goal": {
            "kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-28",
            "target_meal_types": [],
        },
        "attempts": [{"client_turn_id": "turn-other", "tool_calls": []}],
        "final": {"claims_complete": False},
    }

    scored = score_trajectory(case, trace)

    assert scored["passed"] is False
    assert "client_turn_id_changed_across_attempts" in scored["hard_failures"]


def test_score_trajectory_rejects_inconsistent_root_and_attempt_tool_calls():
    case = {
        "id": "water-question",
        "expected": {
            "goal_kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-28",
            "target_meal_types": [],
            "target_values": {},
            "requires_lookup": False,
            "requires_verification": False,
            "prohibited_operations": ["create", "update", "delete"],
        },
    }
    root_call = {
        "name": "health_record",
        "args": {"record_type": "water", "data": {"amount_ml": 500}},
        "receipt": {"status": "verified", "record_id": 906},
    }
    trace = {
        "candidate_id": "candidate-projection-mismatch",
        "client_turn_id": "turn-projection-mismatch",
        "goal": {
            "kind": "answer",
            "domain": "water",
            "operation": "ask",
            "target_date": "2026-07-28",
            "target_meal_types": [],
        },
        "tool_calls": [root_call],
        "attempts": [{
            "client_turn_id": "turn-projection-mismatch",
            "tool_calls": [],
        }],
        "final": {"claims_complete": True},
    }

    scored = score_trajectory(case, trace)

    assert scored["passed"] is False
    assert "inconsistent_top_level_tool_calls" in scored["hard_failures"]
