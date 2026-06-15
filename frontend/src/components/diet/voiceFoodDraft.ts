export type DietMealType = 'breakfast' | 'lunch' | 'dinner' | 'snack';
export type VoiceMealType = DietMealType | 'extra';

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
  clarifying_question?: string | null;
  parser_version: string;
}

export interface DietVoiceFormPatch {
  meal_type: DietMealType;
  food_items: string;
  calories: string;
  protein: string;
  carbs: string;
  fat: string;
  notes: string;
}

const RISK_LABELS: Record<string, string> = {
  alcohol: '含酒精',
  sweet_drink: '甜饮',
};

export function voiceDraftToDietForm(draft: VoiceFoodParseResponse): DietVoiceFormPatch {
  const foods = draft.foods ?? [];
  const foodItems = foods.length > 0
    ? foods.map(foodLabel).filter(Boolean).join('、')
    : draft.raw_text;
  const riskLabels = (draft.risk_tags ?? []).map(tag => RISK_LABELS[tag] ?? tag);
  const notes = [
    `语音草稿: ${draft.meal_type_label || draft.meal_type} · 置信度 ${Math.round((draft.confidence ?? 0) * 100)}%`,
    draft.needs_confirmation ? '需确认后保存' : null,
    riskLabels.length > 0 ? `风险标签: ${riskLabels.join('、')}` : null,
    draft.clarifying_question ? `澄清: ${draft.clarifying_question}` : null,
  ].filter(Boolean).join('\n');

  return {
    meal_type: draft.meal_type === 'extra' ? 'snack' : draft.meal_type,
    food_items: foodItems || draft.raw_text,
    calories: formatSum(foods, 'calories'),
    protein: formatSum(foods, 'protein'),
    carbs: formatSum(foods, 'carbs'),
    fat: formatSum(foods, 'fat'),
    notes,
  };
}

function foodLabel(food: VoiceFoodDraftItem): string {
  const name = (food.name || '').trim();
  if (!name) return '';
  const quantity = typeof food.quantity === 'number' && Number.isFinite(food.quantity)
    ? trimNumber(food.quantity)
    : '';
  const unit = food.unit || '';
  return quantity ? `${name} ${quantity}${unit}` : name;
}

function formatSum(foods: VoiceFoodDraftItem[], key: 'calories' | 'protein' | 'carbs' | 'fat'): string {
  const values = foods
    .map(food => food[key])
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (values.length === 0) return '';
  return trimNumber(values.reduce((sum, value) => sum + value, 0));
}

function trimNumber(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded}` : `${rounded}`;
}
