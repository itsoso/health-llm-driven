/**
 * InsightCard — 今日洞察卡 (从"管你"到"懂你")
 *
 * 展示 Memory KG + 时序数据挖出的跨事件 pattern.
 * 底部"有用 / 不对" 反馈 → 后台写入 user_feedback 用于 Trust Loop.
 */
import React, { useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useTodayInsight, useInsightFeedback } from '../../hooks/useInsights';
import { spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
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

function severityToTokens(sev: string, c: ColorPalette) {
  if (sev === 'medium') return { color: c.amber, tint: c.tintAmber };
  if (sev === 'low')    return { color: '#0A84FF', tint: c.tintBlue };
  return { color: c.brand, tint: c.brandLight };
}

export default function InsightCard() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { data: insight, isLoading } = useTodayInsight();
  const feedbackMut = useInsightFeedback();

  if (isLoading || !insight) return null;

  const iconName = KIND_ICON[insight.kind] ?? 'bulb-outline';
  const sev = severityToTokens(insight.severity, c);
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
      iconTint={sev.tint}
      iconColor={sev.color}
      kicker={`今日洞察 · ${kindLabel}`}
      title={insight.title}
      collapsible
      defaultCollapsed
    >
      <Text style={styles.body}>{insight.body}</Text>
      {!!cite && (
        <View style={styles.citeRow}>
          <Ionicons name="information-circle-outline" size={11} color={c.labelTertiary} />
          <Text style={styles.cite}>{cite}</Text>
        </View>
      )}

      <View style={styles.feedbackBar}>
        {hasFeedback ? (
          <View style={styles.feedbackDoneRow}>
            <Ionicons name="checkmark-circle" size={14} color={c.green} />
            <Text style={styles.feedbackDoneText}>
              已反馈: {
                insight.user_feedback === 'helpful' ? '有用' :
                insight.user_feedback === 'not_helpful' ? '不对' :
                insight.user_feedback === 'already_knew' ? '我知道' : '不相关'
              }
            </Text>
          </View>
        ) : (
          <>
            <Text style={styles.feedbackPrompt}>这个洞察对你有用吗?</Text>
            <View style={styles.btnRow}>
              <TouchableOpacity
                style={[styles.btn, styles.btnHelpful]}
                onPress={() => handleFeedback('helpful')}
                accessibilityLabel="觉得有用"
              >
                <Ionicons name="thumbs-up-outline" size={14} color={c.brand} />
                <Text style={[styles.btnText, { color: c.brand }]}>有用</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.btn, styles.btnNeutral]}
                onPress={() => handleFeedback('already_knew')}
                accessibilityLabel="我早就知道"
              >
                <Text style={[styles.btnText, { color: c.labelSecondary }]}>我知道</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.btn, styles.btnNo]}
                onPress={() => handleFeedback('not_helpful')}
                accessibilityLabel="不对"
              >
                <Ionicons name="thumbs-down-outline" size={14} color={c.red} />
                <Text style={[styles.btnText, { color: c.red }]}>不对</Text>
              </TouchableOpacity>
            </View>
          </>
        )}
      </View>
    </DashboardCard>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    body: { fontSize: 13, color: c.labelSecondary, lineHeight: 20 } as TextStyle,
    citeRow: {
      flexDirection: 'row', alignItems: 'center', gap: 4,
      backgroundColor: c.bgPrimary,
      paddingHorizontal: 8, paddingVertical: 6, borderRadius: 8,
    },
    cite: { flex: 1, fontSize: 11, color: c.labelTertiary, fontStyle: 'italic' as const } as TextStyle,
    feedbackBar: {
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: c.separator,
      paddingTop: spacing.sm,
      gap: 6,
    },
    feedbackPrompt: { fontSize: 12, color: c.labelTertiary } as TextStyle,
    btnRow: { flexDirection: 'row', gap: 6 },
    btn: {
      flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4,
      paddingVertical: 8, borderRadius: 8, borderWidth: StyleSheet.hairlineWidth,
    },
    btnHelpful: { borderColor: c.brand, backgroundColor: c.brandLight },
    btnNeutral: { borderColor: c.separator, backgroundColor: c.bgPrimary },
    btnNo:      { borderColor: `${c.red}44`, backgroundColor: c.tintRed },
    btnText: { fontSize: 12, fontWeight: '600' as const } as TextStyle,
    feedbackDoneRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 4 },
    feedbackDoneText: { fontSize: 12, color: c.labelSecondary } as TextStyle,
  });
}
