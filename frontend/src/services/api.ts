import axios from 'axios';

// 判断是否为原生App环境
// 原生App使用完整的API地址，Web版本使用相对路径（通过Next.js代理）
const isNativeApp = typeof window !== 'undefined' && (
  process.env.NEXT_PUBLIC_IS_NATIVE_APP === 'true' ||
  // Capacitor 环境检测
  (window as any).Capacitor?.isNativePlatform?.()
);

// API基础地址
const API_BASE_URL = isNativeApp 
  ? 'https://health.executor.life/api'  // 原生App直接调用线上API（新域名）
  : (process.env.NEXT_PUBLIC_API_BASE_URL || '/api');  // Web版本使用代理

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器：自动附加认证token
api.interceptors.request.use(
  (config) => {
    // 从localStorage获取token（使用与AuthContext相同的键名）
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('auth_token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器：处理401错误（未授权）
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // token过期或无效，清除本地存储并跳转登录
      if (typeof window !== 'undefined') {
        localStorage.removeItem('auth_token');
        // 如果不在登录页，跳转到登录页
        if (!window.location.pathname.includes('/login')) {
          window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

// 用户相关
export const userApi = {
  getUsers: () => api.get('/users'),
  getUser: (id: number) => api.get(`/users/${id}`),
  createUser: (data: any) => api.post('/users', data),
};

// 基础健康数据
export const basicHealthApi = {
  create: (data: any) => api.post('/basic-health', data),
  getUserData: (userId: number) => api.get(`/basic-health/user/${userId}`),
  getLatest: (userId: number) => api.get(`/basic-health/user/${userId}/latest`),
  // 使用 /me 端点，自动使用当前登录用户
  getMyLatest: () => api.get('/basic-health/me/latest'),
  getMyData: () => api.get('/basic-health/me'),
};

// 体检数据
export const medicalExamApi = {
  create: (data: any) => api.post('/medical-exams', data),
  getUserExams: (userId: number) => api.get(`/medical-exams/user/${userId}`),
  importFromJson: (userId: number, data: any) =>
    api.post(`/medical-exams/import/json?user_id=${userId}`, data),
};

// 疾病记录
export const diseaseApi = {
  create: (data: any) => api.post('/diseases', data),
  getUserDiseases: (userId: number, status?: string) =>
    api.get(`/diseases/user/${userId}`, { params: { status } }),
};

// 日常健康记录
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
export const goalApi = {
  create: (data: any) => api.post('/goals/', data),
  getUserGoals: (userId: number, status?: string, goalType?: string, goalPeriod?: string) =>
    api.get(`/goals/user/${userId}`, {
      params: { status, goal_type: goalType, goal_period: goalPeriod },
    }),
  updateProgress: (goalId: number, progressDate: string, progressValue?: number) =>
    api.post(`/goals/${goalId}/progress`, null, {
      params: { progress_date: progressDate, progress_value: progressValue },
    }),
  getProgress: (goalId: number, startDate?: string, endDate?: string) =>
    api.get(`/goals/${goalId}/progress`, {
      params: { start_date: startDate, end_date: endDate },
    }),
  generateFromAnalysis: (userId: number) =>
    api.post(`/goals/generate-from-analysis/${userId}`),
  checkCompletion: (goalId: number, checkDate?: string) =>
    api.get(`/goals/${goalId}/completion`, { params: { check_date: checkDate } }),
  // 使用 /me 端点
  getMyGoals: (status?: string, goalType?: string, goalPeriod?: string) =>
    api.get('/goals/me', { params: { status, goal_type: goalType, goal_period: goalPeriod } }),
  generateMyGoalsFromAnalysis: () =>
    api.post('/goals/me/generate-from-analysis'),
  // 获取目标智能引导
  getGuidance: (data: { goal_type: string; goal_description?: string; target_value?: number }) =>
    api.post('/goals/guidance', data),
};

// 数据收集
export const dataCollectionApi = {
  syncGarmin: (userId: number, targetDate: string, accessToken?: string) =>
    api.post('/data-collection/garmin/sync', null, {
      params: { user_id: userId, target_date: targetDate, access_token: accessToken },
    }),
};

// 健康分析
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
export const dataCollectionStatusApi = {
  getSyncStatus: (userId: number, days: number = 30) =>
    api.get(`/data-collection/garmin/sync-status/${userId}`, { params: { days } }),
  // 使用 /me 端点，自动使用当前登录用户
  getMySyncStatus: (days: number = 30) =>
    api.get('/data-collection/garmin/me/sync-status', { params: { days } }),
};

// 每日建议
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
};

// 习惯追踪 API（已废弃，模块已移除）
// export const habitApi = { ... };

// 设备管理
export const deviceApi = {
  // 获取支持的设备列表
  getSupportedDevices: () => api.get('/devices/supported'),
  // 获取当前用户绑定的设备
  getMyDevices: () => api.get('/devices/me'),
  // 获取指定设备凭证
  getDeviceCredential: (deviceType: string) => api.get(`/devices/me/${deviceType}`),
  // Apple Health 导入
  importAppleHealth: (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/devices/apple/import', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
  },
  // Apple Health 测试连接
  testAppleConnection: () => api.post('/devices/apple/test-connection'),
  // Apple Health 同步
  syncAppleData: (days: number = 7) => api.post('/devices/apple/sync', { days }),
  // 通用设备同步
  syncDevice: (deviceType: string, days: number = 7) => 
    api.post(`/devices/${deviceType}/sync`, { days }),
  // 同步所有设备
  syncAllDevices: (days: number = 7) => api.post('/devices/sync-all', { days }),
  // 解绑设备
  unbindDevice: (deviceType: string) => api.delete(`/devices/${deviceType}`),
};

// 运动指导
export const workoutGuidanceApi = {
  // 获取运动前指导
  getPreWorkoutGuidance: (goalId?: number, workoutType?: string, debug: boolean = false) => {
    const params = new URLSearchParams();
    if (goalId) params.append('goal_id', goalId.toString());
    if (workoutType) params.append('workout_type', workoutType);
    if (debug) params.append('debug', 'true');
    return api.post(`/workout/pre-workout-guidance?${params.toString()}`);
  },
  // 获取运动后分析
  getPostWorkoutAnalysis: (workoutId: number, forceRegenerate: boolean = false, debug: boolean = false, cacheOnly: boolean = false) => {
    const params = new URLSearchParams();
    if (forceRegenerate) params.append('force_regenerate', 'true');
    if (debug) params.append('debug', 'true');
    if (cacheOnly) params.append('cache_only', 'true');
    return api.post(`/workout/post-workout-analysis/${workoutId}?${params.toString()}`);
  },
};

// 饮食推荐 API
export const dietRecommendationApi = {
  // 获取我的饮食推荐
  getMyRecommendation: (mealType?: string) => {
    const params = new URLSearchParams();
    if (mealType) params.append('meal_type', mealType);
    return api.get(`/v1/diet-recommendation/me?${params.toString()}`);
  },
};

// 资讯 API
export interface NewsArticle {
  id: number;
  source_batch_id: string;
  source_type: string;
  title: string;
  summary: string | null;
  content?: string;
  tags: string[] | null;
  topics?: string[] | null;
  key_people?: string[] | null;
  source_group: string | null;
  llm_models?: string[] | null;
  aggregator_model?: string | null;
  is_pinned: boolean;
  view_count: number;
  source_created_at?: string;
  created_at: string;
}

export const newsApi = {
  // 获取资讯列表
  getArticles: (page: number = 1, pageSize: number = 20, sourceType?: string) => {
    const params = new URLSearchParams();
    params.append('page', page.toString());
    params.append('page_size', pageSize.toString());
    if (sourceType) params.append('source_type', sourceType);
    return api.get<NewsArticle[]>(`/news/articles?${params.toString()}`);
  },
  // 获取资讯详情
  getArticle: (articleId: number) => api.get<NewsArticle>(`/news/articles/${articleId}`),
  // 管理员删除文章
  deleteArticle: (articleId: number) => api.delete(`/news/admin/articles/${articleId}`),
  // 获取文章评论
  getComments: (articleId: number) => api.get<CommentsResponse>(`/news/articles/${articleId}/comments`),
  // 发表评论
  createComment: (articleId: number, content: string, parentId?: number) =>
    api.post<NewsComment>(`/news/articles/${articleId}/comments`, { content, parent_id: parentId }),
  // 删除评论
  deleteComment: (commentId: number) => api.delete(`/news/comments/${commentId}`),
};

// 评论相关类型
export interface CommentUser {
  id: number;
  name: string;
  is_admin: boolean;
}

export interface NewsComment {
  id: number;
  article_id: number;
  user_id: number;
  parent_id: number | null;
  content: string;
  created_at: string;
  user: CommentUser;
  replies: NewsComment[];
}

export interface CommentsResponse {
  comments: NewsComment[];
  total: number;
}

// 外部建议接口
export interface ExternalRecommendation {
  id: number;
  category: string;
  title: string;
  content: string;
  source_name: string;
  recommendation_date: string;
  created_at: string;
}

export interface TodayExternalRecommendations {
  date: string;
  has_recommendations: boolean;
  categories: Record<string, ExternalRecommendation[]>;
}

export const externalRecommendationApi = {
  // 获取今日外部建议
  getToday: () => api.get<TodayExternalRecommendations>('/external-recommendations/today'),
};

// 情绪追踪 API
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

export interface HealthScoreTrendItem {
  date: string;
  score: number;
  grade: string;
}

export interface HealthScoreTrend {
  scores: HealthScoreTrendItem[];
  avg_score: number | null;
  trend: string | null;
  best_day: HealthScoreTrendItem | null;
  worst_day: HealthScoreTrendItem | null;
}

export const healthScoreApi = {
  getDailyScore: (targetDate?: string) =>
    api.get<HealthScoreResult>('/health-score/daily/me', { params: { target_date: targetDate } }),
  getScoreTrend: (days: number = 7) =>
    api.get<HealthScoreTrend>('/health-score/trend/me', { params: { days } }),
};

// 用药管理 API
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

export interface MedicationAdherence {
  adherence_rate: number;
  total_taken: number;
  total_skipped: number;
  total_expected: number;
  days: number;
}

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

export const bodyCompositionApi = {
  getTrend: (days: number = 30) =>
    api.get<BodyCompositionTrend>('/body-composition/trend/me', { params: { days } }),
  getAnalysis: () =>
    api.get<BodyAnalysisResult>('/body-composition/analysis/me'),
};

// OpenClaw AI 对话接口
export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  last_message?: string;
}

export interface ConversationDetail {
  id: number;
  title: string;
  messages: ChatMessage[];
}

export interface DietSavedData {
  record_id: number;
  food_items: string;
  total_calories?: number;
  total_protein?: number;
  total_carbs?: number;
  total_fat?: number;
  meal_type: string;
  record_date: string;
}

export interface ChatSendResponse {
  conversation_id: number;
  message_id: number;
  reply: string;
  diet_saved?: boolean;
  diet_data?: DietSavedData;
}

// ====== 女性健康 ======
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

export interface CycleCalendar {
  year: number;
  month: number;
  period_days: string[];
  symptom_days: Record<string, Array<{ type: string; severity: number }>>;
}

export interface CycleSymptomItem {
  id: number;
  cycle_id: number | null;
  record_date: string;
  symptom_type: string;
  severity: number;
  notes: string | null;
}

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

export const chatApi = {
  // 发送消息
  sendMessage: (message: string, conversationId?: number) =>
    api.post<ChatSendResponse>('/chat/send', { message, conversation_id: conversationId }),
  // 获取对话列表
  getConversations: (limit: number = 20) =>
    api.get<Conversation[]>(`/chat/conversations?limit=${limit}`),
  // 获取对话详情
  getConversation: (conversationId: number) =>
    api.get<ConversationDetail>(`/chat/conversations/${conversationId}`),
  // 删除对话
  deleteConversation: (conversationId: number) =>
    api.delete(`/chat/conversations/${conversationId}`),
};
