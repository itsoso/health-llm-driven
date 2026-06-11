import api from './client';

// ---- 后端契约 (backend Phase 2, 依赖 PR #113) ----
// 经 next.config.js rewrites: 前端 /api/prescriptions/* → 后端 /api/v1/prescriptions/*

/** 单种原研药信息。未收录时整个 originator 为 null。 */
export interface OriginatorInfo {
  generic: string;
  brand: string;
  manufacturer: string;
}

/** 处方识别出的单条药品。 */
export interface PrescriptionItem {
  raw_name: string;
  generic_name: string;
  dosage: string;
  frequency: string;
  originator: OriginatorInfo | null;
  has_originator: boolean;
}

export interface RecognizeResponse {
  items: PrescriptionItem[];
  matched_originators: number;
  note: string;
}

/** 原研药换药建议(已采纳/忽略的不返回)。 */
export interface OriginatorRecommendation {
  med_name: string;
  generic_name: string;
  generic_key: string;
  brand: string;
  manufacturer: string;
}

export interface RecommendationsResponse {
  recommendations: OriginatorRecommendation[];
}

export type RecommendationStatus = 'adopted' | 'dismissed' | 'suggested';

export interface RecommendationStatusResponse {
  generic_name: string;
  status: RecommendationStatus;
}

export interface OriginatorLookupResponse {
  query: string;
  originator: OriginatorInfo | null;
  has_originator: boolean;
}

/** 上传处方图片 → 识别药品并匹配原研药。 */
export const recognizePrescription = async (file: File): Promise<RecognizeResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await api.post('/prescriptions/recognize', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return res.data;
};

/** 获取可换原研药的在用药建议列表。 */
export const getOriginatorRecommendations = async (): Promise<RecommendationsResponse> => {
  const res = await api.get('/prescriptions/recommendations');
  return res.data;
};

/** 更新某条原研药建议的状态(采纳 / 忽略 / 重新建议)。 */
export const setRecommendationStatus = async (payload: {
  generic_name: string;
  status: RecommendationStatus;
  brand?: string;
  manufacturer?: string;
}): Promise<RecommendationStatusResponse> => {
  const res = await api.post('/prescriptions/recommendations/status', payload);
  return res.data;
};

/** 按通用名/商品名查询原研药。 */
export const lookupOriginator = async (name: string): Promise<OriginatorLookupResponse> => {
  const res = await api.get('/prescriptions/originator', { params: { name } });
  return res.data;
};
