import { isMedicationRecordItem } from '../services/medicationFilters';

export function assertDietFoodItemsAllowed(
  foodItems: string,
  options: { ownerBoundPhotoDraft?: boolean } = {},
): void {
  if (looksLikeDietManagementIntent(foodItems)) {
    throw new Error('invalid_diet_food_items_management');
  }
  // Server-bound photo drafts are owner-scoped, expiring capabilities. Their
  // canonical backend guard remains authoritative; the broad local `片`
  // heuristic must not reject valid food portions before the request exists.
  if (!options.ownerBoundPhotoDraft && looksLikeNonDietIntake(foodItems)) {
    throw new Error('invalid_diet_food_items_non_diet');
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
  if (isMedicationRecordItem({ name: value })) return true;
  // 饮品里常见的维 C 茶/柠檬饮料不应被补剂关键词误杀。
  if (/维\s*c\s*(?:茶|饮|饮料|果汁|柠檬|柠)/i.test(value)) return false;
  if (/鱼油|维生素|维\s*d|d3|d2|b族|益生菌|辅酶\s*q?\s*10|甘氨酸镁|钙片|叶酸|锌片/i.test(value)) {
    return true;
  }
  return /(^|[^a-z0-9])(?:nac|magnesium|glycinate)(?=$|[^a-z0-9])/i.test(value);
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
