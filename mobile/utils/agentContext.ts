import type { Router } from 'expo-router';

import type { DailyDietSummary } from '@/services/diet';
import type { MedicalExam } from '@/services/medicalExams';
import type { SafetyAlert } from '@/services/safety';
import type { GarminSleepDay, SleepDebt, SleepStats } from '@/services/sleep';
import type { WorkoutStats, WorkoutSummary } from '@/services/workouts';

export const AGENT_CONTEXT_MAX_CHARS = 4000;

type AgentContextValue =
  | string
  | number
  | boolean
  | null
  | AgentContextValue[]
  | { [key: string]: AgentContextValue };

export type AgentContextPayload = Record<string, AgentContextValue>;

export interface ChatContextRouteInput {
  prompt: string;
  context: AgentContextPayload | string;
  badge: string;
}

export function serializeAgentContext(context: AgentContextPayload | string): string {
  const raw = typeof context === 'string' ? context : JSON.stringify(context);
  if (raw.length <= AGENT_CONTEXT_MAX_CHARS) return raw;
  const suffix = '...[truncated]';
  return `${raw.slice(0, AGENT_CONTEXT_MAX_CHARS - suffix.length)}${suffix}`;
}

export function buildChatContextRoute(input: ChatContextRouteInput) {
  return {
    pathname: '/(tabs)/chat' as const,
    params: {
      prompt: input.prompt,
      context: serializeAgentContext(input.context),
      badge: input.badge,
    },
  };
}

export function pushChatWithContext(router: Router, input: ChatContextRouteInput): void {
  router.push(buildChatContextRoute(input) as never);
}

export function createDietAgentContext(
  daily: DailyDietSummary,
  targets: { tdee?: number | null; protein_target?: number | null } | null = null,
): AgentContextPayload {
  return {
    from: `diet/${daily.record_date}`,
    date: daily.record_date,
    totals: {
      calories: daily.total_calories ?? null,
      protein: daily.total_protein ?? null,
      carbs: daily.total_carbs ?? null,
      fat: daily.total_fat ?? null,
      fiber: daily.total_fiber ?? null,
    },
    targets,
    meals: (daily.meals ?? []).map(meal => ({
      meal_type: meal.meal_type,
      food_items: meal.food_items,
      calories: meal.calories,
      protein: meal.protein,
      carbs: meal.carbs,
      fat: meal.fat,
      fiber: meal.fiber,
      notes: meal.notes,
    })),
  };
}

export function createSleepAgentContext(args: {
  periodDays: number;
  stats?: SleepStats | null;
  latestNight?: GarminSleepDay | null;
  debt?: SleepDebt | null;
}): AgentContextPayload {
  const latest = args.latestNight ?? null;
  return {
    from: `sleep/${args.periodDays}d`,
    period_days: args.periodDays,
    date: latest?.record_date ?? null,
    sleep_score: latest?.sleep_score ?? args.stats?.avg_sleep_score ?? null,
    duration_h: latest?.total_sleep_duration != null
      ? latest.total_sleep_duration / 60
      : args.stats?.avg_duration_hours ?? null,
    deep_min: latest?.deep_sleep_duration ?? null,
    rem_min: latest?.rem_sleep_duration ?? null,
    light_min: latest?.light_sleep_duration ?? null,
    awake_min: latest?.awake_duration ?? null,
    debt: args.debt ? {
      target_hours: args.debt.target_hours,
      cumulative_debt_hours: args.debt.cumulative_debt_hours,
      severity: args.debt.debt_severity,
      recovery_plan: args.debt.recovery_plan,
    } : null,
    trend: (args.stats?.daily_trend ?? []).map(day => ({
      date: day.date,
      duration_hours: day.duration_hours,
      score: day.score,
    })),
  };
}

export function createWorkoutAgentContext(args: {
  workouts?: WorkoutSummary[] | null;
  stats?: WorkoutStats | null;
  readinessZone?: string | null;
  acwr?: number | null;
}): AgentContextPayload {
  return {
    from: 'workouts/recent',
    recent_workouts: (args.workouts ?? []).slice(0, 5).map(workout => ({
      id: workout.id,
      date: workout.workout_date,
      type: workout.workout_type,
      name: workout.workout_name,
      duration_min: workout.duration_seconds != null ? Math.round(workout.duration_seconds / 60) : null,
      distance_km: workout.distance_meters != null ? workout.distance_meters / 1000 : null,
      avg_heart_rate: workout.avg_heart_rate,
      calories: workout.calories,
      feeling: workout.feeling,
    })),
    stats: args.stats ? {
      total_workouts: args.stats.total_workouts,
      total_duration_minutes: args.stats.total_duration_minutes,
      total_distance_km: args.stats.total_distance_km,
      total_calories: args.stats.total_calories,
      recent_trend: args.stats.recent_trend,
    } : null,
    acwr: args.acwr ?? null,
    readiness_zone: args.readinessZone ?? null,
  };
}

export function createSafetyAlertAgentContext(alert: SafetyAlert): AgentContextPayload {
  return {
    from: `safety-alert/${alert.rule_id}`,
    alert_id: alert.rule_id,
    rule_name: alert.title,
    severity: alert.severity,
    category: alert.category,
    message: alert.message,
    action: alert.action ?? null,
    triggered_metrics: (alert.context ?? null) as AgentContextValue,
  };
}

export function createMedicalExamAgentContext(exam: MedicalExam): AgentContextPayload {
  return {
    from: `medical-exam/${exam.id}`,
    exam_date: exam.exam_date,
    exam_type: exam.exam_type ?? null,
    hospital_name: exam.hospital_name ?? null,
    overall_assessment: exam.overall_assessment ?? null,
    abnormal_items: (exam.items ?? [])
      .filter(item => {
        const flag = (item.is_abnormal || '').toLowerCase().trim();
        return flag && flag !== 'normal';
      })
      .map(item => ({
        name: item.item_name,
        value: item.value ?? item.value_text ?? null,
        unit: item.unit ?? null,
        ref_range: item.reference_range ?? null,
        flag: item.is_abnormal ?? null,
      })),
  };
}

export function createTodayAgentContext(args: {
  alerts: SafetyAlert[];
  twinSnapshot: AgentContextPayload;
}): AgentContextPayload {
  return {
    from: 'today-dashboard',
    active_alerts: args.alerts.slice(0, 5).map(alert => ({
      alert_id: alert.rule_id,
      rule_name: alert.title,
      severity: alert.severity,
      message: alert.message,
      action: alert.action ?? null,
      triggered_metrics: (alert.context ?? null) as AgentContextValue,
    })),
    today_metrics_summary: args.twinSnapshot,
  };
}
