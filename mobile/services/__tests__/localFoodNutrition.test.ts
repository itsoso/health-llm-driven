import {
  lookupLocalFoodNutrition,
  parseLocalFoodAmount,
} from '../localFoodNutrition';

describe('local food nutrition', () => {
  it('scales attributed nutrients for explicit grams', () => {
    expect(lookupLocalFoodNutrition('米饭', { grams: 150 })).toEqual({
      status: 'matched',
      foodId: 'fdc-168878',
      canonicalName: '白米饭',
      grams: 150,
      nutrients: {
        calories: 195,
        protein: 4.035,
        carbs: 42.3,
        fat: 0.42,
        fiber: 0.6,
      },
      source: expect.objectContaining({
        provider: 'USDA FoodData Central',
        release: 'SR Legacy 2018-04',
        fdcId: 168878,
      }),
      portionBasis: 'measured',
    });
  });

  it('uses only approved source-backed household portions', () => {
    expect(lookupLocalFoodNutrition('鸡蛋', { count: 2, unit: '个' })).toMatchObject({
      status: 'matched',
      grams: 100,
      portionBasis: 'source_portion',
      nutrients: { calories: 155, protein: 12.6 },
    });
  });

  it('preserves unknown or unsupported amounts instead of fabricating totals', () => {
    expect(lookupLocalFoodNutrition('炒饭', { count: 1, unit: '盘' })).toEqual({
      status: 'not_found',
    });
    expect(lookupLocalFoodNutrition('米饭', { count: 1, unit: '勺' })).toEqual({
      status: 'unsupported_amount',
      foodId: 'fdc-168878',
      canonicalName: '白米饭',
    });
  });

  it('parses bounded Chinese gram and approved-unit quantities', () => {
    expect(parseLocalFoodAmount('鸡胸肉200g')).toEqual({ name: '鸡胸肉', grams: 200 });
    expect(parseLocalFoodAmount('两个鸡蛋')).toEqual({ name: '鸡蛋', count: 2, unit: '个' });
    expect(parseLocalFoodAmount('半碗米饭')).toEqual({ name: '米饭', count: 0.5, unit: '碗' });
    expect(parseLocalFoodAmount('很多米饭')).toEqual({ name: '很多米饭' });
  });
});
