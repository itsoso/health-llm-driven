import api from './client';

export interface BodyAnalysisItem {
  metric: string;
  value: any;
  status: string;
  advice: string;
}

export interface BodyAnalysisResult {
  status: string;
  record_date?: string;
  analysis: BodyAnalysisItem[];
}

export interface BodyCompositionDataPoint {
  date: string;
  weight: number;
  body_fat_percentage: number | null;
  muscle_mass_kg: number | null;
  visceral_fat: number | null;
  bone_mass_kg: number | null;
  water_percentage: number | null;
  bmi: number | null;
  bmr: number | null;
  skeletal_muscle_pct: number | null;
}

export interface BodyCompositionTrend {
  data_points: BodyCompositionDataPoint[];
  summary: {
    current_weight: number | null;
    weight_change: number | null;
    current_body_fat: number | null;
    current_muscle_mass: number | null;
    current_bmi: number | null;
    record_count: number;
    date_range: string;
    body_fat_change?: number;
    muscle_mass_change?: number;
  };
}

export interface CycleCalendar {
  year: number;
  month: number;
  period_days: string[];
  symptom_days: Record<string, Array<{ type: string; severity: number }>>;
}

export interface CyclePrediction {
  predicted_start: string;
  predicted_end: string;
  avg_cycle_length: number;
  avg_period_length: number | null;
  based_on_cycles: number;
}

export interface CycleStats {
  avg_cycle_length: number | null;
  avg_period_length: number | null;
  total_cycles: number;
}

export interface CycleSymptomItem {
  id: number;
  cycle_id: number | null;
  record_date: string;
  symptom_type: string;
  severity: number;
  notes: string | null;
}

export interface HealthReport {
  id: number;
  user_id: number;
  report_type: string;
  start_date: string;
  end_date: string;
  title: string;
  exercise_summary: Record<string, any>;
  diet_summary: Record<string, any>;
  sleep_summary: Record<string, any>;
  weight_summary: Record<string, any>;
  mood_summary: Record<string, any>;
  checkin_summary: Record<string, any>;
  vital_signs_summary: Record<string, any>;
  ai_analysis: string | null;
  ai_recommendations: string[];
  health_score: number | null;
  comparison: Record<string, any>;
  created_at: string;
  updated_at: string | null;
}

export interface HealthScoreDimension {
  name: string;
  score: number;
  weight: number;
  description: string;
  details: Record<string, any>;
}

export interface HealthScoreResult {
  status: string;
  date?: string;
  total_score: number;
  grade?: string;
  dimensions: HealthScoreDimension[];
  suggestions: string[];
}

export interface HealthScoreTrend {
  scores: HealthScoreTrendItem[];
  avg_score: number | null;
  trend: string | null;
  best_day: HealthScoreTrendItem | null;
  worst_day: HealthScoreTrendItem | null;
}

export interface HealthScoreTrendItem {
  date: string;
  score: number;
  grade: string;
}

export interface MenstrualCycleItem {
  id: number;
  user_id: number;
  start_date: string;
  end_date: string | null;
  cycle_length: number | null;
  period_length: number | null;
  flow_intensity: string;
  notes: string | null;
  created_at: string | null;
}

export const basicHealthApi = {
  create: (data: any) => api.post('/basic-health', data),
  getUserData: (userId: number) => api.get(`/basic-health/user/${userId}`),
  getLatest: (userId: number) => api.get(`/basic-health/user/${userId}/latest`),
  // 使用 /me 端点，自动使用当前登录用户
  getMyLatest: () => api.get('/basic-health/me/latest'),
  getMyData: () => api.get('/basic-health/me'),
};

// 体检数据
export const dailyHealthApi = {
  createGarminData: (data: any) => api.post('/daily-health/garmin', data),
  // 使用 /me 端点，自动使用当前登录用户
  getMyGarminData: (startDate?: string, endDate?: string) =>
    api.get('/daily-health/garmin/me', {
      params: { start_date: startDate, end_date: endDate },
    }),
  // 保留旧方法以兼容
  getUserGarminData: (userId: number, startDate?: string, endDate?: string) =>
    api.get(`/daily-health/garmin/user/${userId}`, {
      params: { start_date: startDate, end_date: endDate },
    }),
  createExercise: (data: any) => api.post('/daily-health/exercise', data),
  createDiet: (data: any) => api.post('/daily-health/diet', data),
  createWater: (data: any) => api.post('/daily-health/water', data),
  createSupplement: (data: any) => api.post('/daily-health/supplement', data),
  createOutdoor: (data: any) => api.post('/daily-health/outdoor', data),
};

// 健康打卡
export const healthAnalysisApi = {
  analyzeIssues: (userId: number, forceRefresh: boolean = false) => 
    api.get(`/analysis/user/${userId}/issues`, { params: { force_refresh: forceRefresh } }),
  getAdvice: (userId: number, checkinDate: string) =>
    api.get(`/analysis/user/${userId}/advice`, { params: { checkin_date: checkinDate } }),
  // 使用 /me 端点
  analyzeMyIssues: (forceRefresh: boolean = false) =>
    api.get('/analysis/me/issues', { params: { force_refresh: forceRefresh } }),
  getMyAdvice: (checkinDate: string) =>
    api.get('/analysis/me/advice', { params: { checkin_date: checkinDate } }),
};

// Garmin数据分析
export const garminAnalysisApi = {
  analyzeSleep: (userId: number, days: number = 7) =>
    api.get(`/garmin-analysis/user/${userId}/sleep`, { params: { days } }),
  analyzeHeartRate: (userId: number, days: number = 7) =>
    api.get(`/garmin-analysis/user/${userId}/heart-rate`, { params: { days } }),
  analyzeBodyBattery: (userId: number, days: number = 7) =>
    api.get(`/garmin-analysis/user/${userId}/body-battery`, { params: { days } }),
  analyzeActivity: (userId: number, days: number = 7) =>
    api.get(`/garmin-analysis/user/${userId}/activity`, { params: { days } }),
  getComprehensive: (userId: number, days: number = 7) =>
    api.get(`/garmin-analysis/user/${userId}/comprehensive`, { params: { days } }),
  // 使用 /me 端点，自动使用当前登录用户
  getMyComprehensive: (days: number = 7) =>
    api.get('/garmin-analysis/me/comprehensive', { params: { days } }),
  analyzeMySleep: (days: number = 7) =>
    api.get('/garmin-analysis/me/sleep', { params: { days } }),
  analyzeMyHeartRate: (days: number = 7) =>
    api.get('/garmin-analysis/me/heart-rate', { params: { days } }),
  analyzeMyBodyBattery: (days: number = 7) =>
    api.get('/garmin-analysis/me/body-battery', { params: { days } }),
  analyzeMyActivity: (days: number = 7) =>
    api.get('/garmin-analysis/me/activity', { params: { days } }),
};

// 数据收集状态
export const healthScoreApi = {
  getDailyScore: (targetDate?: string) =>
    api.get<HealthScoreResult>('/health-score/daily/me', { params: { target_date: targetDate } }),
  getScoreTrend: (days: number = 7) =>
    api.get<HealthScoreTrend>('/health-score/trend/me', { params: { days } }),
};

// 用药管理 API
export const healthReportApi = {
  generate: (reportType: string, startDate?: string) =>
    api.post<HealthReport>('/health-report/generate', {
      report_type: reportType,
      start_date: startDate,
    }),
  list: (reportType?: string, limit?: number) =>
    api.get<HealthReport[]>('/health-report/list/me', {
      params: { report_type: reportType, limit },
    }),
  getDetail: (id: number) =>
    api.get<HealthReport>(`/health-report/detail/${id}`),
  delete: (id: number) =>
    api.delete(`/health-report/${id}`),
};

// 健康评分 API
export const healthTrendApi = {
  getLatest: () =>
    api.get<{
      report_date: string | null;
      dimensions: Array<{
        dimension: string;
        period: string;
        trend_direction: string | null;
        insights: string[];
        suggestions: string[];
        risk_alerts: string[];
        report_date: string;
      }>;
    }>('/health-trends/latest'),
  getDimension: (dimension: string, period: string = '7d') =>
    api.get<{
      id: number;
      report_date: string;
      dimension: string;
      period: string;
      trend_direction: string | null;
      raw_data_summary: Record<string, unknown> | null;
      insights: string[];
      suggestions: string[];
      risk_alerts: string[];
      full_report: string | null;
      created_at: string;
    }>(`/health-trends/${dimension}`, { params: { period } }),
  getHistory: (limit: number = 20, offset: number = 0) =>
    api.get<{
      total: number;
      items: Array<{
        id: number;
        report_date: string;
        dimension: string;
        period: string;
        trend_direction: string | null;
        insights: string[];
        created_at: string;
      }>;
    }>('/health-trends/history', { params: { limit, offset } }),
  generate: () =>
    api.post<{ analyzed_dimensions: string[] }>('/health-trends/generate'),
};

// OpenClaw Skills 远程管理 (admin only)
export const dailyRecommendationApi = {
  getRecommendations: (userId: number, useLlm: boolean = true) =>
    api.get(`/daily-recommendation/user/${userId}/recommendations`, { params: { use_llm: useLlm } }),
  getToday: (userId: number, useLlm: boolean = true) =>
    api.get(`/daily-recommendation/user/${userId}/today`, { params: { use_llm: useLlm } }),
  // 使用 /me 端点
  getMyRecommendations: (useLlm: boolean = true) =>
    api.get('/daily-recommendation/me', { params: { use_llm: useLlm } }),
};

// 补剂管理
export const bodyCompositionApi = {
  getTrend: (days: number = 30) =>
    api.get<BodyCompositionTrend>('/body-composition/trend/me', { params: { days } }),
  getAnalysis: () =>
    api.get<BodyAnalysisResult>('/body-composition/analysis/me'),
};

// OpenClaw AI 对话接口
export const womensHealthApi = {
  startPeriod: (start_date: string, flow_intensity: string = 'moderate') =>
    api.post<MenstrualCycleItem>('/womens-health/period/start', { start_date, flow_intensity }),
  endPeriod: (cycleId: number, end_date: string) =>
    api.post<MenstrualCycleItem>(`/womens-health/period/${cycleId}/end`, { end_date }),
  getCycles: (limit: number = 12) =>
    api.get<MenstrualCycleItem[]>(`/womens-health/cycles/me?limit=${limit}`),
  predict: () =>
    api.get<{ prediction: CyclePrediction | null; message?: string }>('/womens-health/predict/me'),
  logSymptom: (data: { record_date: string; symptom_type: string; severity: number; notes?: string }) =>
    api.post<CycleSymptomItem>('/womens-health/symptoms', data),
  getStats: () =>
    api.get<CycleStats>('/womens-health/stats/me'),
  getCalendar: (year: number, month: number) =>
    api.get<CycleCalendar>(`/womens-health/calendar/me?year=${year}&month=${month}`),
  getSymptoms: (params?: { cycle_id?: number; start_date?: string; end_date?: string }) =>
    api.get<CycleSymptomItem[]>('/womens-health/symptoms/me', { params }),
};
