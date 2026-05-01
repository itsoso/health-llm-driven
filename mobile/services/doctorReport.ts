import api from './api';

export interface DoctorExport {
  user_brief: { name?: string; gender?: string; age?: number };
  window: { start: string; end: string; days: number };
  vitals: {
    samples: number;
    avg_rhr: number | null;
    avg_hrv: number | null;
    avg_sleep_score: number | null;
    avg_sleep_hours: number | null;
    avg_stress: number | null;
    avg_steps: number | null;
  };
  directives: Array<{
    kind: string;
    instruction: string;
    source: string | null;
    severity: string | null;
    medication_name: string | null;
    target_value: string | null;
  }>;
  alerts: Array<{
    created_at: string | null;
    alert_type: string;
    metric_name: string;
    severity: string;
    message: string;
  }>;
  ai_scorecard: {
    total_graded: number;
    hit_count: number;
    hit_rate_pct: number;
    avg_score: number;
  };
  recent_journal: Array<{
    generated_at: string | null;
    created_by: string;
    subjective: string;
    objective: string;
    assessment: string;
    plan: string;
  }>;
  spo2_pattern: null | {
    covered_nights: number;
    avg_odi: number | null;
    median_min_spo2: number | null;
    pct_nights_odi_ge_5: number | null;
    pct_nights_min_spo2_below_90: number | null;
    pct_events_in_rem: number | null;
    pattern_flags: string[];
  };
  markdown: string;
}

export interface DoctorFeedback {
  id: number;
  generated_at: string | null;
  subjective: string | null;
  objective: string | null;
  assessment: string | null;
  plan: string | null;
}

export interface DoctorFeedbackInput {
  summary?: string;
  assessment?: string;
  plan?: string;
  visit_date?: string;  // YYYY-MM-DD
}

export async function exportDoctorReport(days = 30): Promise<DoctorExport> {
  const { data } = await api.get<DoctorExport>(
    '/doctor-report/export', { params: { days } },
  );
  return data;
}

export async function submitDoctorFeedback(input: DoctorFeedbackInput): Promise<void> {
  await api.post('/doctor-report/feedback', input);
}

export async function listDoctorFeedback(limit = 20): Promise<DoctorFeedback[]> {
  const { data } = await api.get<{ feedback: DoctorFeedback[] }>(
    '/doctor-report/feedback/me', { params: { limit } },
  );
  return data.feedback;
}
