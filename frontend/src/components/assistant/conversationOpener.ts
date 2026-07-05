/**
 * Web conversation-opener helpers — mirrors mobile/services/conversationOpener.ts.
 *
 * The chat opener is a stateful surface: a quick reply like "做到了" only has
 * meaning together with the opener card that asked. These helpers normalize the
 * opener API shape and build the `extra_context` payload that the backend's
 * `apply_opener_quick_reply_context` needs to resolve which ActionCard/check the
 * reply refers to — instead of the LLM guessing from a bare string.
 *
 * Kept byte-for-byte compatible with the mobile payload so the same backend
 * handler fires for web and RN.
 */

// 冷启动契约 (P0-3): quick reply 可带一个本地导航 action; 带 action 的 reply
// 点击时走客户端本地导航 (不发文本)。枚举与后端/mobile 一字不差。
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
  text: string;
  source: string;
  source_id?: number | null;
  quick_replies: QuickReply[];
  deep_link?: string | null;
  priority?: number;
}

/**
 * quick reply 兼容到达 shape (rollout / rollback 安全):
 * - 纯字符串 (存量后端) → {text}
 * - {text} 对象
 * - {label} 对象 (后端 OpenerQuickReply.asdict 的真实字段名) → {text}
 * - 带 action 的上述对象; action 不在枚举内 → 丢弃 action (降级为发文本)。
 */
export function normalizeQuickReply(r: unknown): QuickReply | null {
  if (typeof r === 'string') {
    return r.trim() ? { text: r } : null;
  }
  if (r && typeof r === 'object') {
    const o = r as Record<string, unknown>;
    const text =
      typeof o.text === 'string' && o.text.trim()
        ? o.text
        : typeof o.label === 'string' && o.label.trim()
          ? o.label
          : null;
    if (text) {
      const action =
        typeof o.action === 'string' &&
        (QUICK_REPLY_ACTIONS as readonly string[]).includes(o.action)
          ? (o.action as QuickReplyAction)
          : undefined;
      return action ? { text, action } : { text };
    }
  }
  return null;
}

/** 把任意到达形状的 opener 规整成内部 ConversationOpener (quick_replies 归一)。 */
export function normalizeOpener(raw: unknown): ConversationOpener | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.text !== 'string' || !o.text.trim()) return null;
  const replies = Array.isArray(o.quick_replies)
    ? (o.quick_replies.map(normalizeQuickReply).filter(Boolean) as QuickReply[]).slice(0, 3)
    : [];
  return {
    text: o.text,
    source: typeof o.source === 'string' ? o.source : '',
    source_id: (o.source_id as number | null | undefined) ?? null,
    quick_replies: replies,
    deep_link: typeof o.deep_link === 'string' ? o.deep_link : null,
    priority: typeof o.priority === 'number' ? o.priority : 0,
  };
}

/**
 * 构造 extra_context JSON. 与 mobile buildConversationOpenerReplyContext 逐字段一致,
 * 让后端 apply_opener_quick_reply_context 在 web/RN 上走同一条判定路径。
 */
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

/** 发送用的消息文本: 把 opener 摘要拼进用户回复, 与 mobile 一致。 */
export function buildConversationOpenerReplyMessage(
  opener: ConversationOpener,
  reply: string,
): string {
  const openerText = opener.text.trim().replace(/\s+/g, ' ');
  const clipped = openerText.length > 90 ? `${openerText.slice(0, 90)}...` : openerText;
  return `针对「${clipped}」：${reply}`;
}

// 冷启动 quick reply 的本地导航映射。目标都是 grep 核实过的既有 Web 路由:
// - photo_meal      → /diet   (拍照/记饮食页)
// - record_weight   → /weight (体重录入页)
// - connect_device  → /settings (数据连接 hub: Garmin/Apple Health/授权)
const QUICK_ACTION_ROUTE: Record<QuickReplyAction, string> = {
  photo_meal: '/diet',
  record_weight: '/weight',
  connect_device: '/settings',
};

export function routeForQuickReplyAction(action: QuickReplyAction): string {
  return QUICK_ACTION_ROUTE[action];
}
