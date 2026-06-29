export function formatHealthActionTitle(raw: string | null | undefined): string {
  let title = String(raw ?? '').trim();
  if (!title) return '';

  title = title
    .replace(/^(今日|今天)?\s*(训练|运动|行动|任务|计划)\s*[:：]\s*/u, '')
    .replace(/^今天(?=\S)/u, '')
    .replace(/^今日(?=\S)/u, '')
    .replace(/，/gu, ',')
    .replace(/；/gu, ';');

  const commaIndex = title.indexOf(',');
  const semicolonIndex = title.indexOf(';');
  const firstBreak = [commaIndex, semicolonIndex].filter((index) => index >= 0).sort((a, b) => a - b)[0];
  if (firstBreak > 0) {
    title = `${title.slice(0, firstBreak)}:${title.slice(firstBreak + 1)}`;
  }

  return title.replace(/\s+/gu, ' ').trim();
}
