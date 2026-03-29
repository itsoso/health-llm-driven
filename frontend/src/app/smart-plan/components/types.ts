import { Dumbbell, Utensils, Moon, Sparkles, MoreHorizontal } from 'lucide-react';
import React from 'react';

export interface PlanItem {
  id: number;
  day_of_week: number;
  category: string;
  title: string;
  description: string | null;
  target_value: number | null;
  target_unit: string | null;
  checkin_template_id: number | null;
  is_completed: boolean;
  completed_at: string | null;
  sort_order: number;
}

export interface WeeklyPlan {
  id: number;
  user_id: number;
  week_start: string;
  status: string;
  focus_areas: string[];
  ai_insights: string[];
  ai_risks: string[];
  weekly_summary: string | null;
  completion_rate: number;
  ai_model: string | null;
  user_feedback: number | null;
  items: PlanItem[];
  created_at: string;
  updated_at: string | null;
}

export interface PlanListItem {
  id: number;
  week_start: string;
  status: string;
  focus_areas: string[];
  completion_rate: number;
  user_feedback: number | null;
  item_count: number;
  completed_count: number;
  created_at: string;
}

export interface GoalMetric {
  id: number;
  metric_type: string;
  metric_name: string | null;
  current_value: number | null;
  target_value: number | null;
  unit: string | null;
  milestones: { period: string; target: number; action: string }[] | null;
  strategy: string | null;
}

export interface PeriodGoal {
  id: number;
  user_id: number;
  period_type: string;
  period_start: string;
  period_end: string;
  status: string;
  focus_areas: string[];
  summary: string | null;
  ai_model: string | null;
  user_feedback: number | null;
  metrics: GoalMetric[];
  created_at: string;
  updated_at: string | null;
}

export interface GoalListItem {
  id: number;
  period_type: string;
  period_start: string;
  period_end: string;
  status: string;
  focus_areas: string[];
  summary: string | null;
  metric_count: number;
  created_at: string;
}

export interface AnalyzeData {
  week_start: string;
  week_end: string;
  past_performance: {
    weeks_analyzed: number;
    avg_completion_rate: number;
    by_category: Record<string, { done: number; total: number; rate: number; top_items: string[] }>;
    trend: string;
    strong_items: string[];
    weak_items: string[];
  };
  body_metrics: {
    weight?: { current: number; target: number | null; unit: string; date: string };
    bmi?: number;
    body_fat?: number;
    body_battery?: number;
    stress_level?: number;
    sleep_score?: number;
    resting_hr?: number;
  };
  weather_forecast: {
    available: boolean;
    city?: string;
    daily?: { date: string; day_name: string; weather: string; temp_high: number; temp_low: number }[];
    air_quality?: { aqi: number; level: string; primary_pollutant: string };
    exercise_advice?: string;
    reason?: string;
  };
  active_goals: { id: number; period_type: string; focus_areas: string[]; metrics: { metric_name: string; current_value: number | null; target_value: number | null; unit: string | null }[] }[];
  trips: { name: string; destination: string; start_date: string; end_date: string; days: { day_name: string; date: string; title: string; type: string }[] }[];
  suggested_focus: { label: string; reason: string }[];
}

export const dayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];

export const categoryConfig: Record<string, { label: string; color: string; icon: React.ReactNode }> = {
  exercise: { label: '运动', color: 'bg-blue-100 text-blue-700', icon: React.createElement(Dumbbell, { className: 'w-3.5 h-3.5' }) },
  diet: { label: '饮食', color: 'bg-green-100 text-green-700', icon: React.createElement(Utensils, { className: 'w-3.5 h-3.5' }) },
  rest: { label: '休息', color: 'bg-purple-100 text-purple-700', icon: React.createElement(Moon, { className: 'w-3.5 h-3.5' }) },
  habit: { label: '习惯', color: 'bg-amber-100 text-amber-700', icon: React.createElement(Sparkles, { className: 'w-3.5 h-3.5' }) },
  other: { label: '其他', color: 'bg-gray-100 text-gray-700', icon: React.createElement(MoreHorizontal, { className: 'w-3.5 h-3.5' }) },
};
