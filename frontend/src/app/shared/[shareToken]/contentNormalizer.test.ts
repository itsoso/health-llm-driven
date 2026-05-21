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
    const legacy = '根据你当前的身体状态，给你安排今天的锻炼： 📋 今日锻炼计划 恢复评估：优秀 ✅ HRV 63ms（较7日均值↑12%），身体电量100，压力11 🏋️ 推荐方案（约30分钟） 阶段 内容 时长 说明 热身 快走 + 关节活动 5min 把步数先拉到1000+ 主训练 瑜伽/拉伸 或 游泳 20min 低冲击，保护脊柱 放松 深呼吸 + 拉伸 5min 帮助HRV恢复 具体选项（二选一）： A. 居家方案（推荐） 🎯 今日步数目标 目前才238步，建议今天至少补到5000步。\n\n— 健康 Agent';

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
      '具体选项（二选一）： A. 居家方案（推荐）',
      '',
      '## 🎯 今日步数目标',
      '',
      '目前才238步，建议今天至少补到5000步。',
      '',
      '— 健康 Agent',
    ].join('\n'));
  });

  it('rebuilds flattened medical advice sections and supplement tables', () => {
    const legacy = '这个核酸检测结果非常关键！ 🔬 诊断：典型的"病毒搭台，细菌唱戏"混合感染 感染机制还原 人鼻病毒先入侵。 💊 治疗策略 抗生素（针对流感嗜血杆菌） ⚠️ 以下为医学常规方案科普。 🌿 补剂调整方案（感染期强化） 你目前的补剂清单很全面，感染期建议做以下调整： 补剂 建议 科学依据 甘氨酸锌 ✅ 继续，可短期加量 锌对鼻病毒有明确抑制作用 维生素 C ✅ 继续 支持免疫细胞功能 🗣️ 嗓子哑（急性喉炎）专项护理 绝对声带休息：尽量少说话。 🚀 怎么才能恢复得快？ 维度 具体行动 睡眠 保持 7.5-8.5h 饮水 目标 2000ml+ 饮食 清淡软食 运动 暂停中高强度训练 监测 发热需复诊 📋 行动清单 带报告复诊呼吸科：明确是否需要抗生素。 饮水打卡：现在开始记录饮水。 继续睡眠优势：保持高质量睡眠节奏。 需要我帮你记录今天的饮水吗？ — 健康 Agent';

    expect(normalizeSharedAgentContent(legacy)).toContain([
      '## 🔬 诊断：典型的"病毒搭台，细菌唱戏"混合感染',
      '',
      '感染机制还原 人鼻病毒先入侵。',
      '',
      '## 💊 治疗策略',
    ].join('\n'));
    expect(normalizeSharedAgentContent(legacy)).toContain([
      '你目前的补剂清单很全面，感染期建议做以下调整：',
      '',
      '| 补剂 | 建议 | 科学依据 |',
      '| --- | --- | --- |',
      '| 甘氨酸锌 | ✅ 继续，可短期加量 | 锌对鼻病毒有明确抑制作用 |',
      '| 维生素 C | ✅ 继续 | 支持免疫细胞功能 |',
    ].join('\n'));
    expect(normalizeSharedAgentContent(legacy)).toContain('## 🗣️ 嗓子哑（急性喉炎）专项护理');
    expect(normalizeSharedAgentContent(legacy)).toContain([
      '## 🚀 怎么才能恢复得快？',
      '',
      '| 维度 | 具体行动 |',
      '| --- | --- |',
      '| 睡眠 | 保持 7.5-8.5h |',
      '| 饮水 | 目标 2000ml+ |',
      '| 饮食 | 清淡软食 |',
      '| 运动 | 暂停中高强度训练 |',
      '| 监测 | 发热需复诊 |',
    ].join('\n'));
    expect(normalizeSharedAgentContent(legacy)).toContain([
      '## 📋 行动清单',
      '',
      '- 带报告复诊呼吸科：明确是否需要抗生素。',
      '- 饮水打卡：现在开始记录饮水。',
      '- 继续睡眠优势：保持高质量睡眠节奏。',
      '',
      '需要我帮你记录今天的饮水吗？',
      '',
      '— 健康 Agent',
    ].join('\n'));
  });
});
