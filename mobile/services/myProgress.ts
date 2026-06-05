import api from './api';

export interface ProgressCard {
  id: number;
  title: string;
  status: string | null;
  user_decision: string | null;
  outcome: 'improved' | 'unchanged' | 'worsened' | 'inconclusive' | null;
  effect_size: number | null;
  accuracy_score: number | null;
  metric_key: string | null;
  baseline_value: string | null;
  actual_value: string | null;
  evidence_level: 'high' | 'medium' | 'low' | 'medical_grade' | null;
  created_at: string | null;
  completed_at: string | null;
  graded_at: string | null;
}

export interface ProgressDashboard {
  window: { since: string; until: string; days: number };
  stats: {
    total_surfaced: number;
    accepted: number;
    declined: number;
    pending: number;
    completed: number;
    graded: number;
    improved: number;
    unchanged: number;
    worsened: number;
    inconclusive: number;
    safe_closed: number;
    acceptance_rate: number | null;
    verification_rate: number | null;
    improvement_rate: number | null;
  };
  closed_cards: ProgressCard[];
  verifying_cards: ProgressCard[];
}

export async function fetchMyProgress(days = 30): Promise<ProgressDashboard> {
  const { data } = await api.get<ProgressDashboard>(
    `/action-cards/me/progress?days=${days}`,
  );
  return data;
}

// ───────────── 抗衰"信任时刻": 生物年龄改善 (Step 3C) ─────────────

export interface BioAgeWin {
  baseline: number; // 干预前身体年龄
  actual: number; // 复检后身体年龄
  deltaYears: number; // = baseline - actual,正数 = 年轻了几岁
  gradedAt: string | null;
}

/**
 * 从 progress dashboard 里挑出"最值得展示的生物年龄改善"卡。
 * 只认 metric_key=phenotypic_age/biological_age + outcome=improved 的真实改善
 * (不把 worsened/unchanged 粉饰成 win);取最近一次 graded。无 → null。
 */
/** 安全解析数字字符串:null / '' / 非数字 → NaN(避免 Number(null)===0 的坑)。 */
function _num(v: string | null | undefined): number {
  if (v == null || v === '') return NaN;
  return Number(v);
}

export function pickBioAgeWin(d: ProgressDashboard | undefined | null): BioAgeWin | null {
  const cards = d?.closed_cards ?? [];
  let best: BioAgeWin | null = null;
  let bestTs = -Infinity;
  for (const c of cards) {
    const key = (c.metric_key || '').toLowerCase();
    if (key !== 'phenotypic_age' && key !== 'biological_age') continue;
    if (c.outcome !== 'improved') continue;
    const baseline = _num(c.baseline_value);
    const actual = _num(c.actual_value);
    if (!Number.isFinite(baseline) || !Number.isFinite(actual)) continue;
    if (actual >= baseline) continue; // improved 必然变小,double-check
    const ts = c.graded_at ? Date.parse(c.graded_at) : 0;
    if (ts >= bestTs) {
      bestTs = ts;
      best = {
        baseline: Math.round(baseline * 10) / 10,
        actual: Math.round(actual * 10) / 10,
        deltaYears: Math.round((baseline - actual) * 10) / 10,
        gradedAt: c.graded_at,
      };
    }
  }
  return best;
}
