from eval.agent_trajectory_scorer import compare_candidates, score_trajectory


CASE = {
    "id": "diet_recalculate_visible_breakfast_lunch",
    "expected": {
        "goal_kind": "diet_recalculate_update",
        "domain": "diet",
        "operation": "update",
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
