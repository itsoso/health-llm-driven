import type { ServerCardDescriptor } from './types';

function canonicalize(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (!value || typeof value !== 'object') return value;
  return Object.keys(value as Record<string, unknown>)
    .sort()
    .reduce<Record<string, unknown>>((result, key) => {
      result[key] = canonicalize((value as Record<string, unknown>)[key]);
      return result;
    }, {});
}

export function stableServerCardId(
  card: Pick<ServerCardDescriptor, 'type' | 'data' | 'actions'>,
): string | undefined {
  const raw = card.data?.card_id;
  if (typeof raw !== 'string') return undefined;
  const normalized = raw.trim();
  return normalized ? `${card.type}:${normalized}` : undefined;
}

export function serverCardIdentity(
  card: Pick<ServerCardDescriptor, 'type' | 'data' | 'actions'>,
): string {
  const stableId = stableServerCardId(card);
  if (stableId) return stableId;
  try {
    return JSON.stringify(canonicalize([
      card.type,
      card.data ?? {},
      card.actions ?? [],
    ]));
  } catch {
    return `${card.type}:legacy`;
  }
}

/** Preserve the first display position, but keep the latest projection. */
export function dedupeServerCards(cards: ServerCardDescriptor[]): ServerCardDescriptor[] {
  const deduped: ServerCardDescriptor[] = [];
  const indexes = new Map<string, number>();
  cards.forEach((card) => {
    const key = serverCardIdentity(card);
    const existingIndex = indexes.get(key);
    if (existingIndex == null) {
      indexes.set(key, deduped.length);
      deduped.push(card);
      return;
    }
    deduped[existingIndex] = card;
  });
  return deduped;
}
