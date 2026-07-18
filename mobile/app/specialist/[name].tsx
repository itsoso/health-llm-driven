/**
 * Specialist Scorecard Detail
 *
 * Task 7: 近 30 天某 specialist 的所有 ActionCard + 评分详情.
 * 从 Home SpecialistChipRow 点击进入.
 */
import React, { useEffect, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { useSpecialistScorecard } from '../../hooks/useSpecialistScorecard';
import { specialistLabel } from '../../services/personalOutcome';
import type { ScorecardCard } from '../../services/specialistScorecard';
import { emitClientEvent } from '../../services/clientEvents';
import { spacing, radii, typography } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import AgentFeedbackLink from '../../components/agent/AgentFeedbackLink';
import { createSpecialistScorecardAgentContext } from '../../utils/agentContext';

function scoreColor(score: number, c: ColorPalette): string {
  if (score >= 70) return c.green;
  if (score >= 40) return c.amber;
  return c.red;
}

function CardRow({ card, c }: { card: ScorecardCard; c: ColorPalette }) {
  const styles = useMemo(() => createCardStyles(c), [c]);
  const graded = card.accuracy_score !== null;

  return (
    <View style={styles.card}>
      <Text style={styles.title} numberOfLines={2}>
        {card.title}
      </Text>

      {graded ? (
        <View style={styles.metricsRow}>
          {card.target_value && (
            <Text style={styles.metric}>目标 {card.target_value}</Text>
          )}
          {card.actual_value && (
            <Text style={styles.metric}>实际 {card.actual_value}</Text>
          )}
          <Text style={[styles.score, { color: scoreColor(card.accuracy_score!, c) }]}>
            {card.accuracy_score}/100
          </Text>
        </View>
      ) : (
        <Text style={styles.pending}>
          {card.score_status === 'clinician_review' ? '需临床复核' : '等待评分'}
        </Text>
      )}

      {card.why_short && <Text style={styles.why}>{card.why_short}</Text>}
    </View>
  );
}

export default function SpecialistScorecardScreen() {
  const { name } = useLocalSearchParams<{ name: string }>();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const router = useRouter();
  const specialistName = typeof name === 'string' ? name : null;

  if (!specialistName) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <Stack.Screen options={{ title: '专家成绩单', headerBackTitle: '返回' }} />
        <View style={styles.center}>
          <Text style={styles.errorTitle}>specialist 未知</Text>
          <Text style={styles.errorHint}>这个链接缺少专家名称，不能加载成绩单。</Text>
          <TouchableOpacity style={styles.retryBtn} onPress={() => router.back()}>
            <Text style={styles.retryText}>返回</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return <SpecialistScorecardContent name={specialistName} />;
}

function SpecialistScorecardContent({ name }: { name: string }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const { data, isLoading, isError, error, isRefetching, refetch } = useSpecialistScorecard(name, 30);
  const label = specialistLabel(name);

  // Task 9: 埋点 — 每次 mount 发 specialist_scorecard_entered, 看板算进入率
  useEffect(() => {
    if (name) {
      emitClientEvent('specialist_scorecard_entered', { specialist: name });
    }
  }, [name]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ title: `${label} 成绩单`, headerBackTitle: '返回' }} />

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl
            refreshing={isRefetching}
            onRefresh={refetch}
            tintColor={c.brand}
          />
        }
      >
        {isLoading && (
          <View style={styles.center}>
            <ActivityIndicator size="large" color={c.brand} />
          </View>
        )}

        {!isLoading && isError && (
          <View style={styles.center}>
            <Text style={styles.errorTitle}>
              加载失败: {(error as Error)?.message ?? '网络问题'}
            </Text>
            <TouchableOpacity style={styles.retryBtn} onPress={() => refetch()}>
              <Text style={styles.retryText}>重试</Text>
            </TouchableOpacity>
          </View>
        )}

        {data && (
          <>
            <View style={styles.summary}>
              <Text style={styles.h1}>{label}</Text>
              <Text style={styles.stat}>
                近 {data.window_days} 天: {data.proposed_count} 条建议 · {data.graded_count} 条评分
              </Text>
              <Text style={styles.stat}>
                评分覆盖 {Math.round(data.grading_coverage * 100)}%
                {data.clinical_review_count > 0 ? ` · ${data.clinical_review_count} 条需临床复核` : ''}
              </Text>
              {data.avg_accuracy !== null && (
                <Text style={styles.stat}>
                  平均命中度{' '}
                  <Text style={[styles.avgScore, { color: scoreColor(data.avg_accuracy, c) }]}>
                    {data.avg_accuracy}
                  </Text>{' '}
                  / 100
                </Text>
              )}
            </View>

            <AgentFeedbackLink
              label="跟小巴复盘这个专家建议"
              accessibilityLabel="跟小巴复盘这个专家建议"
              prompt={`请基于${label}方向近 30 天可归因建议的成绩单，分析哪些建议有效、哪些偏离，并给出下一轮建议应如何调整。需要临床复核的指标不做自动有效性判断。`}
              context={createSpecialistScorecardAgentContext({ label, data: data as any })}
              badge={data.hit_rate === null ? `${label}暂无可归因评分` : `${label}命中率 ${data.hit_rate.toFixed(0)}%`}
              style={styles.agentLink}
            />

            {data.cards.length === 0 ? (
              <View style={styles.empty}>
                <Text style={styles.emptyTitle}>还没有评分数据</Text>
                <Text style={styles.emptyHint}>
                  评分由 outcome_grader 在建议的 check_back_date 自动生成.
                  {'\n'}
                  新产的建议需等到检查日 (通常 3-14 天) 后才会出现结果.
                </Text>
              </View>
            ) : (
              data.cards.map((card) => <CardRow key={card.id} card={card} c={c} />)
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    scroll: { padding: spacing.md, paddingBottom: 80 },
    center: { paddingVertical: 40, alignItems: 'center' },
    errorTitle: {
      fontSize: typography.bodyMedium.fontSize,
      fontWeight: '600' as const,
      color: c.labelPrimary,
      marginBottom: spacing.xs,
    },
    errorHint: {
      fontSize: typography.bodySmall.fontSize,
      color: c.labelSecondary,
      textAlign: 'center',
      marginBottom: spacing.md,
    },
    retryBtn: {
      paddingHorizontal: spacing.lg,
      paddingVertical: spacing.sm,
      borderRadius: radii.sm,
      backgroundColor: c.brand,
      marginTop: spacing.sm,
    },
    retryText: {
      color: '#fff',
      fontSize: typography.bodySmall.fontSize,
      fontWeight: '600' as const,
    },
    summary: {
      backgroundColor: c.bgCard,
      borderRadius: radii.md,
      padding: spacing.md,
      marginBottom: spacing.md,
    },
    agentLink: { marginBottom: spacing.md },
    h1: {
      fontSize: typography.titleMedium.fontSize,
      fontWeight: '700' as const,
      color: c.labelPrimary,
    },
    stat: {
      marginTop: 4,
      fontSize: typography.bodyMedium.fontSize,
      color: c.labelSecondary,
    },
    avgScore: { fontWeight: '700' as const },
    empty: { padding: spacing.xl, alignItems: 'center' },
    emptyTitle: {
      fontSize: typography.bodyMedium.fontSize,
      fontWeight: '600' as const,
      color: c.labelPrimary,
      marginBottom: spacing.xs,
    },
    emptyHint: {
      fontSize: typography.bodySmall.fontSize,
      color: c.labelSecondary,
      textAlign: 'center',
      lineHeight: 18,
    },
  });
}

function createCardStyles(c: ColorPalette) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard,
      padding: spacing.md,
      borderRadius: radii.md,
      marginBottom: spacing.sm,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    },
    title: {
      fontSize: typography.bodyMedium.fontSize,
      fontWeight: '600' as const,
      color: c.labelPrimary,
      marginBottom: 6,
    },
    metricsRow: {
      flexDirection: 'row',
      alignItems: 'center',
      flexWrap: 'wrap',
      gap: 12,
    },
    metric: {
      fontSize: typography.bodySmall.fontSize,
      color: c.labelSecondary,
    },
    score: {
      fontWeight: '700' as const,
      fontSize: typography.bodyMedium.fontSize,
    },
    pending: {
      fontSize: typography.bodySmall.fontSize,
      color: c.labelTertiary,
      fontStyle: 'italic',
    },
    why: {
      marginTop: 6,
      fontSize: typography.bodySmall.fontSize,
      color: c.labelSecondary,
      lineHeight: 18,
    },
  });
}
