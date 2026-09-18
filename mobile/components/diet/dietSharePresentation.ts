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
  nutritionItems: DietShareNutritionItem[];
  tags: string[];
  publicNote: string;
  disclosure: string;
};

export type DietShareNutritionItem = {
  key: 'calories' | 'protein' | 'carbs' | 'fat';
  label: string;
  value: string;
  unit: 'kcal' | 'g';
  qualifier: '约' | null;
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
  | 'ai_confidence'
> & { record_date?: string | null };

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
  return confidence == null || confidence < LOW_CONFIDENCE_THRESHOLD;
}

function metric(value: number | null, approximate = false): string | null {
  return typeof value === 'number' && Number.isFinite(value)
    ? formatDisplayNumber(approximate ? Math.round(value) : value)
    : null;
}

function usesEstimatedNutrition(record: DietShareRecord): boolean {
  return !(record.source && MANUALLY_CONFIRMED_SOURCES.has(record.source));
}

function formatFoodLine(value: string): string {
  return value
    .replace(/\s*\+\s*/g, ' · ')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildMacroLines(record: DietShareRecord): string[] {
  if (isLowConfidence(record)) return ['营养待核对'];

  const approximate = usesEstimatedNutrition(record);
  const qualifier = approximate ? '约 ' : '';
  const calories = metric(record.calories, approximate);
  const protein = metric(record.protein, approximate);
  const carbs = metric(record.carbs, approximate);
  const fat = metric(record.fat, approximate);
  const firstLine = [
    calories != null ? `${qualifier}${calories} kcal` : null,
    protein != null ? `蛋白质${qualifier}${protein}g` : null,
  ].filter((part): part is string => Boolean(part)).join(' · ');
  const secondLine = [
    carbs != null ? `碳水${qualifier}${carbs}g` : null,
    fat != null ? `脂肪${qualifier}${fat}g` : null,
  ].filter((part): part is string => Boolean(part)).join(' · ');
  const lines = [firstLine, secondLine].filter(Boolean);
  return lines.length > 0 ? lines : ['营养估算中'];
}

function buildNutritionItems(record: DietShareRecord): DietShareNutritionItem[] {
  if (isLowConfidence(record)) return [];

  const approximate = usesEstimatedNutrition(record);
  const qualifier = approximate ? '约' : null;
  const candidates: (DietShareNutritionItem | null)[] = [
    metric(record.calories, approximate) != null
      ? { key: 'calories', label: '热量', value: metric(record.calories, approximate)!, unit: 'kcal', qualifier }
      : null,
    metric(record.protein, approximate) != null
      ? { key: 'protein', label: '蛋白质', value: metric(record.protein, approximate)!, unit: 'g', qualifier }
      : null,
    metric(record.carbs, approximate) != null
      ? { key: 'carbs', label: '碳水', value: metric(record.carbs, approximate)!, unit: 'g', qualifier }
      : null,
    metric(record.fat, approximate) != null
      ? { key: 'fat', label: '脂肪', value: metric(record.fat, approximate)!, unit: 'g', qualifier }
      : null,
  ];
  return candidates.filter((item): item is DietShareNutritionItem => item != null);
}

function buildTags(record: DietShareRecord, mealLabel: string): string[] {
  if (isLowConfidence(record)) return ['待核对'];
  return [
    `${mealLabel}记录`,
    usesEstimatedNutrition(record) ? '图片估算' : '营养已确认',
  ];
}

function buildHeadline(record: DietShareRecord, mealLabel: string): string {
  if (isLowConfidence(record)) return '待核对的一餐';
  return `${mealLabel}打卡｜这一餐吃了什么`;
}

function buildDisclosure(record: DietShareRecord): string {
  if (isLowConfidence(record)) return '营养待核对';
  if (record.source && MANUALLY_CONFIRMED_SOURCES.has(record.source)) return '营养已确认';
  if (record.source?.includes('photo') || record.source?.includes('image')) {
    return buildNutritionItems(record).length < 4 ? '部分图片估算 · 仅供记录' : '图片估算 · 仅供记录';
  }
  return '营养估算 · 仅供记录';
}

function buildPublicNote(record: DietShareRecord): string {
  if (isLowConfidence(record)) return '先核对食物与份量，再生成营养记录。';
  if (record.source && MANUALLY_CONFIRMED_SOURCES.has(record.source)) {
    return '这份营养记录已由你确认。';
  }
  if (buildNutritionItems(record).length < 4) {
    return '仅展示可识别部分，实际以食材与份量为准。';
  }
  return '图片估算仅用于日常记录，实际以食材与份量为准。';
}

function normalizedDietRecordDate(value: unknown): string | undefined {
  const raw = text(value);
  const match = raw?.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return undefined;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const parsed = new Date(Date.UTC(year, month - 1, day));
  if (
    parsed.getUTCFullYear() !== year
    || parsed.getUTCMonth() !== month - 1
    || parsed.getUTCDate() !== day
  ) {
    return undefined;
  }
  return raw;
}

export function buildDietShareDateLabel(value: unknown): string {
  const recordDate = normalizedDietRecordDate(value);
  return recordDate ? recordDate.replace(/-/g, '.') : '餐食记录';
}

export function buildDietSharePresentation(record: DietShareRecord): DietSharePresentation {
  const mealLabel = MEAL_LABELS[record.meal_type] ?? '餐食';
  return {
    mealLabel,
    headline: buildHeadline(record, mealLabel),
    foodLine: formatFoodLine(record.food_items),
    macroLines: buildMacroLines(record),
    nutritionItems: buildNutritionItems(record),
    tags: buildTags(record, mealLabel),
    publicNote: buildPublicNote(record),
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
  const recordDate = normalizedDietRecordDate(cardData.record_date);

  const record: DietShareRecord = {
    id: recordId,
    ...(recordDate ? { record_date: recordDate } : {}),
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
    ai_confidence: nullableNumber(cardData.ai_confidence ?? cardData.confidence),
  };
  return { available: true, record, photoUri };
}
