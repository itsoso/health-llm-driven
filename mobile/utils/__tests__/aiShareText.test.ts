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

    expect(buildAiShareMessage(content)).toBe(`${content}\n\n— 小巴`);
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
      '— 小巴',
    ].join('\n'));
  });

  it('does not collapse ordinary markdown replies into one paragraph', () => {
    const content = [
      '## 🔬 诊断',
      '',
      '- 鼻病毒先入侵',
      '- 继发细菌感染风险升高',
      '',
      '## 💊 治疗策略',
      '',
      '请线下就医确认处方。',
    ].join('\n');

    expect(buildAiShareMessage(content)).toBe(`${content}\n\n— 小巴`);
  });

  it('turns a completed diet record reply into a polished WeChat/XHS-ready share note', () => {
    const content = [
      '✅ 已记录午餐 — 煎牛肉能量碗 + 姜黄鲜柠维C茶，770 kcal（蛋白 30g / 碳水 70g / 脂肪 17g）',
      '晚餐建议：优先补 40g 蛋白，少油少刺激。',
    ].join('\n');

    expect(buildAiShareMessage(content)).toBe([
      '今天这餐被小巴认真记下来了',
      '',
      '午餐 · 煎牛肉能量碗 + 姜黄鲜柠维C茶',
      '',
      '770 kcal · 蛋白 30g · 碳水 70g · 脂肪 17g',
      '',
      '下一步：晚餐优先补 40g 蛋白，少油少刺激。',
      '',
      '#饮食记录 #健康管理 #小巴',
      '',
      '— 小巴',
    ].join('\n'));
  });

  it('structures flattened advice with headings and action labels', () => {
    const content = '收到，立刻撤回"加量"建议！ 你的身体反馈是最准确的，20 分钟对你来说就是黄金安全区。 🛑 为什么上次"连跑三天挂了"？ 结合你的病史，原因很可能是： 免疫"开窗期"：连续跑步后，免疫系统会短暂下降。 累积疲劳：连续跑没有给关节和肌肉修复时间。 🛡️ 新策略：细水长流（保命版） 时长锁定：20 分钟，绝不贪多。 频率红线：跑一休一 或 跑二休一。 看灯行事：身体电量 < 50 或 HRV 不平衡就不跑。 跑后防护（关键）：出汗后立刻擦干。 总结：今天的 20 分钟非常完美。 💧 提醒：跑后记得补 300ml 水。';

    expect(buildAiShareMessage(content)).toBe([
      '收到，立刻撤回"加量"建议！ 你的身体反馈是最准确的，20 分钟对你来说就是黄金安全区。',
      '',
      '## 🛑 为什么上次"连跑三天挂了"？',
      '',
      '结合你的病史，原因很可能是：',
      '',
      '- 免疫"开窗期"：连续跑步后，免疫系统会短暂下降。',
      '',
      '- 累积疲劳：连续跑没有给关节和肌肉修复时间。',
      '',
      '## 🛡️ 新策略：细水长流（保命版）',
      '',
      '- 时长锁定：20 分钟，绝不贪多。',
      '',
      '- 频率红线：跑一休一 或 跑二休一。',
      '',
      '- 看灯行事：身体电量 < 50 或 HRV 不平衡就不跑。',
      '',
      '- 跑后防护（关键）：出汗后立刻擦干。',
      '',
      '**总结：** 今天的 20 分钟非常完美。',
      '',
      '## 💧 提醒：',
      '',
      '跑后记得补 300ml 水。',
      '',
      '— 小巴',
    ].join('\n'));
  });
});
