export interface ExerciseRecommendation {
  type: string;
  location: string;
  duration: string;
  intensity: string;
  best_time: string;
  reason: string;
}

export interface DailyRecommendation {
  status: string;
  date: string;
  analysis_date: string;
  user: string;
  sleep_analysis: {
    status: string;
    score: number | null;
    duration_hours: number | null;
    quality_assessment: string;
    trend: string;
    issues: string[];
    recommendations: string[];
  };
  activity_analysis: {
    status: string;
    steps: number | null;
    steps_goal_met: boolean;
    active_minutes: number | null;
    calories_burned: number | null;
    trend: string;
    issues: string[];
    recommendations: string[];
  };
  heart_rate_analysis: {
    status: string;
    resting_hr: number | null;
    avg_hr: number | null;
    hrv: number | null;
    trend: string;
    issues: string[];
    recommendations: string[];
  };
  stress_analysis: {
    stress_level: number | null;
    body_battery_highest: number | null;
    recovery_status: string;
    issues: string[];
    recommendations: string[];
  };
  overall_status: string;
  priority_recommendations: string[];
  enhanced_recommendations?: string[];
  daily_goals: Array<{
    category: string;
    goal: string;
    icon: string;
    target_value: number;
    unit: string;
  }>;
  raw_data: {
    sleep_score: number | null;
    sleep_duration_minutes: number | null;
    steps: number | null;
    resting_heart_rate: number | null;
    stress_level: number | null;
    body_battery_highest: number | null;
    body_battery_current: number | null;
    body_battery_lowest: number | null;
    body_battery_drained: number | null;
  };
  environment?: {
    weather: {
      available: boolean;
      temperature: number | null;
      feels_like: number | null;
      humidity: number | null;
      weather: string;
      wind_speed: number | null;
      summary: string;
    };
    air_quality: {
      available: boolean;
      aqi: number | null;
      level: string;
      description: string;
      pm25: number | null;
      health_implications: string;
    };
    exercise: {
      outdoor_suitable: boolean;
      score: number;
      status: string;
      recommended_activities: string[];
    };
    advices: string[];
    warnings: string[];
  };
  ai_insights?: {
    health_summary: string;
    key_insights: string[];
    today_focus: string;
    encouragement: string;
    warnings: string[];
  };
  ai_advice?: {
    sleep: string;
    activity: string;
    heart_health: string;
    recovery: string;
    environment?: string;
  };
  exercise_recommendations?: ExerciseRecommendation[];
  llm_analysis?: {
    available: boolean;
    error?: string;
    environment_advice?: string;
    exercise_recommendations?: ExerciseRecommendation[];
  };
  // Allow extra fields from seven-day data
  [key: string]: any;
}

export const statusColors: Record<string, string> = {
  excellent: 'bg-green-500',
  good: 'bg-green-400',
  fair: 'bg-yellow-400',
  poor: 'bg-red-400',
  concerning: 'bg-red-500',
  needs_attention: 'bg-orange-400',
  unknown: 'bg-gray-400',
};

export const statusLabels: Record<string, string> = {
  excellent: '优秀',
  good: '良好',
  fair: '一般',
  poor: '较差',
  concerning: '需关注',
  needs_attention: '需要注意',
  unknown: '未知',
};

export const trendIcons: Record<string, string> = {
  improving: '📈',
  stable: '➡️',
  declining: '📉',
  concerning: '⚠️',
};
