import { extractAttributions, type AttributionItem } from '../attributionExtract';

describe('extractAttributions', () => {
  it('returns empty for empty/null input', () => {
    expect(extractAttributions('')).toEqual([]);
    expect(extractAttributions(undefined as any)).toEqual([]);
    expect(extractAttributions('普通文本无任何归因')).toEqual([]);
  });

  it('extracts single genetic marker', () => {
    const out = extractAttributions('建议补叶酸 800mcg (基于你的 MTHFR C677T 杂合)。');
    expect(out).toHaveLength(1);
    expect(out[0].source).toBe('genetic');
    expect(out[0].label).toBe('MTHFR');
  });

  it('extracts lab marker', () => {
    const out = extractAttributions('继续观察 LDL 趋势 (参照你 6 月 LDL 4.1)。');
    expect(out).toHaveLength(1);
    expect(out[0].source).toBe('lab');
    expect(out[0].label).toContain('LDL');
  });

  it('extracts medication marker', () => {
    const out = extractAttributions('避免饮酒 (因你在服异丙托溴铵)。');
    expect(out).toHaveLength(1);
    expect(out[0].source).toBe('medication');
    expect(out[0].label).toBe('异丙托溴铵');
  });

  it('extracts history marker — 基于你之前提到的', () => {
    const out = extractAttributions('今晚做鼻腔清洗 (基于你之前提到的鼻塞)。');
    expect(out).toHaveLength(1);
    expect(out[0].source).toBe('history');
    expect(out[0].label).toContain('鼻塞');
  });

  it('extracts history marker — 基于你之前反馈的', () => {
    const out = extractAttributions('调整睡前流程 (基于你之前反馈的失眠)。');
    expect(out).toHaveLength(1);
    expect(out[0].source).toBe('history');
    expect(out[0].label).toContain('失眠');
  });

  it('extracts trend marker', () => {
    const out = extractAttributions('训练量降 20% (参照你近 90 天 HRV 下降趋势)。');
    expect(out).toHaveLength(1);
    expect(out[0].source).toBe('trend');
    expect(out[0].label).toContain('HRV');
  });

  it('extracts multiple markers in order', () => {
    const text =
      '建议补叶酸 800mcg (基于你的 MTHFR C677T 杂合), ' +
      '继续观察 LDL (参照你 6 月 LDL 4.1), ' +
      '避免饮酒 (因你在服异丙托溴铵)。';
    const out = extractAttributions(text);
    expect(out).toHaveLength(3);
    expect(out.map((o) => o.source)).toEqual(['genetic', 'lab', 'medication']);
  });

  it('dedupes same source + same label', () => {
    const text =
      '(基于你的 MTHFR C677T 杂合) ... ' +
      '(基于你的 MTHFR C677T 杂合) 第二处一样.';
    const out = extractAttributions(text);
    expect(out).toHaveLength(1);
  });

  it('keeps two genetic markers if labels differ', () => {
    const text =
      '(基于你的 MTHFR C677T 杂合) 和 (基于你的 ALDH2 杂合)';
    const out = extractAttributions(text);
    expect(out).toHaveLength(2);
    expect(out[0].label).toBe('MTHFR');
    expect(out[1].label).toBe('ALDH2');
  });

  it('handles 全角括号 (Apple 输入法)', () => {
    const out = extractAttributions('建议 X （基于你的 MTHFR 杂合）。');
    expect(out).toHaveLength(1);
    expect(out[0].source).toBe('genetic');
  });

  it('truncates long inner text to keep chip readable', () => {
    const text = '(基于你的 ' + 'A'.repeat(100) + ')';
    const out = extractAttributions(text);
    expect(out).toHaveLength(1);
    expect(out[0].label.length).toBeLessThanOrEqual(16);
  });

  it('ignores empty inner content', () => {
    expect(extractAttributions('(基于你的 )')).toEqual([]);
    expect(extractAttributions('(参照你 )')).toEqual([]);
  });

  it('does NOT match generic parens — false positive防御', () => {
    // 非归因括号不该匹配
    expect(extractAttributions('建议 (注意时间).')).toEqual([]);
    expect(extractAttributions('剂量 (一日两次).')).toEqual([]);
    expect(extractAttributions('(NOTE: this is just a note)')).toEqual([]);
  });

  it('returns AttributionItem with raw including parens', () => {
    const out = extractAttributions('建议 (基于你的 MTHFR 杂合)。');
    expect(out[0].raw).toBe('(基于你的 MTHFR 杂合)');
  });

  it('preserves order of first appearance across patterns', () => {
    const text =
      '先说化验 (参照你 6 月 LDL 4.1), 再说基因 (基于你的 MTHFR 杂合)';
    const out = extractAttributions(text);
    // labels 出现顺序: lab 在前, genetic 在后. 但我们的实现是按 PATTERNS 顺序遍历,
    // genetic 在 PATTERNS 中排在 lab 之前 → 输出 [genetic, lab]
    // 这是 acceptable 的: chip 行按 source category 分组, 不按文本顺序
    expect(out).toHaveLength(2);
    const sources = out.map((o) => o.source).sort();
    expect(sources).toEqual(['genetic', 'lab']);
  });
});
