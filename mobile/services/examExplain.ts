import api from './api';

export interface AbnormalItem {
  item_name: string;
  value: number | null;
  value_text: string | null;
  unit: string | null;
  reference_range: string | null;
  is_abnormal: string;
  gene_links: string[];
}

export interface TrendPoint {
  date: string;
  value: number | null;
  value_text: string | null;
  is_abnormal: string;
}

export interface ExplainAction {
  category: 'diet' | 'supplement' | 'follow_up' | 'lifestyle' | 'see_doctor' | string;
  title: string;
  rationale: string;
  evidence_level: 'high' | 'medium' | 'low' | 'medical_grade';
  metric_key: string | null;
  suggested_days: number;
}

export interface RelatedCardSummary {
  id: number;
  title: string;
  status: string;
  outcome: string | null;
  evidence_level: string | null;
}

export interface ExamExplain {
  exam: { id: number; exam_type: string | null; exam_date: string };
  abnormal_items: AbnormalItem[];
  trends: Record<string, TrendPoint[]>;
  explanation: {
    summary: string;
    actions: ExplainAction[];
    recheck_window_days: number;
    see_doctor_specialty: string | null;
  } | null;
  related_cards: RelatedCardSummary[];
  user_gene_hits: string[];
}

export async function fetchExamExplain(examId: number): Promise<ExamExplain> {
  const { data } = await api.get<ExamExplain>(`/medical-exams/${examId}/explain`);
  return data;
}
