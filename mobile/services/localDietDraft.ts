import type { DietRecordCreate, MealType } from './diet';
import {
  lookupLocalFoodNutrition,
  parseLocalFoodAmount,
  type LocalFoodNutritionResult,
} from './localFoodNutrition';

export type LocalDietDraftItem = {
  raw: string;
  name: string;
  grams?: number;
  matchStatus: LocalFoodNutritionResult['status'];
  canonicalName?: string;
  foodId?: string;
  portionBasis?: 'measured' | 'source_portion' | 'estimated_portion';
};

export type LocalDietDraft = {
  rawText: string;
  mealType: MealType;
  items: LocalDietDraftItem[];
  nutritionComplete: boolean;
  needsConfirmation: true;
  record: DietRecordCreate;
};

const mealPrefixes: { pattern: RegExp; mealType: MealType }[] = [
  { pattern: /^(早餐|早饭|早上)/, mealType: 'breakfast' },
  { pattern: /^(午餐|午饭|中午)/, mealType: 'lunch' },
  { pattern: /^(晚餐|晚饭|晚上)/, mealType: 'dinner' },
  { pattern: /^(加餐|零食|夜宵)/, mealType: 'snack' },
];

function inferMealType(text: string, fallback?: MealType): MealType {
  return mealPrefixes.find(({ pattern }) => pattern.test(text))?.mealType ?? fallback ?? 'snack';
}

function stripMealPrefix(text: string): string {
  for (const { pattern } of mealPrefixes) {
    if (pattern.test(text)) return text.replace(pattern, '').trim();
  }
  return text.trim();
}

function tokenize(text: string): string[] {
  const normalized = text.trim().replace(/[；;]/g, '、');
  const quantity = '(?:半|[一二两三四五六七八九十]|\\d+(?:\\.\\d+)?)';
  const unit = '(?:个|碗|杯|根|份|块|盘|勺)';
  const pattern = new RegExp(
    `${quantity}${unit}.+?(?=${quantity}${unit}|[+、，,和与]|$)`,
    'g',
  );
  const quantityMatches = [...normalized.matchAll(pattern)].map((match) => match[0].trim());
  if (quantityMatches.length) return quantityMatches;
  const split = normalized.split(/[+、，,和与]/).map((part) => part.trim()).filter(Boolean);
  return split.length ? split : [normalized];
}

function sum(items: { nutrition: Extract<LocalFoodNutritionResult, { status: 'matched' }> }[], key: keyof Extract<LocalFoodNutritionResult, { status: 'matched' }>['nutrients']) {
  return Math.round(items.reduce((total, item) => total + item.nutrition.nutrients[key], 0) * 1_000_000) / 1_000_000;
}

export function createLocalDietDraft(
  input: string,
  recordDate: string,
  fallbackMealType?: MealType,
): LocalDietDraft {
  const rawText = input.trim().slice(0, 500);
  if (!rawText || !/^\d{4}-\d{2}-\d{2}$/.test(recordDate)) {
    throw new Error('local_diet_draft_invalid');
  }
  const mealType = inferMealType(rawText, fallbackMealType);
  const body = stripMealPrefix(rawText);
  const parsed = tokenize(body).map((raw) => {
    const amount = parseLocalFoodAmount(raw);
    const nutrition = lookupLocalFoodNutrition(amount.name, amount);
    const item: LocalDietDraftItem = {
      raw,
      name: amount.name,
      matchStatus: nutrition.status,
    };
    if (nutrition.status === 'matched') {
      Object.assign(item, {
        grams: nutrition.grams,
        canonicalName: nutrition.canonicalName,
        foodId: nutrition.foodId,
        portionBasis: nutrition.portionBasis,
      });
      return { item, nutrition };
    }
    if (nutrition.status === 'unsupported_amount') {
      Object.assign(item, {
        canonicalName: nutrition.canonicalName,
        foodId: nutrition.foodId,
      });
    }
    return { item, nutrition: null };
  });
  const nutritionComplete = parsed.every(({ nutrition }) => nutrition?.status === 'matched');
  const matched = parsed.filter(
    (entry): entry is { item: LocalDietDraftItem; nutrition: Extract<LocalFoodNutritionResult, { status: 'matched' }> } => (
      entry.nutrition?.status === 'matched'
    ),
  );
  const record: DietRecordCreate = {
    record_date: recordDate,
    meal_type: mealType,
    food_items: parsed.map(({ item }) => item.raw).join('、'),
    source: nutritionComplete ? 'local_deterministic_usda' : 'local_manual_unknown_nutrition',
  };
  if (nutritionComplete && matched.length) {
    record.calories = sum(matched, 'calories');
    record.protein = sum(matched, 'protein');
    record.carbs = sum(matched, 'carbs');
    record.fat = sum(matched, 'fat');
    record.fiber = sum(matched, 'fiber');
  }
  return {
    rawText,
    mealType,
    items: parsed.map(({ item }) => item),
    nutritionComplete,
    needsConfirmation: true,
    record,
  };
}
