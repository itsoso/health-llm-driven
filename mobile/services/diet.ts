import api from './api';

export type MealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';
export type VoiceMealType = MealType | 'extra';

export interface DietPhotoAsset {
  id: string;
  /** Short-lived private URL returned at read time; never a persisted client value. */
  url: string;
  ordinal: number;
  captured_at: string | null;
  origin: string;
}

export interface DietRecord {
  id: number;
  user_id: number;
  record_date: string;
  meal_type: MealType;
  food_items: string;
  food_id?: string | null;
  source?: string | null;
  calories: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
  fiber: number | null;
  alcohol_units: number | null;
  image_url: string | null;
  image_urls?: string[];
  photo_assets?: DietPhotoAsset[];
  notes: string | null;
  health_tips: string | null;
  ai_recognized?: number | null;
  ai_confidence?: number | null;
  updated_at?: string | null;
}

/**
 * Resolve display-order photos while retaining the old single-image contract.
 * Assets are authoritative because they carry stable ordinal ordering; records
 * created before the asset table retain only `image_url`.
 */
export function dietRecordImageUrls(record: Pick<DietRecord, 'image_url' | 'image_urls' | 'photo_assets'>): string[] {
  const assetUrls = (record.photo_assets ?? [])
    .slice()
    .sort((left, right) => left.ordinal - right.ordinal)
    .map((asset) => asset.url);
  const candidates = assetUrls.length > 0
    ? assetUrls
    : [...(record.image_urls ?? []), record.image_url ?? ''];
  const seen = new Set<string>();
  return candidates.filter((url) => {
    const normalized = String(url ?? '').trim();
    if (!normalized || seen.has(normalized)) return false;
    seen.add(normalized);
    return true;
  });
}

export interface DietRecordCreate {
  record_date: string;
  meal_type: MealType;
  food_items: string;
  food_id?: string;
  source?: string;
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  alcohol_units?: number;
  notes?: string;
  image_base64?: string;
  image_type?: string;
  photo_draft_token?: string;
  /** Client-only. Sent as Idempotency-Key and removed from the JSON body. */
  idempotency_key?: string;
  ai_recognized?: number;
  ai_confidence?: number;
  ai_raw_result?: FoodRecognitionResponse;
  health_tips?: string;
}

export interface DietRecordUpdate {
  meal_type?: MealType;
  food_items?: string;
  food_id?: string | null;
  source?: string | null;
  calories?: number | null;
  protein?: number | null;
  carbs?: number | null;
  fat?: number | null;
  fiber?: number | null;
  alcohol_units?: number | null;
  notes?: string | null;
  health_tips?: string | null;
  ai_recognized?: number | null;
  ai_confidence?: number | null;
  ai_raw_result?: FoodRecognitionResponse | null;
}

export interface DietRecordNutritionRecalculateRequest {
  food_items: string;
  meal_type?: MealType;
  expected_updated_at: string | null;
}

export interface DailyDietSummary {
  record_date: string;
  total_calories: number;
  total_protein: number;
  total_carbs: number;
  total_fat: number;
  total_fiber: number;
  meals_count: number;
  meals: DietRecord[];
}

export interface DietStats {
  average_daily_calories: number | null;
  average_daily_protein: number | null;
  average_daily_carbs: number | null;
  average_daily_fat: number | null;
  total_records: number;
  days_recorded: number;
}

export interface FoodItem {
  name: string;
  quantity: string | null;
  calories: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
  fiber: number | null;
  confidence: number | null;
  food_id?: string | null;
  source?: string | null;
  quantity_grams?: number | null;
  nutrition_basis?: 'food_table' | 'vision_estimate' | string | null;
  portion_basis?: 'vision_estimate' | 'unknown' | 'measured' | 'label' | string | null;
  portion_confidence?: number | null;
}

export interface FoodRecognitionResponse {
  success: boolean;
  foods: FoodItem[];
  meal_description: string | null;
  health_tips: string | null;
  ai_confidence?: number | null;
  confidence?: number | null;
  total_calories: number | null;
  total_protein: number | null;
  total_carbs: number | null;
  total_fat: number | null;
  total_fiber?: number | null;
  photo_draft_token?: string | null;
  timing_ms?: {
    vision: number;
    calibration: number;
    photo_draft: number;
    total: number;
  } | null;
  error: string | null;
}

export interface VoiceFoodDraftItem {
  name: string;
  quantity?: number | null;
  unit?: string | null;
  calories?: number | null;
  protein?: number | null;
  carbs?: number | null;
  fat?: number | null;
}

export interface VoiceFoodParseResponse {
  raw_text: string;
  meal_type: VoiceMealType;
  meal_type_label: string;
  foods: VoiceFoodDraftItem[];
  risk_tags: string[];
  confidence: number;
  needs_confirmation: boolean;
  clarifying_question: string | null;
  parser_version: string;
}

export async function getDailyDiet(date: string): Promise<DailyDietSummary> {
  const { data } = await api.get<DailyDietSummary>(`/diet/records/me/date/${date}`);
  return data;
}

export async function getDietStats(days = 7): Promise<DietStats> {
  const { data } = await api.get<DietStats>('/diet/records/me/stats', { params: { days } });
  return data;
}

export interface FrequentFood {
  food_items: string;
  meal_type: MealType;
  count: number;
  calories: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
}

/**
 * 常吃食物 (后端 /diet/records/me/frequent 按历史频次聚合). 用于一键复用.
 * 营养素是按历史中位数估算, 可能为 null —— 调用方不应假装精确.
 */
export async function getFrequentFoods(limit = 8, days = 30): Promise<FrequentFood[]> {
  const { data } = await api.get<FrequentFood[]>('/diet/records/me/frequent', {
    params: { limit, days },
  });
  return data;
}

export async function createDietRecord(record: DietRecordCreate): Promise<DietRecord> {
  const { idempotency_key: idempotencyKey, ...payload } = record;
  const { data } = await api.post<DietRecord>(
    '/diet/records',
    payload,
    idempotencyKey ? { headers: { 'Idempotency-Key': idempotencyKey } } : undefined,
  );
  if (!data?.id || !Number.isFinite(data.id)) {
    throw new Error('diet_record_missing_id');
  }
  return data;
}

export async function updateDietRecord(id: number, patch: DietRecordUpdate): Promise<DietRecord> {
  const { data } = await api.put<DietRecord>(`/diet/records/${id}`, patch);
  return data;
}

export async function recalculateDietRecordNutrition(
  id: number,
  request: DietRecordNutritionRecalculateRequest,
  idempotencyKey: string,
): Promise<DietRecord> {
  const operationKey = idempotencyKey.trim();
  if (!operationKey) {
    throw new Error('diet_recalculation_idempotency_key_required');
  }
  const { data } = await api.post<DietRecord>(
    `/diet/records/${id}/recalculate-nutrition`,
    request,
    { headers: { 'Idempotency-Key': operationKey } },
  );
  return data;
}

export async function deleteDietRecord(id: number): Promise<void> {
  await api.delete(`/diet/records/${id}`);
}

export async function recognizeFood(imageBase64: string): Promise<FoodRecognitionResponse> {
  const { data } = await api.post<FoodRecognitionResponse>('/diet/recognize', {
    image_base64: imageBase64,
    image_type: 'jpeg',
    create_photo_draft: true,
  });
  return data;
}

export async function discardDietPhotoDraft(token: string): Promise<void> {
  await api.delete(`/diet/photo-drafts/${encodeURIComponent(token)}`);
}

export async function getDietPhotoDraftStatus(
  token: string,
): Promise<{ status: 'pending'; expires_at: string }> {
  const { data } = await api.get<{ status: 'pending'; expires_at: string }>(
    `/diet/photo-drafts/${encodeURIComponent(token)}/status`,
  );
  return data;
}

export async function estimateNutrition(description: string): Promise<FoodRecognitionResponse> {
  const { data } = await api.post<FoodRecognitionResponse>(`/diet/estimate-nutrition?food_description=${encodeURIComponent(description)}`);
  return data;
}

export async function parseVoiceFood(rawText: string, mealType?: MealType): Promise<VoiceFoodParseResponse> {
  const { data } = await api.post<VoiceFoodParseResponse>('/diet/voice/parse', {
    raw_text: rawText,
    meal_type: mealType,
  });
  return data;
}
