import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import type { useTodayTimeline } from '../../hooks/useTodayTimeline';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

type TimelineData = ReturnType<typeof useTodayTimeline>['data'];

// 今日简报条副标题：只消费后端 timeline 的真实计数。都没有 → 中性占位（不编造指标）。
export function buildBriefingSummary(timeline: TimelineData | undefined): string {
  if (!timeline) return '查看今日待办与身体信号';
  const actionable = Math.max(0, Math.round(timeline.counts?.actionable ?? 0));
  const completed = Math.max(0, Math.round(timeline.past?.completed_count ?? 0));
  const parts: string[] = [];
  if (actionable > 0) parts.push(`${actionable} 项待办`);
  if (completed > 0) parts.push(`${completed} 项已完成`);
  if (parts.length === 0) return '今天暂无待办 · 查看身体信号';
  return parts.join(' · ');
}

/**
 * 今日简报条(agent-native:不跳独立页)。默认 onPress 在对话页内联展开「今日」
 * 动态 UI 面板(由 chat.tsx 传入 toggle + expanded);未传 onPress 时回退旧的
 * 原生半屏 sheet 导航(向后兼容)。数字来自 /timeline/today 真实计数。
 */
export default function BriefingStrip({
  timeline,
  onDismiss,
  onPress,
  expanded = false,
}: {
  timeline: TimelineData | undefined;
  onDismiss?: () => void;
  onPress?: () => void;
  expanded?: boolean;
}) {
  const briefingSummary = buildBriefingSummary(timeline);
  return (
    <TouchableOpacity
      style={[styles.briefingStrip, expanded && styles.briefingStripExpanded]}
      onPress={onPress ?? (() => router.navigate('/today-sheet' as any))}
      activeOpacity={0.75}
      accessibilityRole="button"
      accessibilityState={{ expanded }}
      accessibilityLabel={`今日简报：${briefingSummary}`}
      accessibilityHint={expanded ? '收起今日面板，回到对话' : '在对话内展开今日待办、身体信号与未来节奏'}
    >
      <View style={styles.briefingIconWrap}>
        <Ionicons name="today-outline" size={15} color={C.green500} />
      </View>
      <View style={styles.briefingTextWrap}>
        <Text maxFontSizeMultiplier={1.2} style={txt.briefingLabel}>今日简报</Text>
        <Text maxFontSizeMultiplier={1.2} style={txt.briefingSummary} numberOfLines={1}>
          {briefingSummary}
        </Text>
      </View>
      <Ionicons name={expanded ? 'chevron-down' : 'chevron-forward'} size={16} color={C.ink3} />
      {onDismiss ? (
        <TouchableOpacity
          onPress={onDismiss}
          hitSlop={10}
          style={styles.briefingDismiss}
          accessibilityRole="button"
          accessibilityLabel="关闭今日简报"
          accessibilityHint="隐藏这条简报，可从今日屏查看完整内容"
        >
          <Ionicons name="close" size={15} color={C.ink3} />
        </TouchableOpacity>
      ) : null}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  briefingStrip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: revaSpacing.s2,
    marginHorizontal: revaSpacing.s3,
    marginTop: 2,
    marginBottom: 4,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: 8,
    borderRadius: revaRadii.lg,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    ...revaShadows.sm,
  },
  briefingStripExpanded: {
    borderColor: C.green500,
    backgroundColor: C.green50,
  },
  briefingIconWrap: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  briefingTextWrap: {
    flex: 1,
    minWidth: 0,
  },
  briefingDismiss: {
    width: 26,
    height: 26,
    borderRadius: 13,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 2,
    backgroundColor: C.paper2,
  },
});

const txt = {
  briefingLabel: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '700', color: C.ink3 } as TextStyle,
  briefingSummary: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '700', color: C.ink1, marginTop: 1 } as TextStyle,
};
