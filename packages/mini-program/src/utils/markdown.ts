/**
 * Markdown 转 HTML 解析器
 * 专为小程序 RichText 组件设计
 * 注意：RichText 只支持标准 HTML 标签（div, span, p, h1-h6, table 等），
 * 不支持 Taro 的 view/text 标签
 */

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function processInline(text: string): string {
  // 粗体+斜体
  let result = text.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  // 粗体
  result = result.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // 斜体
  result = result.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // 行内代码
  result = result.replace(/`([^`]+)`/g, (_, code) => {
    return `<span class="md-code">${escapeHtml(code)}</span>`;
  });
  // 链接
  result = result.replace(/\[([^\]]+)\]\([^)]+\)/g, '<span class="md-link">$1</span>');
  return result;
}

export function markdownToHtml(markdown: string): string {
  if (!markdown) return '';

  try {
    const lines = markdown.split('\n');
    const output: string[] = [];
    let i = 0;

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      // 空行
      if (!trimmed) {
        i++;
        continue;
      }

      // 代码块
      if (trimmed.startsWith('```')) {
        const codeLines: string[] = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith('```')) {
          codeLines.push(lines[i]);
          i++;
        }
        i++; // skip closing ```
        const code = escapeHtml(codeLines.join('\n'));
        output.push(`<div class="md-codeblock"><span class="md-code-text">${code}</span></div>`);
        continue;
      }

      // 表格检测
      if (trimmed.includes('|') && i + 1 < lines.length && /^\|?[\s-:|]+\|?$/.test(lines[i + 1]?.trim())) {
        // 表头
        const headers = trimmed.split('|').map(h => h.trim()).filter(Boolean);
        const headerHtml = headers.map(h => `<th class="md-th">${processInline(h)}</th>`).join('');
        i += 2; // skip header + separator

        // 表体
        const rowsHtml: string[] = [];
        while (i < lines.length && lines[i].trim().includes('|')) {
          const cells = lines[i].trim().split('|').map(c => c.trim()).filter(Boolean);
          const cellsHtml = cells.map(c => `<td class="md-td">${processInline(c)}</td>`).join('');
          rowsHtml.push(`<tr class="md-tr">${cellsHtml}</tr>`);
          i++;
        }

        output.push(`<div class="md-table"><table><thead><tr class="md-tr">${headerHtml}</tr></thead><tbody>${rowsHtml.join('')}</tbody></table></div>`);
        continue;
      }

      // 标题
      const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (headingMatch) {
        const level = headingMatch[1].length;
        output.push(`<h${level} class="md-h${level}">${processInline(headingMatch[2])}</h${level}>`);
        i++;
        continue;
      }

      // 分隔线
      if (/^[-*_]{3,}$/.test(trimmed)) {
        output.push('<div class="md-hr"></div>');
        i++;
        continue;
      }

      // 引用块 - 收集连续引用行
      if (trimmed.startsWith('> ')) {
        const quoteLines: string[] = [];
        while (i < lines.length && lines[i].trim().startsWith('> ')) {
          quoteLines.push(lines[i].trim().substring(2));
          i++;
        }
        const quoteHtml = quoteLines.map(l => `<p class="md-p">${processInline(l)}</p>`).join('');
        output.push(`<div class="md-blockquote">${quoteHtml}</div>`);
        continue;
      }

      // 无序列表 - 收集连续列表项（支持缩进）
      const ulMatch = trimmed.match(/^[-*+]\s+(.+)$/);
      if (ulMatch) {
        const items: string[] = [];
        while (i < lines.length) {
          const itemLine = lines[i].trim();
          const m = itemLine.match(/^[-*+]\s+(.+)$/);
          if (m) {
            items.push(m[1]);
            i++;
          } else if (itemLine && !itemLine.match(/^\d+\.\s/) && !itemLine.startsWith('#') && !itemLine.startsWith('```') && !itemLine.startsWith('>')) {
            // 续行（属于上一个列表项）
            if (items.length > 0) {
              items[items.length - 1] += ' ' + itemLine;
            }
            i++;
          } else {
            break;
          }
        }
        const listHtml = items.map(item =>
          `<div class="md-li"><span class="md-li-marker">•</span><span class="md-li-text">${processInline(item)}</span></div>`
        ).join('');
        output.push(`<div class="md-list">${listHtml}</div>`);
        continue;
      }

      // 有序列表
      const olMatch = trimmed.match(/^(\d+)\.\s+(.+)$/);
      if (olMatch) {
        const items: { num: string; text: string }[] = [];
        while (i < lines.length) {
          const itemLine = lines[i].trim();
          const m = itemLine.match(/^(\d+)\.\s+(.+)$/);
          if (m) {
            items.push({ num: m[1], text: m[2] });
            i++;
          } else if (itemLine && !itemLine.match(/^[-*+]\s/) && !itemLine.startsWith('#') && !itemLine.startsWith('```') && !itemLine.startsWith('>')) {
            if (items.length > 0) {
              items[items.length - 1].text += ' ' + itemLine;
            }
            i++;
          } else {
            break;
          }
        }
        const listHtml = items.map(item =>
          `<div class="md-li"><span class="md-li-marker">${item.num}.</span><span class="md-li-text">${processInline(item.text)}</span></div>`
        ).join('');
        output.push(`<div class="md-list">${listHtml}</div>`);
        continue;
      }

      // 普通段落
      output.push(`<p class="md-p">${processInline(trimmed)}</p>`);
      i++;
    }

    return output.join('');
  } catch (error) {
    console.error('[Markdown解析错误]', error);
    return `<p class="md-p">${markdown.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br/>')}</p>`;
  }
}
