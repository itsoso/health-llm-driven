import type { UIMessage } from '../hooks/useChatEngine';
import type { ServerCardDescriptor } from '../components/chat/cards/types';

const NUTRIENTS = ['calories', 'protein', 'carbs', 'fat', 'fiber'] as const;
const CONTENT_FIELDS = ['food_items', 'meal_type', 'record_date'] as const;

type Projection = { data: Record<string, any>; revision: number };

function revision(value: unknown): number | null {
  if (typeof value !== 'string' || !value) return null;
  const iso = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?$/.test(value)
    ? `${value.replace(' ', 'T')}Z` : value;
  const result = Date.parse(iso);
  return Number.isFinite(result) ? result : null;
}

function savedRecordKey(card: ServerCardDescriptor): string | null {
  const data = card.data;
  if (card.type !== 'diet_draft' || data?.recorded !== true || data.record_unavailable === true
    || !Number.isSafeInteger(data.record_id) || data.record_id <= 0) return null;
  // A message collection is scoped to one authenticated conversation. When
  // explicit owner metadata is present, never merge it with another/absent owner.
  return `${data.user_id ?? 'conversation'}:${data.record_id}`;
}

function visit(card: ServerCardDescriptor, fn: (card: ServerCardDescriptor) => void): void {
  fn(card);
  if (card.type === 'cards_group' && Array.isArray(card.data?.cards)) {
    card.data.cards.forEach((child: ServerCardDescriptor) => { if (child?.data) visit(child, fn); });
  }
}

/** Reconcile only durable, versioned record projections; never parse assistant prose. */
export function reconcileRecordedDietCards(messages: UIMessage[]): UIMessage[] {
  const latest = new Map<string, Projection>();
  for (const message of messages) {
    if (message.role !== 'assistant' || !message.cardType || !message.cardData) continue;
    visit({ type: message.cardType, data: message.cardData }, card => {
      const key = savedRecordKey(card);
      const version = revision(card.data?.updated_at);
      const data = card.data;
      if (!key || version == null || !NUTRIENTS.some(field => Object.hasOwn(data, field))) return;
      if (NUTRIENTS.some(field => Object.hasOwn(data, field)
        && data[field] !== null && (typeof data[field] !== 'number' || !Number.isFinite(data[field]) || data[field] < 0))) return;
      if (version > (latest.get(key)?.revision ?? -Infinity)) latest.set(key, { data, revision: version });
    });
  }
  const project = (card: ServerCardDescriptor): ServerCardDescriptor => {
    if (card.type === 'cards_group' && Array.isArray(card.data?.cards)) {
      const cards = card.data.cards.map((child: ServerCardDescriptor) => child?.data ? project(child) : child);
      return cards.some((child: ServerCardDescriptor, index: number) => child !== card.data.cards[index])
        ? { ...card, data: { ...card.data, cards } } : card;
    }
    const key = savedRecordKey(card);
    const currentVersion = revision(card.data?.updated_at);
    const newer = key ? latest.get(key) : undefined;
    // A persisted row may have a known null revision before its first update.
    // Missing/invalid revisions are unknown and cannot establish an ordering.
    if (!newer || (currentVersion == null && card.data.updated_at !== null)
      || (currentVersion != null && newer.revision <= currentVersion)) return card;
    const data = { ...card.data };
    for (const field of NUTRIENTS) data[field] = newer.data[field] ?? null;
    for (const field of CONTENT_FIELDS) {
      if (Object.hasOwn(newer.data, field)) data[field] = newer.data[field];
    }
    data.updated_at = newer.data.updated_at;
    // Derived advice/confidence for the old portion must not survive a new row.
    for (const field of ['confidence', 'suggestions', 'post_meal_walk', 'next_meal_detail']) delete data[field];
    if (data.adjust_record && typeof data.adjust_record === 'object') {
      const authoritativeSeed = newer.data.adjust_record;
      const seed = authoritativeSeed && authoritativeSeed.record_id === data.record_id
        && authoritativeSeed.updated_at === data.updated_at ? authoritativeSeed : data;
      data.adjust_record = { ...data.adjust_record, ...Object.fromEntries(
        [...NUTRIENTS, ...CONTENT_FIELDS, 'updated_at'].filter(field => Object.hasOwn(seed, field)).map(field => [field, seed[field]]),
      ) };
    }
    return { ...card, data };
  };
  return messages.map(message => {
    if (message.role !== 'assistant' || !message.cardType || !message.cardData) return message;
    const descriptor = { type: message.cardType, data: message.cardData, actions: message.cardActions };
    const next = project(descriptor);
    return next === descriptor ? message : { ...message, cardData: next.data };
  });
}
