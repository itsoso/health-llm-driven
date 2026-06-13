import api from './client';

// ---- 后端契约 (backend, GET /data-health/integrity) ----
// 经 next.config.js rewrites: 前端 /api/data-health/* → 后端 /api/v1/data-health/*

export type IntegritySeverity = 'error' | 'warning' | 'info';

/** 单条数据正确性问题(量纲错 / 范围越界 / 层断连 / 周期空目标等静默损坏)。 */
export interface IntegrityIssue {
  code: string;
  severity: IntegritySeverity;
  detail: string;
  count: number;
  fix_hint: string;
}

/** GET /data-health/integrity 响应。空 issues = 健康。 */
export interface DataIntegrityReport {
  healthy: boolean;
  issue_count: number;
  issues: IntegrityIssue[];
}

/** 获取数据正确性自检结果(区别于 /status 的完整度,这里查正确性)。 */
export const getDataIntegrity = async (): Promise<DataIntegrityReport> => {
  const res = await api.get('/data-health/integrity');
  return res.data;
};
