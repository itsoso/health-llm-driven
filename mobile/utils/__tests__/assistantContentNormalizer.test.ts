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

  it('replaces a raw function-parameter tool protocol reply with a safe retry message', () => {
    const result = normalizeAssistantContent([
      '<tool_call>',
      '<function=health_record>',
      '<parameter=record_type>event</parameter>',
      '<parameter=data>{"title":"测试行程","location":"测试地点"}</parameter>',
      '</function>',
      '</tool_call>',
    ].join('\n'));

    expect(result.text).toBe('这条回复未能正常完成，请重新发送。');
    expect(result.text).not.toMatch(/tool_call|health_record|parameter/i);
    expect(result.cards).toEqual([]);
    expect(result.qualityFlags).toContain('raw_tool_protocol_removed');
  });

  it('preserves a function-parameter tool protocol shown inside a code example', () => {
    const markdown = [
      '示例：',
      '```xml',
      '<tool_call><function=health_query></function></tool_call>',
      '```',
    ].join('\n');

    expect(normalizeAssistantContent(markdown).text).toBe(markdown);
  });

  it('removes every consecutive raw tool protocol block', () => {
    const block = [
      '<tool_call>',
      '<function=health_record>',
      '<parameter=record_type>event</parameter>',
      '<parameter=data>{"title":"测试行程"}</parameter>',
      '</function>',
      '</tool_call>',
    ].join('\n');

    const result = normalizeAssistantContent(`${block}\n${block}`);

    expect(result.text).toBe('这条回复未能正常完成，请重新发送。');
    expect(result.text).not.toMatch(/tool_call|health_record|parameter/i);
  });

  it.each([
    '<function=',
    '<tool_call><function=',
    '<function=health_record',
    '<tool_call><function=health_record',
  ])('fails closed for a truncated raw protocol prefix: %s', (protocol) => {
    const result = normalizeAssistantContent(protocol);

    expect(result.text).toBe('这条回复未能正常完成，请重新发送。');
    expect(result.text).not.toMatch(/tool_call|health_record|function/i);
    expect(result.qualityFlags).toContain('raw_tool_protocol_removed');
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
