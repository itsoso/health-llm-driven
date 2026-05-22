import { formatOpenerText, formatQuickReplyLabel } from '../OpenerCard';

describe('OpenerCard formatting', () => {
  it('hides raw metric keys in opener copy', () => {
    expect(formatOpenerText('今天就是「[spo2_avg] 血氧饱和度偏低：91.0%（阈值 95%），请注意」的检验日，做到了吗？'))
      .toBe('今天就是「血氧饱和度偏低：91.0%（阈值 95%），请注意」的检验日，做到了吗？');
  });

  it('uses calm action labels for quick replies', () => {
    expect(formatQuickReplyLabel('做到了 ✅')).toBe('完成了');
    expect(formatQuickReplyLabel('没做 ❌')).toBe('未完成');
    expect(formatQuickReplyLabel('调整下计划')).toBe('调整计划');
  });
});
