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
    case 'diet_record.create':
      assertManualConfirm(action);
      assertEndpoint(action, '/diet/records');
      await createDietRecordFromCard(action);
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

async function createDietRecordFromCard(action: ChatCardActionDescriptor): Promise<void> {
  const record = readDietRecord(action);
  await api.post('/diet/records', record);
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

function readDietRecord(action: ChatCardActionDescriptor): Record<string, unknown> {
  const raw = action.payload?.record ?? action.payload;
  if (!raw || typeof raw !== 'object') {
    throw new Error('invalid_diet_record_payload');
  }
  const source = raw as Record<string, unknown>;
  const foodItems = readFoodItems(source.food_items);
  const mealType = readMealType(source.meal_type);
  const recordDate = readRecordDate(source.record_date);
  const out: Record<string, unknown> = {
    record_date: recordDate,
    meal_type: mealType,
    food_items: foodItems,
  };
  copyOptionalNumber(source, out, 'calories');
  copyOptionalNumber(source, out, 'protein');
  copyOptionalNumber(source, out, 'carbs');
  copyOptionalNumber(source, out, 'fat');
  copyOptionalNumber(source, out, 'fiber');
  copyOptionalNumber(source, out, 'alcohol_units');
  const notes = optionalText(source.notes);
  if (notes) out.notes = notes;
  return out;
}

function readRequiredText(raw: unknown, errorCode: string): string {
  const value = optionalText(raw);
  if (!value) throw new Error(errorCode);
  return value;
}

function readFoodItems(raw: unknown): string {
  if (Array.isArray(raw)) {
    const items = raw.map(optionalText).filter((item): item is string => Boolean(item));
    if (items.length > 0) return items.slice(0, 8).join(' + ');
  }
  return readRequiredText(raw, 'invalid_diet_food_items');
}

function optionalText(raw: unknown): string | undefined {
  if (typeof raw !== 'string') return undefined;
  const value = raw.trim();
  return value.length > 0 ? value.slice(0, 500) : undefined;
}

function readMealType(raw: unknown): string {
  const value = optionalText(raw) || guessMealType();
  if (['breakfast', 'lunch', 'dinner', 'snack'].includes(value)) return value;
  throw new Error('invalid_diet_meal_type');
}

function readRecordDate(raw: unknown): string {
  const value = optionalText(raw);
  if (value && /^\d{4}-\d{2}-\d{2}$/.test(value)) return value;
  return todayString();
}

function copyOptionalNumber(source: Record<string, unknown>, target: Record<string, unknown>, key: string): void {
  const value = source[key];
  if (value == null || value === '') return;
  const parsed = typeof value === 'number' ? value : typeof value === 'string' ? Number(value.trim()) : NaN;
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`invalid_diet_${key}`);
  target[key] = Math.round(parsed * 10) / 10;
}

function todayString(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function guessMealType(): string {
  const h = new Date().getHours();
  if (h < 10) return 'breakfast';
  if (h < 14) return 'lunch';
  if (h < 20) return 'dinner';
  return 'snack';
}

function normalizeNumericId(raw: unknown): number {
  if (typeof raw === 'number' && Number.isInteger(raw) && raw > 0) return raw;
  if (typeof raw === 'string' && /^\d+$/.test(raw.trim())) return Number(raw);
  throw new Error('invalid_card_action_id');
}
