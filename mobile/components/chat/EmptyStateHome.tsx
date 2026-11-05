/** Home presentation only: neutral greeting, owned content and existing explicit actions. */
import React, { useEffect, useState } from 'react';
import {
  AppState,
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
import { freshConversationPrompt, isHomePhotoEntry } from '../../utils/homePrompts';
import XiaoBaAvatar from './XiaoBaAvatar';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
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

// Retained local shortcuts; photo capture remains in the composer attachment menu.
const QUICK_START_ACTIONS: {
  action: QuickReplyAction;
  icon: keyof typeof Ionicons.glyphMap;
}[] = [
  { action: 'record_weight', icon: 'body-outline' },
  { action: 'connect_device', icon: 'watch-outline' },
];

interface Props {
  freshStart?: boolean;
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
    if (isHomePhotoEntry(reply.text, reply.action)) continue;
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
  freshStart = false,
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
  const [hour, setHour] = useState(() => new Date().getHours());
  useEffect(() => {
    const refresh = () => setHour(new Date().getHours());
    const timer = setInterval(refresh, 60_000);
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') refresh();
    });
    return () => { clearInterval(timer); subscription.remove(); };
  }, []);
  // A fresh conversation never presents an older opener, memory or Today focus.
  const activeOpener = freshStart ? null : opener;
  const memoryText = freshStart ? '' : formatMemoryOpenerText(memoryOpener);
  const showMemory = !activeOpener && memoryText.length > 0;
  const replies = activeOpener ? buildVisibleOpenerReplies(activeOpener.quick_replies || []) : [];
  const showQuickStart = !activeOpener && !showMemory && (freshStart || onboarding);
  const quickActions = QUICK_START_ACTIONS.filter(({ action }) => !freshStart || action !== 'connect_device');

  return (
    <View style={[styles.container, !showReplyActions && styles.containerCompact]}>
      <View style={styles.hero}>
        <View style={styles.heroCopy}>
          <Text accessibilityRole="header" style={[txt.greetingHi, !showReplyActions && txt.greetingCompact]}>
            {greetingForHour(hour)}
          </Text>
          <Text style={txt.greetingSub}>
            {showQuickStart ? freshConversationPrompt(hour).text : '今天想从哪里开始？'}
          </Text>
        </View>
      </View>

      {!freshStart && <TodayCockpit focus={todayFocus} onOpenToday={onOpenToday} />}

      {activeOpener && (
        <View style={styles.contentCard}>
          <View style={styles.contentCardHeader}>
            <XiaoBaAvatar size={32} compact />
            <View>
              <Text style={txt.eyebrow}>小气候</Text>
              <Text style={txt.contentCardMeta}>想和你聊聊</Text>
            </View>
          </View>
          <Text style={txt.bubbleBody}>{formatOpenerText(activeOpener.text)}</Text>
          {showReplyActions && replies.length > 0 && (
            <View style={styles.repliesRow}>
              {replies.map(({ key, label, reply, changeTopic }, index) => {
                const primary = index === 0 && !changeTopic;
                const onPress = reply.action && onQuickAction
                  ? () => onQuickAction(reply.action as QuickReplyAction)
                  : () => onOpenerQuickReply(reply.text);
                return (
                  <Pressable key={key} onPress={onPress}
                    style={({ pressed }) => [styles.reply, primary ? styles.replyPrimary : styles.replyNeutral,
                      pressed && styles.replyPressed]}
                    accessibilityRole="button"
                    accessibilityLabel={changeTopic ? CHANGE_TOPIC_REPLY : `一键回复: ${reply.action ? label : reply.text}`}>
                    {reply.action && <Ionicons name={quickActionIcon(reply.action)} size={16}
                      color={primary ? C.greenOn : C.green600} />}
                    <Text style={[txt.reply, primary && txt.replyPrimary]}>{label}</Text>
                  </Pressable>
                );
              })}
            </View>
          )}
        </View>
      )}

      {showMemory && (
        <View style={styles.contentCard}>
          <View style={styles.memorySourceBadge}>
            <Ionicons name="bookmark-outline" size={14} color={C.green600} />
            <Text style={txt.memorySourceBadge}>记忆 · {memoryOpener[0]?.type_label || '健康'}</Text>
          </View>
          <Text style={txt.bubbleBody} numberOfLines={2}>{memoryText}</Text>
          <TouchableOpacity onPress={onOpenMemory} activeOpacity={0.65}
            style={styles.memoryAction} accessibilityRole="button" accessibilityLabel="查看和校准 AI 记忆">
            <Text style={txt.footnoteAction}>查看与校准</Text>
            <Ionicons name="chevron-forward" size={16} color={C.green600} />
          </TouchableOpacity>
        </View>
      )}

      {showQuickStart && showReplyActions && onQuickAction && (
        <View style={styles.quickStartSection}>
          <Text style={txt.quickStartEyebrow}>快捷记录</Text>
          <View style={styles.quickStartRow}>
            {quickActions.map(({ action, icon }) => (
              <Pressable key={action} onPress={() => onQuickAction(action)}
                style={({ pressed }) => [styles.quickStartAction, pressed && styles.replyPressed]}
                accessibilityRole="button" accessibilityLabel={QUICK_ACTION_LABEL[action]}>
                <View style={styles.quickStartIcon}><Ionicons name={icon} size={18} color={C.green600} /></View>
                <Text style={txt.quickStartLabel}>{QUICK_ACTION_LABEL[action]}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  // The FlatList already owns the page gutter; do not inset the home a second time.
  container: { width: '100%', maxWidth: 680, alignSelf: 'center', paddingTop: revaSpacing.s4,
    paddingBottom: revaSpacing.s4, gap: revaSpacing.s4 },
  containerCompact: { paddingTop: revaSpacing.s2, gap: revaSpacing.s3 },
  hero: { paddingHorizontal: revaSpacing.s1, paddingBottom: revaSpacing.s1 },
  heroCopy: { flex: 1, minWidth: 0 },
  contentCard: { backgroundColor: C.surface, borderRadius: revaRadii.xl, padding: revaSpacing.s5,
    borderWidth: StyleSheet.hairlineWidth, borderColor: C.line, gap: revaSpacing.s3 },
  contentCardHeader: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s2 },
  repliesRow: { flexDirection: 'row', flexWrap: 'wrap', gap: revaSpacing.s2,
    paddingTop: revaSpacing.s2 },
  reply: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    minHeight: 44, maxWidth: '100%', paddingHorizontal: revaSpacing.s4, paddingVertical: revaSpacing.s2,
    borderRadius: revaRadii.md },
  replyPrimary: { backgroundColor: C.green600 },
  replyNeutral: { backgroundColor: C.paper2 },
  replyPressed: { opacity: 0.65 },
  memorySourceBadge: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  memoryAction: { minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end',
    gap: revaSpacing.s1, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line,
    paddingTop: revaSpacing.s2 },
  quickStartSection: { gap: revaSpacing.s2, paddingHorizontal: revaSpacing.s1 },
  quickStartRow: { flexDirection: 'row', flexWrap: 'wrap', gap: revaSpacing.s2 },
  quickStartAction: { minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s2,
    paddingVertical: revaSpacing.s2, paddingLeft: revaSpacing.s2, paddingRight: revaSpacing.s4,
    borderRadius: revaRadii.pill, backgroundColor: C.green50 },
  quickStartIcon: { width: 32, height: 32, borderRadius: revaRadii.pill,
    alignItems: 'center', justifyContent: 'center', backgroundColor: C.surface },
  todayCockpit: { backgroundColor: C.green50, borderRadius: revaRadii.xl, padding: revaSpacing.s5,
    gap: revaSpacing.s3, borderWidth: StyleSheet.hairlineWidth, borderColor: C.green100 },
  todayCockpitHeader: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s2 },
  todayCockpitMark: { width: 36, height: 36, borderRadius: revaRadii.sm, backgroundColor: C.surface,
    alignItems: 'center', justifyContent: 'center' },
  todayCockpitPill: { maxWidth: 96, borderRadius: revaRadii.pill, backgroundColor: C.surface,
    paddingHorizontal: revaSpacing.s2, paddingVertical: revaSpacing.s1 },
  todayCockpitBody: { gap: revaSpacing.s1 },
  todayCockpitAction: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 4, minHeight: 44 },
});

const txt = {
  greetingHi: { fontFamily: revaFonts.sans, fontSize: 26, lineHeight: 34, fontWeight: '700', color: C.ink1 } as TextStyle,
  greetingCompact: { fontSize: 22, lineHeight: 29 } as TextStyle,
  greetingSub: { fontFamily: revaFonts.sans, fontSize: 15, lineHeight: 23, color: C.ink2, marginTop: revaSpacing.s1 } as TextStyle,
  eyebrow: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 18, color: C.green600, fontWeight: '600' } as TextStyle,
  contentCardMeta: { fontFamily: revaFonts.sans, fontSize: 11, lineHeight: 16, color: C.ink3 } as TextStyle,
  bubbleBody: { fontFamily: revaFonts.sans, fontSize: 16, lineHeight: 26, color: C.ink1, fontWeight: '400' } as TextStyle,
  reply: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 21, color: C.ink2, fontWeight: '600', flexShrink: 1 } as TextStyle,
  replyPrimary: { color: C.greenOn } as TextStyle,
  memorySourceBadge: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 18, color: C.green600, fontWeight: '600' } as TextStyle,
  footnoteAction: { fontFamily: revaFonts.sans, fontSize: 13, lineHeight: 20, fontWeight: '600', color: C.green600 } as TextStyle,
  quickStartEyebrow: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 18, fontWeight: '600', color: C.ink3 } as TextStyle,
  quickStartLabel: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 21, fontWeight: '600', color: C.green700 } as TextStyle,
  todayCockpitEyebrow: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '600', color: C.green600 } as TextStyle,
  todayCockpitLabel: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink2, marginTop: 2 } as TextStyle,
  todayCockpitPill: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '600', color: C.green600 } as TextStyle,
  todayCockpitTitle: { fontFamily: revaFonts.sans, fontSize: 17, lineHeight: 25, fontWeight: '600', color: C.ink1 } as TextStyle,
  todayCockpitSub: { fontFamily: revaFonts.sans, fontSize: 13, lineHeight: 20, color: C.ink2 } as TextStyle,
  todayCockpitAction: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.green600 } as TextStyle,
};
