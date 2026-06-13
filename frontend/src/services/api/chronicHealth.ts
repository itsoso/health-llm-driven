import api from './client';

// ---- 后端契约 (backend P0①, 依赖 PR #121) ----
// 经 next.config.js rewrites: 前端 /api/chronic/* → 后端 /api/v1/chronic/*

export type TrendDirection = 'up' | 'down' | 'flat';
export type TrendVerdict = 'improving' | 'worsening' | 'stable';

/** 单个指标的长期趋势。后端 verdict 已按「higher_is_worse」判好,前端直接配色。 */
export interface IndicatorTrend {
  n: number;
  first_value: number;
  last_value: number;
  first_date: string;
  last_date: string;
  pct_change: number;
  direction: TrendDirection;
  verdict: TrendVerdict;
}

/** GET /api/chronic/liver 响应。所有字段为「趋势提示」,非诊断。 */
export interface LiverAssessment {
  available: boolean;
  reason?: string;
  alt_latest: number | null;
  ast_latest: number | null;
  ggt_latest: number | null;
  platelets_latest: number | null;
  tg_latest: number | null;
  ast_alt_ratio: number | null;
  alt_trend: IndicatorTrend | null;
  ggt_trend: IndicatorTrend | null;
  fib4: number | null;
  fib4_band: string | null;
  fatty_liver_risk: string | null;
  summary_lines: string[];
  advice: string[];
}

/** 获取肝脏趋势评估(消费历史肝酶,给 ALT/GGT 趋势 + FIB-4 + 脂肪肝风险提示)。 */
export const getLiverAssessment = async (): Promise<LiverAssessment> => {
  const res = await api.get('/chronic/liver');
  return res.data;
};

// ---- 社会连接自评 (backend P1.2, GET/POST /chronic/connection) ----

/** GET /chronic/connection 响应。到期判断 + 解读,非诊断。 */
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

/** POST /chronic/connection 请求体。ucla_score 须为 3-9(UCLA-3 三题各 1-3 分)。 */
export interface ConnectionCheckinPayload {
  ucla_score: number;
  has_confidant: boolean;
  in_stable_group: boolean;
  notes?: string;
}

export interface ConnectionCheckinResponse {
  id: number;
  checkin_date: string;
  status: ConnectionStatus;
}

/** 获取社会连接自评状态(上次自评 + 是否到期 + 解读)。 */
export const getConnectionStatus = async (): Promise<ConnectionStatus> => {
  const res = await api.get('/chronic/connection');
  return res.data;
};

/** 提交一次社会连接自评(UCLA-3 + 是否有知心人 + 是否在稳定群体)。 */
export const submitConnectionCheckin = async (
  payload: ConnectionCheckinPayload
): Promise<ConnectionCheckinResponse> => {
  const res = await api.post('/chronic/connection', payload);
  return res.data;
};

// ---- 时滞因果:用药干预 → 指标变化 (backend P1.1, GET /chronic/causal-links) ----

/** 单条「用药 → 指标前后均值变化」。描述性关联,非严格因果。 */
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

/** GET /chronic/causal-links 响应。note 强调非因果。 */
export interface CausalLinksResponse {
  intervention_effects: InterventionEffect[];
  note: string;
}

/** 获取用药干预 → 目标指标前后变化(描述性关联)。 */
export const getCausalLinks = async (): Promise<CausalLinksResponse> => {
  const res = await api.get('/chronic/causal-links');
  return res.data;
};
