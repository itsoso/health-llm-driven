import type { DietRecordCreate, VoiceFoodParseResponse, VoiceMealType } from '../services/diet';

const RISK_LABELS: Record<string, string> = {
  alcohol: '含酒精',
  sweet_drink: '甜饮',
};

export function voiceDraftToDietDefaults(
  draft: VoiceFoodParseResponse,
  recordDate: string,
): Partial<DietRecordCreate> {
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
    record_date: recordDate,
    meal_type: toRecordMealType(draft.meal_type),
    food_items: foodItems || draft.raw_text,
    calories: sumField(foods, 'calories'),
    protein: sumField(foods, 'protein'),
    carbs: sumField(foods, 'carbs'),
    fat: sumField(foods, 'fat'),
    notes,
  };
}

function foodLabel(food: VoiceFoodParseResponse['foods'][number]): string {
  const name = (food.name || '').trim();
  if (!name) return '';
  const quantity = typeof food.quantity === 'number' && Number.isFinite(food.quantity)
    ? trimNumber(food.quantity)
    : '';
  const unit = food.unit || '';
  return quantity ? `${name} ${quantity}${unit}` : name;
}

function sumField(
  foods: VoiceFoodParseResponse['foods'],
  key: 'calories' | 'protein' | 'carbs' | 'fat',
): number | undefined {
  const values = foods
    .map(food => food[key])
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value));
  if (values.length === 0) return undefined;
  return roundOne(values.reduce((sum, value) => sum + value, 0));
}

function trimNumber(value: number): string {
  return Number.isInteger(value) ? `${value}` : `${roundOne(value)}`;
}

function roundOne(value: number): number {
  return Math.round(value * 10) / 10;
}

function toRecordMealType(mealType: VoiceMealType): DietRecordCreate['meal_type'] {
  return mealType === 'extra' ? 'snack' : mealType;
}
