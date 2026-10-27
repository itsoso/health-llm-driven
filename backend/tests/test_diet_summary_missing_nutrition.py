import pytest

from app.services.genui.diet_summary import build_diet_daily_summary


def test_partial_totals_are_known_subtotals_without_adequacy_claims():
    data = build_diet_daily_summary({
        'meals': [{'calories': 98, 'protein': 1.1, 'carbs': 26, 'fat': .2},
                  {'calories': None, 'protein': None, 'carbs': None, 'fat': None}],
        'total_calories': 999, 'total_fat': 40,
    }, weight_kg=70)['data']
    assert data['totals']['calories'] == 98
    assert data['totals']['fiber'] is None
    assert data['nutrition_coverage']['incomplete_records'] == 1
    assert data['nutrition_coverage']['missing_by_nutrient']['calories'] == 1
    assert data['observations'] == []


@pytest.mark.parametrize('value', [None, True, -1, float('nan'), float('inf'), ''])
def test_unknown_nutrition_never_becomes_zero(value):
    data = build_diet_daily_summary({'meals': [{'calories': value}],
                                   'total_calories': 0})['data']
    assert data['totals']['calories'] is None
    assert data['meals'][0]['calories'] is None


def test_real_zero_is_known_and_raw_values_are_summed_before_display_rounding():
    data = build_diet_daily_summary({'meals': [
        {'calories': .004, 'protein': 0, 'carbs': 0, 'fat': 0},
        {'calories': .004, 'protein': 0, 'carbs': 0, 'fat': 0},
    ]})['data']
    assert data['totals']['calories'] == .01
    assert data['totals']['protein'] == 0
    assert data['nutrition_coverage']['incomplete_records'] == 0
