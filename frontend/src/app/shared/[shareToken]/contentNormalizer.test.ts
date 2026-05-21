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

  it('rebuilds legacy flattened workout plan tables into markdown', () => {
    const legacy = '根据你当前的身体状态，给你安排今天的锻炼： 📋 今日锻炼计划 恢复评估：优秀 ✅ HRV 63ms（较7日均值↑12%），身体电量100，压力11 🏋️ 推荐方案（约30分钟） 阶段 内容 时长 说明 热身 快走 + 关节活动 5min 把步数先拉到1000+ 主训练 瑜伽/拉伸 或 游泳 20min 低冲击，保护脊柱 放松 深呼吸 + 拉伸 5min 帮助HRV恢复 🎯 今日步数目标 目前才238步，建议今天至少补到5000步。\n\n— 健康 Agent';

    expect(normalizeSharedAgentContent(legacy)).toBe([
      '根据你当前的身体状态，给你安排今天的锻炼：',
      '',
      '## 📋 今日锻炼计划',
      '',
      '恢复评估：优秀 ✅ HRV 63ms（较7日均值↑12%），身体电量100，压力11',
      '',
      '## 🏋️ 推荐方案（约30分钟）',
      '',
      '| 阶段 | 内容 | 时长 | 说明 |',
      '| --- | --- | --- | --- |',
      '| 热身 | 快走 + 关节活动 | 5min | 把步数先拉到1000+ |',
      '| 主训练 | 瑜伽/拉伸 或 游泳 | 20min | 低冲击，保护脊柱 |',
      '| 放松 | 深呼吸 + 拉伸 | 5min | 帮助HRV恢复 |',
      '',
      '## 🎯 今日步数目标',
      '',
      '目前才238步，建议今天至少补到5000步。',
      '',
      '— 健康 Agent',
    ].join('\n'));
  });
});
