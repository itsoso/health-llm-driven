import {
  MAX_MARKDOWN_INPUT_LENGTH,
  prepareSafeMarkdown,
  safeMarkdownIt,
} from '../safeMarkdown';

describe('safeMarkdown', () => {
  it('disables expensive automatic link and smartquote scans', () => {
    expect(safeMarkdownIt.options.linkify).toBe(false);
    expect(safeMarkdownIt.options.typographer).toBe(false);
    expect(safeMarkdownIt.options.html).toBe(false);
  });

  it('bounds untrusted markdown before parsing', () => {
    const input = 'a'.repeat(MAX_MARKDOWN_INPUT_LENGTH + 500);
    const prepared = prepareSafeMarkdown(input);

    expect(prepared.length).toBeLessThan(input.length);
    expect(prepared).toContain('内容过长，已截断显示');
  });
});
