import api from './client';

export interface CommentUser {
  id: number;
  name: string;
  is_admin: boolean;
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

export interface KidsPetResponse {
  has_pet: boolean;
  kids_points: number;
  pet?: KidsPetState | null;
  message?: string;
}

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

export interface KidsPlanReviewResponse {
  range: string;
  start_date: string;
  end_date: string;
  review_text: string;
  stats_summary: Record<string, number>;
}

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

export interface TodayExternalRecommendations {
  date: string;
  has_recommendations: boolean;
  categories: Record<string, ExternalRecommendation[]>;
}

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
export const externalRecommendationApi = {
  // 获取今日外部建议
  getToday: () => api.get<TodayExternalRecommendations>('/external-recommendations/today'),
};

// 情绪追踪 API
export const dietRecommendationApi = {
  // 获取我的饮食推荐
  getMyRecommendation: (mealType?: string) => {
    const params = new URLSearchParams();
    if (mealType) params.append('meal_type', mealType);
    return api.get(`/diet-recommendation/me?${params.toString()}`);
  },
};

// 资讯 API
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
