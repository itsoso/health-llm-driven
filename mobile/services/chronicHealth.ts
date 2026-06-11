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
