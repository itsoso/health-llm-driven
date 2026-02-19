/**
 * browser-llm-orchestrator API 接口
 */
import { baseRequest } from './baseApi';
import type { Batch, CreateBatchParams, HistoryItem, PromptTemplate, SchedulerTask } from '../types/llm';

export const llmAPI = {
  // ==================== 批次管理 ====================

  /** 检查是否有正在处理的批次 */
  checkProcessing: () =>
    baseRequest<{ ok: boolean; has_processing: boolean; can_submit: boolean; processing_batches?: string[] }>({
      url: '/custom-prompt/processing',
    }),

  /** 创建分析批次 */
  createBatch: (data: CreateBatchParams) =>
    baseRequest<{ ok: boolean; batch_id: string; batch: Batch }>({
      url: '/custom-prompt/create',
      method: 'POST',
      data,
    }),

  /** 开始处理批次 */
  processBatch: (batchId: string) =>
    baseRequest<{ ok: boolean; message: string }>({
      url: `/custom-prompt/process/${batchId}`,
      method: 'POST',
    }),

  /** 获取批次状态 */
  getBatchStatus: (batchId: string) =>
    baseRequest<{ ok: boolean; batch: Batch }>({
      url: `/custom-prompt/batch/${batchId}`,
    }),

  /** 取消批次 */
  cancelBatch: (batchId: string) =>
    baseRequest<{ ok: boolean; message: string }>({
      url: `/custom-prompt/cancel/${batchId}`,
      method: 'POST',
    }),

  /** 取消单个模型 */
  cancelModel: (batchId: string, llmSite: string) =>
    baseRequest<{ ok: boolean; message: string }>({
      url: `/custom-prompt/cancel-model/${batchId}/${llmSite}`,
      method: 'POST',
    }),

  /** 重试批次 */
  retryBatch: (batchId: string, data?: { aggregate_only?: boolean; retry_models?: string[] }) =>
    baseRequest<{ ok: boolean; message: string; batch?: Batch }>({
      url: `/custom-prompt/retry/${batchId}`,
      method: 'POST',
      data,
    }),

  /** 重新汇总 */
  reAggregate: (batchId: string, data?: { aggregator_site?: string; aggregator_model?: string }) =>
    baseRequest<{ ok: boolean; message: string }>({
      url: `/custom-prompt/re-aggregate/${batchId}`,
      method: 'POST',
      data,
    }),

  // ==================== 历史记录 ====================

  /** 获取历史记录 (分页) */
  getHistory: (page = 1, pageSize = 20) =>
    baseRequest<{ ok: boolean; items: HistoryItem[]; total: number; total_pages: number }>({
      url: '/history/custom-prompt',
      params: { page, page_size: pageSize },
    }),

  /** 搜索历史 */
  searchHistory: (q: string, limit = 20) =>
    baseRequest<{ ok: boolean; items: HistoryItem[]; total: number }>({
      url: '/history/search',
      params: { q, limit },
    }),

  /** 删除批次 */
  deleteBatch: (batchId: string) =>
    baseRequest<{ ok: boolean }>({
      url: `/history/batch/${batchId}`,
      method: 'DELETE',
    }),

  // ==================== 模板 ====================

  /** 获取模板列表 */
  getTemplates: (type?: string, sceneType?: string) =>
    baseRequest<{ ok: boolean; templates: PromptTemplate[] }>({
      url: '/templates',
      params: { type, scene_type: sceneType },
    }),

  // ==================== 调度器 ====================

  /** 获取调度器配置 */
  getSchedulerConfig: () =>
    baseRequest<any>({ url: '/scheduler/config' }),

  /** 保存调度器配置 */
  saveSchedulerConfig: (data: any) =>
    baseRequest<any>({ url: '/scheduler/config', method: 'POST', data }),

  /** 获取调度器任务列表 */
  getSchedulerTasks: () =>
    baseRequest<{ ok: boolean; tasks: SchedulerTask[] }>({ url: '/scheduler/tasks' }),

  /** 手动触发任务 */
  triggerTask: (taskId: string) =>
    baseRequest<{ ok: boolean; message: string }>({ url: `/scheduler/trigger/${taskId}`, method: 'POST' }),

  // ==================== 系统 ====================

  /** 获取系统状态 */
  getStatus: () =>
    baseRequest<any>({ url: '/status' }),
};
