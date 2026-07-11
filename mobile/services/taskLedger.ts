import api from './api';

/**
 * 统一任务账本(Harness Slice 4)— 「小巴的任务」五源只读聚合。
 * 后端 GET /agent/tasks:write_intents / desktop_jobs / agenda / heartbeat / recipes
 * 统一 shape;单源失败进 failed_sources(fail-loud),不整包 500。
 * v1 只读:无取消/重试。
 */
export interface TaskLedgerItem {
  kind: string;
  title: string;
  status: string;
  when: string | null;
  source: string;
}

export interface TaskLedgerFailedSource {
  source: string;
  error: string;
}

export interface TaskLedgerResponse {
  items: TaskLedgerItem[];
  failed_sources: TaskLedgerFailedSource[];
}

/** 拉取任务账本。网络/服务错误向上抛,由面板显式呈现(不静默吞成假空态)。 */
export async function fetchTaskLedger(): Promise<TaskLedgerResponse> {
  const { data } = await api.get<TaskLedgerResponse>('/agent/tasks');
  return {
    items: Array.isArray(data?.items) ? data.items : [],
    failed_sources: Array.isArray(data?.failed_sources) ? data.failed_sources : [],
  };
}
