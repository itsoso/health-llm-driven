import { normalizeAssistantContent } from '../assistantContentNormalizer';

describe('normalizeAssistantContent', () => {
  it.each(['<br>', '<br/>', '<br />', '<BR />'])(
    'converts %s into a markdown-safe newline',
    (breakTag) => {
      const result = normalizeAssistantContent(`第一段${breakTag}第二段`);

      expect(result.text).toBe('第一段\n第二段');
      expect(result.text).not.toMatch(/<br\s*\/?>/i);
      expect(result.qualityFlags).toContain('html_break_normalized');
    },
  );

  it('removes a bounded flood of isolated placeholder punctuation without deleting ordinary punctuation', () => {
    const result = normalizeAssistantContent([
      '结论。',
      '.',
      '.',
      '.',
      '.',
      '.',
      '.',
      '.',
      '下一步：继续观察。',
      '.',
    ].join('\n'));

    expect(result.text).toBe('结论。\n下一步：继续观察。\n.');
    expect(result.qualityFlags).toContain('placeholder_flood_removed');
  });

  it('extracts supported reva-ui blocks and never exposes their protocol JSON', () => {
    const result = normalizeAssistantContent([
      '近 7 天趋势如下。',
      '```reva-ui',
      JSON.stringify({
        type: 'metric_table',
        v: 1,
        title: '睡眠',
        columns: [{ key: 'date', label: '日期' }, { key: 'value', label: '时长' }],
        rows: [{ date: '昨晚', value: '7.5h' }],
      }),
      '```',
    ].join('\n'));

    expect(result.text).toBe('近 7 天趋势如下。');
    expect(result.text).not.toContain('metric_table');
    expect(result.cards).toHaveLength(1);
    expect(result.cards[0].type).toBe('metric_table');
  });

  it('replaces malformed and unsupported reva-ui blocks with a readable fallback', () => {
    const result = normalizeAssistantContent([
      '```reva-ui',
      '{"v":2,"component":"unknown","private":"must-not-leak"}',
      '```',
    ].join('\n'));

    expect(result.text).toBe('这张动态卡片暂时无法显示，请让小巴用文字说明。');
    expect(result.text).not.toContain('must-not-leak');
    expect(result.cards).toEqual([]);
    expect(result.qualityFlags).toContain('malformed_protocol_block');
  });

  it('bounds oversized answers and reports a quality flag', () => {
    const result = normalizeAssistantContent('a'.repeat(60_000));

    expect(result.text.length).toBeLessThanOrEqual(50_000);
    expect(result.text).toContain('内容过长，已截断显示');
    expect(result.qualityFlags).toContain('display_length_truncated');
  });

  it('preserves valid Markdown byte-for-byte when no normalization is needed', () => {
    const markdown = '## 睡眠分析\n\n- 时长：7.5 小时\n- **结论**：保持规律作息。';

    expect(normalizeAssistantContent(markdown)).toEqual({
      text: markdown,
      cards: [],
      qualityFlags: [],
    });
  });

  it('returns an empty safe surface for empty input', () => {
    expect(normalizeAssistantContent('')).toEqual({
      text: '',
      cards: [],
      qualityFlags: ['empty_content'],
    });
  });
});
