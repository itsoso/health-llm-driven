/**
 * 共享常量定义
 */

// 睡眠评分等级
export const SLEEP_SCORE_LEVELS = {
  EXCELLENT: { min: 85, label: '优秀', color: '#22c55e' },
  GOOD: { min: 70, label: '良好', color: '#3b82f6' },
  FAIR: { min: 50, label: '一般', color: '#f59e0b' },
  POOR: { min: 0, label: '较差', color: '#ef4444' },
};

// HRV 状态
export const HRV_STATUS = {
  BALANCED: { label: '平衡', color: '#22c55e' },
  UNBALANCED: { label: '失衡', color: '#f59e0b' },
  LOW: { label: '偏低', color: '#ef4444' },
};

// 压力等级
export const STRESS_LEVELS = {
  REST: { max: 25, label: '休息', color: '#3b82f6' },
  LOW: { max: 50, label: '低', color: '#22c55e' },
  MEDIUM: { max: 75, label: '中', color: '#f59e0b' },
  HIGH: { max: 100, label: '高', color: '#ef4444' },
};

// 运动类型
export const WORKOUT_TYPES = {
  running: { label: '跑步', icon: '🏃', color: '#f97316' },
  cycling: { label: '骑行', icon: '🚴', color: '#22c55e' },
  swimming: { label: '游泳', icon: '🏊', color: '#3b82f6' },
  walking: { label: '步行', icon: '🚶', color: '#8b5cf6' },
  hiking: { label: '徒步', icon: '🥾', color: '#10b981' },
  strength: { label: '力量', icon: '🏋️', color: '#ef4444' },
  yoga: { label: '瑜伽', icon: '🧘', color: '#ec4899' },
  hiit: { label: 'HIIT', icon: '⚡', color: '#f59e0b' },
  cardio: { label: '有氧', icon: '❤️', color: '#ef4444' },
  other: { label: '其他', icon: '🏅', color: '#6b7280' },
};

// 洗鼻类型
export const NASAL_WASH_TYPES = {
  wash: { label: '洗鼻', icon: '💧', color: '#3b82f6' },
  soak: { label: '泡鼻', icon: '🫧', color: '#8b5cf6' },
};

// 餐食类型
export const MEAL_TYPES = {
  breakfast: { label: '早餐', icon: '🌅', color: '#f59e0b' },
  lunch: { label: '午餐', icon: '☀️', color: '#22c55e' },
  dinner: { label: '晚餐', icon: '🌙', color: '#3b82f6' },
  snack: { label: '加餐', icon: '🍪', color: '#8b5cf6' },
};
