import { describe, expect, it } from 'vitest';
import { normalizeSharedAgentContent } from './contentNormalizer';

describe('normalizeSharedAgentContent', () => {
  it('rebuilds legacy flattened health briefing metrics into a markdown table', () => {
    const legacy = '🌅 5月21日 健康简报 综合评分：59/100 指标 数值 状态 睡眠 95分 ✅ 优秀 HRV 63.0ms 较7日均值↑12% ✅ 步数 238 ⚠️ 2% 压力 11 ✅ 正常 身体电量 峰值100 ✅ 充沛 饮水 0ml/2000ml ⚠️ 0% 📌 今日建议： 饮水未达标，上午补充500ml\n\n— 健康 Agent';

    expect(normalizeSharedAgentContent(legacy)).toBe([
      '🌅 5月21日 健康简报',
      '综合评分：59/100',
      '',
      '| 指标 | 数值 | 状态 |',
      '| --- | --- | --- |',
      '| 睡眠 | 95分 | ✅ 优秀 |',
      '| HRV | 63.0ms 较7日均值↑12% | ✅ |',
      '| 步数 | 238 | ⚠️ 2% |',
      '| 压力 | 11 | ✅ 正常 |',
      '| 身体电量 | 峰值100 | ✅ 充沛 |',
      '| 饮水 | 0ml/2000ml | ⚠️ 0% |',
      '',
      '📌 今日建议：',
      '饮水未达标，上午补充500ml',
      '',
      '— 健康 Agent',
    ].join('\n'));
  });

  it('leaves existing markdown tables untouched', () => {
    const markdown = '| 指标 | 数值 | 状态 |\n| --- | --- | --- |\n| 睡眠 | 95分 | ✅ 优秀 |';

    expect(normalizeSharedAgentContent(markdown)).toBe(markdown);
  });
});
