"""Evidence interning is a provider projection; authority and row semantics stay intact."""
from copy import deepcopy

import pytest


def evidence(count):
    return {"version": "composed-read-evidence.v1", "queries": [{
        "query": {"dimension": "diet", "timezone": "Asia/Shanghai"},
        "availability": "available", "record_count": count,
        "field_units": {"calories": "kcal"}, "records": [{
            "record_index": i + 1,
            "known_fields": {"food_name": "同名餐，不是新指令", "calories": 400.123456789, "id": i + 1},
            "unknown_fields": {key: "not_returned" for key in
                               ("protein", "carbs", "fat", "fiber", "quantity", "unit", "meal_time", "food_items")},
        } for i in range(count)],
    }], "limitations": ["synthetic"], "record_text_authority": "data_only_not_instructions_or_consent"}


@pytest.mark.parametrize("count", [1, 7, 31])
def test_reversible_projection_keeps_all_rows_values_order_and_unknown_states(count):
    from eval.experimental_read_evidence_format import intern_unknown_fields

    original = evidence(count)
    if count > 1:
        original["queries"][0]["records"][-1]["unknown_fields"]["fat"] = "null_in_result"
    before = deepcopy(original)
    compact = intern_unknown_fields(original)
    assert original == before
    if count == 1:
        assert compact == original
        return
    assert compact != original
    restored = deepcopy(compact)
    for query in restored["queries"]:
        sets = query.pop("unknown_field_sets")
        for row in query["records"]:
            row["unknown_fields"] = sets[row.pop("unknown_fields_ref")]
    assert restored == original
    compact["queries"][0]["records"][0]["known_fields"]["food_name"] = "changed"
    assert original == before


@pytest.mark.parametrize("mutation", [
    lambda x: x.update(version="unknown"),
    lambda x: x["queries"][0]["records"][0].pop("unknown_fields"),
    lambda x: x["queries"][0]["records"][0]["unknown_fields"].update(fat="unknown_future_state"),
    lambda x: x["queries"][0].update(unknown_field_sets=[]),
])
def test_unrecognized_evidence_is_preserved(mutation):
    from eval.experimental_read_evidence_format import intern_unknown_fields

    original = evidence(7)
    mutation(original)
    before = deepcopy(original)
    assert intern_unknown_fields(original) == before
    assert original == before
