from datetime import date, timedelta
from types import SimpleNamespace

from app.services.supplement_safety_context import (
    extract_supplement_safety_labs_from_indicators,
)


def _indicator(name, value, *, days_ago=0, name_en=None, item_code=None, unit=None, row_id=1):
    return SimpleNamespace(
        id=row_id,
        name=name,
        name_en=name_en,
        item_code=item_code,
        value=value,
        unit=unit,
        record_date=date.today() - timedelta(days=days_ago),
    )


def test_extract_supplement_labs_uses_latest_matching_indicator():
    rows = [
        _indicator("铁蛋白", 18, days_ago=120, row_id=1),
        _indicator("Ferritin", 72, days_ago=7, row_id=2),
        _indicator("eGFR", 25, days_ago=5, unit="mL/min/1.73m²", row_id=3),
        _indicator("甘油三酯", 2.4, days_ago=3, name_en="TG", row_id=4),
    ]

    labs = extract_supplement_safety_labs_from_indicators(rows)

    assert labs["ferritin"] == 72
    assert labs["egfr"] == 25
    assert labs["triglycerides"] == 2.4


def test_extract_supplement_labs_does_not_match_transferrin_as_ferritin():
    rows = [
        _indicator("转铁蛋白", 1.5, days_ago=1, name_en="Transferrin", row_id=1),
        _indicator("铁蛋白", 28, days_ago=30, row_id=2),
    ]

    labs = extract_supplement_safety_labs_from_indicators(rows)

    assert labs["ferritin"] == 28


def test_extract_supplement_labs_recognizes_vitamin_d_aliases():
    rows = [
        _indicator("25-羟维生素D", 19.5, days_ago=10, item_code="25-OH-D", unit="ng/mL"),
    ]

    labs = extract_supplement_safety_labs_from_indicators(rows)

    assert labs["vitamin_d"] == 19.5
