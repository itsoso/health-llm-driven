import api from './api';
import { confirmWriteIntent, dismissWriteIntent } from './writeIntents';
import type { ChatCardActionDescriptor } from '../components/chat/cards/types';
import { isSafeInternalRoute } from '../utils/internalRoutes';
import { normalizeHealthActionRoute } from '../utils/dailyArtifactNavigation';
import { assertDietFoodItemsAllowed } from '../utils/dietIntakeGuard';
import {
  createVerifiedWriteReceipt,
  normalizeWriteReceipt,
  type WriteReceipt,
} from './writeReceipt';
import type { MedicationSafetyAlert } from './medications';

type DietNutritionStatus = 'not_needed' | 'estimated' | 'estimate_failed';

const WRITE_CARD_ACTIONS = new Set([
  'agenda.complete',
  'daily_plan_action.complete',
  'diet_record.create',
  'write_intent.confirm',
  'write_intent.dismiss',
  'aigc_media.confirm',
]);

export interface ChatCardActionResult {
  status: 'completed' | 'dismissed' | 'expired' | 'opened';
  decision_status?: 'executed' | 'dismissed' | 'expired';
  route?: string;
  nutrition_status?: DietNutritionStatus;
  patch?: Record<string, unknown>;
  receipt?: WriteReceipt;
  write_receipts?: WriteReceipt[];
  safety_alerts?: MedicationSafetyAlert[];
}

export interface ChatCardActionContext {
  cardType?: string;
  cardData?: Record<string, unknown> | null;
}

export async function dispatchChatCardAction(
  action: ChatCardActionDescriptor,
  idempotencyKey?: string,
  context?: ChatCardActionContext,
): Promise<ChatCardActionResult> {
  switch (action.action) {
    case 'agenda.complete':
      assertManualConfirm(action);
      assertRegisteredWritePolicy(action);
      assertEndpoint(action, '/agenda/complete');
      return {
        status: 'completed',
        receipt: receiptFromAgendaResult(action, await completeAgendaFromCard(action)),
      };
    case 'daily_plan_action.complete':
      assertManualConfirm(action);
      assertRegisteredWritePolicy(action);
      return {
        status: 'completed',
        receipt: receiptFromDailyPlanResult(action, await completeDailyPlanActionFromCard(action)),
      };
    case 'diet_record.create':
      assertManualConfirm(action);
      assertRegisteredWritePolicy(action);
      assertEndpoint(action, '/diet/records');
      {
        const result = await createDietRecordFromCard(action, idempotencyKey);
        return {
        status: 'completed',
          nutrition_status: result.nutritionStatus,
          receipt: createVerifiedWriteReceipt({
            operationId: action.id || `diet_record.create:${result.recordId}`,
            resourceType: 'diet_record',
            resourceId: result.recordId,
          }),
        };
      }
    case 'write_intent.confirm':
      assertManualConfirm(action);
      assertRegisteredWritePolicy(action);
      {
        const medicationBatch = readMedicationBatchContext(action, context);
        const intentId = readWriteIntentId(action);
        let result;
        try {
          result = await confirmWriteIntent(intentId);
        } catch (error) {
          if (isExpiredWriteIntentConfirmation(error)) {
            return { status: 'expired', decision_status: 'expired' };
          }
          throw error;
        }
        if (result.status === 'dismissed' && medicationBatch) {
          const decisionStatus = readMedicationDecisionStatus(result.decision_status);
          if (decisionStatus === 'expired') {
            return { status: 'expired', decision_status: 'expired' };
          }
          if (decisionStatus === 'dismissed') {
            return { status: 'dismissed', decision_status: 'dismissed' };
          }
          throw new Error('medication_batch_decision_status_missing');
        }
        if (result.status !== 'executed') throw new Error('write_intent_not_executed');
        const serverReceipts = medicationBatch
          ? normalizeMedicationBatchReceipts(
              result.write_receipts,
              intentId,
              medicationBatch.itemCount,
            )
          : normalizeServerWriteReceipts(result.write_receipts);
        if (result.write_receipts && serverReceipts.length !== result.write_receipts.length) {
          throw new Error('write_intent_receipts_unverified');
        }
        if (
          serverReceipts.length === 0
          && String(result.executed_ref || '').startsWith('medication_logs:')
        ) {
          throw new Error('medication_batch_write_receipts_missing');
        }
        const receipts = serverReceipts.length > 0
          ? serverReceipts
          : [createVerifiedWriteReceipt({
            operationId: action.id || `write_intent.confirm:${intentId}`,
            executedRef: result.executed_ref,
            ...(result.executed_ref === 'acknowledged' ? {
              resourceType: 'write_intent',
              resourceId: intentId,
            } : {}),
          })];
        const safetyAlerts = Array.isArray(result.safety_alerts) ? result.safety_alerts : [];
        return {
          status: 'completed',
          decision_status: 'executed',
          receipt: receipts[receipts.length - 1],
          write_receipts: receipts,
          ...(safetyAlerts.length > 0 ? { safety_alerts: safetyAlerts } : {}),
        };
      }
    case 'write_intent.dismiss':
      assertManualConfirm(action);
      assertRegisteredWritePolicy(action);
      {
        const medicationBatch = readMedicationBatchContext(action, context);
        const intentId = readWriteIntentId(action);
        const result = await dismissWriteIntent(intentId);
        if (result.status === 'dismissed') {
          const decisionStatus = medicationBatch
            ? readMedicationDecisionStatus(result.decision_status)
            : 'dismissed';
          if (decisionStatus === 'expired') {
            return { status: 'expired', decision_status: 'expired' };
          }
          if (decisionStatus !== 'dismissed') {
            throw new Error('medication_batch_decision_status_missing');
          }
          // A dismissal is a terminal decision, not a verified health write.
          return { status: 'dismissed', decision_status: 'dismissed' };
        }
        if (result.status === 'executed' && medicationBatch) {
          const receipts = normalizeMedicationBatchReceipts(
            result.write_receipts,
            intentId,
            medicationBatch.itemCount,
          );
          const safetyAlerts = Array.isArray(result.safety_alerts) ? result.safety_alerts : [];
          return {
            status: 'completed',
            decision_status: 'executed',
            receipt: receipts[receipts.length - 1],
            write_receipts: receipts,
            ...(safetyAlerts.length > 0 ? { safety_alerts: safetyAlerts } : {}),
          };
        }
        throw new Error('write_intent_not_dismissed');
      }
    case 'aigc_media.confirm':
      assertManualConfirm(action);
      assertRegisteredWritePolicy(action);
      {
        const confirmationID = readAIGCMediaConfirmationID(action);
        const { data } = await api.post(`/aigc/media/confirmations/${encodeURIComponent(confirmationID)}/confirm`);
        const jobID = optionalText(data?.id);
        if (!jobID) throw new Error('aigc_media_confirmation_missing_job');
        return {
          status: 'completed',
          patch: { dispatched_job_id: jobID },
          receipt: createVerifiedWriteReceipt({
            operationId: action.id || `aigc_media.confirm:${confirmationID}`,
            resourceType: 'aigc_media_job',
            resourceId: jobID,
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

function isExpiredWriteIntentConfirmation(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const response = (error as { response?: unknown }).response;
  if (!response || typeof response !== 'object') return false;
  const status = (response as { status?: unknown }).status;
  const data = (response as { data?: unknown }).data;
  const detail = data && typeof data === 'object'
    ? (data as { detail?: unknown }).detail
    : undefined;
  return status === 409 && typeof detail === 'string' && detail.includes('已过期');
}

function normalizeServerWriteReceipts(raw: unknown): WriteReceipt[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map(normalizeWriteReceipt)
    .filter((receipt): receipt is WriteReceipt => Boolean(receipt));
}

function normalizeMedicationBatchReceipts(
  raw: unknown,
  intentId: number,
  expectedCount: number,
): WriteReceipt[] {
  if (!Array.isArray(raw) || raw.length !== expectedCount) {
    throw new Error('medication_batch_write_receipts_missing');
  }
  const expectedPrefix = `write_intent:medication_intake_batch:${intentId}:`;
  const receipts = raw.map((value) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('medication_batch_write_receipts_invalid');
    }
    const source = value as Record<string, unknown>;
    const receipt = normalizeWriteReceipt(source);
    if (
      !receipt
      || source.status !== 'verified'
      || source.resource_type !== 'medication_log'
      || receipt.resourceType !== 'medication_log'
      || !receipt.operationId.startsWith(expectedPrefix)
    ) {
      throw new Error('medication_batch_write_receipts_invalid');
    }
    return receipt;
  });
  if (new Set(receipts.map(receipt => receipt.operationId)).size !== expectedCount) {
    throw new Error('medication_batch_write_receipts_invalid');
  }
  return receipts;
}

function readMedicationBatchContext(
  action: ChatCardActionDescriptor,
  context?: ChatCardActionContext,
): { itemCount: number } | null {
  const claimsMedicationBatch = context?.cardType === 'medication_draft'
    || action.capability_id === 'medication_draft.v1';
  if (!claimsMedicationBatch) return null;
  if (context?.cardType !== 'medication_draft') {
    throw new Error('medication_batch_card_context_required');
  }
  const intentId = normalizeNumericId(action.payload?.write_intent_id);
  const cardIntentId = normalizeNumericId(context.cardData?.write_intent_id);
  const items = context.cardData?.items;
  if (
    action.capability_id !== 'medication_draft.v1'
    || intentId !== cardIntentId
    || !Array.isArray(items)
    || items.length < 1
    || items.length > 8
  ) {
    throw new Error('invalid_medication_batch_action');
  }
  return { itemCount: items.length };
}

function readMedicationDecisionStatus(value: unknown): 'executed' | 'dismissed' | 'expired' | null {
  return value === 'executed' || value === 'dismissed' || value === 'expired'
    ? value
    : null;
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
  if (!needsNutritionEstimate(record)) return { nutritionStatus: 'not_needed', recordId };
  return { nutritionStatus: await backfillEstimatedNutrition(recordId, record), recordId };
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

function assertRegisteredWritePolicy(action: ChatCardActionDescriptor): void {
  if (!WRITE_CARD_ACTIONS.has(action.action)) return;
  const capabilityId = typeof action.capability_id === 'string' ? action.capability_id : '';
  if (
    !/^[a-z][a-z0-9_]*\.v\d+$/.test(capabilityId) ||
    action.required_receipt !== true ||
    action.autonomy_tier !== 'manual_confirm' ||
    action.policy_reason !== 'manual_confirm_write'
  ) {
    throw new Error('registered_write_policy_required');
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

function readDailyPlanActionId(action: ChatCardActionDescriptor): string {
  const actionId = optionalText(action.payload?.action_id);
  if (!actionId || actionId.length > 160 || !/^[A-Za-z0-9._:-]+$/.test(actionId)) {
    throw new Error('invalid_daily_plan_action_id');
  }
  const endpoint = `/daily-plan/actions/${encodeURIComponent(actionId)}/events`;
  assertEndpoint(action, endpoint);
  return actionId;
}

async function completeDailyPlanActionFromCard(
  action: ChatCardActionDescriptor,
): Promise<Record<string, unknown>> {
  const actionId = readDailyPlanActionId(action);
  const { data } = await api.post(
    `/daily-plan/actions/${encodeURIComponent(actionId)}/events`,
    { event_type: 'completed', payload: { source: 'chat_card' } },
  );
  return data && typeof data === 'object' ? data : {};
}

function receiptFromDailyPlanResult(
  action: ChatCardActionDescriptor,
  result: Record<string, unknown>,
): WriteReceipt {
  const eventId = readOptionalNumericId(result.id);
  if (!eventId) throw new Error('write_receipt_missing_identity');
  return createVerifiedWriteReceipt({
    operationId: action.id || `daily_plan_action.complete:${eventId}`,
    resourceType: 'intervention_event',
    resourceId: eventId,
  });
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
  const raw = action.payload?.write_intent_id;
  const id = normalizeNumericId(raw);
  const expectedSuffix = action.action === 'write_intent.dismiss' ? `/write-intents/${id}/dismiss` : `/write-intents/${id}/confirm`;
  if (action.endpoint !== expectedSuffix) {
    throw new Error('unsupported_card_action_endpoint');
  }
  return id;
}

function readAIGCMediaConfirmationID(action: ChatCardActionDescriptor): string {
  const prefix = 'aigc_media.confirm:';
  const id = optionalText(action.id)?.startsWith(prefix)
    ? optionalText(action.id)!.slice(prefix.length)
    : undefined;
  if (!id || !/^[A-Za-z0-9_-]{1,80}$/.test(id)) {
    throw new Error('invalid_aigc_media_confirmation_id');
  }
  const endpoint = `/aigc/media/confirmations/${encodeURIComponent(id)}/confirm`;
  assertEndpoint(action, endpoint);
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

async function backfillEstimatedNutrition(recordId: number, record: Record<string, unknown>): Promise<DietNutritionStatus> {
  try {
    const foodItems = readFoodItems(record.food_items);
    const { data } = await api.post(`/diet/estimate-nutrition?food_description=${encodeURIComponent(foodItems)}`);
    const patch = readNutritionPatch(data, record);
    if (!Object.keys(patch).length) return 'estimate_failed';
    await api.put(`/diet/records/${recordId}`, patch);
    return 'estimated';
  } catch {
    return 'estimate_failed';
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
