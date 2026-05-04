/**
 * Conversation Opener API client.
 *
 * 拉 chat 起手"未读续接". 失败/无信号都安全 — 调用方退化到默认 SUGGESTIONS chip.
 */
import api from './api';

export type OpenerSource =
  | 'action_card_due'    // ActionCard 检验日 ≤ 2d
  | 'anomaly'            // 24h 内 anomaly_alert
  | 'case_thread'        // case_thread 3-7d 前更新
  | 'memory_fact';       // 7d 内 memory fact

export interface ConversationOpener {
  text: string;                      // AI 主动开场白
  source: OpenerSource;
  source_id?: number | null;
  quick_replies: string[];           // 1-3 个 quick reply chip
  deep_link?: string | null;         // 点开场白 banner 跳哪
  priority: number;
}

/**
 * 拉一次 opener. 任何错误返回 null, 不抛 — chat 启动不能被这个挂.
 */
export async function fetchConversationOpener(): Promise<ConversationOpener | null> {
  try {
    const res = await api.get<{ opener: ConversationOpener | null }>(
      '/agent/conversation-opener',
    );
    return res.data?.opener ?? null;
  } catch {
    return null;
  }
}
