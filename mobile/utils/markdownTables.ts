const isTableRow = (line: string) => /^\s*\|.*\|\s*$/.test(line);
const isDividerRow = (line: string) => /^\s*\|[\s\-:|]+\|\s*$/.test(line);

function splitTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map(cell => cell.trim())
    .filter(Boolean);
}

function pushListRows(out: string[], rows: string[][]): void {
  for (const row of rows) {
    const first = row[0] ? `**${row[0]}**` : '';
    const rest = row.slice(1).filter(Boolean).join(' · ');
    const text = `${first}${first && rest ? ' · ' : ''}${rest}`.trim();
    if (text) out.push(`- ${text}`);
  }
}

export function containsMarkdownTable(md: string): boolean {
  const lines = md.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    if (isTableRow(lines[i]) && isDividerRow(lines[i + 1] ?? '')) return true;
    if (isDividerRow(lines[i]) && isTableRow(lines[i + 1] ?? '')) return true;
  }
  return false;
}

export function preprocessMarkdownTables(md: string): string {
  const lines = md.split('\n');
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];
    const next = lines[i + 1];

    if (isTableRow(line) && next && isDividerRow(next)) {
      const headers = splitTableRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && isTableRow(lines[i]) && !isDividerRow(lines[i])) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      if (headers.length > 0) out.push(`**${headers.join(' · ')}**`);
      pushListRows(out, rows);
      out.push('');
      continue;
    }

    if (isDividerRow(line) && next && isTableRow(next)) {
      const rows: string[][] = [];
      i += 1;
      while (i < lines.length && isTableRow(lines[i]) && !isDividerRow(lines[i])) {
        rows.push(splitTableRow(lines[i]));
        i += 1;
      }
      pushListRows(out, rows);
      out.push('');
      continue;
    }

    out.push(line);
    i += 1;
  }

  return out.join('\n');
}
