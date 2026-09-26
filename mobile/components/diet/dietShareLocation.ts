/** Explicit, session-only public label. Never infer from a record or device. */
export const DIET_SHARE_LOCATION_MAX_LENGTH = 40;

export function normalizeDietShareLocation(value: string = ''): string {
  return Array.from(value
    .replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()).slice(0, DIET_SHARE_LOCATION_MAX_LENGTH).join('').trim();
}

export function dietShareLocationLine(value?: string): string {
  const label = normalizeDietShareLocation(value);
  return label ? `地点：${label}` : '';
}

export function withDietShareLocation(message: string, value?: string): string {
  const line = dietShareLocationLine(value);
  return line ? `${message}\n\n${line}` : message;
}
