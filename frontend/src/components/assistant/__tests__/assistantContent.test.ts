import { describe, expect, it } from 'vitest';
import {
  preprocessAssistantContent,
  stripInternalMarkers,
} from '../assistantContent';

describe('stripInternalMarkers', () => {
  it('strips [claim:xxx] markers and leading whitespace', () => {
    const out = stripInternalMarkers('训练后补蛋白很重要。 [claim:c_protein_target_training_boundary]');
    expect(out).toBe('训练后补蛋白很重要。');
    expect(out).not.toContain('claim');
  });

  it('strips bare claim:xxx without brackets', () => {
    const out = stripInternalMarkers('结论如上 claim:c_foo_bar');
    expect(out).not.toContain('claim');
  });

  it('strips multiple claim markers', () => {
    const out = stripInternalMarkers('A [claim:c_a] 中间 B [claim:c_b]');
    expect(out).not.toContain('claim');
    expect(out).toContain('A');
    expect(out).toContain('B');
  });

  it('strips [工具调用: ...] chinese tool markers', () => {
    const out = stripInternalMarkers('先看数据[工具调用: health_query(days=7)]再分析');
    expect(out).toBe('先看数据再分析');
  });

  it('leaves normal content untouched', () => {
    const text = '你好，这是一段正常回答。\n第二行。';
    expect(stripInternalMarkers(text)).toBe(text);
  });
});

describe('preprocessAssistantContent — meal plan extraction', () => {
  const mealJson = JSON.stringify({
    title: '户外日午餐',
    reason: '今天训练量大，需要补碳水和蛋白。',
    items: [
      { name: '鸡胸肉', qty: '150g', kcal: 165, protein: 31 },
      { name: '糙米饭', qty: '1碗', kcal: 220 },
    ],
    totals: { kcal: 520, protein: 38, carbs: 55, fat: 12 },
    shopping_list: ['鸡胸肉 150g', '糙米 100g'],
  });

  it('extracts a fenced meal plan into mealPlan and removes it from text', () => {
    const content = `给你安排一下：\n\`\`\`json\n${mealJson}\n\`\`\`\n照这个吃。`;
    const { text, mealPlan } = preprocessAssistantContent(content);
    expect(mealPlan).not.toBeNull();
    expect(mealPlan?.title).toBe('户外日午餐');
    expect(mealPlan?.items).toHaveLength(2);
    expect(mealPlan?.shopping_list).toEqual(['鸡胸肉 150g', '糙米 100g']);
    expect(text).not.toContain('shopping_list');
    expect(text).toContain('给你安排一下');
    expect(text).toContain('照这个吃');
  });

  it('extracts a bare (unfenced) meal plan JSON', () => {
    const content = `这是你的午餐方案 ${mealJson}`;
    const { text, mealPlan } = preprocessAssistantContent(content);
    expect(mealPlan?.title).toBe('户外日午餐');
    expect(text).not.toContain('{');
    expect(text).toContain('这是你的午餐方案');
  });

  it('strips claim marker that trails the meal plan', () => {
    const content = `${mealJson}\n[claim:c_protein_target_training_boundary]`;
    const { text, mealPlan } = preprocessAssistantContent(content);
    expect(mealPlan?.title).toBe('户外日午餐');
    expect(text).not.toContain('claim');
  });
});

describe('preprocessAssistantContent — non-meal-plan JSON', () => {
  it('pretty-prints a bare unrecognized JSON object into a json code fence', () => {
    const content = 'debug: {"foo":1,"bar":[1,2,3]}';
    const { text, mealPlan } = preprocessAssistantContent(content);
    expect(mealPlan).toBeNull();
    expect(text).toContain('```json');
    // pretty-printed → multi-line with indentation
    expect(text).toMatch(/"foo": 1/);
    expect(text).toMatch(/"bar": \[/);
  });

  it('leaves already-fenced non-meal JSON as-is', () => {
    const content = '看这个:\n```json\n{"foo":1}\n```';
    const { text, mealPlan } = preprocessAssistantContent(content);
    expect(mealPlan).toBeNull();
    // 不重复包裹
    expect(text.match(/```json/g) || []).toHaveLength(1);
  });

  it('handles plain prose with no JSON', () => {
    const content = '今天睡眠不错，HRV 偏高，建议保持。';
    const { text, mealPlan } = preprocessAssistantContent(content);
    expect(mealPlan).toBeNull();
    expect(text).toBe(content);
  });

  it('does not treat a JSON object missing items as a meal plan', () => {
    const content = '{"title":"只是标题","foo":"bar"}';
    const { mealPlan } = preprocessAssistantContent(content);
    expect(mealPlan).toBeNull();
  });
});

describe('preprocessAssistantContent — reva-ui GenUI fences pass through intact', () => {
  // 回归护栏: reva-ui 围栏里的 JSON 不能被当成"裸吐 JSON"pretty 成 ```json,
  // 否则 MarkdownRenderer 抽卡片直接崩 (charts/metric_table 在真实 ChatView 路径全废)。
  it('leaves a metric_table reva-ui block untouched (not rewritten as ```json)', () => {
    const table = '{"type":"metric_table","v":1,"title":"近3天","columns":[{"key":"m","label":"指标"}],"rows":[{"m":"睡眠"}]}';
    const content = `这是你的概览:\n\n\`\`\`reva-ui\n${table}\n\`\`\``;
    const { text, mealPlan } = preprocessAssistantContent(content);
    expect(mealPlan).toBeNull();
    expect(text).toContain('```reva-ui');
    expect(text).toContain(table);
    expect(text).not.toContain('```json');
  });

  it('leaves a metric_line_chart reva-ui block untouched', () => {
    const chart = '{"v":1,"component":"metric_line_chart","x":["1","2"],"series":[{"name":"v","points":[5.8,8.3]}]}';
    const content = `睡眠趋势:\n\n\`\`\`reva-ui\n${chart}\n\`\`\``;
    const { text } = preprocessAssistantContent(content);
    expect(text).toContain('```reva-ui');
    expect(text).not.toContain('```json');
  });

  it('still extracts a real meal plan that sits alongside a reva-ui block', () => {
    const chart = '{"v":1,"component":"metric_line_chart","x":["1"],"series":[{"name":"v","points":[1]}]}';
    const meal = JSON.stringify({ title: '午餐', items: [{ name: '鸡胸肉' }] });
    const content = `\`\`\`reva-ui\n${chart}\n\`\`\`\n\n${meal}`;
    const { text, mealPlan } = preprocessAssistantContent(content);
    expect(mealPlan?.title).toBe('午餐');
    expect(text).toContain('```reva-ui'); // 图表围栏保留
    expect(text).not.toContain('鸡胸肉'); // meal plan 已抽走
  });
});
