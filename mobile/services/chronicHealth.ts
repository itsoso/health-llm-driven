import api from './api';
import { semanticColors, type SemanticPalette } from '../constants/theme';

/**
 * 慢病 / 肝脏趋势 —— 后端 GET /chronic/liver(PR #121)。
 *
 * 该端点无 OpenAPI response_model,故此处手写接口,严格对齐后端契约。
 * verdict ∈ improving|worsening|stable;direction ∈ rising|falling|flat。
 * available=false 时只有 reason,其余字段缺省。
 */

export type LiverVerdict = 'improving' | 'worsening' | 'stable';
export type LiverDirection = 'rising' | 'falling' | 'flat';

export interface LiverTrend {
  n: number;
  first_value: number;
  last_value: number;
  first_date: string;
  last_date: string;
  pct_change: number;
  direction: LiverDirection;
  verdict: LiverVerdict;
}

export interface LiverAssessment {
  available: boolean;
  reason?: string;

  alt_latest: number | null;
  ast_latest: number | null;
  ggt_latest: number | null;
  platelets_latest: number | null;
  tg_latest: number | null;

  ast_alt_ratio: number | null;

  alt_trend: LiverTrend | null;
  ggt_trend: LiverTrend | null;

  fib4: number | null;
  fib4_band: string | null;

  fatty_liver_risk: string | null;

  summary_lines: string[];
  advice: string[];
}

export async function getLiverAssessment(): Promise<LiverAssessment> {
  const { data } = await api.get<LiverAssessment>('/chronic/liver');
  return data;
}

// ──────────────────────────────────────────────────────────────
// 时滞因果:用药干预 → 目标指标前后变化(描述性关联,非因果)
// 后端 GET /chronic/causal-links(PR #150)。无 OpenAPI response_model,手写对齐。
// 见 backend/app/services/causal_links.py::medication_intervention_effects。
// ──────────────────────────────────────────────────────────────

export interface InterventionEffect {
  medication: string;
  metric_label: string;
  before_mean: number;
  after_mean: number;
  delta: number;
  pct: number | null;
  n_before: number;
  n_after: number;
}

export interface CausalLinks {
  intervention_effects: InterventionEffect[];
  note: string;
}

export async function getCausalLinks(): Promise<CausalLinks> {
  const { data } = await api.get<CausalLinks>('/chronic/causal-links');
  return data;
}

/** delta 方向 → 箭头 + 主题语义色。delta<0 视为下降(降脂/降糖通常是好转方向)。 */
export function effectArrow(e: InterventionEffect): '↓' | '↑' | '→' {
  if (e.delta < 0) return '↓';
  if (e.delta > 0) return '↑';
  return '→';
}

// ──────────────────────────────────────────────────────────────
// 社会连接自评(UCLA-3 + 连接结构)
// 后端 GET/POST /chronic/connection(PR #150)。手写对齐:
// 见 backend/app/services/connection_service.py::status / record_checkin。
// ──────────────────────────────────────────────────────────────

export interface ConnectionStatus {
  has_checkin: boolean;
  due: boolean;
  days_since: number | null;
  last_date?: string;
  ucla_score?: number;
  has_confidant?: boolean;
  in_stable_group?: boolean;
  interpretation: string;
}

export interface ConnectionCheckinInput {
  ucla_score: number; // UCLA-3 总分 3-9(三题各 1-3 分)
  has_confidant: boolean;
  in_stable_group: boolean;
  notes?: string;
}

/** POST /chronic/connection 的响应:status 是嵌套的完整状态对象(非字符串)。 */
export interface ConnectionCheckinResult {
  id: number;
  checkin_date: string;
  status: ConnectionStatus;
}

export async function getConnectionStatus(): Promise<ConnectionStatus> {
  const { data } = await api.get<ConnectionStatus>('/chronic/connection');
  return data;
}

export async function submitConnectionCheckin(
  input: ConnectionCheckinInput,
): Promise<ConnectionCheckinResult> {
  const { data } = await api.post<ConnectionCheckinResult>('/chronic/connection', input);
  return data;
}

/** UCLA-3 三题原始分(各 1-3)合成总分(3-9)。clamp 到合法区间,挡住后端 400。 */
export function ucla3Total(q1: number, q2: number, q3: number): number {
  const sum = q1 + q2 + q3;
  return Math.min(9, Math.max(3, sum));
}

// ── 纯 helper(UI 无关,可单测)──

/** verdict → 人话标签。 */
export function verdictLabel(v: LiverVerdict): string {
  switch (v) {
    case 'improving':
      return '好转';
    case 'worsening':
      return '恶化';
    case 'stable':
      return '平稳';
  }
}

/**
 * verdict → 主题语义色(好转绿 / 恶化红 / 平稳灰)。
 * 默认取亮色调色板;传入 s 时跟随当前 light/dark。
 */
export function verdictColor(v: LiverVerdict, s: SemanticPalette = semanticColors): string {
  switch (v) {
    case 'improving':
      return s.success.solid;
    case 'worsening':
      return s.danger.solid;
    case 'stable':
      return s.neutral.solid;
  }
}
