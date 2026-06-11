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
