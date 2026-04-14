// 运动记录类型
export interface WorkoutSummary {
  id: number;
  workout_date: string;
  workout_type: string;
  workout_name: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  avg_heart_rate: number | null;
  calories: number | null;
  feeling: string | null;
  has_ai_analysis: boolean;
}

// 饮食记录类型
export interface DietRecord {
  id: number;
  record_date: string;
  meal_type: string;
  food_items: string;
  calories: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
  fiber: number | null;
}

// 每日饮食汇总
export interface DailyDietSummary {
  record_date: string;
  total_calories: number;
  total_protein: number;
  total_carbs: number;
  total_fat: number;
  total_fiber: number;
  meals_count: number;
  meals: DietRecord[];
}

export interface GarminData {
  id: number;
  record_date: string;
  sleep_score: number | null;
  total_sleep_duration: number | null;
  sleep_start_time: string | null;
  sleep_end_time: string | null;
  resting_heart_rate: number | null;
  avg_heart_rate: number | null;
  hrv: number | null;
  hrv_status: string | null;
  hrv_7day_avg: number | null;
  steps: number | null;
  calories_burned: number | null;
  active_calories: number | null;
  bmr_calories: number | null;
  active_minutes: number | null;
  intensity_minutes_goal: number | null;
  moderate_intensity_minutes: number | null;
  vigorous_intensity_minutes: number | null;
  stress_level: number | null;
  body_battery_charged: number | null;
  body_battery_drained: number | null;
  body_battery_most_charged: number | null;
  body_battery_lowest: number | null;
  body_battery_current: number | null;
  avg_respiration_awake: number | null;
  avg_respiration_sleep: number | null;
  lowest_respiration: number | null;
  highest_respiration: number | null;
  spo2_avg: number | null;
  spo2_min: number | null;
  spo2_max: number | null;
  vo2max_running: number | null;
  floors_climbed: number | null;
  distance_meters: number | null;
}

// 格式化时长
export function formatDuration(minutes: number | null | undefined): string {
  if (!minutes) return '--';
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}小时${mins}分钟`;
}

// HRV状态翻译
export function getHrvStatusText(status: string | null | undefined): { text: string; color: string } {
  const statusMap: Record<string, { text: string; color: string }> = {
    'BALANCED': { text: '平衡', color: 'text-green-500' },
    'balanced': { text: '平衡', color: 'text-green-500' },
    'UNBALANCED': { text: '不平衡', color: 'text-orange-500' },
    'unbalanced': { text: '不平衡', color: 'text-orange-500' },
    'LOW': { text: '偏低', color: 'text-red-500' },
    'low': { text: '偏低', color: 'text-red-500' },
  };
  return statusMap[status || ''] || { text: status || '--', color: 'text-gray-500' };
}

// 格式化睡眠时间 (HH:MM:SS -> 北京时间24小时制)
export function formatSleepTime(timeStr: string | null | undefined): string {
  if (!timeStr) return '--';
  try {
    const [hours, minutes] = timeStr.split(':').map(Number);
    return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}`;
  } catch {
    return '--';
  }
}

// 睡眠分数颜色
export function getSleepScoreColor(score: number | null | undefined): string {
  if (!score) return 'text-gray-400';
  if (score >= 80) return 'text-blue-400';
  if (score >= 60) return 'text-green-400';
  if (score >= 40) return 'text-yellow-400';
  return 'text-red-400';
}

// 卡片组件
export function MetricCard({
  icon,
  title,
  children,
  className = '',
}: {
  icon: string;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`bg-white rounded-2xl shadow-md hover:shadow-lg transition-shadow duration-200 p-5 flex flex-col ${className}`}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xl">{icon}</span>
        <span className="text-gray-600 font-medium text-sm">{title}</span>
      </div>
      <div className="flex-1">
        {children}
      </div>
    </div>
  );
}

// 获取运动类型名称
export function getWorkoutTypeName(type: string): string {
  const typeMap: Record<string, string> = {
    running: '跑步',
    walking: '步行',
    cycling: '骑行',
    swimming: '游泳',
    strength: '力量训练',
    yoga: '瑜伽',
    hiking: '徒步',
    other: '其他',
  };
  return typeMap[type] || type;
}

// 获取餐食类型名称
export function getMealTypeName(type: string): string {
  const typeMap: Record<string, string> = {
    breakfast: '早餐',
    lunch: '午餐',
    dinner: '晚餐',
    snack: '加餐',
    extra: '其他',
  };
  return typeMap[type] || type;
}
