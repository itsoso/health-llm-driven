import { parseSafeHtmlTable, splitHtmlTableContent } from '../safeHtmlTable';
import { normalizeAssistantContent } from '../assistantContentNormalizer';

const table = '<table border="1" style="width:100%"><thead><tr><th>日期</th><th>睡眠</th></tr></thead><tbody><tr><td>周一</td><td>7小时10分</td></tr></tbody></table>';

describe('safe HTML table projection (never an HTML interpreter)', () => {
  it('projects the screenshot table, dropping presentation attributes', () => {
    expect(parseSafeHtmlTable(table)?.rows).toEqual([
      [{ text: '日期', header: true }, { text: '睡眠', header: true }],
      [{ text: '周一', header: false }, { text: '7小时10分', header: false }],
    ]);
  });
  it('preserves empty cells, pipes, entities and line breaks', () => {
    expect(parseSafeHtmlTable('<table><tr><td></td><td>A | B &amp; C<br>7&#x65F6; &lt;script&gt;</td></tr></table>')?.rows[0].map(c => c.text))
      .toEqual(['', 'A | B & C\n7时 <script>']);
  });
  it('keeps captions and inline text without interpreting markdown', () => {
    expect(parseSafeHtmlTable('<table><caption>本周 &nbsp; 睡眠</caption><tr><td><b>**7**</b> 小时</td></tr></table>'))
      .toEqual({ caption: '本周 \u00a0 睡眠', rows: [[{ text: '**7** 小时', header: false }]] });
  });
  it.each([
    '<table onclick="x()"><tr><td>7</td></tr></table>',
    '<table><tr><td colspan="2">7</td></tr></table>',
    '<table><tr><td><img src="https://invalid.test/a"></td></tr></table>',
    '<table><tr><td><script>alert(1)</script></td></tr></table>',
    '<table><tr><td><a href="javascript:alert(1)">7</a></td></tr></table>',
    '<table><tr><td data-action="confirm">7</td></tr></table>',
    '<table><tr><td><table><tr><td>7</td></tr></table></td></tr></table>',
    '<table><tr><td>7</tr></table>',
    '<table><tr><td>7</td></tr><tr><td>8</td><td>9</td></tr></table>',
    '<table><tr><td>7</td></tr></table><script>x()</script>',
    '<table>lost text<tr><td>7</td></tr></table>',
  ])('fails closed, keeping unsupported source: %s', html => {
    expect(parseSafeHtmlTable(html)).toBeNull();
  });
  it('never evaluates CSS, and decodes entities only once', () => {
    expect(parseSafeHtmlTable('<table style="background:url(https://invalid.test)"><tr><td>&amp;lt;img&amp;gt; &unknown; &#0;</td></tr></table>')?.rows[0][0].text)
      .toBe('&lt;img&gt; &unknown; &#0;');
    expect(parseSafeHtmlTable('<table><tr><td>&am<span>p;</span></td></tr></table>')?.rows[0][0].text).toBe('&amp;');
  });
  it('rejects over-budget tables instead of truncating data', () => {
    expect(parseSafeHtmlTable('<table>' + '<tr><td>x</td></tr>'.repeat(101) + '</table>')).toBeNull();
    expect(parseSafeHtmlTable('<table><tr>' + '<td>x</td>'.repeat(21) + '</tr></table>')).toBeNull();
    expect(parseSafeHtmlTable('<table><tr><td>' + 'x'.repeat(2001) + '</td></tr></table>')).toBeNull();
    expect(parseSafeHtmlTable(' '.repeat(32001) + table)).toBeNull();
    expect(parseSafeHtmlTable('<table><tr><td>' + '👩‍💻'.repeat(500) + '</td></tr></table>')).toBeNull();
    expect(parseSafeHtmlTable('<table><tr><td>' + '<span>'.repeat(40) + 'x' + '</span>'.repeat(40) + '</td></tr></table>')).toBeNull();
    expect(parseSafeHtmlTable('<table class="a" class="b"><tr><td>x</td></tr></table>')).toBeNull();
    expect(parseSafeHtmlTable('<table><caption>' + '<br>'.repeat(2001) + '</caption><tr><td>x</td></tr></table>')).toBeNull();
  });
});

describe('HTML table segmentation', () => {
  it('does not promote indented HTML code into a preview during cleanup', () => {
    const code = `    ${table}`;
    const normalized = normalizeAssistantContent(code);
    expect(normalized.text).toBe(code);
    expect(splitHtmlTableContent(normalized.text).some(part => part.kind === 'table')).toBe(false);
    for (const prefix of ['<function=read_data></function>', '<tool_call><function=read_data></function></tool_call>', '<function=a></function>\n<function=b></function>']) {
      const result = normalizeAssistantContent(`${prefix}\n${code}`);
      expect(result.text).toContain(`\n${code}`);
      expect(splitHtmlTableContent(result.text).some(part => part.kind === 'table')).toBe(false);
    }
  });
  it('keeps emoji-prefixed sibling protocol fences inert without swallowing the next table', () => {
    const source = '📋 ```menu_share\n{"title":"示例"}\n```\n' + table;
    expect(splitHtmlTableContent(source).filter(part => part.kind === 'table')).toHaveLength(1);
    expect(normalizeAssistantContent(source).cards).toEqual([]);
  });
  it('keeps separate prose action fences inert in HTML-bearing messages', () => {
    const actionSource = '```reva-ui\n{"v":1,"component":"diet_draft","actions":[{"id":"save","action":"diet_record.create","label":"保存"}]}\n```';
    const result = normalizeAssistantContent(`${table}\n\n${actionSource}`);
    expect(result.cards).toEqual([]);
    expect(result.text).toContain(actionSource);
    const prefixed = normalizeAssistantContent(`<function=read_data></function>\n${table}\n\n${actionSource}`);
    expect(prefixed.cards).toEqual([]);
    expect(prefixed.text).toContain(actionSource);
    expect(prefixed.text).not.toContain('<function=');
  });
  it('preserves mixed prose and supports fenced and raw tables', () => {
    const source = `前文\n\n\`\`\`HTML\n${table}\n\`\`\`\n后文\n${table}`;
    const parts = splitHtmlTableContent(source);
    expect(parts.filter(p => p.kind === 'table')).toHaveLength(2);
    expect(parts.map(p => p.source).join('')).toBe(source);
  });
  it('does not preview other languages, unclosed fences, or nested code samples', () => {
    for (const source of [`\`\`\`text\n${table}\n\`\`\``, `\`\`\`html\n${table}`, `\`\`\`\`md\n\`\`\`html\n${table}\n\`\`\`\n\`\`\`\``]) {
      expect(splitHtmlTableContent(source).some(p => p.kind === 'table')).toBe(false);
      expect(splitHtmlTableContent(source).map(p => p.source).join('')).toBe(source);
    }
  });
  it('supports tilde fences and preserves rejected HTML as literal source', () => {
    expect(splitHtmlTableContent(`~~~htm\n${table}\n~~~`)[0].kind).toBe('table');
    expect(splitHtmlTableContent('```html\n<script>x()</script>\n```')[0].kind).toBe('source');
  });
});
