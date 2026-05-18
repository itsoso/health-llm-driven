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

export function buildConversationOpenerReplyContext(
  opener: ConversationOpener,
  reply: string,
): string {
  return JSON.stringify({
    entry: 'conversation_opener_quick_reply',
    user_reply: reply,
    opener_text: opener.text,
    source: opener.source,
    source_id: opener.source_id ?? null,
    deep_link: opener.deep_link ?? null,
    action_card_id: opener.source === 'action_card_due' ? opener.source_id ?? null : null,
    instruction:
      'This user reply is responding to the opener_text above. Use source/source_id as the verification target instead of treating the reply as standalone text.',
  });
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
