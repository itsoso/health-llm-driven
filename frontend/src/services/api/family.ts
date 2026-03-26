import api from './client';

export const familyApi = {
  // 家庭组
  createGroup: (name: string) => api.post('/family/groups', { name }),
  getGroups: () => api.get('/family/groups'),

  // 成员
  addMember: (data: { name: string; relationship_type: string; nickname?: string; gender?: string; birth_date?: string }) =>
    api.post('/family/members', data),
  getMembers: () => api.get('/family/members'),
  removeMember: (id: number) => api.delete(`/family/members/${id}`),

  // 视角切换
  switchToMember: (userId: number) => api.post('/family/switch', { user_id: userId }),

  // 仪表盘
  getDashboard: () => api.get('/family/dashboard'),

  // 每日巡检
  getDailyCheck: () => api.get('/family-health/daily-check'),
  sendDailyCheck: () => api.post('/family-health/daily-check/send'),

  // 体检报告
  uploadReport: (data: { report_date: string; hospital?: string; report_type?: string; title?: string; image_base64_list?: string[] }) =>
    api.post('/family-health/medical-reports/upload', data),
  getReports: (limit?: number) => api.get('/family-health/medical-reports/me', { params: { limit } }),
  getReportDetail: (id: number) => api.get(`/family-health/medical-reports/${id}`),
  getIndicatorTrend: (name: string) => api.get(`/family-health/medical-indicators/trend/${encodeURIComponent(name)}`),

  // 用药
  recognizeMedication: (imageBase64: string) => api.post('/family-health/medications/recognize', { image_base64: imageBase64 }),
  addMedication: (data: { name: string; dosage?: string; frequency?: string; category?: string; purpose?: string; notes?: string }) =>
    api.post('/family-health/medications', data),
  getMedications: () => api.get('/family-health/medications/me'),
  takeMedication: (id: number) => api.post(`/family-health/medications/${id}/take`),

  // 复查日历
  addReview: (data: { item_name: string; next_due_date: string; category?: string; department?: string; hospital?: string; interval_months?: number; last_check_date?: string; priority?: string; notes?: string }) =>
    api.post('/family-health/review-calendar', data),
  getReviewCalendar: () => api.get('/family-health/review-calendar/me'),
  completeReview: (id: number) => api.post(`/family-health/review-calendar/${id}/complete`),
};
