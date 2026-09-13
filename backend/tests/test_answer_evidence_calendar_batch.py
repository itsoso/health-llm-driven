"""Current-turn calendar batch facts must have the same provenance as single reads."""

from copy import deepcopy
import json

import pytest

from app.services.answer_evidence import (
    MAX_BASIS_ITEMS,
    MAX_LIMITATIONS,
    build_answer_evidence,
    normalize_answer_evidence,
)

WINDOW = {
    "start_date": "2026-09-07",
    "end_date": "2026-09-13",
    "timezone": "Asia/Shanghai",
}


def query(dimension):
    return {"dimension": dimension, "days": 7, **WINDOW}


def payload(dimension):
    row = {
        "record_date": "2026-09-12",
        "notes": {"secret": "PRIVATE_PAYLOAD"},
        "user_id": 90001,
    }
    data = {
        "dimension": dimension,
        "window": dict(WINDOW),
        "records": [row],
        "availability": "available",
        "limitations": [],
    }
    if dimension == "diet":
        row.update(food_name="合成餐", calories=323.4567)
    elif dimension == "sleep":
        row.update(sleep_score=80, total_sleep_duration=423)
    elif dimension == "workout":
        data["source_scope"] = "owned_actual_workout_records"
        row.update(
            record_kind="workout_record",
            duration_seconds=1854,
            calories=150,
            workout_type="PRIVATE_PAYLOAD",
        )
    else:
        data["source_scope"] = "owned_actual_supplement_intake_logs"
        row.update(
            record_kind="supplement_intake",
            taken=True,
            dosage=999.12345,
            supplement_name="PRIVATE_PAYLOAD",
            unit="PRIVATE_PAYLOAD",
        )
    return data


def build_batch(dimensions=("diet", "sleep", "workout", "supplements"), *, mutate=None):
    args = {"queries": [query(d) for d in dimensions]}
    result = {"status": "success", "results": [payload(d) for d in dimensions]}
    if mutate:
        mutate(args, result)
    return build_answer_evidence(
        tool_calls=[("health_query_batch", args, json.dumps(result))]
    )


def without_ids(items):
    return [{k: v for k, v in item.items() if k != "id"} for item in items]


@pytest.mark.parametrize("dimension", ["diet", "sleep", "workout", "supplements"])
def test_batch_result_has_same_actual_facts_as_single_query(dimension):
    single = build_answer_evidence(
        tool_calls=[("health_query", query(dimension), json.dumps(payload(dimension)))]
    )
    batch = build_batch((dimension,))
    assert single and single["basis"]
    assert batch and batch["basis"]
    assert without_ids(batch["basis"]) == without_ids(single["basis"])
    assert normalize_answer_evidence(batch) == batch


def test_four_domains_fit_bounded_basis_without_leaking_raw_fields():
    result = build_batch()
    assert result and len(result["basis"]) == MAX_BASIS_ITEMS
    rendered = json.dumps(result, ensure_ascii=False)
    for label in ("饮食", "睡眠", "运动", "补剂"):
        assert label in rendered
    assert "323.46" in rendered and "30.9" in rendered
    assert (
        "PRIVATE_PAYLOAD" not in rendered
        and "90001" not in rendered
        and "999.12345" not in rendered
    )
    assert len(result["limitations"]) <= MAX_LIMITATIONS


@pytest.mark.parametrize(
    "mutate",
    [
        lambda a, r: r.update(status="failed", error="PRIVATE_PAYLOAD"),
        lambda a, r: r.update(status="partial"),
        lambda a, r: r.update(status="queued"),
        lambda a, r: r.update(success=False),
        lambda a, r: r.update(results=None),
        lambda a, r: r.update(results=[r["results"][0], r["results"][0]]),
        lambda a, r: r["results"][0].update(dimension="sleep"),
        lambda a, r: r["results"][0]["window"].update(timezone="UTC"),
        lambda a, r: r["results"][0]["records"][0].update(record_date="2026-09-06"),
        lambda a, r: r["results"][0].update(status="error", message="PRIVATE_PAYLOAD"),
        lambda a, r: a["queries"][0].update(days=1),
        lambda a, r: a["queries"][0].update(days=True),
        lambda a, r: a["queries"][0].update(user_id=90001),
        lambda a, r: a.update(owner_id=90001),
    ],
)
def test_malformed_mismatched_or_failed_batch_does_not_promote_attached_rows(mutate):
    result = build_batch(("diet",), mutate=mutate)
    assert result and not result["basis"] and result["limitations"]
    assert "PRIVATE_PAYLOAD" not in json.dumps(result)


def test_successful_batch_item_survives_another_failed_item_with_limitation():
    def mutate(args, result):
        result["results"][1].update(status="failed", error="PRIVATE_PAYLOAD")

    result = build_batch(("diet", "sleep"), mutate=mutate)
    assert len(result["basis"]) == 1 and "饮食" in result["basis"][0]["label"]
    assert result["limitations"] and "睡眠" in result["limitations"][0]["title"]
    assert "PRIVATE_PAYLOAD" not in json.dumps(result)


def test_missing_batch_item_is_limitation_not_success_or_old_data_fallback():
    def mutate(args, result):
        result["results"].pop()
        result["queries"] = [{"dimension": "sleep", "value": 99, "unit": "分"}]

    result = build_batch(("diet", "sleep"), mutate=mutate)
    assert len(result["basis"]) == 1
    assert result["limitations"]
    assert "99" not in json.dumps(result, ensure_ascii=False)


@pytest.mark.parametrize("dimension,mutation", [
    ("workout", "source"), ("workout", "kind"),
    ("supplements", "source"), ("supplements", "kind"), ("supplements", "taken"),
])
def test_plans_and_definitions_do_not_become_actual_intake_or_activity_evidence(
    dimension, mutation
):

    def mutate(args, result):
        data = result["results"][0]
        if mutation == "source":
            data["source_scope"] = "definitions"
        elif mutation == "kind":
            data["records"][0]["record_kind"] = "plan"
        else:
            data["records"][0]["taken"] = False

    result = build_batch((dimension,), mutate=mutate)
    assert result and not result["basis"] and result["limitations"]


def test_partial_data_has_only_actual_readings_and_explicit_gap():
    def mutate(args, result):
        result["results"][0]["availability"] = "partial"
        result["results"][0]["limitations"] = ["sync_status_unknown"]

    result = build_batch(("sleep",), mutate=mutate)
    assert result["basis"] and result["limitations"]
    assert "缺失" in result["limitations"][0]["detail"]


def test_no_data_is_only_limitation():
    def mutate(args, result):
        result["results"][0].update(records=[], availability="no_data")

    result = build_batch(("supplements",), mutate=mutate)
    assert result and not result["basis"] and result["limitations"]


def test_many_rows_preserve_domain_representation_and_bound_display():
    def mutate(args, result):
        for item in result["results"]:
            item["records"] *= 20

    result = build_batch(mutate=mutate)
    assert len(result["basis"]) == MAX_BASIS_ITEMS
    assert len(result["limitations"]) <= MAX_LIMITATIONS
    assert len({item["id"] for item in result["basis"]}) == len(result["basis"])
    for label in ("饮食", "睡眠", "运动", "补剂"):
        assert any(label in item["label"] for item in result["basis"])
    assert any("部分记录" in item["detail"] for item in result["limitations"])
    assert normalize_answer_evidence(result) == result


def test_json_or_mapping_results_match_and_input_remains_unchanged():
    args, data = query("sleep"), payload("sleep")
    original = deepcopy(data)
    mapped = build_answer_evidence(
        tool_calls=[
            (
                "health_query_batch",
                {"queries": [args]},
                {"status": "success", "results": [data]},
            )
        ]
    )
    assert mapped == build_batch(("sleep",))
    assert data == original


def test_unserializable_private_metadata_is_never_traversed_or_rendered():
    data = payload("sleep")
    data["records"][0]["private_attachment"] = object()
    data["private_context"] = object()
    result = build_answer_evidence(tool_calls=[(
        "health_query_batch", {"queries": [query("sleep")]},
        {"status": "success", "results": [data]},
    )])
    assert result and result["basis"]
    assert "object" not in json.dumps(result)


def test_all_result_limits_remain_bounded_and_do_not_echo_failures():
    def mutate(args, result):
        for item in result["results"]:
            item.update(status="failed", error={"private": "PRIVATE_PAYLOAD"})
    result = build_batch(mutate=mutate)
    assert not result["basis"] and len(result["limitations"]) == MAX_LIMITATIONS
    assert "PRIVATE_PAYLOAD" not in json.dumps(result)


@pytest.mark.parametrize("shape", ["separate", "batch", "mixed", "reverse"])
@pytest.mark.parametrize("with_packet", [False, True])
def test_global_domain_coverage_is_independent_of_call_grouping(shape, with_packet):
    from types import SimpleNamespace
    dimensions = ("diet", "sleep", "workout", "supplements")
    items = []
    for dimension in dimensions:
        data = payload(dimension)
        data["records"] *= 6
        items.append(("health_query", query(dimension), data))
    if shape == "batch":
        calls = [("health_query_batch", {"queries": [item[1] for item in items]},
                  {"status": "success", "results": [item[2] for item in items]})]
    elif shape == "mixed":
        calls = [("health_query_batch", {"queries": [item[1] for item in items[:2]]},
                  {"status": "success", "results": [item[2] for item in items[:2]]}), *items[2:]]
    else:
        calls = items if shape == "separate" else list(reversed(items))
    packet = SimpleNamespace(evidence=[SimpleNamespace(
        value=1, unit=None, label=f"其他指标{i}", evidence_id=f"packet-{i}",
        category="metric", source_kind="manual",
    ) for i in range(4)]) if with_packet else None
    result = build_answer_evidence(tool_calls=calls, personal_packet=packet)
    assert len(result["basis"]) == MAX_BASIS_ITEMS
    assert {item["label"].split(" · ")[0] for item in result["basis"]} == {"饮食", "睡眠", "运动", "补剂"}
    assert normalize_answer_evidence(result) == result


def test_multidomain_reserves_actual_read_then_fills_packet_before_extra_rows():
    from types import SimpleNamespace
    packet = SimpleNamespace(evidence=[SimpleNamespace(
        value=1, unit=None, label=f"其他指标{i}", evidence_id=f"packet-{i}",
        category="metric", source_kind="manual",
    ) for i in range(4)])
    calls = []
    for dimension in ("diet", "sleep"):
        data = payload(dimension)
        data["records"] *= 5
        calls.append(("health_query", query(dimension), data))
    result = build_answer_evidence(tool_calls=calls, personal_packet=packet)
    assert [r["label"].split(" · ")[0] for r in result["basis"]] == ["饮食", "睡眠", "其他指标0", "其他指标1"]
    # A single read and packet-only projection retain the original priority.
    single = build_answer_evidence(tool_calls=calls[:1], personal_packet=packet)
    packet_only = build_answer_evidence(personal_packet=packet)
    assert single["basis"] == packet_only["basis"]
    assert [r["id"] for r in single["basis"]] == [f"packet-{i}" for i in range(4)]


@pytest.mark.parametrize("failure", ["missing", "failed", "empty", "source"])
def test_global_fairness_never_creates_basis_for_unverified_or_empty_domain(failure):
    calls = []
    for dimension in ("diet", "sleep", "workout", "supplements"):
        data = payload(dimension)
        data["records"] *= 5
        if dimension == "workout":
            if failure == "missing":
                data = None
            elif failure == "failed":
                data.update(status="failed")
            elif failure == "empty":
                data.update(records=[], availability="no_data")
            else:
                data["source_scope"] = "definitions"
        calls.append(("health_query", query(dimension), data))
    result = build_answer_evidence(tool_calls=calls)
    assert {item["label"].split(" · ")[0] for item in result["basis"]} == {"饮食", "睡眠", "补剂"}
    assert len(result["basis"]) == MAX_BASIS_ITEMS
    assert any("运动" in note["title"] for note in result["limitations"])


def test_same_dimension_different_verified_windows_keep_both_comparison_facts():
    calls = []
    for days, start, duration in [(7, "2026-09-07", 1800), (30, "2026-08-15", 3600)]:
        args = {**query("workout"), "days": days, "start_date": start}
        data = payload("workout")
        data["window"]["start_date"] = start
        data["records"][0]["duration_seconds"] = duration
        data["records"] *= 5
        calls.append(("health_query", args, data))
    result = build_answer_evidence(tool_calls=calls)
    assert len(result["basis"]) == MAX_BASIS_ITEMS
    assert {row["observation"] for row in result["basis"]} == {
        "运动时长 30 分钟", "运动时长 60 分钟",
    }


@pytest.mark.parametrize("unavailable", ["failed", "empty"])
def test_packet_order_is_unchanged_with_only_one_available_query(unavailable):
    from types import SimpleNamespace

    packet = SimpleNamespace(evidence=[SimpleNamespace(
        value=1, unit=None, label=f"其他指标{i}", evidence_id=f"packet-{i}",
        category="metric", source_kind="manual",
    ) for i in range(4)])
    second = payload("sleep")
    if unavailable == "failed":
        second["status"] = "failed"
    else:
        second.update(records=[], availability="no_data")
    result = build_answer_evidence(tool_calls=[
        ("health_query", query("diet"), payload("diet")),
        ("health_query", query("sleep"), second),
    ], personal_packet=packet)
    assert result["basis"] == build_answer_evidence(personal_packet=packet)["basis"]
    assert result["limitations"]
