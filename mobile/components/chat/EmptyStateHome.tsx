/**
 * EmptyStateHome — 小巴 会诊页「新对话」空状态首屏。
 *
 * 从 chat.tsx 抽出来（chat.tsx 500 行预算收紧）。纯 props-driven，
 * 所有 handler（发送 / 记忆跳转 / opener 快回复 / 埋点）仍留在 chat.tsx，
 * 本组件只负责排版与视觉。
 *
 * 「小巴先开口」(State A, 2026-07 founder CDS):
 * - system content 不再是卡片家具, 而是小巴在流里的开场消息气泡:
 *   30pt paw-avatar + 气泡(非对称圆角, surface + hairline)。
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
import type { ConversationOpener } from '../../services/conversationOpener';
import { formatOpenerText } from './OpenerCard';
import type { MemoryOpenerItem } from '../../services/memoryOpener';
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

// 气泡外「换个话题」中性 chip — 发送语义走同一条 onQuickReply 路径。
export const CHANGE_TOPIC_REPLY = '换个话题';

interface Props {
  memoryOpener: MemoryOpenerItem[];
  opener: ConversationOpener | null;
  onOpenMemory: () => void;
  onOpenerQuickReply: (text: string) => void;
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

/**
 * 记忆 footnote — 气泡内部 hairline 分隔的一行: 书签图标 + 文本 + 「校准」入口。
 * 复用外层的 formatMemoryOpenerText 清洗结果(never render raw memory)。
 */
function MemoryFootnote({
  text,
  onOpenMemory,
}: {
  text: string;
  onOpenMemory: () => void;
}) {
  return (
    <View style={styles.footnote}>
      <View style={styles.footnoteLead}>
        <Ionicons name="bookmark-outline" size={12} color={C.ink3} />
        <Text style={txt.footnoteBody} numberOfLines={2}>
          {text}
        </Text>
      </View>
      <TouchableOpacity
        onPress={onOpenMemory}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel="查看和校准 AI 记忆"
      >
        <Text style={txt.footnoteAction}>校准</Text>
      </TouchableOpacity>
    </View>
  );
}

export default function EmptyStateHome({
  memoryOpener,
  opener,
  onOpenMemory,
  onOpenerQuickReply,
}: Props) {
  const memoryText = formatMemoryOpenerText(memoryOpener);
  const showMemory = memoryOpener.length > 0 && memoryText.length > 0;
  const greeting = greetingForHour(new Date().getHours());

  // opener 存在 → 完整开场气泡(问候 + opener.text + 可选记忆 footnote + quick replies)。
  if (opener) {
    const openerText = formatOpenerText(opener.text);
    // 气泡外 quick replies: opener 自带的 + 末尾追加「换个话题」中性 chip。
    const replies = opener.quick_replies || [];
    return (
      <View style={styles.container}>
        <View style={styles.bubbleRow}>
          <View style={styles.avatar}>
            <Ionicons name="paw" size={15} color={C.green600} />
          </View>
          <View style={styles.bubble}>
            <Text style={txt.bubbleBody}>
              <Text style={txt.greetingInline}>{greeting}。</Text>
              {openerText}
            </Text>
            {showMemory && (
              <MemoryFootnote text={memoryText} onOpenMemory={onOpenMemory} />
            )}
          </View>
        </View>

        <View style={styles.repliesRow}>
          {replies.map((reply, i) => {
            const tinted = i === 0;
            return (
              <Pressable
                key={reply}
                style={({ pressed }) => [
                  styles.reply,
                  tinted ? styles.replyTinted : styles.replyNeutral,
                  pressed && styles.replyPressed,
                ]}
                onPress={() => onOpenerQuickReply(reply)}
                accessibilityRole="button"
                accessibilityLabel={`一键回复: ${reply}`}
              >
                <Text style={[txt.reply, tinted ? txt.replyTinted : txt.replyNeutral]}>
                  {formatQuickReplyLabel(reply)}
                </Text>
              </Pressable>
            );
          })}
          <Pressable
            style={({ pressed }) => [
              styles.reply,
              styles.replyNeutral,
              pressed && styles.replyPressed,
            ]}
            onPress={() => onOpenerQuickReply(CHANGE_TOPIC_REPLY)}
            accessibilityRole="button"
            accessibilityLabel="换个话题"
          >
            <Text style={[txt.reply, txt.replyNeutral]}>{CHANGE_TOPIC_REPLY}</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  // opener 为空但有记忆 → 记忆-only 气泡(同一外壳, footnote 文本当正文)。
  if (showMemory) {
    return (
      <View style={styles.container}>
        <View style={styles.greeting}>
          <Text style={txt.greetingHi} numberOfLines={1}>{greeting}</Text>
          <Text style={txt.greetingSub} numberOfLines={1}>今天想从哪里开始？</Text>
        </View>
        <View style={styles.bubbleRow}>
          <View style={styles.avatar}>
            <Ionicons name="paw" size={15} color={C.green600} />
          </View>
          <View style={styles.bubble}>
            <View style={styles.memoryOnlyLead}>
              <Ionicons name="bookmark-outline" size={13} color={C.ink3} />
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

  // 两者都无 → 只保留独立问候块。
  return (
    <View style={styles.container}>
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
  avatar: {
    width: AVATAR,
    height: AVATAR,
    borderRadius: AVATAR / 2,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  bubble: {
    flexShrink: 1,
    maxWidth: '86%',
    backgroundColor: C.surface,
    // 非对称圆角: 左上贴近 avatar 收窄(4), 其余保持气泡感(16)。
    borderTopLeftRadius: 4,
    borderTopRightRadius: 16,
    borderBottomLeftRadius: 16,
    borderBottomRightRadius: 16,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s3,
    ...revaShadows.sm,
  },
  footnote: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: revaSpacing.s2,
    marginTop: revaSpacing.s2,
    paddingTop: revaSpacing.s2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  footnoteLead: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 5,
    flexShrink: 1,
    minWidth: 0,
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
  footnoteBody: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink3,
    lineHeight: 17,
    flexShrink: 1,
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
};
