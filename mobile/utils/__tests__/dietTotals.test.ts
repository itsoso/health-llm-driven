import { computeDietTotals, isPendingNutrition } from '../dietTotals';
import type { DietRecord } from '../../services/diet';

function rec(partial: Partial<DietRecord>): DietRecord {
  return {
    id: 1,
    user_id: 1,
    record_date: '2026-06-19',
    meal_type: 'lunch',
    food_items: '测试',
    calories: null,
    protein: null,
    carbs: null,
    fat: null,
    fiber: null,
    alcohol_units: null,
    image_url: null,
    notes: null,
    health_tips: null,
    ...partial,
  };
}

describe('isPendingNutrition', () => {
  it('treats null calories as pending', () => {
    expect(isPendingNutrition(rec({ calories: null }))).toBe(true);
  });
  it('treats a real calorie value (incl. 0) as not pending', () => {
    expect(isPendingNutrition(rec({ calories: 0 }))).toBe(false);
    expect(isPendingNutrition(rec({ calories: 420 }))).toBe(false);
  });
});

describe('computeDietTotals', () => {
  it('excludes pending (null) entries from totals and counts them', () => {
    const totals = computeDietTotals([
      rec({ id: 1, calories: 400, protein: 30, carbs: 40, fat: 10, fiber: 5 }),
      rec({ id: 2, calories: null }), // pending — must NOT count as 0
      rec({ id: 3, calories: 200, protein: 10, carbs: 20, fat: 5, fiber: 2 }),
    ]);
    expect(totals.calories).toBe(600);
    expect(totals.protein).toBe(40);
    expect(totals.carbs).toBe(60);
    expect(totals.fat).toBe(15);
    expect(totals.fiber).toBe(7);
    expect(totals.countedMeals).toBe(2);
    expect(totals.pendingMeals).toBe(1);
  });

  it('returns zeros with pending count when all entries are pending', () => {
    const totals = computeDietTotals([rec({ id: 1, calories: null }), rec({ id: 2, calories: null })]);
    expect(totals.calories).toBe(0);
    expect(totals.countedMeals).toBe(0);
    expect(totals.pendingMeals).toBe(2);
  });

  it('handles an empty list', () => {
    expect(computeDietTotals([])).toEqual({
      calories: 0, protein: 0, carbs: 0, fat: 0, fiber: 0, countedMeals: 0, pendingMeals: 0,
    });
  });

  it('tolerates partially-filled nutrition (null sub-fields count as 0)', () => {
    const totals = computeDietTotals([rec({ id: 1, calories: 300, protein: null, carbs: 20, fat: null, fiber: null })]);
    expect(totals.calories).toBe(300);
    expect(totals.protein).toBe(0);
    expect(totals.carbs).toBe(20);
    expect(totals.countedMeals).toBe(1);
  });
});
