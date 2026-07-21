// markdown-it 处理的是服务端和用户可控文本。关闭已知高复杂度规则，并在解析前设上限。
// 显式 Markdown 链接仍可用；只是纯文本 URL 不再自动 linkify。
// The maintained React Native renderer uses this namespaced markdown-it fork.
// Keep it as an explicit dependency so clean CI/OTA installs do not rely on a
// transitive package being hoisted into the application.
// @ts-ignore the runtime package does not bundle TypeScript declarations.
import MarkdownIt from '@rexovolt/markdown-it';

export const MAX_MARKDOWN_INPUT_LENGTH = 50_000;

export const safeMarkdownIt = MarkdownIt('default', {
  typographer: false,
  breaks: false,
  linkify: false,
  html: false,
});

export function prepareSafeMarkdown(value: string | null | undefined): string {
  const text = String(value ?? '');
  if (text.length <= MAX_MARKDOWN_INPUT_LENGTH) return text;
  return `${text.slice(0, MAX_MARKDOWN_INPUT_LENGTH)}\n\n> 内容过长，已截断显示`;
}
