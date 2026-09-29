/** A deliberately small, fail-closed table grammar, NOT an HTML sanitizer.
 * Output is text/booleans only. Never pass source or attributes to a WebView.
 * Keep the contract aligned with Mac SafeHTMLTable and the feature spec.
 */
export interface SafeHtmlTable {
  caption?: string;
  rows: { text: string; header: boolean }[][];
}
export type HtmlTablePart =
  | { kind: 'table'; source: string; table: SafeHtmlTable }
  | { kind: 'markdown' | 'code' | 'source'; source: string };

const PRESENTATION_ATTRIBUTES = new Set([
  'style', 'border', 'cellpadding', 'cellspacing', 'width', 'height', 'align', 'valign', 'class',
]);
const INLINE = new Set(['b', 'strong', 'i', 'em', 'span']);
const NAMED_ENTITIES: Record<string, string> = {
  amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00a0',
};

/** Broader than preview eligibility: cleanup must not promote indented/code HTML. */
export function containsHtmlTableCandidate(source: string): boolean {
  return /<table\b/i.test(source)
    || /^ {0,3}(?:`{3,}|~{3,})[ \t]*(?:html|htm)[ \t]*\r?$/im.test(source);
}

function decodeText(text: string): string {
  return text.replace(/&(#x[0-9a-f]+|#[0-9]+|amp|lt|gt|quot|apos|nbsp);/gi, (original, entity: string) => {
    if (!entity.startsWith('#')) return NAMED_ENTITIES[entity] ?? original;
    const hex = entity[1].toLowerCase() === 'x';
    const scalar = Number.parseInt(entity.slice(hex ? 2 : 1), hex ? 16 : 10);
    if (!Number.isFinite(scalar) || scalar <= 0 || scalar > 0x10ffff || (scalar >= 0xd800 && scalar <= 0xdfff)) return original;
    return String.fromCodePoint(scalar);
  });
}

function validAttributes(raw: string): boolean {
  const pattern = /\s+([a-zA-Z][a-zA-Z0-9_-]*)\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+)/y;
  let position = 0;
  const seen = new Set<string>();
  while (position < raw.length) {
    if (!raw.slice(position).trim()) return true;
    pattern.lastIndex = position;
    const match = pattern.exec(raw);
    if (!match || !PRESENTATION_ATTRIBUTES.has(match[1].toLowerCase()) || seen.has(match[1].toLowerCase())) return false;
    seen.add(match[1].toLowerCase());
    position = pattern.lastIndex;
  }
  return true;
}

export function parseSafeHtmlTable(source: string): SafeHtmlTable | null {
  if (source.length > 32000) return null;
  const tokens = /<(?:[^>"']|"[^"]*"|'[^']*')*>|[^<]+/g;
  const stack: string[] = [];
  const result: SafeHtmlTable = { rows: [] };
  let row: SafeHtmlTable['rows'][number] = [];
  let text = '';
  let seenTable = false;
  let position = 0;
  let match: RegExpExecArray | null;
  const finishText = () => text.replace(/^[ \t\r\n]+|[ \t\r\n]+$/g, '');
  while ((match = tokens.exec(source))) {
    if (match.index !== position) return null;
    position = tokens.lastIndex;
    const token = match[0];
    const parent = stack[stack.length - 1];
    if (!token.startsWith('<')) {
      if (stack.some(tag => tag === 'td' || tag === 'th' || tag === 'caption')) {
        text += decodeText(token.replace(/[ \t\r\n]+/g, ' '));
        if (text.length > 2000) return null;
      } else if (/[^ \t\r\n]/.test(token)) return null;
      continue;
    }
    const tagMatch = /^<(\/)?([a-zA-Z][a-zA-Z0-9]*)([\s\S]*?)>$/.exec(token);
    if (!tagMatch) return null;
    const [, closing, rawTag, rawAttributes] = tagMatch;
    const tag = rawTag.toLowerCase();
    if (closing) {
      if (rawAttributes.trim() || parent !== tag) return null;
      stack.pop();
      if (tag === 'td' || tag === 'th') {
        const value = finishText();
        if (value.length > 2000) return null;
        row.push({ text: value, header: tag === 'th' });
        if (row.length > 20) return null;
        text = '';
      } else if (tag === 'caption') {
        result.caption = finishText();
        text = '';
      } else if (tag === 'tr') {
        if (!row.length || (result.rows.length && row.length !== result.rows[0].length)) return null;
        result.rows.push(row);
        if (result.rows.length > 100) return null;
        row = [];
      }
      continue;
    }
    const selfClosing = /\/\s*$/.test(rawAttributes);
    const attributes = selfClosing ? rawAttributes.replace(/\/\s*$/, '') : rawAttributes;
    if (!validAttributes(attributes) || (selfClosing && tag !== 'br')) return null;
    if (tag === 'table') {
      if (stack.length || seenTable) return null;
      seenTable = true;
    } else if (tag === 'caption') {
      if (parent !== 'table' || result.caption !== undefined || result.rows.length) return null;
    } else if (['thead', 'tbody', 'tfoot'].includes(tag)) {
      if (parent !== 'table') return null;
    } else if (tag === 'tr') {
      if (!['table', 'thead', 'tbody', 'tfoot'].includes(parent)) return null;
    } else if (tag === 'th' || tag === 'td') {
      if (parent !== 'tr') return null;
    } else if (INLINE.has(tag) || tag === 'br') {
      if (!['th', 'td', 'caption'].includes(parent) && !INLINE.has(parent)) return null;
      if (tag === 'br') {
        text += '\n';
        if (text.length > 2000) return null;
        continue;
      }
    } else return null;
    stack.push(tag);
    if (stack.length > 32) return null;
  }
  return position === source.length && seenTable && !stack.length && result.rows.length ? result : null;
}

/** Preserve bytes and code-fence boundaries; only standalone tables are candidates. */
export function splitHtmlTableContent(source: string): HtmlTablePart[] {
  const lines = source.match(/[^\n]*\n|[^\n]+$/g) ?? [];
  const parts: HtmlTablePart[] = [];
  const append = (kind: 'markdown' | 'code' | 'source', value: string) => {
    const previous = parts[parts.length - 1];
    if (previous?.kind === kind) previous.source += value;
    else parts.push({ kind, source: value });
  };
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index].replace(/\r?\n$/, '');
    const fence = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
    if (fence) {
      const closing = new RegExp(`^ {0,3}${fence[1][0]}{${fence[1].length},}\\s*$`);
      let end = index + 1;
      while (end < lines.length && !closing.test(lines[end])) end++;
      const closed = end < lines.length;
      const original = lines.slice(index, closed ? end + 1 : end).join('');
      const isHtml = /^(html|htm)$/i.test(fence[2].trim());
      const table = isHtml && closed ? parseSafeHtmlTable(lines.slice(index + 1, end).join('')) : null;
      if (table) parts.push({ kind: 'table', source: original, table });
      else append(isHtml ? 'source' : 'code', original);
      index = end;
    } else if (/^ {0,3}<table(?:\s|>)/i.test(line)) {
      let end = index;
      while (end < lines.length && !/<\/table\s*>/i.test(lines[end])) end++;
      const original = lines.slice(index, end + 1).join('');
      const table = parseSafeHtmlTable(original);
      if (table) parts.push({ kind: 'table', source: original, table });
      else append('source', original);
      index = end;
    } else append('markdown', lines[index]);
  }
  return parts;
}
