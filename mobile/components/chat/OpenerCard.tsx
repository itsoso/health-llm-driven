/**
 * OpenerCard — Chat 起手"未读续接" 卡片.
 *
 * P1 (2026-05-04 产品规划): 用户每天发 22 条对话, 但 22 个 query 都是独立 ad-hoc.
 * 这张卡是 "AI 主动续接" 的物理体现 —— 进 chat 看到的不是空白 + 4 个泛泛 chip,
 * 而是 AI 拿当前 trust loop 状态 / anomaly / case / memory 主动开场.
 *
 * 设计要点:
 * - 视觉: 半透明 brand 色背景 + sparkles 图标 + 圆角, 让用户认出"这是 AI 主动说的"
 * - 交互: 点 quick reply chip = 一键发送回复; 点 deep_link icon = 跳目标页
 * - 退化: opener 为 null → 不渲染, 让 ListEmptyComponent 走默认 SUGGESTIONS
 */
import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import type { ConversationOpener } from '../../services/conversationOpener';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface Props {
  opener: ConversationOpener;
  onQuickReply: (text: string) => void;
}

export default function OpenerCard({ opener, onQuickReply }: Props) {
  const { c, isDark } = useTheme();
  const router = useRouter();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const onCardPress = () => {
    if (opener.deep_link) {
      try {
        router.push(opener.deep_link as any);
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
        accessibilityLabel={`AI 主动续接: ${opener.text}`}
      >
        <View style={styles.iconWrap}>
          <Ionicons name="sparkles" size={14} color={c.brand} />
        </View>
        <View style={styles.textWrap}>
          <Text style={txt.body}>{opener.text}</Text>
        </View>
        {opener.deep_link ? (
          <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
        ) : null}
      </Pressable>

      {opener.quick_replies.length > 0 ? (
        <View style={styles.chipsRow}>
          {opener.quick_replies.map(reply => (
            <Pressable
              key={reply}
              style={({ pressed }) => [styles.chip, pressed && styles.chipPressed]}
              onPress={() => onQuickReply(reply)}
              accessibilityRole="button"
              accessibilityLabel={`一键回复: ${reply}`}
            >
              <Text style={txt.chip}>{reply}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
    </View>
  );
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    wrap: {
      paddingHorizontal: spacing.lg,
      paddingTop: spacing.lg,
      gap: spacing.sm,
    },
    card: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.sm,
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm + 2,
      backgroundColor: c.brandLight,
      borderRadius: radii.md,
      borderWidth: isDark ? StyleSheet.hairlineWidth : 0,
      borderColor: c.fill,
    },
    cardPressed: { opacity: 0.7 },
    iconWrap: {
      width: 24, height: 24, borderRadius: 12,
      backgroundColor: c.bgPrimary,
      alignItems: 'center', justifyContent: 'center',
    },
    textWrap: { flex: 1 },
    chipsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
    chip: {
      paddingHorizontal: spacing.md,
      paddingVertical: 6,
      backgroundColor: c.bgCard,
      borderRadius: radii.full,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.fill,
    },
    chipPressed: { opacity: 0.6 },
  });
}

function createTxt(c: ColorPalette) {
  return {
    body: {
      fontSize: 14,
      lineHeight: 20,
      color: c.labelPrimary,
      fontWeight: '500',
    } as TextStyle,
    chip: {
      fontSize: 13,
      color: c.labelPrimary,
    } as TextStyle,
  };
}
