import { describe, expect, it } from 'vitest';
import { statusStagePhrase } from '../statusStagePhrase';

describe('statusStagePhrase', () => {
  it('maps vision to 识别图片中', () => {
    expect(statusStagePhrase({ stage: 'vision' })).toBe('识别图片中');
    // detail 对 vision 不影响
    expect(statusStagePhrase({ stage: 'vision', detail: '忽略' })).toBe('识别图片中');
  });

  it('maps thinking without detail to default phrase', () => {
    expect(statusStagePhrase({ stage: 'thinking' })).toBe('小巴正在思考');
    expect(statusStagePhrase({ stage: 'thinking', detail: null })).toBe('小巴正在思考');
    expect(statusStagePhrase({ stage: 'thinking', detail: '   ' })).toBe('小巴正在思考');
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

  // ──── P0-1 flat progress family (accepted / tool label / synthesis) ────

  it('maps accepted to the received-and-preparing phrase', () => {
    expect(statusStagePhrase({ stage: 'accepted' })).toBe('已收到，正在准备…');
    expect(statusStagePhrase({
      stage: 'accepted',
      label: '我先读取睡眠和恢复数据，再判断今天适合的运动强度。',
    })).toBe('我先读取睡眠和恢复数据，再判断今天适合的运动强度。');
  });

  it('maps tool label (progress family) verbatim, taking priority over detail', () => {
    // 新进度家族的 label 已是完整人话 → 原样显示 (不加"正在"前缀)。
    expect(statusStagePhrase({ stage: 'tool', label: '查看健康数据…' })).toBe('查看健康数据…');
    expect(statusStagePhrase({ stage: 'tool', round: 1, label: '正在记录…' })).toBe('正在记录…');
    // label 优先于 detail。
    expect(statusStagePhrase({ stage: 'tool', label: '联网搜索中…', detail: 'ignored' })).toBe(
      '联网搜索中…',
    );
    // label 空白 → 回退旧 detail 行为。
    expect(statusStagePhrase({ stage: 'tool', label: '   ', detail: '查询睡眠数据' })).toBe(
      '正在查询睡眠数据',
    );
  });

  it('maps synthesis from the flat progress family too', () => {
    expect(statusStagePhrase({ stage: 'synthesis', round: null })).toBe('整理回复中');
  });
});
