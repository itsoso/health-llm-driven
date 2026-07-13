import {
  normalizeLooseMarkdown,
  preprocessMarkdownTables,
  containsMarkdownTable,
} from '../markdownTables';

// 一个 markdown 行是否能被解析器当成表格 / 标题 / 列表, 判据: 归一化后是否满足解析器的
// 结构要求 (ATX 标题 `#` 后要空格; 表头与 `|---|` 分隔要在两行)。这里直接对归一化输出
// 断言结构, 不拉起 react-native-markdown-display (它在 jest 里渲染成 <Text>)。
describe('normalizeLooseMarkdown (脏 markdown 规范化)', () => {
  it('adds a space after glued ATX headings (##标题 → ## 标题)', () => {
    expect(normalizeLooseMarkdown('##今日状态总览')).toBe('## 今日状态总览');
    expect(normalizeLooseMarkdown('###今日恢复方案')).toBe('### 今日恢复方案');
    expect(normalizeLooseMarkdown('#顶级标题')).toBe('# 顶级标题');
  });

  it('adds a space after headings glued to an ordered marker (###1. → ### 1.)', () => {
    expect(normalizeLooseMarkdown('###1. 早睡')).toBe('### 1. 早睡');
  });

  it('adds a space after glued ordered list markers (1.今天 → 1. 今天)', () => {
    expect(normalizeLooseMarkdown('1.今天走了 8000 步')).toBe('1. 今天走了 8000 步');
    expect(normalizeLooseMarkdown('  2.缩进项')).toBe('  2. 缩进项');
  });

  it('splits a header row glued to its separator with || into two lines', () => {
    expect(normalizeLooseMarkdown('| 指标 | 数值 | 状态 || --- | --- | --- |'))
      .toBe('| 指标 | 数值 | 状态 |\n| --- | --- | --- |');
    // 无内部空格的紧凑形态同样拆开。
    expect(normalizeLooseMarkdown('|指标|数值||---|---|'))
      .toBe('|指标|数值|\n|---|---|');
  });

  it('leaves already-valid markdown untouched (no double spaces, no false splits)', () => {
    expect(normalizeLooseMarkdown('## 已有空格标题')).toBe('## 已有空格标题');
    expect(normalizeLooseMarkdown('### 已有空格')).toBe('### 已有空格');
    expect(normalizeLooseMarkdown('1. 已有空格列表')).toBe('1. 已有空格列表');
    // 普通表格 (两行) 不被误拆。
    expect(normalizeLooseMarkdown('| a | b |\n| --- | --- |'))
      .toBe('| a | b |\n| --- | --- |');
    // 行内的 # (非行首) 不当标题处理。
    expect(normalizeLooseMarkdown('正常段落 # 不是标题')).toBe('正常段落 # 不是标题');
  });
});

describe('preprocessMarkdownTables applies normalization before table degrade', () => {
  it('recovers a glued header+separator table into a parseable list block', () => {
    const dirty = '| 指标 | 数值 | 状态 || --- | --- | --- |\n| 睡眠 | 7h | 良好 |';
    const out = preprocessMarkdownTables(dirty);
    // 表格降级成列表 (pushListRows): 表头一行 + 每行一个 bullet。渲染器能解析。
    expect(out).toContain('**指标 · 数值 · 状态**');
    expect(out).toContain('- **睡眠** · 7h · 良好');
    // 原始黏连的分隔管道不再逐字出现在输出里。
    expect(out).not.toContain('|| ---');
  });

  it('normalizes glued headings so the done-render path never shows raw markers', () => {
    const dirty = '##今日状态总览\n\n你昨晚睡了 7 小时。\n\n###1. 早睡';
    const out = preprocessMarkdownTables(dirty);
    expect(out).toContain('## 今日状态总览');
    expect(out).toContain('### 1. 早睡');
    // 归一化后不残留无空格的黏连标题。
    expect(out).not.toMatch(/^##今日/m);
    expect(out).not.toMatch(/^###1\./m);
  });

  it('still detects the glued table as a table via containsMarkdownTable after normalization', () => {
    // containsMarkdownTable 在 ChatBubble 用于决定气泡是否加宽; 归一化拆行后应识别为表格。
    const dirty = '| 指标 | 数值 || --- | --- |\n| 睡眠 | 7h |';
    expect(containsMarkdownTable(normalizeLooseMarkdown(dirty))).toBe(true);
  });
});
