import { buildAiShareMessage, buildXiaohongshuShareMessage } from '../aiShareText';

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

  it('turns a completed diet record into a detailed Xiaohongshu food diary', () => {
    const content = [
      '✅ 已记录午餐 — 煎牛肉能量碗 + 姜黄鲜柠维C茶，770 kcal（蛋白 30g / 碳水 70g / 脂肪 17g）',
      '晚餐建议：优先补 40g 蛋白，少油少刺激。',
    ].join('\n');

    expect(buildXiaohongshuShareMessage(content)).toBe([
      '今天的饮食打卡｜午餐 🍱',
      '',
      '不追求每餐都完美，先把真实吃下的东西记清楚。',
      '',
      '🥢 这一餐',
      '煎牛肉能量碗 + 姜黄鲜柠维C茶',
      '',
      '📊 营养估算',
      '热量 770 kcal',
      '蛋白质 30g ｜ 碳水 70g ｜ 脂肪 17g',
      '',
      '💡 下一餐怎么接',
      '晚餐优先补 40g 蛋白，少油少刺激。',
      '',
      '记录一餐，才更容易看见自己的饮食节奏。',
      '营养数据为估算值，实际会因食材、份量和烹饪方式变化。',
      '',
      '#健康饮食 #饮食记录 #一日三餐 #健康管理 #小巴',
    ].join('\n'));
  });

  it('turns an assistant suggestion into a concise Xiaohongshu caption', () => {
    const content = [
      '## 今日建议',
      '',
      '建议今晚 23:00 前睡觉，并在睡前 3 小时停止正餐。',
      '',
      '原因：最近 HRV 偏低，先把恢复放在第一位。',
    ].join('\n');

    expect(buildXiaohongshuShareMessage(content)).toBe([
      '小巴给我的今日建议',
      '',
      '建议今晚 23:00 前睡觉，并在睡前 3 小时停止正餐。',
      '原因：最近 HRV 偏低，先把恢复放在第一位。',
      '',
      '仅作健康管理参考，不替代医生诊疗。',
      '#健康管理 #生活方式改善 #小巴',
    ].join('\n'));
  });

  it('turns markdown-heavy replies into Xiaohongshu-ready plain text', () => {
    const content = [
      '## 今日复盘',
      '',
      '![餐食](file:///tmp/meal.jpg)',
      '',
      '| 指标 | 数值 | 状态 |',
      '| --- | --- | --- |',
      '| 蛋白 | 75g | 偏低 |',
      '| 热量 | 1676kcal | 达标 |',
      '',
      '```reva-ui',
      '{"component":"metric_line_chart","v":1}',
      '```',
      '',
      '- **下一步**：晚餐补 30g 蛋白。',
      '[查看详情](https://health.executor.life/shared/token)',
    ].join('\n');

    const caption = buildXiaohongshuShareMessage(content);

    expect(caption).toContain('今日复盘');
    expect(caption).toContain('蛋白：75g，偏低');
    expect(caption).toContain('热量：1676kcal，达标');
    expect(caption).toContain('下一步：晚餐补 30g 蛋白。');
    expect(caption).not.toContain('|');
    expect(caption).not.toContain('```');
    expect(caption).not.toContain('![');
    expect(caption).not.toContain('](');
    expect(caption).not.toContain('https://');
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
