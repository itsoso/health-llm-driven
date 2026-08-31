import { isMedicationRecordItem } from '../services/medicationFilters';

const DIET_FOOD_HOMOGRAPHS_RE = /山药/g;

export function assertDietFoodItemsAllowed(
  foodItems: string,
  options: { ownerBoundPhotoDraft?: boolean } = {},
): void {
  if (looksLikeDietManagementIntent(foodItems)) {
    throw new Error('invalid_diet_food_items_management');
  }
  if (looksLikeNonDietIntake(foodItems)) {
    // Owner-bound photo drafts may contain food slice counts such as `胡萝卜
    // 约3片`. Defer only that ambiguous unit; known medication/supplement
    // signals remain blocked locally and by the canonical backend guard.
    const onlyAmbiguousPhotoSlice = options.ownerBoundPhotoDraft
      && looksLikeOnlyAmbiguousPhotoSlice(foodItems);
    if (!onlyAmbiguousPhotoSlice) {
      throw new Error('invalid_diet_food_items_non_diet');
    }
  }
  if (looksLikeHealthMetricIntent(foodItems)) {
    throw new Error('invalid_diet_food_items_health_metric');
  }
}

export function looksLikeDietManagementIntent(value: string): boolean {
  const normalized = value.replace(/\s+/g, '').toLowerCase();
  return [
    '删除',
    '删掉',
    '删了',
    '删去',
    '移除',
    '撤销',
    '取消记录',
    '取消这一餐',
    '取消这餐',
    '误删',
    '不小心删',
    '恢复',
    '找回',
  ].some((marker) => normalized.includes(marker.toLowerCase()));
}

export function looksLikeNonDietIntake(value: string): boolean {
  const normalizedValue = value
    .normalize('NFKC')
    .replace(/[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]/g, '-')
    .replace(/[\u200B-\u200D\u2060\uFEFF]/g, '');
  // The shared medication classifier intentionally treats `药` as a strong
  // signal. In a diet payload, remove only confirmed food homographs before
  // applying that classifier. Explicit residual signals still block entries
  // such as `山药胶囊` or `山药 + 阿司匹林 1片`.
  const medicationCandidate = normalizedValue.replace(DIET_FOOD_HOMOGRAPHS_RE, ' ');
  if (isMedicationRecordItem({ name: medicationCandidate })) return true;
  // 饮品里常见的维 C 茶/柠檬饮料不应被补剂关键词误杀。
  if (/维\s*c\s*(?:茶|饮|饮料|果汁|柠檬|柠)/i.test(normalizedValue)) return false;
  if (/鱼油|维生素|维\s*d|b族|益生菌|辅酶\s*q?\s*10|甘氨酸镁|钙片|叶酸|锌片/i.test(normalizedValue)) {
    return true;
  }
  const compactValue = normalizedValue.replace(/[\s-]+/g, '');
  if (/(?:vitamind|d[23]|b12|coq10)(?:and)?(?:fishoil|magnesium|nac|omega3)|(?:fishoil|magnesium|nac|omega3)(?:and)?(?:vitamind|d[23]|b12|coq10)/i.test(compactValue)) {
    return true;
  }
  return /(^|[^a-z0-9])(?:vitamin[\s-]*[a-z]\d*|d3|d2|b12|coq[\s-]*10|nac|magnesium|glycinate|fish[\s-]*oil|omega(?:[\s-]*3)?)(?=$|[^a-z0-9]|\d+(?:\.\d+)?\s*(?:mg|mcg|μg|ug|iu|ml|g|粒|片|颗|袋|包|滴|tablet|capsule|softgel))/i.test(normalizedValue);
}

function looksLikeOnlyAmbiguousPhotoSlice(value: string): boolean {
  // `片` alone is not a reliable medication signal in an owner-bound meal
  // photo: it is also part of legitimate food names (`萝卜片`) and food
  // portions (`胡萝卜 3片`). Remove only that ambiguous marker, then run the
  // complete medication/supplement guard again. Strong signals such as drug
  // names, dosage suffixes, fish oil, or vitamins remain blocked here and by
  // the canonical backend classifier.
  const withoutAmbiguousSliceMarker = value.replace(/片/g, ' ');
  if (withoutAmbiguousSliceMarker === value) return false;
  return !looksLikeNonDietIntake(withoutAmbiguousSliceMarker);
}

export function looksLikeHealthMetricIntent(value: string): boolean {
  const normalized = value.replace(/\s+/g, '').toLowerCase();
  return Boolean(
    /(?:跑步|晨跑|夜跑|快走|步数|运动|训练|健身|游泳|骑行)\d*(?:分钟|分|步|公里|km|千米)?/i.test(normalized)
    || /(?:体重|腰围|臀围|体脂|bmi)\d+(?:\.\d+)?(?:kg|公斤|斤|cm|厘米|%)?/i.test(normalized)
    || /(?:睡了|睡眠|入睡|起床|醒来|午睡|小睡)\d+(?:\.\d+)?(?:小时|h|分钟|分)?/i.test(normalized)
    || /(?:血压|收缩压|舒张压)\d{2,3}\/\d{2,3}/i.test(normalized)
    || /(?:血糖|空腹血糖|餐后血糖)\d+(?:\.\d+)?/i.test(normalized)
    || /(?:心率|静息心率|rhr)\d{2,3}/i.test(normalized)
  );
}
