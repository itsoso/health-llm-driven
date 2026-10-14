import type { DietRecord } from './diet';
import { aiConsentRevision } from './aiConsentState';

export type DietRecordProjection = Pick<DietRecord, 'id' | 'user_id' | 'food_items' | 'meal_type' | 'record_date' | 'calories' | 'protein' | 'carbs' | 'fat' | 'fiber' | 'updated_at'>;
type Update = { record: DietRecordProjection; revision: number };
const listeners = new Set<(update: Update) => void>();

/** Ephemeral notification of an authenticated API response, never a write or cache. */
export function publishDietRecordUpdate(record: DietRecordProjection, revision: number): void {
  if (revision !== aiConsentRevision() || !Number.isSafeInteger(record?.id) || record.id <= 0
    || !Number.isSafeInteger(record.user_id) || record.user_id <= 0
    || typeof record.updated_at !== 'string' || !Number.isFinite(Date.parse(record.updated_at))) return;
  const projected = Object.fromEntries(
    ['id', 'user_id', 'food_items', 'meal_type', 'record_date', 'calories', 'protein', 'carbs', 'fat', 'fiber', 'updated_at']
      .map(key => [key, record[key as keyof DietRecordProjection]]),
  ) as DietRecordProjection;
  listeners.forEach(listener => listener({ record: projected, revision }));
}

export function subscribeDietRecordUpdates(listener: (update: Update) => void): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
