const { buildShareText } = require('../MenuShareCard');

describe('MenuShareCard', () => {
  it('shares menu recommendations under the 小巴 persona', async () => {
    const message = buildShareText(
      {
        title: '今晚晚餐',
        reason: '适合轻负担补蛋白。',
        items: [{ name: '鸡胸肉', qty: '150g', kcal: 240 }],
        totals: { kcal: 420, protein: 35, carbs: 40, fat: 12 },
        shopping_list: ['鸡胸肉', '生菜'],
      },
    );

    expect(message).toContain('— 小巴');
    expect(message).not.toContain('健康 Agent');
  });
});
