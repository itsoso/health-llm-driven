import {
  assertDietFoodItemsAllowed,
  looksLikeDietManagementIntent,
  looksLikeDietUiText,
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
    ['和午餐食品营养卡'],
    ['保存并确认'],
  ])('rejects leaked card UI copy as food intake: %s', (text) => {
    expect(looksLikeDietUiText(text)).toBe(true);
    expect(() => assertDietFoodItemsAllowed(text)).toThrow('invalid_diet_food_items_ui_text');
  });

  it.each([
    ['姜黄鲜柠维C茶'],
    ['煎牛肉能量碗 + 姜黄鲜柠维C茶'],
    ['鸡胸肉 200g + 糙米饭一碗'],
  ])('allows real meals and beverages: %s', (text) => {
    expect(() => assertDietFoodItemsAllowed(text)).not.toThrow();
  });
});
