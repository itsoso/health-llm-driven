import api from './api';

export interface MonthlyReportSummary {
  year: number;
  month: number;
  generated_at: string | null;
  coverage_pct: number;
  hit_rate: number;
  total_graded: number;
  narrative: string;
}

export interface MetricTrend {
  metric: string;
  label: string;
  unit: string;
  curr: number;
  prev: number | null;
  delta: number;
  delta_pct: number | null;
  direction: 'improved' | 'regressed' | 'basically_flat' | 'changed';
  desirable: 'up' | 'down' | 'context';
}

export interface ScorecardOverall {
  total_graded: number;
  hit_count: number;
  miss_count: number;
  avg_score: number;
  hit_rate: number;
}

export interface ScorecardSpecialist {
  name: string;
  label: string;
  total: number;
  hits: number;
  hit_rate: number;
  avg_score: number;
}

export interface ScorecardCard {
  card_id: number;
  title: string;
  metric: string | null;
  score: number;
  specialist: string | null;
  graded_at: string | null;
}

export interface KeyIntervention {
  date: string;
  kind: string;
  title: string;
  detail: string | null;
}

export interface MonthlyReportData {
  period: {
    year: number;
    month: number;
    start: string;
    end: string;
    days_in_month: number;
  };
  coverage: { covered_days: number; total_days: number; pct: number };
  metric_trends: MetricTrend[];
  ai_scorecard: {
    overall: ScorecardOverall;
    by_specialist: ScorecardSpecialist[];
    top_hits: ScorecardCard[];
    top_misses: ScorecardCard[];
  };
  key_interventions: KeyIntervention[];
  narrative: string;
  next_focus: string[];
}

export interface MonthlyReportDetail {
  id: number;
  year: number;
  month: number;
  generated_at: string | null;
  version: string;
  report: MonthlyReportData;
}

export async function listMyMonthlyReports(limit = 24): Promise<MonthlyReportSummary[]> {
  const { data } = await api.get<{ reports: MonthlyReportSummary[] }>(
    '/monthly-report/me', { params: { limit } },
  );
  return data.reports;
}

export async function getMonthlyReport(year: number, month: number): Promise<MonthlyReportDetail> {
  const { data } = await api.get<MonthlyReportDetail>(
    `/monthly-report/me/${year}/${month}`,
  );
  return data;
}

export async function regenerateMonthlyReport(year: number, month: number): Promise<MonthlyReportDetail> {
  const { data } = await api.post<MonthlyReportDetail>(
    `/monthly-report/me/${year}/${month}/regenerate`,
  );
  return data;
}

export const INTERVENTION_KIND_LABEL: Record<string, string> = {
  supplement_start: '开始补剂',
  medical_exam: '体检',
  first_bp: '首次血压',
  milestone: '里程碑',
};

export const DIRECTION_LABEL: Record<MetricTrend['direction'], string> = {
  improved: '改善',
  regressed: '退步',
  basically_flat: '持平',
  changed: '变化',
};

export const DIRECTION_COLOR: Record<MetricTrend['direction'], string> = {
  improved: '#34C759',
  regressed: '#FF3B30',
  basically_flat: '#8E8E93',
  changed: '#FF9500',
};

export function formatMonth(year: number, month: number): string {
  return `${year} 年 ${month} 月`;
}

/** "生成于 X 天前" 式相对时间 */
export function relativeTime(iso: string | null): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (isNaN(then)) return '';
  const diff = Date.now() - then;
  if (diff < 3600_000) return `${Math.max(1, Math.floor(diff / 60_000))} 分钟前`;
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`;
  return `${Math.floor(diff / 86400_000)} 天前`;
}
