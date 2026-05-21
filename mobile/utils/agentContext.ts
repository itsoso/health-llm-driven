import type { Router } from 'expo-router';

import type { DailyDietSummary } from '@/services/diet';
import type { MedicalExam } from '@/services/medicalExams';
import type { SafetyAlert } from '@/services/safety';
import type { GarminSleepDay, SleepDebt, SleepStats } from '@/services/sleep';
import type {
  PostWorkoutAnalysisResponse,
  WorkoutAnalysis,
  WorkoutChartData,
  WorkoutDetail,
  WorkoutStats,
  WorkoutSummary,
} from '@/services/workouts';

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

function compactPostWorkoutAnalysis(
  analysis?: PostWorkoutAnalysisResponse | null,
  markdown?: string | null,
): AgentContextValue {
  if (!analysis && !markdown) return null;
  const payload = (analysis ?? {}) as Record<string, any>;
  return {
    summary_markdown: markdown ? markdown.slice(0, 1800) : null,
    overall_rating: payload.overall_rating ?? null,
    intensity_assessment: payload.intensity_assessment ?? null,
    recovery_tips: Array.isArray(payload.recovery_tips) ? payload.recovery_tips.slice(0, 6) : null,
    improvement_tips: Array.isArray(payload.improvement_tips) ? payload.improvement_tips.slice(0, 6) : null,
    knowledge_points: Array.isArray(payload.knowledge_points) ? payload.knowledge_points.slice(0, 4) : null,
  };
}

export function createWorkoutDetailAgentContext(args: {
  workout: WorkoutDetail;
  chart?: WorkoutChartData | null;
  analysis?: WorkoutAnalysis | null;
  postAnalysis?: PostWorkoutAnalysisResponse | null;
  postAnalysisMarkdown?: string | null;
}): AgentContextPayload {
  const workout = args.workout;
  const chart = args.chart ?? null;
  const analysis = args.analysis ?? null;

  return {
    from: `workout/${workout.id}`,
    feedback_intent: 'post_workout_review',
    workout: {
      id: workout.id,
      date: workout.workout_date,
      type: workout.workout_type,
      name: workout.workout_name,
      source: workout.source,
      start_time: workout.start_time,
      end_time: workout.end_time,
      duration_min: workout.duration_seconds != null ? Math.round(workout.duration_seconds / 60) : null,
      distance_km: workout.distance_meters != null ? workout.distance_meters / 1000 : null,
      avg_pace_sec_per_km: workout.avg_pace_seconds_per_km,
      avg_speed_kmh: workout.avg_speed_kmh,
      avg_heart_rate: workout.avg_heart_rate,
      max_heart_rate: workout.max_heart_rate,
      calories: workout.calories,
      steps: workout.steps,
      avg_cadence: workout.avg_cadence,
      avg_stride_length_cm: workout.avg_stride_length_cm,
      elevation_gain_meters: workout.elevation_gain_meters,
      training_effect_aerobic: workout.training_effect_aerobic,
      training_effect_anaerobic: workout.training_effect_anaerobic,
      vo2max: workout.vo2max,
      training_load: workout.training_load,
      has_route: !!workout.route_data,
    },
    chart: chart ? {
      avg_pace_display: chart.avg_pace_display ?? null,
      heart_rate_zones: (chart.heart_rate_zones ?? []).map(zone => ({
        zone: zone.zone,
        minutes: zone.minutes,
        percentage: zone.percentage,
      })),
      heart_rate_samples_count: chart.heart_rate_timeline?.length ?? 0,
      pace_samples_count: chart.pace_timeline?.length ?? 0,
      elevation_samples_count: chart.elevation_timeline?.length ?? 0,
    } : null,
    saved_analysis: analysis ? {
      overall_rating: analysis.overall_rating,
      intensity_assessment: analysis.intensity_assessment,
      heart_rate_analysis: analysis.heart_rate_analysis,
      hr_zone_assessment: analysis.hr_zone_assessment,
      pace_analysis: analysis.pace_analysis,
      training_effect_summary: analysis.training_effect_summary,
      recovery_recommendation: analysis.recovery_recommendation,
      next_workout_suggestion: analysis.next_workout_suggestion,
      comparison_with_history: analysis.comparison_with_history,
      key_insights: analysis.key_insights,
      improvement_tips: analysis.improvement_tips,
    } : null,
    post_workout_analysis: compactPostWorkoutAnalysis(args.postAnalysis, args.postAnalysisMarkdown),
    expected_agent_output: [
      '本次运动复盘',
      '拉伸与恢复建议',
      '下次训练安排',
      '需要用户补充反馈的问题',
    ],
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
