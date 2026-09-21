/** Absolute share of the described whole meal, never a multiplier of an earlier share. */
export function parseDietPortion(value: string): number | null {
  const token = value.trim().replace(/\s+/g, '');
  let fraction: number;
  if (/^\d+(?:\.\d+)?%$/.test(token)) fraction = Number(token.slice(0, -1)) / 100;
  else if (/^\d+\/\d+$/.test(token)) {
    const [numerator, denominator] = token.split('/').map(Number);
    fraction = numerator / denominator;
  } else if (/^\d+(?:\.\d+)?$/.test(token)) fraction = Number(token);
  else return null;
  return Number.isFinite(fraction) && fraction > 0 && fraction <= 1 ? fraction : null;
}

const LEGACY_FRACTIONS: Record<string, string> = {
  一半: '1/2', 半份: '1/2', 二分之一: '1/2', 三分之一: '1/3', 三分之二: '2/3',
  四分之一: '1/4', 四分之三: '3/4', 五分之一: '1/5', 五分之二: '2/5',
  五分之三: '3/5', 五分之四: '4/5',
};

export function splitDietPortion(description: string): { food: string; fraction: number; text: string } {
  const food = description.trim();
  const match = food.match(/（按实际食用([^（）]{1,24})计）\s*$/);
  if (match && match.index !== undefined) {
    const token = LEGACY_FRACTIONS[match[1].trim()] ?? match[1].trim();
    const fraction = parseDietPortion(token);
    const base = food.slice(0, match.index).trim();
    if (fraction !== null && base) return { food: base, fraction, text: token };
  }
  return { food, fraction: 1, text: '1' };
}
