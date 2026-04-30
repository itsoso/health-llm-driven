/**
 * InsightCard — 今日洞察卡 (从"管你"到"懂你")
 *
 * 展示 Memory KG + 时序数据挖出的跨事件 pattern.
 * 底部"有用 / 不对" 反馈 → 后台写入 user_feedback 用于 Trust Loop.
 */
import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, LayoutAnimation, Platform, UIManager,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { useTodayInsight, useInsightFeedback } from '../../hooks/useInsights';
import { colors, spacing, radii, shadows } from '../../constants/theme';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const KIND_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  gene_pgx: 'flask-outline',
  lab_trend: 'trending-up-outline',
  hrv_pattern: 'pulse-outline',
  profile_summary: 'person-circle-outline',
};

const SEV_COLOR: Record<string, string> = {
  info: colors.labelTertiary,
  low: colors.blue,
  medium: colors.amber,
};

const KIND_LABEL: Record<string, string> = {
  gene_pgx: '基因 × 用药',
  lab_trend: '化验趋势',
  hrv_pattern: 'HRV 模式',
  profile_summary: '健康画像',
};

export default function InsightCard() {
  const { data: insight, isLoading } = useTodayInsight();
  const feedbackMut = useInsightFeedback();
  const [expanded, setExpanded] = useState(false);

  if (isLoading || !insight) {
    return null;  // 无数据不占位, 避免首页噪声
  }

  const iconName = KIND_ICON[insight.kind] ?? 'bulb-outline';
  const sevColor = SEV_COLOR[insight.severity] ?? colors.labelTertiary;
  const kindLabel = KIND_LABEL[insight.kind] ?? insight.kind;
  const hasFeedback = !!insight.user_feedback;
  const cite = (insight.evidence && insight.evidence.cite) as string | undefined;

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpanded(!expanded);
    if (!expanded) {
      Haptics.selectionAsync();
    }
  };

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
    <View style={styles.card}>
      <TouchableOpacity activeOpacity={0.7} onPress={toggle}>
        <View style={styles.header}>
          <View style={[styles.iconBox, { backgroundColor: `${sevColor}18` }]}>
            <Ionicons name={iconName} size={18} color={sevColor} />
          </View>
          <View style={styles.headerMain}>
            <View style={styles.kindChipRow}>
              <Text style={styles.kindLabel}>🧠 今日洞察 · {kindLabel}</Text>
            </View>
            <Text style={styles.title} numberOfLines={expanded ? undefined : 2}>
              {insight.title}
            </Text>
          </View>
          <Ionicons
            name={expanded ? 'chevron-up' : 'chevron-down'}
            size={18}
            color={colors.labelTertiary}
          />
        </View>

        {expanded && (
          <View style={styles.bodyWrap}>
            <Text style={styles.body}>{insight.body}</Text>
            {!!cite && (
              <View style={styles.citeRow}>
                <Ionicons name="information-circle-outline" size={11} color={colors.labelTertiary} />
                <Text style={styles.cite}>{cite}</Text>
              </View>
            )}
          </View>
        )}
      </TouchableOpacity>

      {expanded && (
        <View style={styles.feedbackBar}>
          {hasFeedback ? (
            <View style={styles.feedbackDone}>
              <Ionicons name="checkmark-circle" size={14} color={colors.green} />
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
                  <Ionicons name="thumbs-up-outline" size={14} color={colors.brand} />
                  <Text style={[styles.btnText, { color: colors.brand }]}>有用</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.btn, styles.btnNeutral]}
                  onPress={() => handleFeedback('already_knew')}
                  accessibilityLabel="我早就知道"
                >
                  <Text style={[styles.btnText, { color: colors.labelSecondary }]}>我知道</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.btn, styles.btnNo]}
                  onPress={() => handleFeedback('not_helpful')}
                  accessibilityLabel="不对"
                >
                  <Ionicons name="thumbs-down-outline" size={14} color={colors.red} />
                  <Text style={[styles.btnText, { color: colors.red }]}>不对</Text>
                </TouchableOpacity>
              </View>
            </>
          )}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    marginHorizontal: spacing.lg,
    marginBottom: spacing.md,
    borderRadius: radii.lg,
    overflow: 'hidden',
    ...shadows.subtle,
  },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
    padding: spacing.md,
  },
  iconBox: {
    width: 36, height: 36, borderRadius: 18,
    justifyContent: 'center', alignItems: 'center',
  },
  headerMain: { flex: 1, gap: 2 },
  kindChipRow: { flexDirection: 'row', alignItems: 'center' },
  kindLabel: {
    fontSize: 11, fontWeight: '600' as const,
    color: colors.labelTertiary, letterSpacing: 0.2,
  },
  title: {
    fontSize: 15, fontWeight: '600' as const,
    color: colors.labelPrimary, lineHeight: 20,
  },

  bodyWrap: {
    paddingHorizontal: spacing.md, paddingBottom: spacing.sm,
    gap: spacing.sm,
  },
  body: { fontSize: 13, color: colors.labelSecondary, lineHeight: 20 },

  citeRow: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: colors.bgPrimary,
    paddingHorizontal: 8, paddingVertical: 6, borderRadius: 8,
  },
  cite: { flex: 1, fontSize: 11, color: colors.labelTertiary, fontStyle: 'italic' as const },

  feedbackBar: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separator,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, gap: 6,
  },
  feedbackPrompt: { fontSize: 12, color: colors.labelTertiary },
  btnRow: { flexDirection: 'row', gap: 6 },
  btn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4,
    paddingVertical: 8, borderRadius: 8, borderWidth: StyleSheet.hairlineWidth,
  },
  btnHelpful: { borderColor: colors.brand, backgroundColor: colors.brandLight },
  btnNeutral: { borderColor: colors.separator, backgroundColor: colors.bgPrimary },
  btnNo: { borderColor: `${colors.red}44`, backgroundColor: colors.tintRed },
  btnText: { fontSize: 12, fontWeight: '600' as const },

  feedbackDone: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingVertical: 4,
  },
  feedbackDoneText: { fontSize: 12, color: colors.labelSecondary },
});
