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

/**
 * 冷启动契约 (P0-3): quick reply 可带一个本地导航 action。带 action 的 reply
 * 点击时走客户端本地导航(不发文本);枚举与后端一字不差。
 */
export type QuickReplyAction = 'photo_meal' | 'record_weight' | 'connect_device';

const QUICK_REPLY_ACTIONS: readonly QuickReplyAction[] = [
  'photo_meal',
  'record_weight',
  'connect_device',
];

export interface QuickReply {
  text: string;
  action?: QuickReplyAction;
}

export interface ConversationOpener {
  text: string;                      // AI 主动开场白
  source: OpenerSource;
  source_id?: number | null;
  quick_replies: QuickReply[];       // 1-3 个 quick reply chip (可选带本地导航 action)
  deep_link?: string | null;         // 点开场白 banner 跳哪
  priority: number;
}

/**
 * quick reply 兼容三种到达 shape (rollout / rollback 安全):
 * - 纯字符串 (存量后端) → {text}
 * - {text} 对象
 * - {text, action} 对象 (冷启动包新契约); action 不在枚举内 → 丢弃 action (降级为发文本)。
 */
function normalizeQuickReply(r: unknown): QuickReply | null {
  if (typeof r === 'string') {
    return r.trim() ? { text: r } : null;
  }
  if (r && typeof r === 'object') {
    const o = r as Record<string, unknown>;
    if (typeof o.text === 'string' && o.text.trim()) {
      const action =
        typeof o.action === 'string' &&
        (QUICK_REPLY_ACTIONS as readonly string[]).includes(o.action)
          ? (o.action as QuickReplyAction)
          : undefined;
      return action ? { text: o.text, action } : { text: o.text };
    }
  }
  return null;
}

/** 把任意到达形状的 opener 规整成内部 ConversationOpener (quick_replies 归一)。 */
function normalizeOpener(raw: unknown): ConversationOpener | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.text !== 'string' || !o.text) return null;
  const replies = Array.isArray(o.quick_replies)
    ? (o.quick_replies.map(normalizeQuickReply).filter(Boolean) as QuickReply[])
    : [];
  return {
    text: o.text,
    source: o.source as OpenerSource,
    source_id: (o.source_id as number | null | undefined) ?? null,
    quick_replies: replies,
    deep_link: (o.deep_link as string | null | undefined) ?? null,
    priority: typeof o.priority === 'number' ? o.priority : 0,
  };
}

/** A starter chip carries its generator `key` so taps/impressions can be
 *  attributed per generator (CTR). `key` is "default"/"legacy" for fallbacks. */
export interface SuggestionMeta {
  text: string;
  key: string;
  priority: number;
}

export interface ConversationStarters {
  opener: ConversationOpener | null;
  suggestions: SuggestionMeta[] | null;
  /**
   * 冷启动契约 (P0-3): 仅零信号冷启动用户带 true;老用户不带或 false。
   * true → 客户端禁止把 starters 回落成 DEFAULT_SUGGESTIONS,原样渲染后端返回。
   */
  onboarding: boolean;
}

/** Tolerate both the new {text,key,priority} object shape and the legacy
 *  plain-string shape (rollout / rollback safety). */
function normalizeSuggestion(s: unknown): SuggestionMeta | null {
  if (typeof s === 'string') return { text: s, key: 'legacy', priority: 0 };
  if (s && typeof s === 'object') {
    const o = s as Record<string, unknown>;
    if (typeof o.text === 'string' && o.text) {
      return {
        text: o.text,
        key: typeof o.key === 'string' && o.key ? o.key : 'unknown',
        priority: typeof o.priority === 'number' ? o.priority : 0,
      };
    }
  }
  return null;
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

export function buildConversationOpenerReplyMessage(
  opener: ConversationOpener,
  reply: string,
): string {
  const openerText = opener.text.trim().replace(/\s+/g, ' ');
  const clipped = openerText.length > 90 ? `${openerText.slice(0, 90)}...` : openerText;
  return `针对「${clipped}」：${reply}`;
}

/**
 * 拉一次 opener. 任何错误返回 null, 不抛 — chat 启动不能被这个挂.
 */
export async function fetchConversationOpener(): Promise<ConversationOpener | null> {
  try {
    const res = await api.get<{ opener: unknown }>(
      '/agent/conversation-opener',
    );
    return normalizeOpener(res.data?.opener);
  } catch {
    return null;
  }
}

/**
 * 拉新对话页动态 prompts + opener. 任何错误返回 {opener:null,suggestions:null}.
 */
export async function fetchConversationStarters(): Promise<ConversationStarters> {
  try {
    const res = await api.get<{ opener: unknown; suggestions: unknown; onboarding?: unknown }>(
      '/agent/conversation-starters',
    );
    const raw = res.data?.suggestions;
    const suggestions = Array.isArray(raw)
      ? (raw.map(normalizeSuggestion).filter(Boolean) as SuggestionMeta[])
      : null;
    return {
      opener: normalizeOpener(res.data?.opener),
      suggestions: suggestions && suggestions.length > 0 ? suggestions : null,
      onboarding: res.data?.onboarding === true,
    };
  } catch {
    return { opener: null, suggestions: null, onboarding: false };
  }
}
