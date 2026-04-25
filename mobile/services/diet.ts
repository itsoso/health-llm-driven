import api from './api';

export interface DietRecord {
  id: number;
  user_id: number;
  record_date: string;
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  food_items: string;
  calories: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
  fiber: number | null;
  alcohol_units: number | null;
  image_url: string | null;
  notes: string | null;
  health_tips: string | null;
}

export interface DietRecordCreate {
  record_date: string;
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  food_items: string;
  calories?: number;
  protein?: number;
  carbs?: number;
  fat?: number;
  fiber?: number;
  alcohol_units?: number;
  notes?: string;
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
}

export interface FoodRecognitionResponse {
  success: boolean;
  foods: FoodItem[];
  meal_description: string | null;
  health_tips: string | null;
  total_calories: number | null;
  total_protein: number | null;
  total_carbs: number | null;
  total_fat: number | null;
  error: string | null;
}

export async function getDailyDiet(date: string): Promise<DailyDietSummary> {
  const { data } = await api.get<DailyDietSummary>(`/diet/records/me/date/${date}`);
  return data;
}

export async function getDietStats(days = 7): Promise<DietStats> {
  const { data } = await api.get<DietStats>('/diet/records/me/stats', { params: { days } });
  return data;
}

export async function createDietRecord(record: DietRecordCreate): Promise<DietRecord> {
  const { data } = await api.post<DietRecord>('/diet/records', record);
  return data;
}

export async function deleteDietRecord(id: number): Promise<void> {
  await api.delete(`/diet/records/${id}`);
}

export async function recognizeFood(imageBase64: string): Promise<FoodRecognitionResponse> {
  const { data } = await api.post<FoodRecognitionResponse>('/diet/recognize', {
    image_base64: imageBase64,
    image_type: 'jpeg',
  });
  return data;
}

export async function estimateNutrition(description: string): Promise<FoodRecognitionResponse> {
  const { data } = await api.post<FoodRecognitionResponse>(`/diet/estimate-nutrition?food_description=${encodeURIComponent(description)}`);
  return data;
}
