/**
 * 运动相关工具函数
 */

// 运动类型映射
export const WORKOUT_TYPE_MAP: Record<string, string> = {
  'RUNNING': '跑步',
  'CARDIO': '心肺训练',
  'WEIGHT_LOSS': '减脂训练',
  'MUSCLE_GAIN': '力量训练',
  'EXERCISE': '有氧运动',
  'CYCLING': '骑行',
  'SWIMMING': '游泳',
  'YOGA': '瑜伽',
  'STRENGTH': '力量训练'
};

// 运动类型图标
export const WORKOUT_TYPE_ICON: Record<string, string> = {
  'RUNNING': '🏃',
  'CARDIO': '💓',
  'WEIGHT_LOSS': '🔥',
  'MUSCLE_GAIN': '💪',
  'EXERCISE': '🏋️',
  'CYCLING': '🚴',
  'SWIMMING': '🏊',
  'YOGA': '🧘',
  'STRENGTH': '💪'
};

/**
 * 获取运动类型的中文名称
 */
export function getWorkoutTypeName(type: string): string {
  return WORKOUT_TYPE_MAP[type] || type;
}

/**
 * 获取运动类型的图标
 */
export function getWorkoutTypeIcon(type: string): string {
  return WORKOUT_TYPE_ICON[type] || '🏃';
}

/**
 * 获取运动类型的完整显示（图标 + 名称）
 */
export function getWorkoutTypeDisplay(type: string): string {
  const icon = getWorkoutTypeIcon(type);
  const name = getWorkoutTypeName(type);
  return `${icon} ${name}`;
}
