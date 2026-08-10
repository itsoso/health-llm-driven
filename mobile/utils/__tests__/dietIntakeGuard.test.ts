import {
  assertDietFoodItemsAllowed,
  looksLikeDietManagementIntent,
  looksLikeHealthMetricIntent,
  looksLikeNonDietIntake,
} from '../dietIntakeGuard';

describe('dietIntakeGuard', () => {
  it.each([
    ['我刚才不小心删除了'],
    ['删除这一餐'],
    ['取消这餐'],
  ])('detects management intent, not food intake: %s', (text) => {
    expect(looksLikeDietManagementIntent(text)).toBe(true);
    expect(() => assertDietFoodItemsAllowed(text)).toThrow('invalid_diet_food_items_management');
  });

  it.each([
    ['替普瑞酮胶囊（施维舒）'],
    ['刚吃了沃克 20mg'],
    ['鱼油'],
    ['Magnesium Glycinate'],
  ])('detects medication or supplement intake, not diet: %s', (text) => {
    expect(looksLikeNonDietIntake(text)).toBe(true);
    expect(() => assertDietFoodItemsAllowed(text)).toThrow('invalid_diet_food_items_non_diet');
  });

  it.each([
    ['晨跑 30 分钟'],
    ['今天步数 5370'],
    ['体重 73.1kg 腰围 84cm'],
    ['昨晚睡了 6 小时'],
    ['血压 130/85 血糖 6.2'],
  ])('detects health metrics, not diet intake: %s', (text) => {
    expect(looksLikeHealthMetricIntent(text)).toBe(true);
    expect(() => assertDietFoodItemsAllowed(text)).toThrow('invalid_diet_food_items_health_metric');
  });

  it.each([
    ['姜黄鲜柠维C茶'],
    ['煎牛肉能量碗 + 姜黄鲜柠维C茶'],
    ['鸡胸肉 200g + 糙米饭一碗'],
  ])('allows real meals and beverages: %s', (text) => {
    expect(() => assertDietFoodItemsAllowed(text)).not.toThrow();
  });

  it('defers the broad 片 heuristic only for owner-bound photo drafts', () => {
    const text = '小米粥 约1碗 + 胡萝卜 约3片 + 南瓜 约2块';
    expect(looksLikeNonDietIntake(text)).toBe(true);
    expect(() => assertDietFoodItemsAllowed(text)).toThrow('invalid_diet_food_items_non_diet');
    expect(() => assertDietFoodItemsAllowed(text, {
      ownerBoundPhotoDraft: true,
    })).not.toThrow();
  });

  it.each([
    ['删除这一餐', 'invalid_diet_food_items_management'],
    ['体重 73.1kg', 'invalid_diet_food_items_health_metric'],
  ])('keeps non-intake guards for photo drafts: %s', (text, errorCode) => {
    expect(() => assertDietFoodItemsAllowed(text, {
      ownerBoundPhotoDraft: true,
    })).toThrow(errorCode);
  });
});
