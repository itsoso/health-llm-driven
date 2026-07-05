/**
 * OpenerCard — Chat 起手"未读续接" 卡片.
 *
 * P1 (2026-05-04 产品规划): 用户每天发 22 条对话, 但 22 个 query 都是独立 ad-hoc.
 * 这张卡是 "AI 主动续接" 的物理体现 —— 进 chat 看到的不是空白 + 4 个泛泛 chip,
 * 而是 AI 拿当前 trust loop 状态 / anomaly / case / memory 主动开场.
 *
 * 设计要点:
 * - 视觉: surface 卡 + green accent + sparkles 图标 + 圆角, 让用户认出"这是 AI 主动说的"
 * - 交互: 点 quick reply chip = 一键发送回复; 点 deep_link icon = 跳目标页
 * - 退化: opener 为 null → 不渲染, 让 ListEmptyComponent 走默认 SUGGESTIONS
 */
import React from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import type { ConversationOpener } from '../../services/conversationOpener';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';
import { normalizeHealthActionRoute } from '../../utils/dailyArtifactNavigation';

interface Props {
  opener: ConversationOpener;
  onQuickReply: (text: string) => void;
}

const RAW_METRIC_LABELS: Record<string, string> = {
  spo2_avg: '血氧饱和度',
  sleep_score: '睡眠评分',
  resting_hr: '静息心率',
  hrv_avg: 'HRV',
};

export function formatOpenerText(text: string): string {
  let next = (text || '').trim();
  Object.entries(RAW_METRIC_LABELS).forEach(([key, label]) => {
    next = next.replace(new RegExp(`\\[${key}\\]\\s*${label}`, 'gi'), label);
    next = next.replace(new RegExp(`\\[${key}\\]\\s*`, 'gi'), `${label}`);
  });
  return next.replace(/\s+/g, ' ');
}

export function formatQuickReplyLabel(reply: string): string {
  if (/没做|未做|没有做|不算/.test(reply)) return '未完成';
  if (/做到|完成|已做|做了/.test(reply)) return '完成了';
  if (/调整|计划/.test(reply)) return '调整计划';
  return reply.replace(/[✅❌]/g, '').trim();
}

function quickReplyIcon(reply: string): keyof typeof Ionicons.glyphMap {
  if (/没做|未做|没有做|不算/.test(reply)) return 'close-circle-outline';
  if (/做到|完成|已做|做了/.test(reply)) return 'checkmark-circle-outline';
  if (/调整|计划/.test(reply)) return 'repeat-outline';
  return 'chatbubble-ellipses-outline';
}

function sourceLabel(source: ConversationOpener['source']): string {
  if (source === 'action_card_due') return '今日回访';
  if (source === 'anomaly') return '需要留意';
  if (source === 'case_thread') return '继续跟进';
  if (source === 'memory_fact') return '基于近期记录';
  return '主动提醒';
}

export default function OpenerCard({ opener, onQuickReply }: Props) {
  const router = useRouter();
  const openerText = formatOpenerText(opener.text);

  const onCardPress = () => {
    if (opener.deep_link) {
      try {
        const route = normalizeHealthActionRoute(opener.deep_link, openerText);
        if (route) router.push(route as any);
      } catch {
        /* invalid path — fall through silently */
      }
    }
  };

  return (
    <View style={styles.wrap}>
      <Pressable
        onPress={onCardPress}
        disabled={!opener.deep_link}
        style={({ pressed }) => [
          styles.card,
          pressed && opener.deep_link ? styles.cardPressed : null,
        ]}
        accessibilityRole={opener.deep_link ? 'button' : undefined}
        accessibilityLabel={`AI 主动续接: ${openerText}`}
      >
        <View style={styles.accent} />
        <View style={styles.textWrap}>
          <View style={styles.cardHeader}>
            <View style={styles.sourcePill}>
              <Ionicons name="sparkles" size={11} color={C.green500} />
              <Text style={txt.source}>{sourceLabel(opener.source)}</Text>
            </View>
          </View>
          <Text style={txt.body}>{openerText}</Text>
        </View>
        {opener.deep_link ? (
          <View style={styles.chevronWrap}>
            <Ionicons name="chevron-forward" size={15} color={C.ink3} />
          </View>
        ) : null}
      </Pressable>

      {opener.quick_replies.length > 0 ? (
        <View style={styles.chipsRow}>
          {opener.quick_replies.map(reply => (
            <Pressable
              key={reply.text}
              style={({ pressed }) => [styles.chip, pressed && styles.chipPressed]}
              onPress={() => onQuickReply(reply.text)}
              accessibilityRole="button"
              accessibilityLabel={`一键回复: ${reply.text}`}
            >
              <Ionicons name={quickReplyIcon(reply.text)} size={14} color={C.ink2} />
              <Text style={txt.chip}>{formatQuickReplyLabel(reply.text)}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    paddingHorizontal: revaSpacing.s4,
    paddingTop: revaSpacing.s4,
    gap: revaSpacing.s1,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'stretch',
    gap: revaSpacing.s2,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: revaSpacing.s3,
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  },
  cardPressed: { opacity: 0.7 },
  accent: {
    width: 3,
    borderRadius: 3,
    backgroundColor: C.green500,
    opacity: 0.75,
  },
  textWrap: { flex: 1 },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: revaSpacing.s1,
  },
  sourcePill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
  },
  chevronWrap: {
    alignSelf: 'center',
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.paper,
  },
  chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: revaSpacing.s1, paddingLeft: revaSpacing.s2 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: revaSpacing.s2 + 2,
    paddingVertical: 6,
    backgroundColor: C.surface,
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  chipPressed: { opacity: 0.6 },
});

const txt = {
  source: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.green500,
    fontWeight: '700',
  } as TextStyle,
  body: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    lineHeight: 21,
    color: C.ink1,
    fontWeight: '600',
  } as TextStyle,
  chip: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    color: C.ink2,
    fontWeight: '600',
  } as TextStyle,
};
