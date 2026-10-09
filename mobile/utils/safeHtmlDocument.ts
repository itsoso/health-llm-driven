/** Closed static-document grammar. Text data only, never HTML execution. */
export type SafeHtmlDocumentBlock = { kind: 'heading' | 'paragraph' | 'list'; text: string; marker?: string; depth?: number };
export type SafeHtmlDocument = { blocks: SafeHtmlDocumentBlock[] };
const LAYOUT = new Set(['div', 'section', 'article', 'main', 'header', 'footer', 'aside', 'blockquote']);
const INLINE = new Set(['span', 'strong', 'b', 'em', 'i', 'small', 'code']);
const HEADINGS = new Set(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']);
const ENTITIES: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00a0' };
function decode(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#[0-9]+|amp|lt|gt|quot|apos|nbsp);/gi, (raw, entity: string) => {
    if (!entity.startsWith('#')) return ENTITIES[entity.toLowerCase()] ?? raw;
    const hex = entity[1].toLowerCase() === 'x';
    const scalar = Number.parseInt(entity.slice(hex ? 2 : 1), hex ? 16 : 10);
    return scalar > 0 && scalar <= 0x10ffff && !(scalar >= 0xd800 && scalar <= 0xdfff) ? String.fromCodePoint(scalar) : raw;
  });
}
function attributes(raw: string, allowed: Set<string>): boolean {
  const pattern = /\s+([a-z][a-z0-9-]*)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+)/iy;
  const seen = new Set<string>();
  let pos = 0;
  while (raw.slice(pos).trim()) {
    pattern.lastIndex = pos;
    const match = pattern.exec(raw);
    if (!match) return false;
    const key = match[1].toLowerCase();
    if (!allowed.has(key) || seen.has(key)) return false;
    seen.add(key); pos = pattern.lastIndex;
  }
  return true;
}
const PRESENTATION = new Set(['class', 'id', 'style']);

export function parseSafeHtmlDocument(source: string): SafeHtmlDocument | null {
  if (source.length > 32000) return null;
  const lines = source.split(/\r?\n/);
  const opening = /^ {0,3}(`{3,}|~{3,})[ \t]*(?:html|htm)[ \t]*$/i.exec(lines[0]);
  if (!opening) return null;
  if (lines[lines.length - 1] === '') lines.pop();
  const closing = new RegExp(`^ {0,3}${opening[1][0]}{${opening[1].length},}[ \\t]*$`);
  if (lines.length < 3 || !closing.test(lines[lines.length - 1]) || lines.slice(1, -1).some(line => closing.test(line))) return null;
  const html = lines.slice(1, -1).join('\n');
  const document = /^\s*(?:<!doctype\s+html>\s*)?<html\b([^>]*)>\s*<head\b([^>]*)>([\s\S]*?)<\/head>\s*<body\b([^>]*)>([\s\S]*?)<\/body>\s*<\/html>\s*$/i.exec(html);
  if (!document || !attributes(document[1], new Set(['lang', 'dir'])) || !attributes(document[2], new Set()) || !attributes(document[4], PRESENTATION)) return null;
  // Metadata is validated but never exposed as styles, links or native props.
  const head = document[3];
  const headTokens = /\s+|<title>([^<]*)<\/title>|<style\b([^>]*)>([^<]*)<\/style>|<meta\b([^>]*)>/giy;
  let pos = 0;
  while (pos < head.length) {
    headTokens.lastIndex = pos;
    const token = headTokens.exec(head);
    if (!token) return null;
    if (token[2] !== undefined && !attributes(token[2], new Set(['type']))) return null;
    if (token[4] !== undefined && !attributes(token[4].replace(/\/\s*$/, ''), new Set(['charset', 'name', 'content']))) return null;
    pos = headTokens.lastIndex;
  }
  const body = document[5];
  const tokens = /<(?:[^>"']|"[^"]*"|'[^']*')*>|[^<]+/g;
  const stack: string[] = [];
  const lists: { ordered: boolean; count: number }[] = [];
  const items: { marker: string; depth: number; emitted: boolean }[] = [];
  const blocks: SafeHtmlDocumentBlock[] = [];
  let text = '', totalText = 0, tokenCount = 0;
  const flush = (preserveEmptyItem = false) => {
    const value = text.trim(); text = '';
    const item = items[items.length - 1];
    if (!value && !(preserveEmptyItem && item && !item.emitted)) return true;
    totalText += value.length;
    if (value.length > 4000 || totalText > 16000 || blocks.length >= 200) return false;
    if (item) {
      blocks.push({ kind: 'list', text: value, marker: item.emitted ? '' : item.marker, depth: item.depth });
      item.emitted = true;
    } else blocks.push({ kind: stack.some(tag => HEADINGS.has(tag)) ? 'heading' : 'paragraph', text: value });
    return true;
  };
  pos = 0;
  let match: RegExpExecArray | null;
  while ((match = tokens.exec(body))) {
    if (match.index !== pos || ++tokenCount > 4000) return null;
    pos = tokens.lastIndex;
    const token = match[0], parent = stack[stack.length - 1];
    if (!token.startsWith('<')) {
      if ((parent === 'ul' || parent === 'ol') && token.trim()) return null;
      text += decode(token.replace(/[ \t\r\n]+/g, ' '));
      if (text.length > 4000) return null;
      continue;
    }
    const tagMatch = /^<(\/)?([a-z][a-z0-9]*)([\s\S]*?)>$/i.exec(token);
    if (!tagMatch) return null;
    const tag = tagMatch[2].toLowerCase(), closingTag = !!tagMatch[1];
    const block = LAYOUT.has(tag) || HEADINGS.has(tag) || ['p', 'ul', 'ol', 'li'].includes(tag);
    if (!block && !INLINE.has(tag) && tag !== 'br' && tag !== 'hr') return null;
    if (closingTag) {
      if (tagMatch[3].trim() || parent !== tag || ((block || tag === 'hr') && !flush(tag === 'li'))) return null;
      stack.pop();
      if (tag === 'li') items.pop();
      if (tag === 'ul' || tag === 'ol') lists.pop();
      continue;
    }
    const selfClosing = /\/\s*$/.test(tagMatch[3]);
    if ((selfClosing && tag !== 'br' && tag !== 'hr') || !attributes(tagMatch[3].replace(/\/\s*$/, ''), PRESENTATION)) return null;
    if (block && (INLINE.has(parent) || parent === 'p' || HEADINGS.has(parent))) return null;
    if (tag === 'li' && parent !== 'ul' && parent !== 'ol') return null;
    if ((parent === 'ul' || parent === 'ol') && tag !== 'li') return null;
    if (tag === 'br') { text += '\n'; continue; }
    if ((block || tag === 'hr') && !flush(tag === 'ul' || tag === 'ol')) return null;
    if (tag === 'hr') continue;
    if (tag === 'ul' || tag === 'ol') lists.push({ ordered: tag === 'ol', count: 0 });
    if (tag === 'li') {
      const list = lists[lists.length - 1];
      list.count += 1;
      items.push({ marker: list.ordered ? `${list.count}.` : '•', depth: lists.length - 1, emitted: false });
    }
    stack.push(tag);
    if (stack.length > 24) return null;
  }
  return pos === body.length && !stack.length && flush() && blocks.length ? { blocks } : null;
}
