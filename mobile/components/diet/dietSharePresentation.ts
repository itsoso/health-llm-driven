import { BASE_URL } from '../../services/api';
import type { DietRecord, MealType } from '../../services/diet';
import { formatDisplayNumber } from '../../utils/displayNumber';

const MEAL_LABELS: Record<MealType, string> = {
  breakfast: '早餐',
  lunch: '午餐',
  dinner: '晚餐',
  snack: '加餐',
};

const LOW_CONFIDENCE_THRESHOLD = 0.7;
const MANUALLY_CONFIRMED_SOURCES = new Set(['manual', 'user_corrected']);

export type DietSharePresentation = {
  mealLabel: string;
  headline: string;
  foodLine: string;
  macroLines: string[];
  tags: string[];
  nextAction?: string;
  disclosure: string;
};

/**
 * Public-poster projection of a persisted diet record.
 *
 * Chat cards intentionally do not expose `user_id`; requiring a full
 * `DietRecord` here would force the adapter to invent private business data.
 */
export type DietShareRecord = Pick<
  DietRecord,
  | 'id'
  | 'meal_type'
  | 'food_items'
  | 'source'
  | 'calories'
  | 'protein'
  | 'carbs'
  | 'fat'
  | 'fiber'
  | 'image_url'
  | 'image_urls'
  | 'health_tips'
  | 'ai_confidence'
>;

export type ChatDietShareInput =
  | { available: true; record: DietShareRecord; photoUri: string }
  | { available: false; reason: 'unverified' | 'photo_missing' | 'record_missing' };

type ChatDietReceipt = {
  status?: string;
  resourceType?: string;
  resourceId?: string;
};

type DietPhotoCardData = {
  photo_url?: unknown;
  photo_urls?: unknown;
};

function text(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function foodText(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(text).filter((item): item is string => Boolean(item)).join(' + ');
  }
  return text(value) ?? '';
}

function numberValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value.trim());
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function nullableNumber(value: unknown): number | null {
  return numberValue(value) ?? null;
}

function mealTypeValue(value: unknown): MealType | undefined {
  const raw = text(value);
  return raw && raw in MEAL_LABELS ? raw as MealType : undefined;
}

function normalizedConfidence(record: DietShareRecord): number | null {
  const value = record.ai_confidence;
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  const normalized = value > 1 ? value / 100 : value;
  return normalized >= 0 && normalized <= 1 ? normalized : null;
}

function isLowConfidence(record: DietShareRecord): boolean {
  if (record.source && MANUALLY_CONFIRMED_SOURCES.has(record.source)) return false;
  const confidence = normalizedConfidence(record);
  return confidence != null && confidence < LOW_CONFIDENCE_THRESHOLD;
}

function metric(value: number | null): string | null {
  return typeof value === 'number' && Number.isFinite(value)
    ? formatDisplayNumber(value)
    : null;
}

function buildMacroLines(record: DietShareRecord): string[] {
  if (isLowConfidence(record)) return ['营养待核对'];

  const calories = metric(record.calories);
  const protein = metric(record.protein);
  const carbs = metric(record.carbs);
  const fat = metric(record.fat);
  const firstLine = [
    calories != null ? `约 ${calories} kcal` : null,
    protein != null ? `蛋白质 ${protein}g` : null,
  ].filter((part): part is string => Boolean(part)).join(' · ');
  const secondLine = [
    carbs != null ? `碳水 ${carbs}g` : null,
    fat != null ? `脂肪 ${fat}g` : null,
  ].filter((part): part is string => Boolean(part)).join(' · ');
  const lines = [firstLine, secondLine].filter(Boolean);
  return lines.length > 0 ? lines : ['营养估算中'];
}

function buildTags(record: DietShareRecord): string[] {
  if (isLowConfidence(record)) return ['待核对'];
  const tags: string[] = [];
  if (typeof record.protein === 'number' && record.protein >= 30) tags.push('高蛋白');
  if (typeof record.fat === 'number' && record.fat <= 12) tags.push('低脂');
  if (typeof record.fiber === 'number' && record.fiber >= 5) tags.push('含纤维');
  if (typeof record.calories === 'number' && record.calories <= 450) tags.push('轻负担');
  return tags.slice(0, 3);
}

function buildHeadline(record: DietShareRecord, mealLabel: string): string {
  if (isLowConfidence(record)) return '待核对的一餐';
  if (typeof record.calories === 'number' && record.calories >= 700) {
    return `今天的${mealLabel}，能量很足`;
  }
  if (typeof record.protein === 'number' && record.protein >= 30) {
    return `今天的${mealLabel}，蛋白质很在线`;
  }
  return `今天的${mealLabel}，认真吃好`;
}

function buildDisclosure(record: DietShareRecord): string {
  if (isLowConfidence(record)) return '营养待核对';
  if (record.source && MANUALLY_CONFIRMED_SOURCES.has(record.source)) return '营养数据已由用户确认';
  if (record.source?.includes('photo') || record.source?.includes('image')) return '营养由图片估算';
  return '营养数据为估算值';
}

export function buildDietSharePresentation(record: DietShareRecord): DietSharePresentation {
  const mealLabel = MEAL_LABELS[record.meal_type] ?? '餐食';
  // Low-confidence AI copy may contain exact macro/calorie targets even when the
  // structured nutrition fields are hidden. Omit it until the meal is reviewed.
  const nextAction = isLowConfidence(record) ? undefined : text(record.health_tips);
  return {
    mealLabel,
    headline: buildHeadline(record, mealLabel),
    foodLine: record.food_items.trim(),
    macroLines: buildMacroLines(record),
    tags: buildTags(record),
    ...(nextAction ? { nextAction } : {}),
    disclosure: buildDisclosure(record),
  };
}

export function normalizePrivateDietPhotoUri(value: unknown): string | undefined {
  const raw = text(value);
  if (!raw) return undefined;
  try {
    const trustedBase = new URL(BASE_URL);
    if (
      (trustedBase.protocol !== 'https:' && trustedBase.protocol !== 'http:')
      || trustedBase.username
      || trustedBase.password
    ) {
      return undefined;
    }
    const resolved = new URL(raw, `${trustedBase.origin}/`);
    if (
      resolved.origin !== trustedBase.origin
      || resolved.protocol !== trustedBase.protocol
      || resolved.username
      || resolved.password
    ) {
      return undefined;
    }
    return resolved.toString();
  } catch {
    return undefined;
  }
}

export function privateDietPhotoUris(data: DietPhotoCardData): string[] {
  const values = Array.isArray(data.photo_urls) ? data.photo_urls : [data.photo_url];
  const uris: string[] = [];
  const seen = new Set<string>();
  values.forEach((value) => {
    const uri = normalizePrivateDietPhotoUri(value);
    if (uri && !seen.has(uri)) {
      seen.add(uri);
      uris.push(uri);
    }
  });
  return uris;
}

function firstSuggestion(value: unknown): string | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.map(text).find((item): item is string => Boolean(item));
}

function persistedRecordId(value: unknown): number | null {
  const parsed = numberValue(value);
  return parsed != null && Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export function buildChatDietShareInput(
  cardData: Record<string, unknown>,
  receipt?: ChatDietReceipt | null,
): ChatDietShareInput {
  const cardHasRecordId = cardData.record_id !== undefined && cardData.record_id !== null;
  const cardRecordId = persistedRecordId(cardData.record_id);
  let recordId: number;

  if (receipt?.status === 'verified' && receipt.resourceType === 'diet_record') {
    const receiptRecordId = persistedRecordId(receipt.resourceId);
    if (
      receiptRecordId == null
      || (cardHasRecordId && (cardRecordId == null || cardRecordId !== receiptRecordId))
    ) {
      return { available: false, reason: 'record_missing' };
    }
    recordId = receiptRecordId;
  } else if (receipt == null && cardData.recorded === true) {
    if (cardRecordId == null) return { available: false, reason: 'record_missing' };
    recordId = cardRecordId;
  } else {
    return { available: false, reason: 'unverified' };
  }

  const mealType = mealTypeValue(cardData.meal_type);
  const foodItems = foodText(cardData.food_items);
  if (
    !mealType
    || !foodItems
  ) {
    return { available: false, reason: 'record_missing' };
  }

  const photoUris = privateDietPhotoUris(cardData);
  const photoUri = photoUris[0];
  if (!photoUri) return { available: false, reason: 'photo_missing' };

  const record: DietShareRecord = {
    id: recordId,
    meal_type: mealType,
    food_items: foodItems,
    source: text(cardData.source) ?? null,
    calories: nullableNumber(cardData.calories),
    protein: nullableNumber(cardData.protein),
    carbs: nullableNumber(cardData.carbs),
    fat: nullableNumber(cardData.fat),
    fiber: nullableNumber(cardData.fiber),
    image_url: photoUri,
    image_urls: photoUris,
    health_tips: text(cardData.health_tips) ?? firstSuggestion(cardData.suggestions) ?? null,
    ai_confidence: nullableNumber(cardData.ai_confidence ?? cardData.confidence),
  };
  return { available: true, record, photoUri };
}
