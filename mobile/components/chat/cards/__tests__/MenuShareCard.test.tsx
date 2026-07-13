const { buildSharePayload, buildShareText } = require('../MenuShareCard');

describe('MenuShareCard', () => {
  const sampleMenu = {
    title: '今晚晚餐',
    reason: '适合轻负担补蛋白。',
    items: [{ name: '鸡胸肉', qty: '150g', kcal: 240 }],
    totals: { kcal: 420, protein: 35, carbs: 40, fat: 12 },
    shopping_list: ['鸡胸肉', '生菜'],
  };

  it('shares menu recommendations under the 小巴 persona', async () => {
    const message = buildShareText(sampleMenu);

    expect(message).toContain('— 小巴');
    expect(message).not.toContain('健康 Agent');
  });

  it('builds a Xiaohongshu-ready note with title, sections, and hashtags', () => {
    const payload = buildSharePayload(sampleMenu, 'xiaohongshu');

    expect(payload.title).toBe('今晚晚餐｜420 kcal 轻负担高蛋白');
    expect(payload.message).toContain('📌 今晚晚餐');
    expect(payload.message).toContain('🥗 吃什么');
    expect(payload.message).toContain('鸡胸肉 · 150g');
    expect(payload.message).toContain('📊 营养估算');
    expect(payload.message).toContain('420 kcal');
    expect(payload.message).toContain('🛒 备菜');
    expect(payload.message).toContain('#饮食打卡 #健康饮食 #高蛋白饮食 #小巴健康');
  });

  it('keeps WeChat payload concise for family chats', () => {
    const payload = buildSharePayload(sampleMenu, 'wechat');

    expect(payload.title).toBe('今晚晚餐');
    expect(payload.message).toContain('买菜清单:');
    expect(payload.message).not.toContain('#饮食打卡');
  });
});
