/**
 * EmptyStateHome — 小巴 会诊页「新对话」空状态首屏。
 *
 * 从 chat.tsx 抽出来（chat.tsx 500 行预算收紧）。纯 props-driven，
 * 所有 handler（发送 / 记忆跳转 / opener 快回复 / 埋点）仍留在 chat.tsx，
 * 本组件只负责排版与视觉。
 *
 * 「小巴先开口」(State A, 2026-07 founder CDS):
 * - system content 不再是卡片家具, 而是小巴在流里的开场消息气泡:
 *   30pt 小巴品牌头像 + 气泡(非对称圆角, surface + hairline)。
 * - 问候语(早上好/下午好…)折进气泡当第一句, opener.text 接在后面。
 * - 记忆 footnote 在气泡内部(hairline 分隔): 书签图标 + 清洗过的记忆文本 + 「校准」入口。
 * - quick replies 在气泡外下方(chips), 追加一个「换个话题」中性 chip。
 * - opener 为空但有记忆 → 退化成「记忆-only 气泡」(同一外壳, footnote 文本当正文)。
 * - 两者都无 → 只保留独立问候块。
 * - suggestion chips 已移到 composer 上方(chat.tsx), 本组件不再渲染「或者问我别的」。
 *
 * 记忆线索 snippet 客户端防御式清洗(后端并行修复中, 旧缓存文本仍可能到达):
 * 剥离 JSON 残渣 + 折叠空白; 清洗后若把残渣剥没了(<6 字) → 隐藏 footnote。
 */
import React from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Pressable,
  StyleSheet,
  TextStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type {
  ConversationOpener,
  QuickReply,
  QuickReplyAction,
} from '../../services/conversationOpener';
import { formatOpenerText } from './OpenerCard';
import type { MemoryOpenerItem } from '../../services/memoryOpener';
import { QUICK_ACTION_LABEL } from '../../utils/quickReplyAction';
import XiaoBaAvatar from './XiaoBaAvatar';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

export type EmptyStateSuggestion = {
  icon: keyof typeof Ionicons.glyphMap;
  text: string;
  key: string;
  priority: number;
};

export type EmptyStateTodayFocus = {
  title: string;
  subtitle?: string | null;
  urgencyLabel?: string | null;
};

// 气泡外「换个话题」中性 chip — 发送语义走同一条 onQuickReply 路径。
export const CHANGE_TOPIC_REPLY = '换个话题';

// 第三态 Quick Start 卡的三个动作 (冷启动契约枚举)，与开场气泡视觉语言一致。
const QUICK_START_ACTIONS: {
  action: QuickReplyAction;
  icon: keyof typeof Ionicons.glyphMap;
}[] = [
  { action: 'photo_meal', icon: 'camera-outline' },
  { action: 'record_weight', icon: 'body-outline' },
  { action: 'connect_device', icon: 'watch-outline' },
];

interface Props {
  memoryOpener: MemoryOpenerItem[];
  opener: ConversationOpener | null;
  onOpenMemory: () => void;
  onOpenerQuickReply: (text: string) => void;
  /** 冷启动 (零信号) 标记: 第三态 (opener 未到 + 无记忆) 渲染 Quick Start 卡而非仅问候。 */
  onboarding?: boolean;
  /** 带 action 的 quick reply / Quick Start 卡动作 → 本地导航 (不发文本)。 */
  onQuickAction?: (action: QuickReplyAction) => void;
  /** 从 /timeline/today 派生的当前行动;为空则不渲染,不做客户端伪造。 */
  todayFocus?: EmptyStateTodayFocus | null;
  /** 打开聊天页内联 Today 面板。 */
  onOpenToday?: () => void;
  /** 键盘接管视口时隐藏开场回复，避免动作层与输入层竞争。 */
  showReplyActions?: boolean;
}

/**
 * 时间感知问候语。纯客户端 Date，不消费任何数据 → 不伪造健康指标。
 */
export function greetingForHour(hour: number): string {
  if (hour < 5) return '夜深了';
  if (hour < 11) return '早上好';
  if (hour < 14) return '中午好';
  if (hour < 18) return '下午好';
  return '晚上好';
}

/**
 * 记忆线索文案拼接 + 防御式清洗。
 *
 * 后端偶发把结构化 JSON 片段漏进 memory content（历史教训: 旧缓存文本）。
 * 这里剥掉明显的 JSON 残渣（"key":"value" 片段、孤立引号/花括号），折叠空白。
 * 若清洗动作真的剥掉了东西且剩余 <6 字 → 返回空串（调用方隐藏 footnote）；
 * 原文本身就干净（哪怕很短，如「旧记忆」）→ 原样保留。
 */
export function formatMemoryOpenerText(items: MemoryOpenerItem[]): string {
  const raw = items
    .map(item => (item.content || '').trim())
    .filter(Boolean)
    .slice(0, 2)
    .join(' · ');
  const sanitized = sanitizeMemorySnippet(raw);
  // 清洗剥掉了内容且剩得太短 → 判为残渣，隐藏。原文干净则始终保留。
  if (sanitized !== raw && sanitized.length < 6) return '';
  return sanitized;
}

function sanitizeMemorySnippet(text: string): string {
  return text
    // 剥掉 "…", "key": " 这样的 JSON 键值残渣（漏进 content 的结构碎片）
    .replace(/"\s*,\s*"[^"]*"\s*:\s*"/g, ' ')
    // blob 开头没有前置逗号时的 `"key":"` 起手
    .replace(/"[^"]*"\s*:\s*"/g, ' ')
    // 剥掉孤立的引号 / 花括号
    .replace(/["{}]/g, ' ')
    // 折叠空白
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * quick reply chip 文案 — 复用 opener 卡的冷静动作词, 但 chip 布局在气泡外。
 * 直接内联而非从 OpenerCard 导, 避免耦合到已废弃的卡片(仅保留 formatOpenerText / label)。
 */
function formatQuickReplyLabel(reply: string): string {
  if (/没做|未做|没有做|不算/.test(reply)) return '未完成';
  if (/做到|完成|已做|做了/.test(reply)) return '完成了';
  if (/调整|计划/.test(reply)) return '调整计划';
  return reply.replace(/[✅❌]/g, '').trim();
}

type VisibleOpenerReply = {
  key: string;
  label: string;
  reply: QuickReply;
  changeTopic: boolean;
};

export function buildVisibleOpenerReplies(
  replies: QuickReply[],
  limit = 3,
): VisibleOpenerReply[] {
  const visible: VisibleOpenerReply[] = [];
  const seen = new Set<string>();

  for (const reply of replies) {
    const label = reply.action
      ? QUICK_ACTION_LABEL[reply.action]
      : formatQuickReplyLabel(reply.text);
    if (!label) continue;
    const identity = reply.action ? `action:${reply.action}` : `label:${label}`;
    if (seen.has(identity)) continue;
    seen.add(identity);
    visible.push({
      key: identity,
      label,
      reply,
      changeTopic: label === CHANGE_TOPIC_REPLY,
    });
    if (visible.length >= limit) return visible;
  }

  const changeTopicIdentity = `label:${CHANGE_TOPIC_REPLY}`;
  if (visible.length < limit && !seen.has(changeTopicIdentity)) {
    visible.push({
      key: changeTopicIdentity,
      label: CHANGE_TOPIC_REPLY,
      reply: { text: CHANGE_TOPIC_REPLY },
      changeTopic: true,
    });
  }
  return visible;
}

/** 冷启动 action → 图标 (气泡 quick reply + Quick Start 卡共用)。 */
function quickActionIcon(action: QuickReplyAction): keyof typeof Ionicons.glyphMap {
  if (action === 'photo_meal') return 'camera-outline';
  if (action === 'record_weight') return 'body-outline';
  return 'watch-outline';
}

/**
 * 记忆 footnote — 气泡内部 hairline 分隔的一行: 书签图标 + 文本 + 「校准」入口。
 * 复用外层的 formatMemoryOpenerText 清洗结果(never render raw memory)。
 */
function MemoryFootnote({
  count,
  typeLabel,
  onOpenMemory,
}: {
  count: number;
  typeLabel?: string;
  onOpenMemory: () => void;
}) {
  return (
    <TouchableOpacity
      style={styles.footnote}
      onPress={onOpenMemory}
      hitSlop={8}
      activeOpacity={0.62}
      accessibilityRole="button"
      accessibilityLabel="查看和校准 AI 记忆"
    >
      <Ionicons name="layers-outline" size={13} color={C.ink3} />
      <Text style={txt.footnoteSource} numberOfLines={1}>
        依据 {count} 条{typeLabel || '健康记录'}
      </Text>
      <Ionicons name="chevron-forward" size={13} color={C.ink3} />
    </TouchableOpacity>
  );
}

function TodayCockpit({
  focus,
  onOpenToday,
}: {
  focus?: EmptyStateTodayFocus | null;
  onOpenToday?: () => void;
}) {
  if (!focus || !onOpenToday) return null;
  const subtitle = focus.subtitle?.trim();
  const urgency = focus.urgencyLabel?.trim();
  return (
    <Pressable
      style={({ pressed }) => [styles.todayCockpit, pressed && styles.replyPressed]}
      onPress={onOpenToday}
      accessibilityRole="button"
      accessibilityLabel="打开今日操作台"
    >
      <View style={styles.todayCockpitHeader}>
        <View style={styles.todayCockpitMark}>
          <Ionicons name="pulse-outline" size={15} color={C.green600} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={txt.todayCockpitEyebrow} numberOfLines={1}>今日操作台</Text>
          <Text style={txt.todayCockpitLabel} numberOfLines={1}>现在该做</Text>
        </View>
        {urgency ? (
          <View style={styles.todayCockpitPill}>
            <Text style={txt.todayCockpitPill} numberOfLines={1}>{urgency}</Text>
          </View>
        ) : null}
      </View>
      <View style={styles.todayCockpitBody}>
        <Text style={txt.todayCockpitTitle} numberOfLines={2}>{focus.title}</Text>
        {subtitle ? (
          <Text style={txt.todayCockpitSub} numberOfLines={1}>{subtitle}</Text>
        ) : null}
      </View>
      <View style={styles.todayCockpitAction}>
        <Text style={txt.todayCockpitAction}>查看今日</Text>
        <Ionicons name="chevron-forward" size={14} color={C.green600} />
      </View>
    </Pressable>
  );
}

export default function EmptyStateHome({
  memoryOpener,
  opener,
  onOpenMemory,
  onOpenerQuickReply,
  onboarding = false,
  onQuickAction,
  todayFocus,
  onOpenToday,
  showReplyActions = true,
}: Props) {
  const memoryText = formatMemoryOpenerText(memoryOpener);
  const showMemory = memoryOpener.length > 0 && memoryText.length > 0;
  const greeting = greetingForHour(new Date().getHours());
  const todayCockpit = <TodayCockpit focus={todayFocus} onOpenToday={onOpenToday} />;

  // opener 存在 → 完整开场气泡(问候 + opener.text + 可选记忆 footnote + quick replies)。
  if (opener) {
    const openerText = formatOpenerText(opener.text);
    const replies = buildVisibleOpenerReplies(opener.quick_replies || []);
    return (
      <View style={styles.container}>
        {todayCockpit}
        <View style={styles.bubbleRow}>
          <XiaoBaAvatar size={AVATAR} />
          <View style={styles.bubble}>
            <Text style={txt.bubbleBody}>
              <Text style={txt.greetingInline}>{greeting}。</Text>
              {openerText}
            </Text>
            {showMemory && (
              <MemoryFootnote
                count={memoryOpener.length}
                typeLabel={memoryOpener[0]?.type_label}
                onOpenMemory={onOpenMemory}
              />
            )}
          </View>
        </View>

        {showReplyActions && replies.length > 0 && <View style={styles.repliesRow}>
          {replies.map(({ key, label, reply, changeTopic }, i) => {
            const tinted = i === 0;
            // 带 action 的 reply → 本地导航 (不发文本); 否则走既有发送路径。
            const onPress = reply.action && onQuickAction
              ? () => onQuickAction(reply.action as QuickReplyAction)
              : () => onOpenerQuickReply(reply.text);
            // 无障碍标签: action reply 用动作标签; 文本 reply 保留原始文本(既有行为)。
            const a11yLabel = reply.action ? label : reply.text;
            return (
              <Pressable
                key={key}
                style={({ pressed }) => [
                  styles.reply,
                  tinted ? styles.replyTinted : styles.replyNeutral,
                  pressed && styles.replyPressed,
                ]}
                onPress={onPress}
                accessibilityRole="button"
                accessibilityLabel={changeTopic ? CHANGE_TOPIC_REPLY : `一键回复: ${a11yLabel}`}
              >
                {reply.action && (
                  <Ionicons
                    name={quickActionIcon(reply.action)}
                    size={13}
                    color={tinted ? C.green600 : C.ink2}
                  />
                )}
                <Text style={[txt.reply, tinted ? txt.replyTinted : txt.replyNeutral]}>
                  {label}
                </Text>
              </Pressable>
            );
          })}
        </View>}
      </View>
    );
  }

  // opener 为空但有记忆 → 记忆-only 气泡(同一外壳, footnote 文本当正文)。
  if (showMemory) {
    return (
      <View style={styles.container}>
        {todayCockpit}
        <View style={styles.greeting}>
          <Text style={txt.greetingHi} numberOfLines={1}>{greeting}</Text>
          <Text style={txt.greetingSub} numberOfLines={1}>今天想从哪里开始？</Text>
        </View>
        <View style={styles.bubbleRow}>
          <XiaoBaAvatar size={AVATAR} />
          <View style={styles.bubble}>
            <View style={styles.memorySourceBadge}>
              <Ionicons name="bookmark-outline" size={11} color={C.green600} />
              <Text style={txt.memorySourceBadge}>
                记忆 · {memoryOpener[0]?.type_label || '健康'}
              </Text>
            </View>
            <View style={styles.memoryOnlyLead}>
              <Text style={txt.bubbleBody} numberOfLines={2}>{memoryText}</Text>
            </View>
            <View style={styles.memoryOnlyActionRow}>
              <TouchableOpacity
                onPress={onOpenMemory}
                hitSlop={8}
                accessibilityRole="button"
                accessibilityLabel="查看和校准 AI 记忆"
              >
                <Text style={txt.footnoteAction}>校准</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </View>
    );
  }

  // 冷启动第三态 (onboarding 但 opener 因故未到 + 无记忆) → Quick Start 卡:
  // 三个首次价值动作, 视觉与开场气泡一致 (小巴品牌头像 + 非对称圆角气泡 + Reva tokens)。
  // opener 正常到达时上面已 return, 不会走到这里 → 不会气泡 + 卡 + chips 三层堆叠。
  if (onboarding && onQuickAction) {
    return (
      <View style={styles.container}>
        {todayCockpit}
        <View style={styles.bubbleRow}>
          <XiaoBaAvatar size={AVATAR} />
          <View style={styles.bubble}>
            <Text style={txt.bubbleBody}>
              <Text style={txt.greetingInline}>{greeting}。</Text>
              我是小巴，你的健康参谋。先从这三件事之一开始，我就能帮你看懂身体。
            </Text>
            <View style={styles.quickStartRow}>
              {QUICK_START_ACTIONS.map(({ action, icon }) => (
                <Pressable
                  key={action}
                  style={({ pressed }) => [styles.quickStartAction, pressed && styles.replyPressed]}
                  onPress={() => onQuickAction(action)}
                  accessibilityRole="button"
                  accessibilityLabel={QUICK_ACTION_LABEL[action]}
                >
                  <View style={styles.quickStartIcon}>
                    <Ionicons name={icon} size={16} color={C.green600} />
                  </View>
                  <Text style={txt.quickStartLabel} numberOfLines={1}>
                    {QUICK_ACTION_LABEL[action]}
                  </Text>
                  <Ionicons name="chevron-forward" size={14} color={C.ink3} style={{ marginLeft: 'auto' }} />
                </Pressable>
              ))}
            </View>
          </View>
        </View>
      </View>
    );
  }

  // 两者都无 → 只保留独立问候块。
  return (
    <View style={styles.container}>
      {todayCockpit}
      <View style={styles.greeting}>
        <Text style={txt.greetingHi} numberOfLines={1}>{greeting}</Text>
        <Text style={txt.greetingSub} numberOfLines={1}>今天想从哪里开始？</Text>
      </View>
    </View>
  );
}

const AVATAR = 30;

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: revaSpacing.s4,
    paddingTop: revaSpacing.s3,
    gap: revaSpacing.s3,
  },
  greeting: {
    paddingHorizontal: revaSpacing.s1,
    paddingTop: revaSpacing.s2,
    paddingBottom: revaSpacing.s1,
  },
  bubbleRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s2,
    paddingTop: revaSpacing.s2,
  },
  bubble: {
    flexShrink: 1,
    maxWidth: '88%',
    paddingHorizontal: revaSpacing.s1,
    paddingVertical: 2,
  },
  footnote: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 5,
    minHeight: 28,
    marginTop: revaSpacing.s2,
    paddingHorizontal: 0,
  },
  memorySourceBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 3,
    minHeight: 22,
    paddingHorizontal: 7,
    paddingVertical: 2,
    marginBottom: 4,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
  },
  memoryOnlyLead: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 6,
  },
  memoryOnlyActionRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    marginTop: revaSpacing.s2,
    paddingTop: revaSpacing.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  repliesRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    paddingLeft: AVATAR + revaSpacing.s2,
  },
  reply: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: 7,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
  },
  replyTinted: {
    backgroundColor: C.green50,
    borderColor: C.green100,
  },
  replyNeutral: {
    backgroundColor: C.surface,
    borderColor: C.line,
  },
  replyPressed: { opacity: 0.6 },
  // Quick Start 卡 (冷启动第三态): 气泡内部, hairline 分隔的动作列。
  quickStartRow: {
    marginTop: revaSpacing.s3,
    paddingTop: revaSpacing.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
    gap: revaSpacing.s2,
  },
  quickStartAction: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    minHeight: 44,
    paddingHorizontal: revaSpacing.s2,
    paddingVertical: revaSpacing.s2,
    borderRadius: revaRadii.md,
    backgroundColor: C.paper2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  quickStartIcon: {
    width: 28,
    height: 28,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  todayCockpit: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s3,
    gap: revaSpacing.s2,
    ...revaShadows.sm,
  },
  todayCockpitHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
  },
  todayCockpitMark: {
    width: 30,
    height: 30,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  todayCockpitPill: {
    maxWidth: 96,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    paddingHorizontal: revaSpacing.s2,
    paddingVertical: 4,
  },
  todayCockpitBody: {
    paddingLeft: 38,
    gap: 2,
  },
  todayCockpitAction: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 2,
  },
});

const txt = {
  greetingHi: {
    fontFamily: revaFonts.sans,
    fontSize: 20,
    fontWeight: '700',
    color: C.ink1,
  } as TextStyle,
  greetingSub: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink3,
    fontWeight: '500',
    marginTop: 2,
  } as TextStyle,
  bubbleBody: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    lineHeight: 22,
    color: C.ink1,
    fontWeight: '400',
    flexShrink: 1,
  } as TextStyle,
  greetingInline: {
    fontWeight: '600',
    color: C.ink1,
  } as TextStyle,
  footnoteSource: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink3,
    lineHeight: 16,
    fontWeight: '600',
  } as TextStyle,
  memorySourceBadge: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    lineHeight: 14,
    color: C.green600,
    fontWeight: '700',
  } as TextStyle,
  footnoteAction: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.green600,
    fontWeight: '700',
  } as TextStyle,
  reply: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '600',
  } as TextStyle,
  replyTinted: {
    color: C.green600,
  } as TextStyle,
  replyNeutral: {
    color: C.ink2,
  } as TextStyle,
  quickStartLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    fontWeight: '700',
    color: C.ink1,
  } as TextStyle,
  todayCockpitEyebrow: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
  todayCockpitLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '600',
    color: C.ink3,
    marginTop: 1,
  } as TextStyle,
  todayCockpitPill: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
  todayCockpitTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    lineHeight: 21,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  todayCockpitSub: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    fontWeight: '500',
    color: C.ink3,
  } as TextStyle,
  todayCockpitAction: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '800',
    color: C.green600,
  } as TextStyle,
};
