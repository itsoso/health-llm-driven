import { describe, expect, it } from 'vitest';
import { statusStagePhrase } from '../statusStagePhrase';

describe('statusStagePhrase', () => {
  it('maps vision to 识别图片中', () => {
    expect(statusStagePhrase({ stage: 'vision' })).toBe('识别图片中');
    // detail 对 vision 不影响
    expect(statusStagePhrase({ stage: 'vision', detail: '忽略' })).toBe('识别图片中');
  });

  it('maps thinking without detail to default phrase', () => {
    expect(statusStagePhrase({ stage: 'thinking' })).toBe('阿衡正在思考');
    expect(statusStagePhrase({ stage: 'thinking', detail: null })).toBe('阿衡正在思考');
    expect(statusStagePhrase({ stage: 'thinking', detail: '   ' })).toBe('阿衡正在思考');
  });

  it('maps thinking with detail to the detail verbatim', () => {
    expect(
      statusStagePhrase({ stage: 'thinking', detail: '该模型整段生成，需等待完整回答' }),
    ).toBe('该模型整段生成，需等待完整回答');
  });

  it('maps tool to 正在${detail} when detail present, else fallback', () => {
    expect(statusStagePhrase({ stage: 'tool', detail: '查询睡眠数据' })).toBe('正在查询睡眠数据');
    expect(statusStagePhrase({ stage: 'tool' })).toBe('调用工具中');
    expect(statusStagePhrase({ stage: 'tool', detail: '' })).toBe('调用工具中');
  });

  it('maps synthesis to 整理回复中', () => {
    expect(statusStagePhrase({ stage: 'synthesis' })).toBe('整理回复中');
  });

  it('returns null for unknown / missing stage (safely ignored)', () => {
    expect(statusStagePhrase({ stage: 'nope' })).toBeNull();
    expect(statusStagePhrase({})).toBeNull();
    expect(statusStagePhrase(null)).toBeNull();
    expect(statusStagePhrase(undefined)).toBeNull();
  });

  it('trims surrounding whitespace in detail', () => {
    expect(statusStagePhrase({ stage: 'tool', detail: '  分析趋势  ' })).toBe('正在分析趋势');
  });
});
