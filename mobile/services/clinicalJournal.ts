import api from './api';

export interface CaseDetail {
  id: number;
  theme: string;
  metric_key: string | null;
  title: string | null;
  summary: string | null;
  status: 'active' | 'monitoring' | 'resolved';
  severity: 'mild' | 'moderate' | 'severe' | 'unknown' | null;
  opened_at: string | null;
  last_updated_at: string | null;
  resolved_at: string | null;
  entries: JournalEntry[];
}

export interface JournalEntry {
  id: number;
  subjective: string | null;
  objective: string | null;
  assessment: string | null;
  plan: string | null;
  used_specialists: string[];
  related_action_card_ids: number[];
  generated_at: string | null;
  created_by: string | null;
}

export async function getCaseDetail(caseId: number): Promise<CaseDetail> {
  const { data } = await api.get<CaseDetail>(`/clinical-journal/cases/${caseId}`);
  return data;
}

// ------------------------------------------------------------
// Task 4/5: timeline API — threads 分组 + 无主題 bucket
// ------------------------------------------------------------

export interface TimelineEntry {
  id: number;
  generated_at: string;
  created_by: string | null;
  subjective_short: string;
  has_actionable: boolean;
  has_soap?: boolean;
}

export interface TimelineThread {
  thread_id: number | null; // null = 无主題 bucket
  theme: string;
  status: string | null;
  title: string | null;
  entry_count: number;
  last_updated: string;
  entries: TimelineEntry[];
}

export async function fetchJournalTimeline(days = 30): Promise<{ threads: TimelineThread[] }> {
  const { data } = await api.get<{ threads: TimelineThread[] }>(
    '/clinical-journal/timeline',
    { params: { days } },
  );
  return data;
}
