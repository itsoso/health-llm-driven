import api from './api';
import { confirmWriteIntent, dismissWriteIntent } from './writeIntents';
import type { ChatCardActionDescriptor } from '../components/chat/cards/types';
import { isSafeInternalRoute } from '../utils/internalRoutes';
import { normalizeHealthActionRoute } from '../utils/dailyArtifactNavigation';
import { assertDietFoodItemsAllowed } from '../utils/dietIntakeGuard';
import { createVerifiedWriteReceipt, type WriteReceipt } from './writeReceipt';

type DietNutritionStatus = 'not_needed' | 'estimated' | 'estimate_failed';

export interface ChatCardActionResult {
  status: 'completed' | 'dismissed' | 'opened';
  route?: string;
  nutrition_status?: DietNutritionStatus;
  patch?: Record<string, unknown>;
  record?: Record<string, unknown>;
  receipt?: WriteReceipt;
}

export async function dispatchChatCardAction(
  action: ChatCardActionDescriptor,
  idempotencyKey?: string,
): Promise<ChatCardActionResult> {
  switch (action.action) {
    case 'agenda.complete':
      assertManualConfirm(action);
      assertEndpoint(action, '/agenda/complete');
      return {
        status: 'completed',
        receipt: receiptFromAgendaResult(action, await completeAgendaFromCard(action)),
      };
    case 'diet_record.create':
      assertManualConfirm(action);
      assertEndpoint(action, '/diet/records');
      {
        const result = await createDietRecordFromCard(action, idempotencyKey);
        return {
          status: 'completed',
          nutrition_status: result.nutritionStatus,
          record: result.record,
          receipt: createVerifiedWriteReceipt({
            operationId: action.id || `diet_record.create:${result.recordId}`,
            resourceType: 'diet_record',
            resourceId: result.recordId,
          }),
        };
      }
    case 'write_intent.confirm':
      assertManualConfirm(action);
      {
        const intentId = readWriteIntentId(action);
        const result = await confirmWriteIntent(intentId);
        if (result.status !== 'executed') throw new Error('write_intent_not_executed');
        return {
          status: 'completed',
          receipt: createVerifiedWriteReceipt({
            operationId: action.id || `write_intent.confirm:${intentId}`,
            executedRef: result.executed_ref,
            ...(result.executed_ref === 'acknowledged' ? {
              resourceType: 'write_intent',
              resourceId: intentId,
            } : {}),
          }),
        };
      }
    case 'write_intent.dismiss':
      assertManualConfirm(action);
      {
        const intentId = readWriteIntentId(action);
        const result = await dismissWriteIntent(intentId);
        if (result.status !== 'dismissed') throw new Error('write_intent_not_dismissed');
        return {
          status: 'dismissed',
          receipt: createVerifiedWriteReceipt({
            operationId: action.id || `write_intent.dismiss:${intentId}`,
            status: 'dismissed',
            resourceType: 'write_intent',
            resourceId: intentId,
          }),
        };
      }
    case 'route.open':
      return { status: 'opened', route: readRoute(action) };
    case 'ui.inline.expand':
      return { status: 'completed', patch: readInlinePatch(action) };
    default:
      throw new Error('unsupported_card_action');
  }
}

function readInlinePatch(action: ChatCardActionDescriptor): Record<string, unknown> {
  const target = optionalText(action.payload?.target);
  const patch = action.payload?.patch;
  if (!target || !patch || typeof patch !== 'object' || Array.isArray(patch)) {
    throw new Error('invalid_inline_patch_action');
  }
  return sanitizeInlinePatch(patch as Record<string, unknown>);
}

function sanitizeInlinePatch(source: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  const expanded = source.expanded_sections;
  if (Array.isArray(expanded)) {
    const sections = expanded
      .map(optionalText)
      .filter((item): item is string => Boolean(item))
      .filter((item) => ['next_meal'].includes(item));
    if (sections.length > 0) out.expanded_sections = sections.slice(0, 4);
  }
  const detail = source.next_meal_detail;
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    out.next_meal_detail = sanitizeNextMealDetail(detail as Record<string, unknown>);
  }
  if (Object.keys(out).length === 0) {
    throw new Error('invalid_inline_patch_action');
  }
  return out;
}

function sanitizeNextMealDetail(source: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of ['title', 'summary', 'context', 'continue_prompt'] as const) {
    const value = optionalText(source[key]);
    if (value) out[key] = value;
  }
  for (const key of ['options', 'rationale'] as const) {
    const values = readOptionalTextList(source[key]);
    if (values.length > 0) out[key] = values;
  }
  return out;
}

function readOptionalTextList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map(optionalText)
    .filter((item): item is string => Boolean(item))
    .slice(0, 6);
}

async function createDietRecordFromCard(
  action: ChatCardActionDescriptor,
  idempotencyKey?: string,
): Promise<{
  nutritionStatus: DietNutritionStatus;
  recordId: number;
  record?: Record<string, unknown>;
}> {
  const record = readDietRecord(action);
  const normalizedKey = normalizeIdempotencyKey(idempotencyKey);
  const response = normalizedKey
    ? await api.post('/diet/records', record, {
      headers: { 'Idempotency-Key': normalizedKey },
    })
    : await api.post('/diet/records', record);
  const { data } = response;
  const recordId = readOptionalNumericId(data?.id);
  if (!recordId) throw new Error('diet_record_missing_id');
  let savedRecord = normalizeSavedDietRecord(data);
  if (!needsNutritionEstimate(record)) {
    return { nutritionStatus: 'not_needed', recordId, record: savedRecord };
  }
  const estimated = await backfillEstimatedNutrition(recordId, record);
  if (estimated.record) savedRecord = estimated.record;
  return { nutritionStatus: estimated.status, recordId, record: savedRecord };
}

function normalizeIdempotencyKey(raw: string | undefined): string | undefined {
  const value = optionalText(raw);
  if (!value) return undefined;
  if (value.length > 160 || !/^[A-Za-z0-9._:-]+$/.test(value)) {
    throw new Error('invalid_card_action_idempotency_key');
  }
  return value;
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

async function completeAgendaFromCard(action: ChatCardActionDescriptor): Promise<Record<string, unknown>> {
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
  const { data } = await api.post('/agenda/complete', payload);
  return data && typeof data === 'object' ? data : {};
}

function receiptFromAgendaResult(
  action: ChatCardActionDescriptor,
  result: Record<string, unknown>,
): WriteReceipt {
  const eventId = readOptionalNumericId(result.event_id);
  if (!eventId) throw new Error('write_receipt_missing_identity');
  return createVerifiedWriteReceipt({
    operationId: action.id || `agenda.complete:${eventId}`,
    resourceType: 'agenda_event',
    resourceId: eventId,
  });
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
  return normalizeHealthActionRoute(route, action.label) ?? route;
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

function needsNutritionEstimate(record: Record<string, unknown>): boolean {
  return ['calories', 'protein', 'carbs', 'fat'].some((key) => !isUsableNutritionNumber(record[key]));
}

async function backfillEstimatedNutrition(
  recordId: number,
  record: Record<string, unknown>,
): Promise<{ status: DietNutritionStatus; record?: Record<string, unknown> }> {
  try {
    const foodItems = readFoodItems(record.food_items);
    const { data } = await api.post(`/diet/estimate-nutrition?food_description=${encodeURIComponent(foodItems)}`);
    const patch = readNutritionPatch(data, record);
    if (!Object.keys(patch).length) return { status: 'estimate_failed' };
    const updated = await api.put(`/diet/records/${recordId}`, patch);
    return {
      status: 'estimated',
      record: normalizeSavedDietRecord(updated?.data) ?? {
        id: recordId,
        ...record,
        ...patch,
      },
    };
  } catch {
    return { status: 'estimate_failed' };
  }
}

function readNutritionPatch(raw: unknown, existing: Record<string, unknown>): Record<string, number> {
  if (!raw || typeof raw !== 'object') return {};
  const source = raw as Record<string, unknown>;
  if (source.success === false) return {};
  const mapping: [string, string][] = [
    ['total_calories', 'calories'],
    ['total_protein', 'protein'],
    ['total_carbs', 'carbs'],
    ['total_fat', 'fat'],
  ];
  const patch: Record<string, number> = {};
  for (const [estimateKey, recordKey] of mapping) {
    if (isUsableNutritionNumber(existing[recordKey])) continue;
    const value = normalizeOptionalNutritionNumber(source[estimateKey]);
    if (value != null) patch[recordKey] = value;
  }
  return patch;
}

function normalizeOptionalNutritionNumber(raw: unknown): number | undefined {
  const value = typeof raw === 'number' ? raw : typeof raw === 'string' ? Number(raw.trim()) : NaN;
  if (!Number.isFinite(value) || value < 0) return undefined;
  return Math.round(value * 10) / 10;
}

function isUsableNutritionNumber(raw: unknown): boolean {
  return normalizeOptionalNutritionNumber(raw) != null;
}

function readRequiredText(raw: unknown, errorCode: string): string {
  const value = optionalText(raw);
  if (!value) throw new Error(errorCode);
  return value;
}

function readFoodItems(raw: unknown): string {
  let foodItems: string;
  if (Array.isArray(raw)) {
    const items = raw.map(optionalText).filter((item): item is string => Boolean(item));
    if (items.length > 0) {
      foodItems = items.slice(0, 8).join(' + ');
      assertDietFoodItemsAllowed(foodItems);
      return foodItems;
    }
  }
  foodItems = readRequiredText(raw, 'invalid_diet_food_items');
  assertDietFoodItemsAllowed(foodItems);
  return foodItems;
}

function normalizeSavedDietRecord(raw: unknown): Record<string, unknown> | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined;
  const source = raw as Record<string, unknown>;
  const id = readOptionalNumericId(source.id);
  if (!id) return undefined;
  const hasDietShape = Boolean(
    optionalText(source.food_items) ||
    optionalText(source.meal_type) ||
    optionalText(source.record_date),
  );
  if (!hasDietShape) return undefined;
  const out: Record<string, unknown> = { id };
  for (const key of ['record_date', 'meal_type', 'food_items', 'notes'] as const) {
    const value = optionalText(source[key]);
    if (value) out[key] = value;
  }
  for (const key of ['calories', 'protein', 'carbs', 'fat', 'fiber', 'alcohol_units'] as const) {
    const value = normalizeOptionalNutritionNumber(source[key]);
    if (value != null) out[key] = value;
  }
  return out;
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

function readOptionalNumericId(raw: unknown): number | undefined {
  try {
    return normalizeNumericId(raw);
  } catch {
    return undefined;
  }
}
