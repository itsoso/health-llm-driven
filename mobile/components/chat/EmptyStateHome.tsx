/**
 * EmptyStateHome — 阿衡 会诊页「新对话」空状态首屏。
 *
 * 从 chat.tsx 抽出来（chat.tsx 500 行预算收紧）。纯 props-driven，
 * 所有 handler（发送 / 记忆跳转 / opener 快回复 / 埋点）仍留在 chat.tsx，
 * 本组件只负责排版与视觉。
 *
 * 视觉统一（founder 设备反馈 2026-07）:
 * - 三块内容（记忆线索 / 今日回访 opener / 或者问我别的）统一到 app 卡片语言:
 *   surface + hairline + revaRadii.lg，一致的 11px ink3 bold eyebrow（对齐 BriefingStrip 的「今日简报」label）。
 * - 顶部加一条轻量、纯客户端、基于 Date 的问候块（早上好/下午好/晚上好 + 一句静默引导），
 *   把原本挤在顶部的卡片下压，让整屏更有构图感。不做垂直居中（键盘交互）。
 * - 记忆线索 snippet 客户端防御式清洗（后端并行修复中，旧缓存文本仍可能到达）:
 *   剥离 JSON 残渣 + 折叠空白；清洗后若把残渣剥没了（<6 字）→ 整卡隐藏。
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
import OpenerCard from './OpenerCard';
import type { ConversationOpener } from '../../services/conversationOpener';
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

interface Props {
  memoryOpener: MemoryOpenerItem[];
  opener: ConversationOpener | null;
  suggestions: EmptyStateSuggestion[];
  onOpenMemory: () => void;
  onOpenerQuickReply: (text: string) => void;
  onSuggestionPress: (s: EmptyStateSuggestion, position: number) => void;
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
 * 若清洗动作真的剥掉了东西且剩余 <6 字 → 返回空串（调用方隐藏整卡）；
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

export default function EmptyStateHome({
  memoryOpener,
  opener,
  suggestions,
  onOpenMemory,
  onOpenerQuickReply,
  onSuggestionPress,
}: Props) {
  const memoryText = formatMemoryOpenerText(memoryOpener);
  const showMemory = memoryOpener.length > 0 && memoryText.length > 0;
  const greeting = greetingForHour(new Date().getHours());

  return (
    <View style={styles.container}>
      {/* 轻量问候块：纯客户端 Date，压下卡片，给屏更有构图感。 */}
      <View style={styles.greeting}>
        <Text style={txt.greetingHi} numberOfLines={1}>{greeting}</Text>
        <Text style={txt.greetingSub} numberOfLines={1}>今天想从哪里开始？</Text>
      </View>

      {showMemory && (
        <Pressable
          style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
          onPress={onOpenMemory}
          accessibilityRole="button"
          accessibilityLabel="查看和校准 AI 记忆"
        >
          <View style={styles.cardEyebrowRow}>
            <View style={styles.eyebrowLead}>
              <Ionicons name="bookmark-outline" size={12} color={C.green500} />
              <Text style={txt.eyebrow}>记忆线索</Text>
            </View>
            <Text style={txt.eyebrowAction}>校准</Text>
          </View>
          <Text style={txt.memoryBody} numberOfLines={2}>
            {memoryText}
          </Text>
        </Pressable>
      )}

      {opener && (
        <OpenerCard opener={opener} onQuickReply={onOpenerQuickReply} />
      )}

      <View style={styles.card}>
        <View style={styles.cardEyebrowRow}>
          <View style={styles.eyebrowLead}>
            <Ionicons name="sparkles" size={12} color={C.green500} />
            <Text style={txt.eyebrow} numberOfLines={1}>
              阿衡 · {opener ? '或者问我别的' : '会带上你的健康上下文'}
            </Text>
          </View>
        </View>
        <View style={styles.sugGrid}>
          {suggestions.map((s, position) => (
            <TouchableOpacity
              key={s.text}
              style={styles.sugChip}
              onPress={() => onSuggestionPress(s, position)}
              activeOpacity={0.72}
              accessibilityRole="button"
              accessibilityLabel={`向阿衡提问: ${s.text}`}
            >
              <Ionicons name={s.icon} size={13} color={C.green500} />
              <Text style={txt.sugChipText} numberOfLines={1}>{s.text}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
    </View>
  );
}

// Reva 卡片语言: surface + hairline + r-lg + 软阴影; 统一 eyebrow (11px ink3 bold).
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
  card: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s3,
    ...revaShadows.sm,
  },
  cardPressed: { opacity: 0.72 },
  cardEyebrowRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: revaSpacing.s2,
  },
  eyebrowLead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    flexShrink: 1,
    minWidth: 0,
  },
  sugGrid: {
    width: '100%',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  sugChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    maxWidth: '100%',
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
  eyebrow: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink3,
    fontWeight: '700',
    flexShrink: 1,
  } as TextStyle,
  eyebrowAction: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.green500,
    fontWeight: '700',
  } as TextStyle,
  memoryBody: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink2,
    lineHeight: 18,
  } as TextStyle,
  sugChipText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink1,
    fontWeight: '600',
    flexShrink: 1,
  } as TextStyle,
};
