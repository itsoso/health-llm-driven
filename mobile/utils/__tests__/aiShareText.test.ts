import { buildAiShareMessage } from '../aiShareText';

describe('buildAiShareMessage', () => {
  it('preserves markdown tables so the shared web page can render them', () => {
    const content = [
      '5月21日 健康简报',
      '',
      '| 指标 | 数值 | 状态 |',
      '| --- | --- | --- |',
      '| 睡眠 | 95分 | ✅ 优秀 |',
      '| 饮水 | 0ml/2000ml | ⚠️ 未达标 |',
    ].join('\n');

    expect(buildAiShareMessage(content)).toBe(`${content}\n\n— 健康 Agent`);
  });

  it('formats flattened workout plan tables before creating a share page', () => {
    const content = '根据你当前的身体状态，给你安排今天的锻炼： 📋 今日锻炼计划 恢复评估：优秀 ✅ HRV 63ms（较7日均值↑12%），身体电量100，压力11 🏋️ 推荐方案（约30分钟） 阶段 内容 时长 说明 热身 快走 + 关节活动 5min 把步数先拉到1000+ 主训练 瑜伽/拉伸 或 游泳 20min 低冲击，保护脊柱 放松 深呼吸 + 拉伸 5min 帮助HRV恢复 具体选项（二选一）： A. 居家方案（推荐） 🎯 今日步数目标 目前才238步，建议今天至少补到5000步。';

    expect(buildAiShareMessage(content)).toBe([
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
});
