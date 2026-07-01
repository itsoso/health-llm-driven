import api from './api';
import { confirmWriteIntent, dismissWriteIntent } from './writeIntents';
import type { ChatCardActionDescriptor } from '../components/chat/cards/types';
import { isSafeInternalRoute } from '../utils/internalRoutes';

export interface ChatCardActionResult {
  status: 'completed' | 'dismissed' | 'opened';
  route?: string;
}

export async function dispatchChatCardAction(
  action: ChatCardActionDescriptor,
): Promise<ChatCardActionResult> {
  switch (action.action) {
    case 'agenda.complete':
      assertManualConfirm(action);
      assertEndpoint(action, '/agenda/complete');
      await completeAgendaFromCard(action);
      return { status: 'completed' };
    case 'write_intent.confirm':
      assertManualConfirm(action);
      await confirmWriteIntent(readWriteIntentId(action));
      return { status: 'completed' };
    case 'write_intent.dismiss':
      assertManualConfirm(action);
      await dismissWriteIntent(readWriteIntentId(action));
      return { status: 'dismissed' };
    case 'route.open':
      return { status: 'opened', route: readRoute(action) };
    default:
      throw new Error('unsupported_card_action');
  }
}

function assertManualConfirm(action: ChatCardActionDescriptor): void {
  if (action.requires_manual_confirm !== true) {
    throw new Error('manual_confirm_required');
  }
}

function assertEndpoint(action: ChatCardActionDescriptor, expected: string): void {
  if (action.endpoint && action.endpoint !== expected) {
    throw new Error('unsupported_card_action_endpoint');
  }
}

async function completeAgendaFromCard(action: ChatCardActionDescriptor): Promise<void> {
  const source = action.payload?.source;
  if (!source || typeof source.object_type !== 'string') {
    throw new Error('invalid_agenda_source');
  }
  const objectId = normalizeNumericId(source.object_id);
  const payload: Record<string, unknown> = {
    object_type: source.object_type,
    object_id: objectId,
    status: action.payload?.status === 'skipped' ? 'skipped' : 'done',
    track: action.payload?.track === 'manual' ? 'manual' : 'protocol',
    value: action.payload?.value ?? null,
  };
  if (typeof source.slot === 'string' && source.slot.length > 0) {
    payload.slot = source.slot;
  }
  if (payload.status === 'skipped') {
    payload.skip_reason = action.payload?.skip_reason ?? 'no_time';
  }
  await api.post('/agenda/complete', payload);
}

function readWriteIntentId(action: ChatCardActionDescriptor): number {
  const raw = action.payload?.write_intent_id ?? action.payload?.id;
  const id = normalizeNumericId(raw);
  const expectedSuffix = action.action === 'write_intent.dismiss' ? `/write-intents/${id}/dismiss` : `/write-intents/${id}/confirm`;
  if (action.endpoint && action.endpoint !== expectedSuffix) {
    throw new Error('unsupported_card_action_endpoint');
  }
  return id;
}

function readRoute(action: ChatCardActionDescriptor): string {
  const route = action.payload?.route;
  if (!isSafeInternalRoute(route)) {
    throw new Error('invalid_route_action');
  }
  return route;
}

function normalizeNumericId(raw: unknown): number {
  if (typeof raw === 'number' && Number.isInteger(raw) && raw > 0) return raw;
  if (typeof raw === 'string' && /^\d+$/.test(raw.trim())) return Number(raw);
  throw new Error('invalid_card_action_id');
}
