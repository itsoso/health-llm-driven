import * as SecureStore from 'expo-secure-store';

import type { DietRecordCreate, FoodItem, FoodRecognitionResponse } from './diet';

const SNAPSHOT_VERSION = 1;
const PHOTO_DRAFT_TTL_MS = 24 * 60 * 60 * 1_000;
const MAX_FOODS = 8;

export type DietPhotoDraftSnapshot = {
  version: 1;
  saved_at: number;
  expires_at: number;
  record: DietRecordCreate;
};

export function dietPhotoDraftStorageKey(userId: number): string {
  return `diet_photo_draft_v1_user_${Math.max(0, Math.trunc(userId))}`;
}

function compactText(value: unknown, maxLength: number): string | null {
  const text = String(value ?? '').trim();
  return text ? text.slice(0, maxLength) : null;
}

function compactFood(food: FoodItem): FoodItem {
  return {
    name: compactText(food.name, 80) ?? '未命名食物',
    quantity: compactText(food.quantity, 40),
    calories: food.calories,
    protein: food.protein,
    carbs: food.carbs,
    fat: food.fat,
    fiber: food.fiber,
    confidence: food.confidence,
    food_id: compactText(food.food_id, 100),
    source: compactText(food.source, 80),
    quantity_grams: food.quantity_grams,
    nutrition_basis: compactText(food.nutrition_basis, 40),
  };
}

function compactRecognition(
  recognition: FoodRecognitionResponse | undefined,
): FoodRecognitionResponse | undefined {
  if (!recognition) return undefined;
  return {
    success: Boolean(recognition.success),
    foods: (recognition.foods ?? []).slice(0, MAX_FOODS).map(compactFood),
    meal_description: compactText(recognition.meal_description, 500),
    health_tips: null,
    total_calories: recognition.total_calories,
    total_protein: recognition.total_protein,
    total_carbs: recognition.total_carbs,
    total_fat: recognition.total_fat,
    total_fiber: recognition.total_fiber,
    photo_draft_token: compactText(recognition.photo_draft_token, 64),
    timing_ms: recognition.timing_ms,
    error: null,
  };
}

function compactRecord(record: DietRecordCreate): DietRecordCreate {
  return {
    record_date: record.record_date,
    meal_type: record.meal_type,
    food_items: compactText(record.food_items, 500) ?? '未命名餐食',
    food_id: compactText(record.food_id, 100) ?? undefined,
    source: compactText(record.source, 80) ?? undefined,
    calories: record.calories,
    protein: record.protein,
    carbs: record.carbs,
    fat: record.fat,
    fiber: record.fiber,
    alcohol_units: record.alcohol_units,
    notes: compactText(record.notes, 500) ?? undefined,
    image_base64: undefined,
    image_type: compactText(record.image_type, 20) ?? undefined,
    photo_draft_token: compactText(record.photo_draft_token, 64) ?? undefined,
    idempotency_key: compactText(record.idempotency_key, 160) ?? undefined,
    ai_recognized: record.ai_recognized,
    ai_confidence: record.ai_confidence,
    ai_raw_result: compactRecognition(record.ai_raw_result),
    health_tips: undefined,
  };
}

function isSnapshot(value: unknown): value is DietPhotoDraftSnapshot {
  if (!value || typeof value !== 'object') return false;
  const snapshot = value as Partial<DietPhotoDraftSnapshot>;
  const record = snapshot.record as DietRecordCreate | undefined;
  return snapshot.version === SNAPSHOT_VERSION
    && typeof snapshot.saved_at === 'number'
    && typeof snapshot.expires_at === 'number'
    && Boolean(record?.photo_draft_token)
    && Boolean(record?.food_items)
    && Boolean(record?.record_date)
    && ['breakfast', 'lunch', 'dinner', 'snack'].includes(String(record?.meal_type));
}

export async function saveDietPhotoDraft(
  userId: number,
  record: DietRecordCreate,
  now = Date.now(),
): Promise<void> {
  if (!record.photo_draft_token) return;
  const snapshot: DietPhotoDraftSnapshot = {
    version: SNAPSHOT_VERSION,
    saved_at: now,
    expires_at: now + PHOTO_DRAFT_TTL_MS,
    record: compactRecord(record),
  };
  await SecureStore.setItemAsync(
    dietPhotoDraftStorageKey(userId),
    JSON.stringify(snapshot),
    { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY },
  );
}

export async function loadDietPhotoDraft(
  userId: number,
  now = Date.now(),
): Promise<DietPhotoDraftSnapshot | null> {
  const key = dietPhotoDraftStorageKey(userId);
  const raw = await SecureStore.getItemAsync(key);
  if (!raw) return null;
  try {
    const snapshot: unknown = JSON.parse(raw);
    if (!isSnapshot(snapshot) || snapshot.expires_at <= now) {
      await SecureStore.deleteItemAsync(key);
      return null;
    }
    return snapshot;
  } catch {
    await SecureStore.deleteItemAsync(key);
    return null;
  }
}

export async function clearDietPhotoDraft(userId: number): Promise<void> {
  await SecureStore.deleteItemAsync(dietPhotoDraftStorageKey(userId));
}
