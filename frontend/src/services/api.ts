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

// 儿童狗狗空间
export interface KidsPetState {
  breed_id: string;
  breed_name: string;
  breed_image?: string | null;
  breed_cost: number;
  dog_name: string;
  hunger: number;
  happiness: number;
  level: number;
  xp: number;
  food_bags: number;
  has_house: boolean;
  has_garden: boolean;
  last_decay_at?: string | null;
  last_interaction_at?: string | null;
}

export interface KidsPetResponse {
  has_pet: boolean;
  kids_points: number;
  pet?: KidsPetState | null;
  message?: string;
}

export const kidsPetApi = {
  getMyPet: () => api.get<KidsPetResponse>('/kids-pet/me'),
  adoptPet: (data: {
    breed_id: string;
    breed_name: string;
    breed_cost: number;
    breed_image?: string;
    dog_name: string;
  }) => api.post<KidsPetResponse>('/kids-pet/adopt', data),
  action: (action: 'buy_food' | 'feed' | 'feed_full' | 'buy_house' | 'buy_garden' | 'return_house' | 'return_garden' | 'return_dog') =>
    api.post<KidsPetResponse>('/kids-pet/action', { action }),
};

// Kids每日计划 API
export interface KidsPlanItem {
  id: string;
  emoji: string;
  text: string;
  done: boolean;
  startTime?: string;
  endTime?: string;
}

export interface KidsPlanResponse {
  plan_date: string;
  items: KidsPlanItem[];
  awarded_tier: number;
  points_awarded: number;
  total_kids_points: number;
}

export interface KidsPlanDaySummary {
  plan_date: string;
  total_items: number;
  done_count: number;
  completion_rate: number;
  awarded_tier: number;
}

export interface KidsPlanHistoryResponse {
  range: string;
  start_date: string;
  end_date: string;
  days: KidsPlanDaySummary[];
  total_plan_days: number;
  total_items: number;
  total_done: number;
  avg_completion_rate: number;
  current_streak: number;
  best_streak: number;
  top_activities: Array<{ emoji: string; text: string; count: number }>;
}

export interface KidsPlanReviewResponse {
  range: string;
  start_date: string;
  end_date: string;
  review_text: string;
  stats_summary: Record<string, number>;
}

export const kidsPlanApi = {
  getPlan: (planDate: string) =>
    api.get<KidsPlanResponse>(`/kids-plan/${planDate}`),
  savePlan: (planDate: string, items: KidsPlanItem[]) =>
    api.put<KidsPlanResponse>(`/kids-plan/${planDate}`, { items }),
  copyPlan: (fromDate: string, toDate: string) =>
    api.post<KidsPlanResponse>('/kids-plan/copy', { from_date: fromDate, to_date: toDate }),
  getHistory: (range: string) =>
    api.get<KidsPlanHistoryResponse>('/kids-plan/history', { params: { range } }),
  getReview: (range: string) =>
    api.post<KidsPlanReviewResponse>('/kids-plan/review', { range }),
};

// ===== 私信聊天 =====

export interface DMResponse {
  id: number;
  sender_id: number;
  receiver_id: number;
  content: string;
  is_read: boolean;
  created_at: string;
  sender_name: string | null;
  sender_avatar: string | null;
}

export interface DMConversationItem {
  friend_id: number;
  friend_name: string;
  friend_avatar: string | null;
  last_message: string;
  last_message_time: string;
  unread_count: number;
}

export interface DMHistoryResponse {
  messages: DMResponse[];
  has_more: boolean;
}

export const dmApi = {
  getConversations: () =>
    api.get<DMConversationItem[]>('/dm/conversations'),
  getMessages: (friendId: number, beforeId?: number, limit?: number) =>
    api.get<DMHistoryResponse>(`/dm/messages/${friendId}`, {
      params: { before_id: beforeId || 0, limit: limit || 30 },
    }),
  sendMessage: (receiverId: number, content: string) =>
    api.post<DMResponse>('/dm/send', { receiver_id: receiverId, content }),
  markRead: (friendId: number) =>
    api.put(`/dm/read/${friendId}`),
  getUnreadCount: () =>
    api.get<{ total_unread: number }>('/dm/unread-count'),
};

// 排泄记录 API
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

// Withings 设备管理
export const withingsApi = {
  // 获取绑定状态
  getStatus: () => api.get('/devices/withings/status'),
  // 获取 OAuth 授权 URL
  getOAuthUrl: () => api.get('/devices/withings/oauth/authorize'),
  // 手动同步数据
  syncData: (days: number = 7) => api.post(`/devices/withings/sync?days=${days}`),
  // 查看 Webhook 订阅
  listWebhooks: () => api.get('/devices/withings/webhooks/list'),
  // 手动订阅 Webhook
  subscribeWebhooks: () => api.post('/devices/withings/webhooks/subscribe'),
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
  user_id?: number | null;
  visibility?: string;
  author_name?: string | null;
  source_created_at?: string;
  created_at: string;
}

export const newsApi = {
  // 获取资讯列表（支持 feed 过滤）
  getArticles: (page: number = 1, pageSize: number = 20, sourceType?: string, feed?: string) => {
    const params = new URLSearchParams();
    params.append('page', page.toString());
    params.append('page_size', pageSize.toString());
    if (sourceType) params.append('source_type', sourceType);
    if (feed) params.append('feed', feed);
    return api.get<NewsArticle[]>(`/news/articles?${params.toString()}`);
  },
  // 获取资讯详情
  getArticle: (articleId: number) => api.get<NewsArticle>(`/news/articles/${articleId}`),
  // 切换文章可见性
  updateVisibility: (articleId: number, visibility: string) =>
    api.patch(`/news/articles/${articleId}/visibility?visibility=${visibility}`),
  // 删除文章（本人或管理员）
  deleteArticle: (articleId: number) => api.delete(`/news/articles/${articleId}`),
  // 管理员删除文章
  adminDeleteArticle: (articleId: number) => api.delete(`/news/admin/articles/${articleId}`),
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
  image_preview?: string;
  file_name?: string;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  last_message?: string;
  mode?: string;
}

export interface ConversationDetail {
  id: number;
  title: string;
  messages: ChatMessage[];
  mode?: string;
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

export interface ActivitySavedData {
  type: string;
  status: string;
  message: string;
}

export interface ReminderData {
  reminder_minutes: number;
  reminder_message: string;
  activity_name: string;
}

export interface ChatSendResponse {
  conversation_id: number;
  message_id: number;
  reply: string;
  diet_saved?: boolean;
  diet_data?: DietSavedData;
  activities_saved?: boolean;
  activities?: ActivitySavedData[];
  reminder?: ReminderData;
  workout_analysis?: {
    message_id: number;
    content: string;
    workout_data?: Record<string, unknown>;
  };
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
  sendMessage: (message: string, conversationId?: number, isKidsMode?: boolean, imageBase64?: string, imageType?: string, fileBase64?: string, fileName?: string) =>
    api.post<ChatSendResponse>('/chat/send', { message, conversation_id: conversationId, is_kids_mode: isKidsMode || false, image_base64: imageBase64, image_type: imageType, file_base64: fileBase64, file_name: fileName }),
  // 获取对话列表
  getConversations: (limit: number = 20) =>
    api.get<Conversation[]>(`/chat/conversations?limit=${limit}`),
  // 获取对话详情
  getConversation: (conversationId: number) =>
    api.get<ConversationDetail>(`/chat/conversations/${conversationId}`),
  // 删除对话
  deleteConversation: (conversationId: number) =>
    api.delete(`/chat/conversations/${conversationId}`),
  // 语音转文字
  transcribe: (audioBase64: string, audioFormat: string = 'webm') =>
    api.post<{ text: string }>('/chat/transcribe', { audio_base64: audioBase64, audio_format: audioFormat }),
  // 语音指令快速执行
  voiceCommand: (text: string) =>
    api.post<{ matched: boolean; command_type?: string; message?: string; data?: any }>('/chat/voice-command', { text }),
  // 食物图片识别（保留兼容）
  recognizeFood: (imageBase64: string, imageType: string = 'image/jpeg') =>
    api.post<{ success: boolean; foods: any[]; meal_description: string; health_tips: string; totals: any }>('/diet/recognize', { image_base64: imageBase64, image_type: imageType }),
  // 流式发送消息 (SSE)
  streamMessage: async function* (message: string, conversationId?: number, isKidsMode?: boolean, imageBase64?: string, imageType?: string, mode?: string, fileBase64?: string, fileName?: string) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const response = await fetch(`${API_BASE_URL}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        is_kids_mode: isKidsMode || false,
        image_base64: imageBase64,
        image_type: imageType,
        ...(mode ? { mode } : {}),
        ...(fileBase64 ? { file_base64: fileBase64, file_name: fileName } : {}),
      }),
    });

    if (!response.ok) {
      throw new Error(`Stream request failed: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            yield data;
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
  },
};

// OpenClaw Channel API
export const openclawApi = {
  getConversations: (limit: number = 20) =>
    api.get<Conversation[]>(`/openclaw/conversations?limit=${limit}`),

  getConversation: (conversationId: number) =>
    api.get<ConversationDetail>(`/openclaw/conversations/${conversationId}`),

  deleteConversation: (conversationId: number) =>
    api.delete(`/openclaw/conversations/${conversationId}`),

  streamMessage: async function* (message: string, conversationId?: number) {
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const response = await fetch(`${API_BASE_URL}/openclaw/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
      }),
    });

    if (!response.ok) {
      throw new Error(`OpenClaw stream request failed: ${response.status}`);
    }

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));
            yield data;
          } catch {
            // skip malformed JSON
          }
        }
      }
    }
  },
};

// ===== 对话分享 API =====
export const sharedApi = {
  createShare: (conversationId: number, sourceType: string = 'health') =>
    api.post<{ share_token: string; share_url: string }>('/shared/create', {
      conversation_id: conversationId,
      source_type: sourceType,
    }),
  revokeShare: (shareToken: string) =>
    api.delete(`/shared/${shareToken}`),
};

// ===== 活动状态 API =====
export interface ActivityStatusData {
  id: number;
  user_id: number;
  status_text: string;
  category: string;
  start_time: string;
  estimated_duration_minutes: number | null;
  estimated_end_time: string | null;
  actual_end_time: string | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
}

export interface ActivityTimelineItem {
  id: number;
  status_text: string;
  category: string;
  start_time: string;
  end_time: string | null;
  duration_minutes: number | null;
  is_active: boolean;
}

export interface ActivityCategoryStats {
  category: string;
  total_minutes: number;
  count: number;
  percentage: number;
}

export interface ActivityStatsData {
  total_records: number;
  total_active_minutes: number;
  category_distribution: ActivityCategoryStats[];
}

export const activityStatusApi = {
  createRecord: (data: { status_text: string; category: string; estimated_duration_minutes?: number; notes?: string }) =>
    api.post<ActivityStatusData>('/activity-status/records', data),
  getCurrentStatus: () =>
    api.get<ActivityStatusData | null>('/activity-status/records/me/current'),
  endRecord: (recordId: number) =>
    api.put<ActivityStatusData>(`/activity-status/records/${recordId}/end`),
  getTodayTimeline: () =>
    api.get<ActivityTimelineItem[]>('/activity-status/records/me/today'),
  getMyRecords: (params?: { start_date?: string; end_date?: string; limit?: number }) =>
    api.get<ActivityStatusData[]>('/activity-status/records/me', { params }),
  getRecord: (recordId: number) =>
    api.get<ActivityStatusData>(`/activity-status/records/${recordId}`),
  deleteRecord: (recordId: number) =>
    api.delete(`/activity-status/records/${recordId}`),
  getStats: (days: number = 7) =>
    api.get<ActivityStatsData>(`/activity-status/stats/me?days=${days}`),
};

// ===== 好友关系 =====

export interface FriendInfo {
  user_id: number;
  name: string;
  avatar_url: string | null;
  friendship_id: number;
  since: string;
}

export interface FriendRequestData {
  id: number;
  user_id: number;
  friend_id: number;
  status: string;
  message: string | null;
  created_at: string;
  user_name: string | null;
  user_avatar: string | null;
  friend_name: string | null;
  friend_avatar: string | null;
}

export interface UserSearchResultData {
  id: number;
  name: string;
  avatar_url: string | null;
  is_friend: boolean;
  request_pending: boolean;
}

export const friendsApi = {
  sendRequest: (friendId: number, message?: string) =>
    api.post<FriendRequestData>('/friends/request', { friend_id: friendId, message }),
  acceptRequest: (requestId: number) =>
    api.put<FriendRequestData>(`/friends/request/${requestId}/accept`),
  rejectRequest: (requestId: number) =>
    api.put<FriendRequestData>(`/friends/request/${requestId}/reject`),
  listFriends: () =>
    api.get<FriendInfo[]>('/friends/list'),
  pendingRequests: () =>
    api.get<FriendRequestData[]>('/friends/requests/pending'),
  removeFriend: (friendshipId: number) =>
    api.delete(`/friends/${friendshipId}`),
  searchUsers: (q: string) =>
    api.get<UserSearchResultData[]>(`/friends/search?q=${encodeURIComponent(q)}`),
};

// ===== PK挑战 =====

export interface ParticipantInfoData {
  user_id: number;
  user_name: string;
  user_avatar: string | null;
  score: number;
  rank: number | null;
  points: number;
  joined_at: string;
}

export interface PKChallengeData {
  id: number;
  creator_id: number;
  creator_name: string | null;
  title: string;
  challenge_type: string;
  checkin_template_id: number | null;
  checkin_template_name: string | null;
  activity_category: string | null;
  metric: string;
  duration_days: number;
  start_date: string;
  end_date: string;
  status: string;
  participants: ParticipantInfoData[];
  created_at: string;
}

export interface PKChallengeDetailData extends PKChallengeData {
  leaderboard: ParticipantInfoData[];
}

export interface PKStatsData {
  total_challenges: number;
  wins: number;
  active_challenges: number;
  total_points: number;
}

// ===== 每日健康积分 =====

export interface PointItemData {
  category: string;
  name: string;
  points: number;
  max_points: number;
  detail: string;
}

export interface DailyPointsData {
  date: string;
  total_points: number;
  items: PointItemData[];
}

export interface PointsHistoryItemData {
  date: string;
  total_points: number;
}

export interface PointsSummaryData {
  today_points: number;
  week_points: number;
  month_points: number;
  streak_days: number;
  today_detail: DailyPointsData;
}

export const dailyPointsApi = {
  getToday: () =>
    api.get<DailyPointsData>('/points/today'),
  getDate: (targetDate: string) =>
    api.get<DailyPointsData>(`/points/date/${targetDate}`),
  getSummary: () =>
    api.get<PointsSummaryData>('/points/summary'),
  getHistory: (days: number = 7) =>
    api.get<PointsHistoryItemData[]>(`/points/history?days=${days}`),
};

export const pkChallengeApi = {
  create: (data: {
    title: string;
    challenge_type: string;
    checkin_template_id?: number;
    activity_category?: string;
    metric?: string;
    duration_days?: number;
    duration_minutes?: number;
    friend_ids: number[];
  }) => api.post<PKChallengeData>('/pk-challenges', data),
  list: (status?: string) =>
    api.get<PKChallengeData[]>('/pk-challenges', { params: status ? { status } : {} }),
  getDetail: (id: number) =>
    api.get<PKChallengeDetailData>(`/pk-challenges/${id}`),
  refresh: (id: number) =>
    api.post<PKChallengeDetailData>(`/pk-challenges/${id}/refresh`),
  cancel: (id: number) =>
    api.delete(`/pk-challenges/${id}`),
  myStats: () =>
    api.get<PKStatsData>('/pk-challenges/stats/me'),
};

// ====== 单词本 ======
export interface VocabularyWord {
  id: number;
  word: string;
  phonetic_us?: string;
  phonetic_uk?: string;
  meanings?: string;
  example_sentences?: string;
  synonyms?: string;
  antonyms?: string;
  word_roots?: string;
  notes?: string;
  review_count: number;
  correct_count: number;
  mastery_level: number;
  last_reviewed_at?: string;
  next_review_date?: string;
  is_mastered: boolean;
  created_at?: string;
}

export interface VocabularyListResponse {
  total: number;
  words: VocabularyWord[];
}

export const vocabularyApi = {
  getWords: (page: number = 1, pageSize: number = 20, mastered?: boolean) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (mastered !== undefined) params.append('mastered', String(mastered));
    return api.get<VocabularyListResponse>(`/vocabulary/words?${params}`);
  },
  getWord: (wordId: number) =>
    api.get<VocabularyWord>(`/vocabulary/words/${wordId}`),
  getReviewWords: (limit: number = 10) =>
    api.get<VocabularyListResponse>(`/vocabulary/review?limit=${limit}`),
  submitReview: (wordId: number, isCorrect: boolean) =>
    api.post<{ ok: boolean; mastery_level: number; next_review_date: string }>(
      '/vocabulary/review', { word_id: wordId, is_correct: isCorrect }
    ),
  deleteWord: (wordId: number) =>
    api.delete(`/vocabulary/words/${wordId}`),
};

// ── 资产防御与布局 (Security Life) ─────────────────────

export const securityLifeApi = {
  // Profile
  getProfile: () => api.get('/security-life/profile'),
  updateProfile: (data: Record<string, unknown>) => api.put('/security-life/profile', data),

  // Assets (两层资产)
  getAssets: () => api.get('/security-life/assets'),
  updateAssets: (data: Record<string, unknown>) => api.put('/security-life/assets', data),
  addProperty: (data: Record<string, unknown>) => api.post('/security-life/properties', data),
  updateProperty: (id: number, data: Record<string, unknown>) => api.put(`/security-life/properties/${id}`, data),
  deleteProperty: (id: number) => api.delete(`/security-life/properties/${id}`),

  // Baskets (资产篮子)
  getBaskets: () => api.get('/security-life/baskets'),
  updateBasket: (basketId: string, data: Record<string, unknown>) => api.put(`/security-life/baskets/${basketId}`, data),

  // Cash Layers (三层现金)
  getCashLayers: () => api.get('/security-life/cash-layers'),
  updateCashLayers: (data: { layers: Array<{ layer: string; amount: number; institution?: string; note?: string }> }) =>
    api.put('/security-life/cash-layers', data),

  // Checklist (90天清单)
  getChecklist: () => api.get('/security-life/checklist'),
  initChecklist: () => api.post('/security-life/checklist/init'),
  addChecklistItem: (data: Record<string, unknown>) => api.post('/security-life/checklist', data),
  updateChecklistItem: (id: number, data: Record<string, unknown>) => api.put(`/security-life/checklist/${id}`, data),
  deleteChecklistItem: (id: number) => api.delete(`/security-life/checklist/${id}`),
  toggleChecklistItem: (id: number) => api.patch(`/security-life/checklist/${id}/toggle`),

  // Red Lines (三条红线)
  getRedLines: () => api.get('/security-life/red-lines'),
  updateRedLine: (lineId: number, data: { status: string; value_json?: string }) =>
    api.put(`/security-life/red-lines/${lineId}`, data),

  // Dashboard (总览)
  getDashboard: () => api.get('/security-life/dashboard'),
};

// AI 智能计划
export const smartPlanApi = {
  analyze: (targetWeek: string = 'current') =>
    api.get('/smart-plan/analyze', { params: { target_week: targetWeek } }),
  generate: (params: {
    target_week?: string;
    user_focus?: string[];
    user_notes?: string;
    intensity?: string;
  }, debug: boolean = false) => {
    const queryParams = debug ? '?debug=true' : '';
    return api.post(`/smart-plan/generate${queryParams}`, params);
  },
  getCurrent: (week: string = 'current') => api.get('/smart-plan/current', { params: { week } }),
  getHistory: (page: number = 1, pageSize: number = 10) =>
    api.get('/smart-plan/history', { params: { page, page_size: pageSize } }),
  getDetail: (planId: number) => api.get(`/smart-plan/${planId}`),
  getToday: () => api.get('/smart-plan/today'),
  updateItem: (planId: number, itemId: number, isCompleted: boolean) =>
    api.patch(`/smart-plan/${planId}/items/${itemId}`, { is_completed: isCompleted }),
  submitFeedback: (planId: number, score: number) =>
    api.post(`/smart-plan/${planId}/feedback`, { score }),
  deletePlan: (planId: number) => api.delete(`/smart-plan/${planId}`),

  // 阶段性目标
  generateGoal: (periodType: string, targetPeriod?: string, debug: boolean = false) => {
    const params = debug ? '?debug=true' : '';
    return api.post(`/smart-plan/goals/generate${params}`, { period_type: periodType, target_period: targetPeriod });
  },
  getActiveGoals: (periodType?: string) =>
    api.get('/smart-plan/goals/active', { params: periodType ? { period_type: periodType } : {} }),
  getGoalDetail: (goalId: number) => api.get(`/smart-plan/goals/${goalId}`),
  updateMetric: (goalId: number, metricId: number, currentValue: number) =>
    api.patch(`/smart-plan/goals/${goalId}/metrics/${metricId}`, { current_value: currentValue }),
  deleteGoal: (goalId: number) => api.delete(`/smart-plan/goals/${goalId}`),
};

// ===== 群聊 =====

export interface GroupMemberInfo {
  user_id: number;
  name: string;
  avatar_url: string | null;
  role: string;
  joined_at: string;
}

export interface GroupMsgData {
  id: number;
  group_id: number;
  sender_id: number;
  sender_name: string;
  sender_avatar: string | null;
  content: string;
  created_at: string;
}

export interface GroupListItem {
  id: number;
  name: string;
  avatar_url: string | null;
  member_count: number;
  last_message: string | null;
  last_message_at: string | null;
  created_at: string;
}

export interface GroupDetail {
  id: number;
  name: string;
  avatar_url: string | null;
  creator_id: number;
  members: GroupMemberInfo[];
  created_at: string;
}

export interface GroupMsgHistory {
  messages: GroupMsgData[];
  has_more: boolean;
}

export const groupApi = {
  create: (name: string, memberIds: number[]) =>
    api.post<GroupDetail>('/groups', { name, member_ids: memberIds }),
  list: () =>
    api.get<GroupListItem[]>('/groups'),
  getDetail: (groupId: number) =>
    api.get<GroupDetail>(`/groups/${groupId}`),
  update: (groupId: number, name: string) =>
    api.put<GroupDetail>(`/groups/${groupId}`, { name }),
  dissolve: (groupId: number) =>
    api.delete(`/groups/${groupId}`),
  sendMessage: (groupId: number, content: string) =>
    api.post<GroupMsgData>(`/groups/${groupId}/messages`, { content }),
  getMessages: (groupId: number, beforeId?: number, limit?: number) =>
    api.get<GroupMsgHistory>(`/groups/${groupId}/messages`, {
      params: { before_id: beforeId || 0, limit: limit || 50 },
    }),
  addMember: (groupId: number, userId: number) =>
    api.post(`/groups/${groupId}/members`, { user_id: userId }),
  removeMember: (groupId: number, userId: number) =>
    api.delete(`/groups/${groupId}/members/${userId}`),
  leave: (groupId: number) =>
    api.post(`/groups/${groupId}/leave`),
};

export const onboardingApi = {
  getStatus: () =>
    api.get<{
      onboarding_completed: boolean;
      has_profile: boolean;
      has_health_goals: boolean;
      has_checkin_templates: boolean;
      profile_data?: {
        height_cm?: number;
        current_weight_kg?: number;
        gender?: string;
        birth_date?: string;
        target_steps: number;
        target_sleep_hours: number;
        target_water_ml: number;
        target_exercise_minutes: number;
      };
    }>('/onboarding/status'),
  saveStep1: (data: { height_cm?: number; current_weight_kg?: number; gender?: string; birth_date?: string }) =>
    api.post('/onboarding/step1', data),
  saveStep2: (data: { target_steps?: number; target_sleep_hours?: number; target_water_ml?: number; target_exercise_minutes?: number }) =>
    api.post('/onboarding/step2', data),
  complete: (data: { init_default_templates: boolean; selected_template_names?: string[] }) =>
    api.post('/onboarding/complete', data),
  skip: () =>
    api.post('/onboarding/skip'),
};

export const dataExportApi = {
  exportData: (dataType = 'all', format = 'csv', startDate?: string, endDate?: string) =>
    api.get('/export/health-data', {
      params: { data_type: dataType, format, start_date: startDate, end_date: endDate },
      responseType: 'blob',
    }),
};

export const notificationApi = {
  getLogs: (limit = 50, type?: string) =>
    api.get<{ logs: Array<{ id: number; notification_type: string; channel: string; title: string; content: string; status: string; sent_at: string | null; created_at: string | null }> }>('/notification/logs', { params: { limit, notification_type: type } }),
  getSettings: () =>
    api.get('/notification/settings'),
};

export const achievementApi = {
  getDefinitions: () =>
    api.get<Array<{ id: number; code: string; name: string; description: string; icon: string; category: string; criteria_type: string; criteria_value: number; rarity: string; sort_order: number }>>('/achievements/definitions'),
  getMyAchievements: () =>
    api.get<{ total: number; unlocked: number; achievements: Array<{ id: number; code: string; name: string; description: string; icon: string; category: string; rarity: string; criteria_value: number; progress: number; unlocked: boolean; unlocked_at: string | null }> }>('/achievements/me'),
  checkAchievements: () =>
    api.post<{ newly_unlocked: number; badges: Array<{ badge_id: number; progress: number }> }>('/achievements/check'),
};

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
export const openclawSkillsApi = {
  listInstalled: () =>
    api.get<Array<{
      name: string;
      description: string;
      version: string;
      enabled: boolean;
      has_env: boolean;
      env_keys: string[];
    }>>('/v1/openclaw/skills'),
  install: (name: string, skill_md_content: string, enabled: boolean = true, env?: Record<string, string>, api_key?: string) =>
    api.post<{ name: string; status: string; enabled: boolean }>('/v1/openclaw/skills', {
      name, skill_md_content, enabled, env, api_key,
    }),
  remove: (name: string) =>
    api.delete<{ ok: boolean; message: string }>(`/v1/openclaw/skills/${name}`),
  toggle: (name: string, enabled: boolean) =>
    api.put<{ ok: boolean; name: string; enabled: boolean }>(`/v1/openclaw/skills/${name}/toggle`, { enabled }),
  gatewayStatus: () =>
    api.get<{ status: string; uptime: string }>('/v1/openclaw/skills/gateway/status'),
  restartGateway: () =>
    api.post<{ ok: boolean; message: string }>('/v1/openclaw/skills/gateway/restart'),
};
