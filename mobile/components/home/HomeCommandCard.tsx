/**
 * HomeCommandCard —— 今日 Tab 顶部主卡 (2026-05-26 简化重构).
 *
 * 紧凑两行布局:
 *   1. 今日判断 (warning/pulse 图标 + headline + chevron)
 *   2. 现在只做 (flask 图标 + actionText + 完成 / chevron)
 *
 * 之前 HomeCommandHeader 在同一张卡里塞了 4 层 (判断 + 依据 + 看结果 + 行动),
 * 用户反馈"信息密度过高"; 这里只保留判断 + 行动两条主轴.
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';

type CompletionState = 'idle' | 'sending' | 'completed' | 'error';

interface Props {
  agentJudgmentText: string;
  nextStepActionText: string;
  actionLeverLabel: string;
  refreshing: boolean;
  hasCritical: boolean;
  canComplete: boolean;
  completionState: CompletionState;
  onPressJudgment: () => void;
  onPressAction: () => void;
  onPressAgent: () => void;
  onPressComplete?: () => void;
}

function HomeText({
  maxFontSizeMultiplier = 1.18,
  ...rest
}: React.ComponentProps<typeof Text>) {
  return <Text maxFontSizeMultiplier={maxFontSizeMultiplier} {...rest} />;
}

export default function HomeCommandCard({
  agentJudgmentText,
  nextStepActionText,
  actionLeverLabel,
  refreshing,
  hasCritical,
  canComplete,
  completionState,
  onPressJudgment,
  onPressAction,
  onPressAgent,
  onPressComplete,
}: Props) {
  const { c, isDark } = useTheme();

  const judgmentColor = hasCritical ? c.red : c.brand;
  const judgmentTint = hasCritical ? c.tintRed : c.brandLight;
  const judgmentIcon: keyof typeof Ionicons.glyphMap = hasCritical
    ? 'warning'
    : 'pulse';

  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: c.bgCard,
          borderColor: c.separator,
        },
        isDark
          ? null
          : {
              shadowColor: '#000',
              shadowOffset: { width: 0, height: 2 },
              shadowOpacity: 0.05,
              shadowRadius: 6,
              elevation: 2,
            },
      ]}
    >
      <View style={styles.headerRow}>
        <View style={styles.headerLeft}>
          <View style={[styles.statusDot, { backgroundColor: c.brand }]} />
          <HomeText style={[styles.agentName, { color: c.labelPrimary }]}>
            阿衡
          </HomeText>
          <HomeText style={[styles.agentStatus, { color: c.labelTertiary }]}>
            · {refreshing ? '同步中' : '后台监测中'}
          </HomeText>
        </View>
        <Pressable
          onPress={onPressAgent}
          style={({ pressed }) => [
            styles.askPill,
            { backgroundColor: c.brandLight, opacity: pressed ? 0.72 : 1 },
          ]}
          accessibilityRole="button"
          accessibilityLabel="问阿衡原因"
        >
          <Ionicons
            name="chatbubble-ellipses-outline"
            size={12}
            color={c.brand}
          />
          <HomeText style={[styles.askPillText, { color: c.brand }]}>
            问原因
          </HomeText>
        </Pressable>
      </View>

      <Pressable
        testID="home-command-judgment"
        onPress={onPressJudgment}
        style={({ pressed }) => [
          styles.judgmentRow,
          {
            backgroundColor: c.bgPrimary,
            borderColor: c.separator,
            opacity: pressed ? 0.78 : 1,
          },
        ]}
        accessibilityRole="button"
        accessibilityLabel="打开今日判断"
      >
        <View
          style={[
            styles.judgmentIcon,
            { backgroundColor: judgmentTint },
          ]}
        >
          <Ionicons name={judgmentIcon} size={16} color={judgmentColor} />
        </View>
        <View style={styles.judgmentText}>
          <HomeText style={[styles.rowLabel, { color: judgmentColor }]}>
            今日判断
          </HomeText>
          <HomeText
            style={[styles.rowHeadline, { color: c.labelPrimary }]}
            numberOfLines={2}
          >
            {agentJudgmentText}
          </HomeText>
        </View>
        <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
      </Pressable>

      <Pressable
        testID="home-command-action"
        onPress={onPressAction}
        style={({ pressed }) => [
          styles.actionRow,
          {
            backgroundColor: c.brandLight,
            opacity: pressed ? 0.72 : 1,
          },
        ]}
        accessibilityRole="button"
        accessibilityLabel="打开下一步行动"
      >
        <View style={[styles.actionIcon, { backgroundColor: c.bgCard }]}>
          <Ionicons name="flask-outline" size={15} color={c.brand} />
        </View>
        <View style={styles.actionText}>
          <HomeText style={[styles.rowLabel, { color: c.brand }]}>
            {actionLeverLabel}
          </HomeText>
          <HomeText
            style={[styles.actionHeadline, { color: c.labelPrimary }]}
            numberOfLines={1}
          >
            {nextStepActionText}
          </HomeText>
        </View>
        {canComplete && onPressComplete ? (
          <Pressable
            onPress={onPressComplete}
            disabled={
              completionState === 'sending' ||
              completionState === 'completed'
            }
            hitSlop={6}
            style={({ pressed }) => [
              styles.doneButton,
              {
                backgroundColor:
                  completionState === 'completed'
                    ? c.tintGreen
                    : c.bgCard,
                borderColor:
                  completionState === 'completed' ? c.green : c.separator,
                opacity: pressed ? 0.72 : 1,
              },
            ]}
            accessibilityRole="button"
            accessibilityLabel="标记完成"
          >
            <Ionicons
              name={
                completionState === 'completed'
                  ? 'checkmark-circle'
                  : 'checkmark-circle-outline'
              }
              size={14}
              color={
                completionState === 'completed' ? c.green : c.labelSecondary
              }
            />
            <HomeText
              style={[
                styles.doneText,
                {
                  color:
                    completionState === 'completed'
                      ? c.green
                      : c.labelSecondary,
                },
              ]}
            >
              {completionState === 'sending'
                ? '记录中'
                : completionState === 'completed'
                  ? '已完成'
                  : '完成'}
            </HomeText>
          </Pressable>
        ) : (
          <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
        )}
      </Pressable>

      {completionState === 'error' ? (
        <View style={[styles.errorRow, { backgroundColor: c.tintRed }]}>
          <Ionicons name="alert-circle-outline" size={13} color={c.red} />
          <HomeText style={[styles.errorText, { color: c.red }]}>
            记录失败，请重试
          </HomeText>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.xl,
    borderWidth: StyleSheet.hairlineWidth,
    padding: spacing.md,
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xs,
    paddingTop: spacing.xs,
  },
  headerLeft: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  statusDot: { width: 7, height: 7, borderRadius: 3.5 },
  agentName: { fontSize: 13, fontWeight: '700' },
  agentStatus: { fontSize: 11, fontWeight: '500' },
  askPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 9,
    paddingVertical: 4,
    borderRadius: radii.full,
  },
  askPillText: { fontSize: 11, fontWeight: '700' },

  judgmentRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 10,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
  },
  judgmentIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  judgmentText: { flex: 1, gap: 2 },
  rowLabel: { fontSize: 11, fontWeight: '700' },
  rowHeadline: { fontSize: 14, fontWeight: '700', lineHeight: 19 },

  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 10,
    borderRadius: radii.lg,
  },
  actionIcon: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionText: { flex: 1, gap: 2 },
  actionHeadline: { fontSize: 13, fontWeight: '600' },

  doneButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 9,
    paddingVertical: 5,
    borderRadius: radii.full,
    borderWidth: StyleSheet.hairlineWidth,
  },
  doneText: { fontSize: 11, fontWeight: '700' },

  errorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 5,
    borderRadius: radii.md,
  },
  errorText: { fontSize: 11, fontWeight: '600' },
});
