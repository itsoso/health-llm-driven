/**
 * Markdown 转 HTML 解析器
 * 专为小程序 RichText 组件设计
 */

function processTable(html: string): string {
  const tableRegex = /\|(.+)\|\n\|[-:\| ]+\|\n((?:\|.+\|\n?)+)/g;

  return html.replace(tableRegex, (_match, headerRow, bodyRows) => {
    const headers = headerRow.split('|').map((h: string) => h.trim()).filter(Boolean);
    const headerHtml = headers.map((h: string) => `<view class="md-th"><text>${h}</text></view>`).join('');

    const rows = bodyRows.trim().split('\n');
    const bodyHtml = rows.map((row: string) => {
      const cells = row.split('|').map((c: string) => c.trim()).filter(Boolean);
      const cellsHtml = cells.map((c: string) => `<view class="md-td"><text>${c}</text></view>`).join('');
      return `<view class="md-tr">${cellsHtml}</view>`;
    }).join('');

    return `<view class="md-table"><view class="md-thead"><view class="md-tr">${headerHtml}</view></view><view class="md-tbody">${bodyHtml}</view></view>`;
  });
}

export function markdownToHtml(markdown: string): string {
  if (!markdown) return '';

  try {
    let html = markdown;

    // 代码块
    html = html.replace(/```[\s\S]*?```/g, (match) => {
      const code = match.slice(3, -3).replace(/^\w*\n?/, '');
      const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return `<view class="md-codeblock"><text class="md-code-text">${escaped}</text></view>`;
    });

    // 行内代码
    html = html.replace(/`([^`]+)`/g, (_, code) => {
      const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
      return `<text class="md-code">${escaped}</text>`;
    });

    // 标题
    html = html.replace(/^###### (.+)$/gm, '<view class="md-h6">$1</view>');
    html = html.replace(/^##### (.+)$/gm, '<view class="md-h5">$1</view>');
    html = html.replace(/^#### (.+)$/gm, '<view class="md-h4">$1</view>');
    html = html.replace(/^### (.+)$/gm, '<view class="md-h3">$1</view>');
    html = html.replace(/^## (.+)$/gm, '<view class="md-h2">$1</view>');
    html = html.replace(/^# (.+)$/gm, '<view class="md-h1">$1</view>');

    // 粗体和斜体
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<text class="md-strong"><text class="md-em">$1</text></text>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<text class="md-strong">$1</text>');
    html = html.replace(/\*(.+?)\*/g, '<text class="md-em">$1</text>');

    // 链接
    html = html.replace(/\[([^\]]+)\]\([^)]+\)/g, '<text class="md-link">$1</text>');

    // 分隔线
    html = html.replace(/^[-*_]{3,}$/gm, '<view class="md-hr"></view>');

    // 引用块
    html = html.replace(/^> (.+)$/gm, '<view class="md-blockquote"><view class="md-p">$1</view></view>');

    // 无序列表
    html = html.replace(/^[-*+] (.+)$/gm, '<view class="md-li"><text class="md-li-marker">•</text><text class="md-li-text">$1</text></view>');

    // 有序列表
    html = html.replace(/^\d+\. (.+)$/gm, (_, text) =>
      `<view class="md-li"><text class="md-li-marker">•</text><text class="md-li-text">${text}</text></view>`
    );

    // 表格
    html = processTable(html);

    // 段落处理
    const lines = html.split('\n');
    const processed: string[] = [];
    for (const rawLine of lines) {
      const line = rawLine.trim();
      if (!line) continue;
      if (line.startsWith('<view') || line.startsWith('<text') || line.startsWith('<image')) {
        processed.push(line);
      } else {
        processed.push(`<view class="md-p">${line}</view>`);
      }
    }

    return processed.join('').replace(/\n+/g, '');
  } catch (error) {
    console.error('[Markdown解析错误]', error);
    return `<view class="md-p">${markdown.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br/>')}</view>`;
  }
}
