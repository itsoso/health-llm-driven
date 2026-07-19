import { createLocalDietDraft } from '../localDietDraft';

describe('local diet draft', () => {
  it('parses a simple Chinese meal and uses only attributed local nutrition', () => {
    const draft = createLocalDietDraft('午饭半碗米饭两个鸡蛋', '2026-07-19');

    expect(draft).toMatchObject({
      mealType: 'lunch',
      needsConfirmation: true,
      nutritionComplete: true,
      items: [
        { name: '米饭', grams: 79, matchStatus: 'matched', portionBasis: 'estimated_portion' },
        { name: '鸡蛋', grams: 100, matchStatus: 'matched', portionBasis: 'source_portion' },
      ],
      record: {
        record_date: '2026-07-19',
        meal_type: 'lunch',
        food_items: '半碗米饭、两个鸡蛋',
        source: 'local_deterministic_usda',
      },
    });
    expect(draft.record.calories).toBeCloseTo(257.7, 1);
  });

  it('keeps all nutrition unknown if any item cannot be attributed', () => {
    const draft = createLocalDietDraft('晚饭一盘炒饭', '2026-07-19');

    expect(draft).toMatchObject({
      mealType: 'dinner',
      nutritionComplete: false,
      items: [{ name: '炒饭', matchStatus: 'not_found' }],
      record: {
        food_items: '一盘炒饭',
      },
    });
    expect(draft.record.calories).toBeUndefined();
    expect(draft.record.protein).toBeUndefined();
  });

  it('accepts manual descriptions without inventing a zero-valued estimate', () => {
    const draft = createLocalDietDraft('自制蔬菜饼', '2026-07-19', 'snack');

    expect(draft.record).toEqual(expect.objectContaining({
      meal_type: 'snack',
      food_items: '自制蔬菜饼',
    }));
    expect(draft.record.calories).toBeUndefined();
  });
});
