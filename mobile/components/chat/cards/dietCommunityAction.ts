import type { ChatCardActionDescriptor } from './types';

export type DietCommunityActionDisposition = 'embedded' | 'reject' | 'other';

const COMMUNITY_RECORD_ROUTE = /^\/community\?composeRecordId=([1-9][0-9]*)$/;

function positiveSafeInteger(value: unknown): number | null {
  if (typeof value === 'number') {
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  }
  if (typeof value !== 'string' || !/^[1-9][0-9]*$/.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) ? parsed : null;
}

/**
 * Keep the recorded-meal community action bound to the exact card record.
 * Candidate actions that fail any binding check are rejected rather than
 * falling through to the generic action bar.
 */
export function dietCommunityActionDisposition(
  action: ChatCardActionDescriptor,
  cardType: string,
  data: Record<string, unknown> | null | undefined,
): DietCommunityActionDisposition {
  const route = typeof action.payload?.route === 'string' ? action.payload.route : null;
  const candidate = action.id === 'share-with-peers'
    || Boolean(route?.startsWith('/community?composeRecordId'));
  if (!candidate) return 'other';

  if (cardType !== 'diet_draft' || data?.recorded !== true) return 'reject';
  if (action.id !== 'share-with-peers' || action.action !== 'route.open' || route == null) {
    return 'reject';
  }

  const routeMatch = COMMUNITY_RECORD_ROUTE.exec(route);
  const cardRecordId = positiveSafeInteger(data.record_id);
  const routeRecordId = routeMatch ? positiveSafeInteger(routeMatch[1]) : null;
  return cardRecordId != null && routeRecordId === cardRecordId ? 'embedded' : 'reject';
}
