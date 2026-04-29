import api from './client';

// External Recommendations feature removed — stub API maintains type compat
// for `daily-insights` external tab (which will now render empty).
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
  getToday: async (): Promise<{ data: TodayExternalRecommendations }> => ({
    data: { date: new Date().toISOString().slice(0, 10), has_recommendations: false, categories: {} },
  }),
};

// 医疗记录
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

// 饮食推荐
export const dietRecommendationApi = {
  getMyRecommendation: (mealType?: string) => {
    const params = new URLSearchParams();
    if (mealType) params.append('meal_type', mealType);
    return api.get(`/diet-recommendation/me?${params.toString()}`);
  },
};

// 运动前/后指导
export const workoutGuidanceApi = {
  getPreWorkoutGuidance: (goalId?: number, workoutType?: string, debug: boolean = false) => {
    const params = new URLSearchParams();
    if (goalId) params.append('goal_id', goalId.toString());
    if (workoutType) params.append('workout_type', workoutType);
    if (debug) params.append('debug', 'true');
    return api.post(`/workout/pre-workout-guidance?${params.toString()}`);
  },
  getPostWorkoutAnalysis: (workoutId: number, forceRegenerate: boolean = false, debug: boolean = false, cacheOnly: boolean = false) => {
    const params = new URLSearchParams();
    if (forceRegenerate) params.append('force_regenerate', 'true');
    if (debug) params.append('debug', 'true');
    if (cacheOnly) params.append('cache_only', 'true');
    return api.post(`/workout/post-workout-analysis/${workoutId}?${params.toString()}`);
  },
};

// 智能计划
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
