import api from './api';

export interface CaseSummary {
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
  entry_count: number;
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

export interface CaseDetail extends Omit<CaseSummary, 'entry_count'> {
  entries: JournalEntry[];
}

export interface RecentEntry {
  id: number;
  case_thread_id: number | null;
  subjective: string | null;
  assessment_first_line: string;
  plan_first_line: string;
  generated_at: string | null;
}

export async function listCases(status?: string): Promise<CaseSummary[]> {
  const { data } = await api.get<CaseSummary[]>('/clinical-journal/cases', {
    params: status ? { status } : {},
  });
  return data;
}

export async function getCaseDetail(caseId: number): Promise<CaseDetail> {
  const { data } = await api.get<CaseDetail>(`/clinical-journal/cases/${caseId}`);
  return data;
}

export async function recentEntries(days: number = 14): Promise<RecentEntry[]> {
  const { data } = await api.get<RecentEntry[]>('/clinical-journal/entries/recent', {
    params: { days },
  });
  return data;
}
