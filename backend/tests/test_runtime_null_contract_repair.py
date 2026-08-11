import pytest

from app.services.runtime_null_contract_repair import (
    EXPECTED,
    RepairCounts,
    classify_template_rows,
)


def test_runtime_null_contract_repair_has_frozen_expected_population():
    assert EXPECTED == RepairCounts(
        checkin_values=31,
        template_owners=12,
        orphan_templates=6,
        progress_dates=4,
        goal_titles=8,
    )


def test_classify_template_rows_separates_derived_owners_and_orphans():
    owned, orphaned = classify_template_rows(
        [
            {"id": 1, "owner_count": 1, "record_count": 2},
            {"id": 2, "owner_count": 0, "record_count": 0},
        ]
    )

    assert [row["id"] for row in owned] == [1]
    assert [row["id"] for row in orphaned] == [2]


def test_classify_template_rows_rejects_ambiguous_ownership():
    with pytest.raises(RuntimeError, match="ambiguous checkin template ownership"):
        classify_template_rows([{"id": 1, "owner_count": 2, "record_count": 3}])
