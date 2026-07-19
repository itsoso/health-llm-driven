import { renderServerCards } from './registry';
import type { ServerCardDescriptor } from './types';

/**
 * Keep every valid server-issued card attached to the same assistant message.
 * A reply can legitimately contain both a media result and a recoverable diet
 * action; selecting the first descriptor makes the later action undiscoverable.
 */
export function projectServerCards(value: unknown): ServerCardDescriptor | null {
  const cards = renderServerCards(value as ServerCardDescriptor[] | null | undefined);
  if (cards.length === 0) return null;
  if (cards.length === 1) return cards[0];
  return { type: 'cards_group', data: { cards } };
}
