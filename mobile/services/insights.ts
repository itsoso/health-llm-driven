import api from './api';

export type InsightSeverity = 'info' | 'low' | 'medium';
export type InsightFeedback = 'helpful' | 'not_helpful' | 'irrelevant' | 'already_knew';

export interface DailyInsight {
  id: number;
  insight_date: string;
  kind: string;              // gene_pgx / lab_trend / hrv_pattern / profile_summary
  rule_id: string | null;
  title: string;
  body: string;
  evidence: Record<string, any>;
  confidence: number;
  severity: InsightSeverity;
  user_feedback: InsightFeedback | null;
  feedback_note: string | null;
  feedback_at: string | null;
  created_at: string | null;
}

export async function getTodayInsight(): Promise<DailyInsight | null> {
  const { data } = await api.get<{ insight: DailyInsight | null }>('/insights/today');
  return data?.insight ?? null;
}

export async function listRecentInsights(days: number = 14): Promise<DailyInsight[]> {
  const { data } = await api.get<{ insights: DailyInsight[] }>('/insights/recent', {
    params: { days },
  });
  return data?.insights ?? [];
}

export async function submitInsightFeedback(
  insightId: number,
  feedback: InsightFeedback,
  note?: string,
): Promise<void> {
  await api.post(`/insights/${insightId}/feedback`, { feedback, note });
}
