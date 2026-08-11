import type { TrajectoryContext } from './agenda';

export interface TrajectoryDisplayInput {
  target_state_variable?: string | null;
  trajectory_context?: TrajectoryContext | null;
  verify_by?: Record<string, unknown> | null;
  claim_boundary?: string | null;
}

// 指标 key → 中文显示名的单一真相源。verify_by / trajectory / target_state_variable
// 以及 today 各卡的验证 chip 都走这一份;缺映射的原始 key 原样返回(绝不显示英文残缺词)。
// 历史坑:weight / systolic_bp / body_fat_pct 之前只在别处映射,这里漏了 → 首页「验证」chip
// 泄漏出 "weight / systoli…"(截断在词中间)。补齐后凡是这里有的都出中文。
const METRIC_LABELS: Record<string, string> = {
  // trajectory / anchor 语义变量
  waist_cm: '腰围',
  blood_pressure: '血压',
  metabolic_labs: '代谢指标',
  metabolic_health_anchor: '代谢锚点',
  training_readiness_score: '训练准备度',
  sleep_score: '睡眠分',
  sleep_duration_h: '睡眠时长',
  sleep_hours: '睡眠时长',
  hrv_status: 'HRV',
  hrv: 'HRV',
  recovery_capacity_anchor: '恢复锚点',
  pace_of_aging: '衰老速度代理',
  biological_age_delta_years: '生物年龄差',
  methylation_report: '甲基化报告',
  // 常见生理/化验/体测指标 key(与后端 twin/labs/body_composition 字段对齐)
  weight: '体重',
  bmi: 'BMI',
  body_fat_pct: '体脂率',
  systolic_bp: '收缩压',
  diastolic_bp: '舒张压',
  spo2: '血氧',
  steps: '步数',
  resting_hr: '静息心率',
  follow_up_completed: '复查完成情况',
};

export function stateVariableLabel(value?: string | null): string | null {
  if (!value) return null;
  return METRIC_LABELS[value] ?? value;
}

export function horizonLabel(value?: string | null): string | null {
  if (!value) return null;
  const labels: Record<string, string> = {
    upstream_14d: '14天恢复轨迹',
    upstream_90d: '90天上游轨迹',
  };
  return labels[value] ?? value;
}

function uncertaintyLabel(value?: unknown): string | null {
  if (value === 'low') return '低';
  if (value === 'medium') return '中';
  if (value === 'high') return '高';
  return typeof value === 'string' && value.length > 0 ? value : null;
}

export function buildTrajectorySummary(item: TrajectoryDisplayInput): string | null {
  const target = stateVariableLabel(item.target_state_variable ?? item.trajectory_context?.state_variable);
  const horizon = horizonLabel(item.trajectory_context?.horizon);
  if (!target && !horizon) return null;
  const parts = [];
  if (target) parts.push(`目标: ${target}`);
  if (horizon) parts.push(`周期: ${horizon}`);
  return parts.join(' · ');
}

export function buildVerifySummary(item: TrajectoryDisplayInput): string | null {
  const metrics = Array.isArray(item.verify_by?.metrics) ? item.verify_by.metrics as string[] : [];
  const trajectory = item.verify_by?.trajectory as Record<string, unknown> | undefined;
  const windowDays = typeof item.verify_by?.window_days === 'number'
    ? item.verify_by.window_days
    : item.trajectory_context?.verification_window_days;
  const uncertainty = uncertaintyLabel(trajectory?.uncertainty_level);
  if (metrics.length === 0 && !windowDays && !uncertainty) return null;
  const parts = [];
  if (metrics.length > 0) parts.push(metrics.map((metric) => stateVariableLabel(metric) ?? metric).join(' / '));
  if (windowDays) parts.push(`${windowDays}天`);
  if (uncertainty) parts.push(`不确定性: ${uncertainty}`);
  return parts.join(' · ');
}

export function buildBoundarySummary(item: TrajectoryDisplayInput): string | null {
  const boundary = item.claim_boundary ?? item.trajectory_context?.claim_boundary;
  if (!boundary) return null;
  return `边界: ${boundary}`;
}
