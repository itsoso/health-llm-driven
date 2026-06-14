import { describe, expect, it } from 'vitest';
import { hasToolCall, parseToolCalls, toolCallLabel } from '../toolCallParse';

describe('parseToolCalls', () => {
  it('splits a single tool_call out of surrounding text', () => {
    const segs = parseToolCalls(
      '让我查一下你的化验。[tool_call: health_query(type=lab_results, days=7)]结果如下:',
    );
    expect(segs).toEqual([
      { kind: 'text', text: '让我查一下你的化验。' },
      { kind: 'tool_call', name: 'health_query' },
      { kind: 'text', text: '结果如下:' },
    ]);
  });

  it('matches the alt arg style and chinese variant', () => {
    expect(parseToolCalls('[tool_call: health_query(query_type=lab_results, time_range=14d)]')).toEqual([
      { kind: 'tool_call', name: 'health_query' },
    ]);
    expect(parseToolCalls('[工具调用: health_analysis(foo=bar)]')).toEqual([
      { kind: 'tool_call', name: 'health_analysis' },
    ]);
    expect(parseToolCalls('[调用工具：health_record]')).toEqual([
      { kind: 'tool_call', name: 'health_record' },
    ]);
  });

  it('handles consecutive tool calls', () => {
    const segs = parseToolCalls('[tool_call: health_query()] [tool_call: health_analysis()]');
    const calls = segs.filter(s => s.kind === 'tool_call');
    expect(calls).toHaveLength(2);
  });

  it('returns plain text untouched when no tool call present', () => {
    expect(parseToolCalls('你的睡眠还不错。')).toEqual([{ kind: 'text', text: '你的睡眠还不错。' }]);
    expect(hasToolCall('你的睡眠还不错。')).toBe(false);
    expect(hasToolCall('[tool_call: health_query()]')).toBe(true);
  });

  it('does not leak raw args/JSON into any segment text', () => {
    const segs = parseToolCalls('前[tool_call: health_query(type=lab_results, days=7)]后');
    const textBlob = segs.filter(s => s.kind === 'text').map(s => (s as any).text).join('');
    expect(textBlob).toBe('前后');
    expect(textBlob).not.toContain('lab_results');
    expect(textBlob).not.toContain('days');
  });
});

describe('toolCallLabel', () => {
  it('maps known tools to chinese action words', () => {
    expect(toolCallLabel('health_query')).toBe('查询健康数据');
    expect(toolCallLabel('health_record')).toBe('记录健康数据');
    expect(toolCallLabel('health_analysis')).toBe('分析健康数据');
    expect(toolCallLabel('health_manage')).toBe('管理健康计划');
  });

  it('falls back gracefully for unknown tools', () => {
    expect(toolCallLabel('totally_unknown')).toBe('调用工具');
    expect(toolCallLabel('')).toBe('调用工具');
    expect(toolCallLabel('health_brandnew')).toBe('调用健康工具');
  });
});
