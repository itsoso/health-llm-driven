import api from './client';

export interface ExcretionRecord {
  id: number;
  user_id: number;
  record_date: string;
  record_time: string | null;
  type: 'bowel' | 'urine';
  stool_type: number | null;
  color: string | null;
  amount: string | null;
  duration_minutes: number | null;
  blood_present: boolean | null;
  urine_color: string | null;
  urine_amount: string | null;
  urgency: number | null;
  pain_level: number | null;
  notes: string | null;
  created_at: string;
}

export interface ExcretionStats {
  total_records: number;
  bowel_count: number;
  urine_count: number;
  avg_bowel_per_day: number | null;
  avg_urine_per_day: number | null;
  avg_stool_type: number | null;
  stool_type_distribution: Record<number, number>;
  color_distribution: Record<string, number>;
  blood_count: number;
  daily_summary: Array<{
    date: string;
    bowel_count: number;
    urine_count: number;
    avg_stool_type: number | null;
    has_blood: boolean;
    has_pain: boolean;
  }>;
}

export interface MedicationAdherence {
  adherence_rate: number;
  total_taken: number;
  total_skipped: number;
  total_expected: number;
  days: number;
}

export interface MedicationItem {
  id: number;
  user_id: number;
  name: string;
  dosage: string | null;
  frequency: string | null;
  times_per_day: number;
  reminder_times: string[] | null;
  category: string | null;
  purpose: string | null;
  is_active: boolean;
  start_date: string | null;
  end_date: string | null;
  notes: string | null;
  created_at: string | null;
}

export interface MedicationTodayStatus {
  medication_id: number;
  name: string;
  dosage: string | null;
  total_count: number;
  taken_count: number;
  skipped_count: number;
  reminder_times: string[];
  logs: { time: string; status: string; id: number }[];
}

export interface MoodCalendar {
  year: number;
  month: number;
  days: Record<number, {
    mood_score: number;
    mood_tags: string[];
    has_journal: boolean;
    energy_level: number | null;
    stress_level: number | null;
  }>;
  total_days: number;
  recorded_days: number;
  avg_mood_score: number | null;
}

export interface MoodRecord {
  id: number;
  user_id: number;
  record_date: string;
  mood_score: number;
  mood_tags: string[];
  energy_level: number | null;
  stress_level: number | null;
  anxiety_level: number | null;
  sleep_quality: number | null;
  journal: string | null;
  triggers: string[];
  coping_methods: string[];
  record_time: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface MoodStats {
  total_records: number;
  avg_mood_score: number | null;
  avg_energy_level: number | null;
  avg_stress_level: number | null;
  avg_anxiety_level: number | null;
  mood_distribution: Record<number, number>;
  top_mood_tags: Record<string, number>;
  top_triggers: Record<string, number>;
  top_coping_methods: Record<string, number>;
  daily_trend: {
    date: string;
    mood_score: number;
    energy_level: number | null;
    stress_level: number | null;
    anxiety_level: number | null;
    record_count: number;
  }[];
  mood_energy_correlation: number | null;
  mood_sleep_correlation: number | null;
}

export interface SleepRecordData {
  id: number;
  user_id: number;
  record_date: string;
  bedtime: string;
  wake_time: string;
  sleep_quality: number;
  total_duration_minutes: number | null;
  wake_count: number;
  had_dream: boolean;
  dream_description: string | null;
  fall_asleep_difficulty: number | null;
  morning_feeling: number | null;
  notes: string | null;
  created_at: string;
}

export interface SleepStats {
  total_records: number;
  avg_sleep_quality: number | null;
  avg_duration_hours: number | null;
  avg_wake_count: number | null;
  avg_fall_asleep_difficulty: number | null;
  avg_morning_feeling: number | null;
  dream_frequency: number | null;
  quality_distribution: Record<number, number>;
  daily_trend: Array<{
    date: string;
    sleep_quality: number;
    duration_hours: number | null;
    wake_count: number | null;
    morning_feeling: number | null;
  }>;
  avg_bedtime: string | null;
  avg_wake_time: string | null;
}

export const checkinApi = {
  create: (data: any) => api.post('/checkin', data),
  getUserCheckins: (userId: number, startDate?: string, endDate?: string) =>
    api.get(`/checkin/user/${userId}`, {
      params: { start_date: startDate, end_date: endDate },
    }),
  getToday: (userId: number) => api.get(`/checkin/user/${userId}/today`),
  // 使用 /me 端点
  getMyToday: () => api.get('/checkin/me/today'),
};

// 目标管理
export const supplementApi = {
  // 补剂定义
  createDefinition: (data: any) => api.post('/supplements/definitions', data),
  getUserDefinitions: (userId: number, activeOnly: boolean = true) =>
    api.get(`/supplements/definitions/user/${userId}`, { params: { active_only: activeOnly } }),
  updateDefinition: (supplementId: number, data: any) =>
    api.put(`/supplements/definitions/${supplementId}`, data),
  deleteDefinition: (supplementId: number) =>
    api.delete(`/supplements/definitions/${supplementId}`),
  // 补剂打卡
  createRecord: (data: any) => api.post('/supplements/records', data),
  batchCheckin: (data: any) => api.post('/supplements/records/batch', data),
  getUserRecordsWithStatus: (userId: number, recordDate: string) =>
    api.get(`/supplements/records/user/${userId}/date/${recordDate}`),
  getStats: (userId: number, days: number = 7) =>
    api.get(`/supplements/records/user/${userId}/stats`, { params: { days } }),
  // 使用 /me 端点
  getMyRecordsWithStatus: (recordDate: string) =>
    api.get(`/supplements/me/date/${recordDate}`),
  getMyStats: (days: number = 7) =>
    api.get('/supplements/me/stats', { params: { days } }),
  // 科学推荐
  getScientificRecommendation: (targetDate?: string, debug: boolean = false) =>
    api.post('/supplements/scientific-recommendation', { target_date: targetDate, debug }),
  // 每日补剂动态指南
  getDailyGuide: (targetDate?: string) =>
    api.get('/supplements/daily-guide', { params: targetDate ? { target_date: targetDate } : {} }),
};

// 补剂审计 (Supplement Audit) — 长周期决策文档，带 action item 状态追踪
export const supplementAuditApi = {
  listMine: (limit: number = 20) =>
    api.get('/supplement-audits/me', { params: { limit } }),
  getActive: () => api.get('/supplement-audits/me/active'),
  getById: (auditId: number) => api.get(`/supplement-audits/me/${auditId}`),
  create: (payload: any) => api.post('/supplement-audits/me', payload),
  updateItem: (itemId: number, payload: { status?: string; user_note?: string; rejected_reason?: string }) =>
    api.patch(`/supplement-audits/me/items/${itemId}`, payload),
};

// 健康咨询 (Health Consultation) — 多层级症状咨询追踪，含 hypotheses/actions/predictions/red_flags + 自动回测
export const healthConsultationApi = {
  listMine: (limit: number = 20) =>
    api.get('/health-consultations/me', { params: { limit } }),
  getActive: () => api.get('/health-consultations/me/active'),
  getById: (id: number) => api.get(`/health-consultations/me/${id}`),
  create: (payload: any) => api.post('/health-consultations/me', payload),
  updateItem: (itemId: number, payload: {
    status?: string;
    user_note?: string;
    outcome?: string;
    actual_value?: string;
    meta_patch?: Record<string, any>;
  }) => api.patch(`/health-consultations/me/items/${itemId}`, payload),
  // 自动回测 predictions: 对比 garmin_data / medical_indicators 给出建议 status
  verifyPredictions: (id: number) => api.post(`/health-consultations/me/${id}/verify`),
};

// 儿童狗狗空间
export const excretionApi = {
  createRecord: (data: Partial<ExcretionRecord>) =>
    api.post<ExcretionRecord>('/excretion/records', data),
  getMyRecords: (params?: { type?: string; start_date?: string; end_date?: string; limit?: number }) =>
    api.get<ExcretionRecord[]>('/excretion/records/me', { params }),
  getTodayRecords: () =>
    api.get<ExcretionRecord[]>('/excretion/records/me/today'),
  getRecord: (id: number) =>
    api.get<ExcretionRecord>(`/excretion/records/${id}`),
  updateRecord: (id: number, data: Partial<ExcretionRecord>) =>
    api.put<ExcretionRecord>(`/excretion/records/${id}`, data),
  deleteRecord: (id: number) =>
    api.delete(`/excretion/records/${id}`),
  getStats: (days?: number) =>
    api.get<ExcretionStats>('/excretion/stats/me', { params: { days } }),
};

// 睡眠记录 API
export const sleepApi = {
  createRecord: (data: {
    record_date: string;
    bedtime: string;
    wake_time: string;
    sleep_quality: number;
    wake_count?: number;
    had_dream?: boolean;
    dream_description?: string;
    fall_asleep_difficulty?: number;
    morning_feeling?: number;
    notes?: string;
  }) => api.post<SleepRecordData>('/sleep/records', data),
  getMyRecords: (params?: { start_date?: string; end_date?: string; limit?: number }) =>
    api.get<SleepRecordData[]>('/sleep/records/me', { params }),
  getTodayRecord: () =>
    api.get<SleepRecordData | null>('/sleep/records/me/today'),
  getRecord: (id: number) =>
    api.get<SleepRecordData>(`/sleep/records/${id}`),
  updateRecord: (id: number, data: Partial<SleepRecordData>) =>
    api.put<SleepRecordData>(`/sleep/records/${id}`, data),
  deleteRecord: (id: number) =>
    api.delete(`/sleep/records/${id}`),
  getStats: (days?: number) =>
    api.get<SleepStats>('/sleep/stats/me', { params: { days } }),
};

// 习惯追踪 API（已废弃，模块已移除）
// export const habitApi = { ... };

// 设备管理
export const moodApi = {
  createRecord: (data: {
    record_date: string;
    mood_score: number;
    mood_tags?: string[];
    energy_level?: number;
    stress_level?: number;
    anxiety_level?: number;
    sleep_quality?: number;
    journal?: string;
    triggers?: string[];
    coping_methods?: string[];
  }) => api.post<MoodRecord>('/mood/records', data),

  getMyRecords: (startDate?: string, endDate?: string, limit?: number) =>
    api.get<MoodRecord[]>('/mood/records/me', {
      params: { start_date: startDate, end_date: endDate, limit },
    }),

  getTodayRecord: () =>
    api.get<MoodRecord | null>('/mood/records/me/today'),

  getRecord: (id: number) =>
    api.get<MoodRecord>(`/mood/records/${id}`),

  updateRecord: (id: number, data: Partial<{
    mood_score: number;
    mood_tags: string[];
    energy_level: number;
    stress_level: number;
    anxiety_level: number;
    sleep_quality: number;
    journal: string;
    triggers: string[];
    coping_methods: string[];
  }>) => api.put<MoodRecord>(`/mood/records/${id}`, data),

  deleteRecord: (id: number) =>
    api.delete(`/mood/records/${id}`),

  getStats: (days?: number) =>
    api.get<MoodStats>('/mood/stats/me', { params: { days } }),

  getCalendar: (year: number, month: number) =>
    api.get<MoodCalendar>('/mood/calendar/me', { params: { year, month } }),
};

// 健康报告 API
export const medicationApi = {
  addMedication: (data: {
    name: string; dosage?: string; frequency?: string; times_per_day?: number;
    reminder_times?: string[]; category?: string; purpose?: string; notes?: string;
  }) => api.post<MedicationItem>('/medication/medications', data),

  listMyMedications: (activeOnly: boolean = true) =>
    api.get<MedicationItem[]>('/medication/medications/me', { params: { active_only: activeOnly } }),

  updateMedication: (id: number, data: Partial<MedicationItem>) =>
    api.put<MedicationItem>(`/medication/medications/${id}`, data),

  deactivateMedication: (id: number) =>
    api.delete(`/medication/medications/${id}`),

  logMedication: (data: {
    medication_id: number; taken_time: string; status?: string;
    skip_reason?: string; notes?: string;
  }) => api.post('/medication/logs', data),

  getTodayStatus: () =>
    api.get<MedicationTodayStatus[]>('/medication/today/me'),

  getAdherence: (days: number = 7) =>
    api.get<MedicationAdherence>('/medication/adherence/me', { params: { days } }),
};

// 身体成分分析 API