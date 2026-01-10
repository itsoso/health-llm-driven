import axios from 'axios';

// 使用相对路径，通过Next.js的rewrites代理到后端
// 这样无论用什么IP/域名访问前端，都能正确转发API请求
const API_BASE_URL = '/api';

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
  create: (data: any) => api.post('/goals', data),
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
};

// 习惯追踪
export const habitApi = {
  // 习惯定义
  createDefinition: (data: any) => api.post('/habits/definitions', data),
  getUserDefinitions: (userId: number, activeOnly: boolean = true, category?: string) =>
    api.get(`/habits/definitions/user/${userId}`, { params: { active_only: activeOnly, category } }),
  updateDefinition: (habitId: number, data: any) =>
    api.put(`/habits/definitions/${habitId}`, data),
  deleteDefinition: (habitId: number) =>
    api.delete(`/habits/definitions/${habitId}`),
  // 习惯打卡
  createRecord: (data: any) => api.post('/habits/records', data),
  batchCheckin: (data: any) => api.post('/habits/records/batch', data),
  getUserRecordsWithStatus: (userId: number, recordDate: string) =>
    api.get(`/habits/records/user/${userId}/date/${recordDate}`),
  getStats: (userId: number, days: number = 30) =>
    api.get(`/habits/records/user/${userId}/stats`, { params: { days } }),
  getTodaySummary: (userId: number) =>
    api.get(`/habits/records/user/${userId}/today-summary`),
  // 使用 /me 端点
  getMyRecordsWithStatus: (recordDate: string) =>
    api.get(`/habits/me/date/${recordDate}`),
  getMyStats: (days: number = 30) =>
    api.get('/habits/me/stats', { params: { days } }),
  getMyTodaySummary: () =>
    api.get('/habits/me/today-summary'),
};

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
