import api from './client';

export const userApi = {
  getUsers: () => api.get('/users'),
  getUser: (id: number) => api.get(`/users/${id}`),
  createUser: (data: any) => api.post('/users', data),
};

// 基础健康数据
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
        primary_goal?: string;
      };
    }>('/onboarding/status'),
  saveStep1: (data: { height_cm?: number; current_weight_kg?: number; gender?: string; birth_date?: string }) =>
    api.post('/onboarding/step1', data),
  saveStep2: (data: { target_steps?: number; target_sleep_hours?: number; target_water_ml?: number; target_exercise_minutes?: number }) =>
    api.post('/onboarding/step2', data),
  saveStep5: (data: { primary_goal: string }) =>
    api.post('/onboarding/step5', data),
  complete: (data: { init_default_templates: boolean; selected_template_names?: string[] }) =>
    api.post('/onboarding/complete', data),
  skip: () =>
    api.post('/onboarding/skip'),
};

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
export const dataExportApi = {
  exportData: (dataType = 'all', format = 'csv', startDate?: string, endDate?: string) =>
    api.get('/export/health-data', {
      params: { data_type: dataType, format, start_date: startDate, end_date: endDate },
      responseType: 'blob',
    }),
};

export const notificationApi = {
  getLogs: (limit = 50, type?: string) =>
    api.get<{ logs: Array<{ id: number; notification_type: string; channel: string; title: string; content: string; status: string; sent_at: string | null; created_at: string | null; data?: Record<string, any> | null; deep_link?: string | null }> }>('/notification/logs', { params: { limit, notification_type: type } }),
  getSettings: () =>
    api.get('/notification/settings'),
};

export const feedbackApi = {
  submit: (data: {
    conversation_type: 'chat' | 'agent';
    conversation_id: number;
    message_id: number;
    rating: 1 | 5;
    feedback_text?: string;
  }) => api.post<{ id: number; rating: number }>('/feedback', data),
};
