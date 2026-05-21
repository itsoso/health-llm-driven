export function buildAiShareMessage(content: string): string {
  const text = content.trim();
  return text ? `${text}\n\n— 健康 Agent` : '';
}
