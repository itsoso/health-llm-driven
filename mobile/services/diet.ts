import api from './api';

export interface DietRecord {
  id: number;
  user_id: number;
  record_date: string;
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  food_description: string;
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  fiber_g: number | null;
  photo_url: string | null;
  source: string;
  notes: string | null;
}

export interface DietRecordCreate {
  record_date: string;
  meal_type: 'breakfast' | 'lunch' | 'dinner' | 'snack';
  food_description: string;
  calories?: number;
  protein_g?: number;
  carbs_g?: number;
  fat_g?: number;
  fiber_g?: number;
  notes?: string;
}

export interface DailyDietSummary {
  date: string;
  total_calories: number;
  total_protein_g: number;
  total_carbs_g: number;
  total_fat_g: number;
  total_fiber_g: number;
  meal_count: number;
  records: DietRecord[];
}

export interface DietStats {
  avg_daily_calories: number;
  avg_protein_g: number;
  avg_carbs_g: number;
  avg_fat_g: number;
  days_tracked: number;
  calorie_trend: { date: string; calories: number }[];
}

export interface FoodRecognitionResult {
  food_name: string;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  confidence: number;
}

export interface NutritionEstimate {
  food_description: string;
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
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

export async function recognizeFood(imageUri: string): Promise<FoodRecognitionResult[]> {
  const formData = new FormData();
  formData.append('file', { uri: imageUri, name: 'photo.jpg', type: 'image/jpeg' } as any);
  const { data } = await api.post<FoodRecognitionResult[]>('/diet/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function estimateNutrition(description: string): Promise<NutritionEstimate> {
  const { data } = await api.post<NutritionEstimate>('/diet/estimate-nutrition', { food_description: description });
  return data;
}
