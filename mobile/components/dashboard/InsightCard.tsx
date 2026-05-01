/**
 * InsightCard — 今日洞察卡 (从"管你"到"懂你")
 *
 * 展示 Memory KG + 时序数据挖出的跨事件 pattern.
 * 底部"有用 / 不对" 反馈 → 后台写入 user_feedback 用于 Trust Loop.
 */
import React from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useTodayInsight, useInsightFeedback } from '../../hooks/useInsights';
import { colors, spacing } from '../../constants/theme';
import DashboardCard from './DashboardCard';

const KIND_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  gene_pgx: 'flask-outline',
  lab_trend: 'trending-up-outline',
  hrv_pattern: 'pulse-outline',
  profile_summary: 'person-circle-outline',
};

const KIND_LABEL: Record<string, string> = {
  gene_pgx: '基因 × 用药',
  lab_trend: '化验趋势',
  hrv_pattern: 'HRV 模式',
  profile_summary: '健康画像',
};

// 严重度只决定 icon 颜色, 不再像旧版那样喧宾夺主
const SEV_COLOR: Record<string, string> = {
  info: colors.brand,
  low: colors.blue,
  medium: colors.amber,
};
const SEV_TINT: Record<string, string> = {
  info: colors.brandLight,
  low: colors.tintBlue,
  medium: colors.tintAmber,
};

export default function InsightCard() {
  const { data: insight, isLoading } = useTodayInsight();
  const feedbackMut = useInsightFeedback();

  if (isLoading || !insight) return null;  // 无数据不占位

  const iconName = KIND_ICON[insight.kind] ?? 'bulb-outline';
  const sevColor = SEV_COLOR[insight.severity] ?? colors.brand;
  const sevTint = SEV_TINT[insight.severity] ?? colors.brandLight;
  const kindLabel = KIND_LABEL[insight.kind] ?? insight.kind;
  const hasFeedback = !!insight.user_feedback;
  const cite = (insight.evidence && insight.evidence.cite) as string | undefined;

  const handleFeedback = (feedback: 'helpful' | 'not_helpful' | 'already_knew') => {
    if (hasFeedback) return;
    Haptics.notificationAsync(
      feedback === 'helpful'
        ? Haptics.NotificationFeedbackType.Success
        : Haptics.NotificationFeedbackType.Warning,
    );
    feedbackMut.mutate({ id: insight.id, feedback });
  };

  return (
    <DashboardCard
      icon={iconName}
      iconTint={sevTint}
      iconColor={sevColor}
      kicker={`今日洞察 · ${kindLabel}`}
      kickerColor={colors.labelTertiary}
      title={insight.title}
      collapsible
      defaultCollapsed
    >
      <Text style={txt.body}>{insight.body}</Text>
      {!!cite && (
        <View style={styles.citeRow}>
          <Ionicons name="information-circle-outline" size={11} color={colors.labelTertiary} />
          <Text style={txt.cite}>{cite}</Text>
        </View>
      )}

      <View style={styles.feedbackBar}>
        {hasFeedback ? (
          <View style={styles.feedbackDone}>
            <Ionicons name="checkmark-circle" size={14} color={colors.green} />
            <Text style={txt.feedbackDone}>
              已反馈: {
                insight.user_feedback === 'helpful' ? '有用' :
                insight.user_feedback === 'not_helpful' ? '不对' :
                insight.user_feedback === 'already_knew' ? '我知道' : '不相关'
              }
            </Text>
          </View>
        ) : (
          <>
            <Text style={txt.feedbackPrompt}>这个洞察对你有用吗?</Text>
            <View style={styles.btnRow}>
              <TouchableOpacity
                style={[styles.btn, styles.btnHelpful]}
                onPress={() => handleFeedback('helpful')}
                accessibilityLabel="觉得有用"
              >
                <Ionicons name="thumbs-up-outline" size={14} color={colors.brand} />
                <Text style={[txt.btn, { color: colors.brand }]}>有用</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.btn, styles.btnNeutral]}
                onPress={() => handleFeedback('already_knew')}
                accessibilityLabel="我早就知道"
              >
                <Text style={[txt.btn, { color: colors.labelSecondary }]}>我知道</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.btn, styles.btnNo]}
                onPress={() => handleFeedback('not_helpful')}
                accessibilityLabel="不对"
              >
                <Ionicons name="thumbs-down-outline" size={14} color={colors.red} />
                <Text style={[txt.btn, { color: colors.red }]}>不对</Text>
              </TouchableOpacity>
            </View>
          </>
        )}
      </View>
    </DashboardCard>
  );
}

const styles = StyleSheet.create({
  citeRow: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: colors.bgPrimary,
    paddingHorizontal: 8, paddingVertical: 6, borderRadius: 8,
  },
  feedbackBar: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separator,
    paddingTop: spacing.sm,
    gap: 6,
  },
  btnRow: { flexDirection: 'row', gap: 6 },
  btn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4,
    paddingVertical: 8, borderRadius: 8, borderWidth: StyleSheet.hairlineWidth,
  },
  btnHelpful: { borderColor: colors.brand, backgroundColor: colors.brandLight },
  btnNeutral: { borderColor: colors.separator, backgroundColor: colors.bgPrimary },
  btnNo: { borderColor: `${colors.red}44`, backgroundColor: colors.tintRed },
  feedbackDone: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 4 },
});

const txt = {
  body: { fontSize: 13, color: colors.labelSecondary, lineHeight: 20 } as TextStyle,
  cite: { flex: 1, fontSize: 11, color: colors.labelTertiary, fontStyle: 'italic' as const } as TextStyle,
  feedbackPrompt: { fontSize: 12, color: colors.labelTertiary } as TextStyle,
  btn: { fontSize: 12, fontWeight: '600' as const } as TextStyle,
  feedbackDone: { fontSize: 12, color: colors.labelSecondary } as TextStyle,
};
