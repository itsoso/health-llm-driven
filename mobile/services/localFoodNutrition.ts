import foodsDocument from '../assets/food-nutrition/foods.json';

type Nutrients = {
  calories: number;
  protein: number;
  carbs: number;
  fat: number;
  fiber: number;
};

type FoodRow = {
  food_id: string;
  canonical_name: string;
  aliases: string[];
  nutrients_per_100g: Nutrients;
  portions: {
    unit: string;
    grams: number;
    basis: 'source_portion' | 'localized_estimate';
    source_modifier: string;
  }[];
  source: {
    provider: string;
    release: string;
    fdc_id: number;
    data_type: string;
  };
};

export type LocalFoodAmount = {
  grams?: number;
  count?: number;
  unit?: string;
};

export type ParsedLocalFoodAmount = LocalFoodAmount & { name: string };

export type LocalFoodNutritionResult =
  | { status: 'not_found' }
  | { status: 'ambiguous'; candidates: string[] }
  | { status: 'unsupported_amount'; foodId: string; canonicalName: string }
  | {
      status: 'matched';
      foodId: string;
      canonicalName: string;
      grams: number;
      nutrients: Nutrients;
      source: {
        provider: string;
        release: string;
        fdcId: number;
        dataType: string;
      };
      portionBasis: 'measured' | 'source_portion' | 'estimated_portion';
    };

const foods = (foodsDocument.foods as FoodRow[]);
const numberWords: Record<string, number> = {
  半: 0.5,
  一: 1,
  二: 2,
  两: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
  十: 10,
};

function boundedAmount(raw: string): number | null {
  const value = numberWords[raw] ?? Number(raw);
  return Number.isFinite(value) && value > 0 && value <= 5_000 ? value : null;
}

function normalizeName(value: string): string {
  return value.trim().replace(/[，,。；;]+$/g, '').replace(/\s+/g, ' ');
}

export function parseLocalFoodAmount(input: string): ParsedLocalFoodAmount {
  const text = normalizeName(input);
  const gramsMatch = text.match(/^(.+?)(\d+(?:\.\d+)?)\s*(?:g|克)$/i);
  if (gramsMatch) {
    const grams = boundedAmount(gramsMatch[2]);
    if (grams !== null) return { name: normalizeName(gramsMatch[1]), grams };
  }
  const prefixMatch = text.match(/^(半|[一二两三四五六七八九十]|\d+(?:\.\d+)?)(个|碗|杯|根|份|块|盘|勺)(.+)$/);
  if (prefixMatch) {
    const count = boundedAmount(prefixMatch[1]);
    if (count !== null && count <= 20) {
      return { name: normalizeName(prefixMatch[3]), count, unit: prefixMatch[2] };
    }
  }
  const suffixMatch = text.match(/^(.+?)(\d+(?:\.\d+)?)(个|碗|杯|根|份|块|盘|勺)$/);
  if (suffixMatch) {
    const count = boundedAmount(suffixMatch[2]);
    if (count !== null && count <= 20) {
      return { name: normalizeName(suffixMatch[1]), count, unit: suffixMatch[3] };
    }
  }
  return { name: text };
}

export function lookupLocalFoodNutrition(
  name: string,
  amount: LocalFoodAmount,
): LocalFoodNutritionResult {
  const normalized = normalizeName(name);
  const matches = foods.filter((food) => (
    food.canonical_name === normalized || food.aliases.includes(normalized)
  ));
  if (!matches.length) return { status: 'not_found' };
  if (matches.length > 1) {
    return { status: 'ambiguous', candidates: matches.map((food) => food.canonical_name) };
  }
  const food = matches[0];
  let grams: number | null = null;
  let portionBasis: 'measured' | 'source_portion' | 'estimated_portion' = 'measured';
  if (typeof amount.grams === 'number' && Number.isFinite(amount.grams)
      && amount.grams > 0 && amount.grams <= 5_000) {
    grams = amount.grams;
  } else if (typeof amount.count === 'number' && Number.isFinite(amount.count)
      && amount.count > 0 && amount.count <= 20 && amount.unit) {
    const portion = food.portions.find((candidate) => candidate.unit === amount.unit);
    if (portion) {
      grams = portion.grams * amount.count;
      portionBasis = portion.basis === 'source_portion' ? 'source_portion' : 'estimated_portion';
    }
  }
  if (grams === null) {
    return {
      status: 'unsupported_amount',
      foodId: food.food_id,
      canonicalName: food.canonical_name,
    };
  }
  const factor = grams / 100;
  const nutrients = Object.fromEntries(
    Object.entries(food.nutrients_per_100g).map(([key, value]) => [
      key,
      Math.round(value * factor * 1_000_000) / 1_000_000,
    ]),
  ) as Nutrients;
  return {
    status: 'matched',
    foodId: food.food_id,
    canonicalName: food.canonical_name,
    grams,
    nutrients,
    source: {
      provider: food.source.provider,
      release: food.source.release,
      fdcId: food.source.fdc_id,
      dataType: food.source.data_type,
    },
    portionBasis,
  };
}
