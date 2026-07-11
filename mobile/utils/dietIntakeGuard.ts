import { isMedicationRecordItem } from '../services/medicationFilters';

export function assertDietFoodItemsAllowed(foodItems: string): void {
  if (looksLikeDietManagementIntent(foodItems)) {
    throw new Error('invalid_diet_food_items_management');
  }
  if (looksLikeDietUiText(foodItems)) {
    throw new Error('invalid_diet_food_items_ui_text');
  }
  if (looksLikeNonDietIntake(foodItems)) {
    throw new Error('invalid_diet_food_items_non_diet');
  }
}

export function looksLikeDietUiText(value: string): boolean {
  const normalized = value.replace(/\s+/g, '');
  return (
    /^(?:和)?(?:早餐|午餐|晚餐|加餐)?食品营养卡$/.test(normalized)
    || /^(?:保存并确认|确认记录|完成修正|保存|确认)$/.test(normalized)
  );
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
