import { mergeModelIntoExtraContext } from '../chatExtraContext';

describe('mergeModelIntoExtraContext', () => {
  it('无模型选择时原样透传(undefined / 已有 context 都不动)', () => {
    expect(mergeModelIntoExtraContext(undefined, null)).toBeUndefined();
    expect(mergeModelIntoExtraContext(undefined, undefined)).toBeUndefined();
    const ctx = JSON.stringify({ source: 'opener' });
    expect(mergeModelIntoExtraContext(ctx, null)).toBe(ctx);
    expect(mergeModelIntoExtraContext(ctx, '  ')).toBe(ctx);
  });

  it('无已有 context 时生成只含 model_id 的 JSON', () => {
    const out = mergeModelIntoExtraContext(undefined, 'qwen3.7-max');
    expect(JSON.parse(out!)).toEqual({ model_id: 'qwen3.7-max' });
  });

  it('已有 JSON 对象时合并 model_id 且不丢原字段(Siri/opener 上下文不被覆盖)', () => {
    const ctx = JSON.stringify({ source: 'siri', opener_id: 42 });
    const out = mergeModelIntoExtraContext(ctx, 'qwen3.7-max');
    expect(JSON.parse(out!)).toEqual({ source: 'siri', opener_id: 42, model_id: 'qwen3.7-max' });
  });

  it('调用方已带 model_id 时不覆盖(更具体的意图优先)', () => {
    const ctx = JSON.stringify({ model_id: 'deepseek-v4-pro' });
    expect(mergeModelIntoExtraContext(ctx, 'qwen3.7-max')).toBe(ctx);
  });

  it('非 JSON 字符串保持原样(不包一层破坏既有消费方)', () => {
    expect(mergeModelIntoExtraContext('今天的开场白上下文', 'qwen3.7-max')).toBe('今天的开场白上下文');
  });

  it('JSON 数组/标量保持原样', () => {
    expect(mergeModelIntoExtraContext('[1,2]', 'qwen3.7-max')).toBe('[1,2]');
    expect(mergeModelIntoExtraContext('"str"', 'qwen3.7-max')).toBe('"str"');
  });
});
