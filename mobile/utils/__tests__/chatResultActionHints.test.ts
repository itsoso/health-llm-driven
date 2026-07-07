import { deriveChatResultActions } from '../chatResultActionHints';

function keys(text: string) {
  return deriveChatResultActions({ text }).map(action => action.key);
}

describe('deriveChatResultActions', () => {
  it('keeps generic explanations quiet with only follow-up available', () => {
    expect(keys('胆固醇是血脂的一类指标，LDL-C 升高通常代表心血管风险更高。')).toEqual([
      'followup',
    ]);
  });

  it('surfaces a plan action for concrete executable advice', () => {
    expect(keys('今日建议：晚饭后步行 10 分钟，23:00 前上床。')).toEqual([
      'plan',
      'followup',
    ]);
  });

  it('surfaces a record action when the assistant reply contains a deterministic record', () => {
    expect(keys('✅ 已记录午餐 — 鸡胸肉沙拉 + 米饭，约 620 kcal。')).toEqual([
      'record',
      'followup',
    ]);
  });

  it('surfaces memory for durable user preferences without forcing plan or record actions', () => {
    expect(keys('我记得你对乳糖比较敏感，后续我会优先避开牛奶类建议。')).toEqual([
      'memory',
      'followup',
    ]);
  });

  it('caps mixed suggestions to one primary action plus the most relevant secondary actions', () => {
    expect(keys('今日建议：餐后步行 10 分钟。我也记得你工作日晚餐经常偏晚。')).toEqual([
      'plan',
      'memory',
      'followup',
    ]);
  });
});
