import api from './client';

// ---- 后端契约 (backend, GET /medication/deprescribing-review/me) ----
// 经 next.config.js rewrites: 前端 /api/medication/* → 后端 /api/v1/medication/*

/** 单条减药候选提示。绝非建议停药,仅供与医生讨论。 */
export interface DeprescribingFlag {
  /** 规则码: polypharmacy / duplicate_class / long_term_candidate / expired_still_active */
  code: string;
  detail: string;
  suggestion: string;
}

/** GET /medication/deprescribing-review/me 响应。 */
export interface DeprescribingReview {
  active_count: number;
  is_polypharmacy: boolean;
  flags: DeprescribingFlag[];
  disclaimer: string;
}

/** 获取多药梳理 / 减药候选评审(非建议停药,请与医生讨论是否可精简)。 */
export const getDeprescribingReview = async (): Promise<DeprescribingReview> => {
  const res = await api.get('/medication/deprescribing-review/me');
  return res.data;
};
