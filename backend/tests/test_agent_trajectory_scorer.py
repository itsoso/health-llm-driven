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
                "args": {"record_type": "diet", "operation": "list", "date": "today"},
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
                    "data": {"meal_type": "breakfast", "calories": 410},
                },
                "receipt": {
                    "status": "verified",
                    "record_id": 101,
                    "meal_type": "breakfast",
                },
            },
            {
                "name": "health_manage",
                "args": {
                    "record_type": "diet",
                    "operation": "update",
                    "record_id": 102,
                    "data": {"meal_type": "lunch", "calories": 530},
                },
                "receipt": {
                    "status": "verified",
                    "record_id": 102,
                    "meal_type": "lunch",
                },
            },
            {
                "name": "health_manage",
                "args": {"record_type": "diet", "operation": "list", "date": "today"},
                "result": [
                    {"id": 101, "meal_type": "breakfast", "calories": 410},
                    {"id": 102, "meal_type": "lunch", "calories": 530},
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
                    "data": {"amount_ml": "500"},
                },
                "receipt": {
                    "status": receipt_status,
                    "record_id": 501 if receipt_status == "verified" else None,
                },
            },
            {
                "name": "health_manage",
                "args": {"record_type": "water", "operation": "list", "date": "2026-07-17"},
                "result": [{"id": 501, "amount_ml": 500}],
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
        "receipt": {"status": "verified", "record_id": 502},
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
                        {"id": 501, "amount_ml": 500},
                        {"id": 502, "amount_ml": 500},
                    ],
                },
            ],
        },
    ]

    scored = score_trajectory(SIMPLE_WATER_CASE, trace)

    assert scored["passed"] is False
    assert "duplicate_side_effects:2>1" in scored["hard_failures"]


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
