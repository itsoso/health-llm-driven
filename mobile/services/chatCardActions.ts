import type { QueryClient } from '@tanstack/react-query';

import type { CardActionDescriptor } from '../components/chat/cards/types';
import {
  completeAgendaItem,
  type AgendaSkipReason,
  type AgendaSource,
} from './agenda';
import { confirmWriteIntent, dismissWriteIntent } from './writeIntents';

type QueryInvalidator = Pick<QueryClient, 'invalidateQueries'>;

export type ChatCardActionExecutionResult =
  | { status: 'executed'; action: string }
  | { status: 'unsupported'; action: string }
  | { status: 'invalid'; action: string; reason: string };

interface ExecuteChatCardActionDeps {
  queryClient: QueryInvalidator;
}

const AGENDA_REFRESH_KEYS = [
  ['timeline', 'today'],
  ['agenda', 'today'],
  ['dashboard'],
  ['twin', 'me'],
] as const;

const WRITE_INTENT_REFRESH_KEYS = [
  ['write-intents'],
  ['timeline', 'today'],
  ['agenda', 'today'],
  ['dashboard'],
] as const;

function payloadObject(action: CardActionDescriptor): Record<string, any> {
  return action.payload && typeof action.payload === 'object' ? action.payload : {};
}

function readAgendaSource(action: CardActionDescriptor): AgendaSource | null {
  const payload = payloadObject(action);
  const source = payload.source ?? payload.complete_ref ?? payload;
  if (!source || typeof source !== 'object') return null;
  if (typeof source.object_type !== 'string') return null;
  if (source.object_id == null) return null;
  return {
    object_type: source.object_type,
    object_id: source.object_id,
    slot: typeof source.slot === 'string' ? source.slot : undefined,
  };
}

function readWriteIntentId(action: CardActionDescriptor): number | null {
  const payload = payloadObject(action);
  const raw = payload.id ?? payload.write_intent_id;
  const id = typeof raw === 'number' ? raw : Number(raw);
  return Number.isInteger(id) && id > 0 ? id : null;
}

async function invalidate(queryClient: QueryInvalidator, keys: readonly (readonly unknown[])[]): Promise<void> {
  await Promise.all(keys.map((queryKey) => queryClient.invalidateQueries({ queryKey })));
}

export async function executeChatCardAction(
  action: CardActionDescriptor,
  deps: ExecuteChatCardActionDeps,
): Promise<ChatCardActionExecutionResult> {
  switch (action.action) {
    case 'complete_agenda': {
      const source = readAgendaSource(action);
      if (!source) return { status: 'invalid', action: action.action, reason: 'missing agenda source' };
      await completeAgendaItem(source, 'protocol', undefined, { status: 'done' });
      await invalidate(deps.queryClient, AGENDA_REFRESH_KEYS);
      return { status: 'executed', action: action.action };
    }

    case 'skip_agenda': {
      const source = readAgendaSource(action);
      if (!source) return { status: 'invalid', action: action.action, reason: 'missing agenda source' };
      const skipReason = payloadObject(action).skip_reason as AgendaSkipReason | undefined;
      await completeAgendaItem(source, 'protocol', undefined, { status: 'skipped', skipReason });
      await invalidate(deps.queryClient, AGENDA_REFRESH_KEYS);
      return { status: 'executed', action: action.action };
    }

    case 'confirm_write_intent': {
      const id = readWriteIntentId(action);
      if (!id) return { status: 'invalid', action: action.action, reason: 'missing write intent id' };
      await confirmWriteIntent(id);
      await invalidate(deps.queryClient, WRITE_INTENT_REFRESH_KEYS);
      return { status: 'executed', action: action.action };
    }

    case 'dismiss_write_intent': {
      const id = readWriteIntentId(action);
      if (!id) return { status: 'invalid', action: action.action, reason: 'missing write intent id' };
      await dismissWriteIntent(id);
      await invalidate(deps.queryClient, WRITE_INTENT_REFRESH_KEYS);
      return { status: 'executed', action: action.action };
    }

    default:
      return { status: 'unsupported', action: action.action };
  }
}
