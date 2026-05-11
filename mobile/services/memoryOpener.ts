import api from './api';

export interface MemoryOpenerItem {
  id: number;
  type: string;
  type_label: string;
  content: string;
}

interface OpenerResponse {
  items: MemoryOpenerItem[];
}

/**
 * P3-3 (2026-05-11): 会诊页进入时拉 top 1-2 条 active 记忆,
 * 显示 "我记得你: <X>" 给用户感知持久记忆.
 *
 * 失败静默 — 不阻塞 chat 进入. 用户没历史记忆时返回空数组, UI 不显示 banner.
 */
export async function fetchMemoryOpener(k = 2): Promise<MemoryOpenerItem[]> {
  try {
    const { data } = await api.get<OpenerResponse>(
      `/conversation-memory/opener?k=${k}`,
    );
    return data?.items ?? [];
  } catch (err) {
    if (__DEV__) console.warn('[memoryOpener] fetch failed:', err);
    return [];
  }
}
