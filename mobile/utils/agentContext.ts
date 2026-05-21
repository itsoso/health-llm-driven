import type { Router } from 'expo-router';

import type { ActionCard } from '@/services/actionCards';
import type { DailyDietSummary } from '@/services/diet';
import type { DietPlan } from '@/services/dietPlan';
import type { MedicalExam } from '@/services/medicalExams';
import type { MovementPlan } from '@/services/movementPlan';
import type { Medication } from '@/services/medications';
import type { SafetyAlert } from '@/services/safety';
import type { SpO2NightAnalysis } from '@/services/sleepSpo2';
import type { GarminSleepDay, SleepDebt, SleepStats } from '@/services/sleep';
import type { BodyPart } from '@/services/symptoms';
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

export function createHydrationAgentContext(args: {
  date: string;
  totalMl: number;
  targetMl: number;
  records?: Array<Record<string, any>> | null;
}): AgentContextPayload {
  const totalMl = args.totalMl ?? 0;
  const targetMl = args.targetMl || 2000;
  return {
    from: `hydration/${args.date}`,
    feedback_intent: 'hydration_adjustment',
    date: args.date,
    total_ml: totalMl,
    target_ml: targetMl,
    progress_pct: targetMl > 0 ? Math.round((totalMl / targetMl) * 100) : null,
    remaining_ml: Math.max(0, targetMl - totalMl),
    records: (args.records ?? []).slice(0, 8).map(record => ({
      amount_ml: record.amount ?? record.amount_ml ?? null,
      drink_type: record.drink_type ?? record.type ?? null,
      recorded_at: record.recorded_at ?? record.created_at ?? record.time ?? null,
    })),
    expected_agent_output: ['今日饮水复盘', '接下来补水安排', '运动/睡眠/补剂相关注意事项'],
  };
}

function getSupplementId(item: Record<string, any>): number | string | null {
  return item.supplement?.id ?? item.supplement_id ?? item.id ?? null;
}

function getSupplementName(item: Record<string, any>): string {
  return item.supplement?.name ?? item.supplement_name ?? item.name ?? '未知补剂';
}

function getSupplementTiming(item: Record<string, any>): string | null {
  return item.supplement?.timing ?? item.timing ?? null;
}

function getSupplementTaken(item: Record<string, any>): boolean {
  return !!(item.record?.taken ?? item.is_taken ?? item.checked);
}

export function createSupplementAgentContext(args: {
  date: string;
  supplements?: Array<Record<string, any>> | null;
}): AgentContextPayload {
  const supplements = args.supplements ?? [];
  const normalized = supplements.map(item => ({
    id: getSupplementId(item),
    name: getSupplementName(item),
    timing: getSupplementTiming(item),
    taken: getSupplementTaken(item),
  }));
  return {
    from: `supplements/${args.date}`,
    feedback_intent: 'supplement_checkin_review',
    date: args.date,
    total: normalized.length,
    taken: normalized.filter(item => item.taken).length,
    pending: normalized
      .filter(item => !item.taken)
      .slice(0, 10)
      .map(({ id, name, timing }) => ({ id, name, timing })),
    supplements: normalized.slice(0, 20),
    expected_agent_output: ['今日补剂执行复盘', '漏服/冲突风险提醒', '明天服用安排和需要反馈的问题'],
  };
}

export function createDietPlanAgentContext(plan: DietPlan): AgentContextPayload {
  return {
    from: 'diet-plan/current',
    feedback_intent: 'diet_plan_follow_up',
    summary: plan.summary ?? null,
    energy: plan.energy ?? null,
    protein: plan.protein ?? null,
    hydration: plan.hydration ?? null,
    supplement: plan.supplement ?? null,
    next_meal: plan.next_meal ?? null,
    gene_nudges: (plan.gene_nudges ?? []).slice(0, 5) as AgentContextValue,
    labs_concern: plan.labs_concern ?? null,
    proposed_experiments: (plan.proposed_experiments ?? []).slice(0, 5) as AgentContextValue,
    related_cards: (plan.related_cards ?? []).slice(0, 5).map(card => ({
      id: card.id,
      title: card.title,
      outcome: card.outcome,
      metric_key: card.metric_key,
      baseline_value: card.baseline_value,
      actual_value: card.actual_value,
    })),
    expected_agent_output: ['饮食方案复盘', '饮水与补剂调整', '下一餐建议', '需要用户反馈的问题'],
  };
}

export function createMovementPlanAgentContext(plan: MovementPlan): AgentContextPayload {
  return {
    from: 'movement-plan/current',
    feedback_intent: 'movement_plan_follow_up',
    summary: plan.summary ?? null,
    training_status: plan.training_status ?? null,
    today: plan.today ?? null,
    fitness: plan.fitness ?? null,
    gene_biases: (plan.gene_biases ?? []).slice(0, 5) as AgentContextValue,
    week_adjustment: plan.week_adjustment ?? null,
    recent_workouts: plan.recent_workouts ? {
      count: plan.recent_workouts.count,
      avg_perceived_exertion: plan.recent_workouts.avg_perceived_exertion ?? null,
      high_intensity_minutes_7d: plan.recent_workouts.high_intensity_minutes_7d ?? null,
      workouts: (plan.recent_workouts.workouts ?? []).slice(0, 5),
    } as AgentContextValue : null,
    proposed_experiments: (plan.proposed_experiments ?? []).slice(0, 5) as AgentContextValue,
    related_cards: (plan.related_cards ?? []).slice(0, 5).map(card => ({
      id: card.id,
      title: card.title,
      outcome: card.outcome,
      metric_key: card.metric_key,
      baseline_value: card.baseline_value,
      actual_value: card.actual_value,
    })),
    expected_agent_output: ['本周训练方案复盘', '今日训练/恢复安排', '不同运动类型替代方案', '需要用户反馈的问题'],
  };
}

export function createActionCardAgentContext(card: ActionCard): AgentContextPayload {
  return {
    from: `action-card/${card.id}`,
    feedback_intent: 'action_card_adjustment',
    card: {
      id: card.id,
      title: card.title,
      content: card.content ? card.content.slice(0, 1800) : null,
      card_type: card.card_type,
      status: card.status,
      priority: card.priority,
      severity: card.severity ?? null,
      source_type: card.source_type ?? null,
      source_id: card.source_id ?? null,
      metric_key: card.metric_key ?? null,
      baseline_value: card.baseline_value ?? null,
      target_value: card.target_value ?? null,
      actual_value: card.actual_value ?? null,
      verification_days: card.verification_days ?? null,
      check_back_date: card.check_back_date ?? null,
      evidence_level: card.evidence_level ?? null,
      user_decision: card.user_decision ?? null,
      outcome: card.outcome ?? null,
      effect_size: card.effect_size ?? null,
    },
    checklist: (card.checklist ?? []).slice(0, 12),
    latest_assessment: card.latest_assessment ? {
      score: card.latest_assessment.score ?? null,
      summary: card.latest_assessment.summary ?? null,
      evidence: card.latest_assessment.evidence ?? [],
      adjustments: card.latest_assessment.adjustments ?? [],
    } : null,
    expected_agent_output: ['判断建议是否仍适合', '调整执行方案', '复盘指标和体感反馈', '下一步行动'],
  };
}

export function createBodyMetricsAgentContext(args: {
  date: string;
  latestWeightKg?: number | null;
  latestWeightDate?: string | null;
  latestWaistCm?: number | null;
  latestWaistDate?: string | null;
  weightStats?: Record<string, any> | null;
  bloodPressureStats?: Record<string, any> | null;
  draft?: {
    weightKg?: number | null;
    waistCm?: number | null;
    notes?: string | null;
  } | null;
}): AgentContextPayload {
  return {
    from: `body-metrics/${args.date}`,
    feedback_intent: 'body_metrics_review',
    date: args.date,
    latest: {
      weight_kg: args.latestWeightKg ?? null,
      weight_date: args.latestWeightDate ?? null,
      waist_cm: args.latestWaistCm ?? null,
      waist_date: args.latestWaistDate ?? null,
    },
    stats: {
      weight: args.weightStats ?? null,
      blood_pressure: args.bloodPressureStats ?? null,
    },
    draft_record: args.draft ? {
      weight_kg: args.draft.weightKg ?? null,
      waist_cm: args.draft.waistCm ?? null,
      notes: args.draft.notes ?? null,
    } : null,
    expected_agent_output: ['体重/腰围趋势复盘', '血压风险和生活方式建议', '今天饮食运动调整', '需要继续记录的数据'],
  };
}

export function createSymptomAgentContext(args: {
  date: string;
  bodyPart?: BodyPart | null;
  description?: string | null;
  severity?: number | null;
  source?: 'manual' | 'voice' | 'siri';
}): AgentContextPayload {
  return {
    from: `symptom/${args.date}`,
    feedback_intent: 'symptom_triage_support',
    date: args.date,
    symptom: {
      body_part: args.bodyPart ?? null,
      description: args.description?.trim() || null,
      severity: args.severity ?? null,
      source: args.source ?? 'manual',
    },
    safety_boundary: '健康管理建议，不替代诊断；明显异常、急性加重或危险信号应及时就医。',
    expected_agent_output: ['症状复盘', '可能诱因和需要补充的问题', '居家观察与记录建议', '就医/急诊红旗信号'],
  };
}

export function createSleepSpo2AgentContext(analysis: SpO2NightAnalysis): AgentContextPayload {
  return {
    from: `sleep-spo2/${analysis.night_date}`,
    feedback_intent: 'sleep_breathing_review',
    night: {
      date: analysis.night_date,
      odi: analysis.odi,
      events_count: analysis.events_count,
      min_spo2: analysis.min_spo2,
      avg_spo2: analysis.avg_spo2,
      total_sleep_minutes: analysis.total_sleep_minutes,
      snore_events_count: analysis.snore_events?.length ?? 0,
    },
    event_summary: (analysis.events ?? []).slice(0, 8).map(event => ({
      duration_seconds: event.duration_seconds,
      min_spo2: event.min_spo2,
      baseline_spo2: event.baseline_spo2,
      drop_magnitude: event.drop_magnitude,
      concurrent_hr_delta: event.concurrent_hr_delta,
      concurrent_respiration_rate: event.concurrent_respiration_rate,
      sleep_stage: event.sleep_stage,
    })),
    correlations: (analysis.correlations ?? []).slice(0, 8).map(item => ({
      category: item.category,
      subject: item.subject,
      rule: item.rule,
      hypothesis: item.hypothesis,
      suggested_action: item.suggested_action,
      severity: item.severity,
      confidence: item.confidence,
      evidence: item.evidence as AgentContextValue,
    })),
    action_priorities: (analysis.action_priorities ?? []).slice(0, 8),
    ask_questions: (analysis.ask_questions ?? []).slice(0, 8),
    safety_boundary: '用于睡眠健康管理和就医沟通准备，不诊断睡眠呼吸暂停；明显低氧、胸痛、呼吸困难或持续异常应就医。',
    expected_agent_output: ['昨晚呼吸风险复盘', '今晚睡眠实验建议', '需要补充的背景信息', '医生评估提示边界'],
  };
}

function compactMedication(med: Medication): AgentContextValue {
  return {
    id: med.id,
    name: med.name,
    dosage: med.dosage,
    frequency: med.frequency,
    times_per_day: med.times_per_day,
    reminder_times: med.reminder_times,
    category: med.category,
    purpose: med.purpose,
    start_date: med.start_date,
    end_date: med.end_date,
    is_active: med.is_active,
    notes: med.notes,
  };
}

export function createMedicationAgentContext(args: {
  date: string;
  activeMedications?: Medication[] | null;
  archivedMedications?: Medication[] | null;
}): AgentContextPayload {
  const active = args.activeMedications ?? [];
  const archived = args.archivedMedications ?? [];
  return {
    from: `medications/${args.date}`,
    feedback_intent: 'medication_review_support',
    date: args.date,
    active_count: active.length,
    archived_count: archived.length,
    active_medications: active.slice(0, 20).map(compactMedication),
    archived_medications: archived.slice(0, 10).map(compactMedication),
    safety_boundary: '不能自行停药、换药或改剂量；只整理执行情况、疑问和就医沟通清单。',
    expected_agent_output: ['用药执行复盘', '需要向医生确认的问题', '不适症状整理', '记录和提醒优化建议'],
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
