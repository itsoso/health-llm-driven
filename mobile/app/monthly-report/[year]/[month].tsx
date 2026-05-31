import React, { useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextStyle, ScrollView,
  ActivityIndicator, RefreshControl, Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { spacing, radii, shadows } from '../../../constants/theme';
import { ColorPalette, useTheme } from '../../../hooks/useTheme';
import {
  getMonthlyReport, regenerateMonthlyReport, formatMonth, relativeTime,
  INTERVENTION_KIND_LABEL, DIRECTION_LABEL, DIRECTION_COLOR,
  type MonthlyReportDetail, type MetricTrend, type ScorecardCard,
} from '../../../services/monthlyReports';
import AgentFeedbackLink from '../../../components/agent/AgentFeedbackLink';
import { createMonthlyReportAgentContext } from '../../../utils/agentContext';

export default function MonthlyReportDetailScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const qc = useQueryClient();
  const params = useLocalSearchParams<{ year: string; month: string }>();
  const year = parseInt(params.year || '0', 10);
  const month = parseInt(params.month || '0', 10);

  const qk = ['monthlyReport', year, month];

  const { data, isLoading, isRefetching, refetch } = useQuery<MonthlyReportDetail>({
    queryKey: qk,
    queryFn: () => getMonthlyReport(year, month),
    enabled: year > 0 && month > 0,
    staleTime: 60_000,
  });

  const regenMut = useMutation({
    mutationFn: () => regenerateMonthlyReport(year, month),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: qk });
      qc.invalidateQueries({ queryKey: ['monthlyReports'] });
      Alert.alert('已重新生成', '报告已根据最新数据刷新');
    },
    onError: () => Alert.alert('失败', '重新生成失败，请稍后重试'),
  });

  if (isLoading || !data) {
    return (
      <SafeAreaView style={styles.safe} edges={['top']}>
        <View style={styles.center}>
          <ActivityIndicator color={c.brand} />
        </View>
      </SafeAreaView>
    );
  }

  const r = data.report;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>{formatMonth(year, month)} 复盘</Text>
        <TouchableOpacity
          onPress={() => regenMut.mutate()}
          style={styles.backBtn}
          disabled={regenMut.isPending}
        >
          {regenMut.isPending ? (
            <ActivityIndicator size="small" color={c.brand} />
          ) : (
            <Ionicons name="refresh" size={22} color={c.brand} />
          )}
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />
        }
      >
        <Text style={txt.generatedHint}>
          生成于 {relativeTime(data.generated_at)} · 覆盖 {r.coverage.covered_days}/{r.coverage.total_days} 天 · {r.coverage.pct.toFixed(0)}%
        </Text>

        <AgentFeedbackLink
          label="跟 Agent 复盘本月"
          accessibilityLabel="跟 Agent 复盘本月"
          prompt="请基于本月健康报告做一次月度复盘：总结有效和偏离的建议，解释关键指标变化，并给出下月优先行动安排。"
          context={createMonthlyReportAgentContext({ year, month, report: r } as any)}
          badge={`${formatMonth(year, month)}复盘`}
          style={styles.agentLink}
        />

        {r.narrative ? (
          <View style={styles.card}>
            <Text style={txt.sectionTitle}>本月小结</Text>
            <Text style={txt.narrative}>{r.narrative}</Text>
          </View>
        ) : null}

        {r.next_focus.length > 0 && (
          <View style={styles.card}>
            <Text style={txt.sectionTitle}>下月重点</Text>
            {r.next_focus.map((f, i) => (
              <View key={i} style={styles.bulletRow}>
                <View style={styles.bulletDot} />
                <Text style={txt.bulletText}>{f}</Text>
              </View>
            ))}
          </View>
        )}

        {r.metric_trends.length > 0 && (
          <>
            <Text style={txt.section}>指标趋势 (对比上月)</Text>
            <View style={styles.card}>
              {r.metric_trends.map((t, i) => (
                <TrendRow key={t.metric} trend={t} last={i === r.metric_trends.length - 1} styles={styles} txt={txt} />
              ))}
            </View>
          </>
        )}

        {r.ai_scorecard.overall.total_graded > 0 && (
          <>
            <Text style={txt.section}>AI 建议命中率</Text>
            <View style={styles.card}>
              <View style={styles.overallRow}>
                <View style={{ flex: 1 }}>
                  <Text style={txt.hitRateLabel}>本月命中率</Text>
                  <Text style={txt.hitRateValue}>
                    {r.ai_scorecard.overall.hit_rate.toFixed(0)}%
                  </Text>
                  <Text style={txt.hint}>
                    评分 {r.ai_scorecard.overall.total_graded} 条 · 高分 {r.ai_scorecard.overall.hit_count} · 低分 {r.ai_scorecard.overall.miss_count}
                  </Text>
                </View>
                <View style={styles.rateBar}>
                  <View style={[styles.rateBarFill, {
                    height: `${Math.min(100, r.ai_scorecard.overall.hit_rate)}%`,
                    backgroundColor: r.ai_scorecard.overall.hit_rate >= 60
                      ? '#34C759' : r.ai_scorecard.overall.hit_rate >= 30
                      ? '#FF9500' : '#FF3B30',
                  }]} />
                </View>
              </View>
            </View>

            {r.ai_scorecard.by_specialist.length > 0 && (
              <View style={styles.card}>
                <Text style={txt.sectionTitle}>各方向表现</Text>
                {r.ai_scorecard.by_specialist.map((sp) => (
                  <View key={sp.name} style={styles.spRow}>
                    <Text style={txt.spLabel}>{sp.label}</Text>
                    <View style={styles.spBar}>
                      <View style={[styles.spBarFill, {
                        width: `${Math.min(100, sp.hit_rate)}%`,
                        backgroundColor: sp.hit_rate >= 60 ? '#34C759'
                          : sp.hit_rate >= 30 ? '#FF9500' : '#FF3B30',
                      }]} />
                    </View>
                    <Text style={txt.spRate}>{sp.hit_rate.toFixed(0)}%</Text>
                    <Text style={txt.spCount}>({sp.total})</Text>
                  </View>
                ))}
              </View>
            )}

            {r.ai_scorecard.top_hits.length > 0 && (
              <View style={styles.card}>
                <Text style={txt.sectionTitle}>✅ 最贴合的建议</Text>
                {r.ai_scorecard.top_hits.map((card) => (
                  <CardRow key={card.card_id} card={card} good styles={styles} txt={txt} />
                ))}
              </View>
            )}

            {r.ai_scorecard.top_misses.length > 0 && (
              <View style={styles.card}>
                <Text style={txt.sectionTitle}>❌ 偏离较多的建议</Text>
                {r.ai_scorecard.top_misses.map((card) => (
                  <CardRow key={card.card_id} card={card} good={false} styles={styles} txt={txt} />
                ))}
              </View>
            )}
          </>
        )}

        {r.key_interventions.length > 0 && (
          <>
            <Text style={txt.section}>本月关键干预</Text>
            <View style={styles.card}>
              {r.key_interventions.map((iv, i) => (
                <View key={i} style={[
                  styles.ivRow,
                  i < r.key_interventions.length - 1 && styles.ivRowBorder,
                ]}>
                  <View style={styles.ivBadge}>
                    <Text style={txt.ivKind}>
                      {INTERVENTION_KIND_LABEL[iv.kind] || iv.kind}
                    </Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={txt.ivTitle}>{iv.title}</Text>
                    <Text style={txt.ivDate}>{iv.date}</Text>
                    {iv.detail ? <Text style={txt.ivDetail}>{iv.detail}</Text> : null}
                  </View>
                </View>
              ))}
            </View>
          </>
        )}

        {r.ai_scorecard.overall.total_graded === 0 && r.metric_trends.length === 0 && (
          <View style={styles.card}>
            <Text style={txt.empty}>本月数据较少，建议提高打卡与设备同步频率</Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function TrendRow({ trend, last, styles, txt }: {
  trend: MetricTrend; last: boolean;
  styles: ReturnType<typeof createStyles>; txt: ReturnType<typeof createTxt>;
}) {
  const color = DIRECTION_COLOR[trend.direction];
  const arrow = trend.direction === 'basically_flat' ? '→'
    : trend.delta > 0 ? '↑' : '↓';
  return (
    <View style={[styles.trendRow, !last && styles.trendRowBorder]}>
      <View style={{ flex: 1 }}>
        <Text style={txt.trendLabel}>{trend.label}</Text>
        <Text style={txt.trendValues}>
          {trend.prev !== null ? `${trend.prev} → ` : ''}
          <Text style={{ fontWeight: '600' }}>{trend.curr}</Text>
          {trend.unit}
        </Text>
      </View>
      <View style={{ alignItems: 'flex-end' }}>
        <Text style={[txt.trendArrow, { color }]}>
          {arrow} {DIRECTION_LABEL[trend.direction]}
        </Text>
        {trend.delta_pct !== null && trend.direction !== 'basically_flat' && (
          <Text style={[txt.trendPct, { color }]}>
            {trend.delta_pct > 0 ? '+' : ''}{trend.delta_pct.toFixed(1)}%
          </Text>
        )}
      </View>
    </View>
  );
}

function CardRow({ card, good, styles, txt }: {
  card: ScorecardCard; good: boolean;
  styles: ReturnType<typeof createStyles>; txt: ReturnType<typeof createTxt>;
}) {
  return (
    <View style={styles.cardInner}>
      <View style={{ flex: 1 }}>
        <Text style={txt.cardTitle} numberOfLines={2}>{card.title}</Text>
        {card.metric ? (
          <Text style={txt.cardMeta}>{card.metric}</Text>
        ) : null}
      </View>
      <Text style={[txt.cardScore, { color: good ? '#34C759' : '#FF3B30' }]}>
        {card.score}
      </Text>
    </View>
  );
}

function createStyles(c: ColorPalette) { return StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg, paddingBottom: 60 },
  card: {
    backgroundColor: c.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, marginBottom: spacing.md,
    ...shadows.subtle,
  },
  agentLink: { marginBottom: spacing.md },
  bulletRow: {
    flexDirection: 'row', alignItems: 'flex-start',
    marginTop: spacing.sm, gap: 8,
  },
  bulletDot: {
    width: 6, height: 6, borderRadius: 3,
    backgroundColor: c.brand, marginTop: 7,
  },
  trendRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  trendRowBorder: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: c.separator,
  },
  overallRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.lg },
  rateBar: {
    width: 24, height: 100, borderRadius: 4,
    backgroundColor: c.fill, overflow: 'hidden',
    justifyContent: 'flex-end',
  },
  rateBarFill: { width: '100%' },
  spRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: 6, gap: 10,
  },
  spBar: {
    flex: 1, height: 8, borderRadius: 4,
    backgroundColor: c.fill, overflow: 'hidden',
  },
  spBarFill: { height: '100%', borderRadius: 4 },
  cardInner: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: spacing.sm, gap: spacing.md,
  },
  ivRow: {
    flexDirection: 'row', alignItems: 'flex-start',
    paddingVertical: spacing.sm, gap: spacing.md,
  },
  ivRowBorder: {
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: c.separator,
  },
  ivBadge: {
    paddingHorizontal: 8, paddingVertical: 4,
    borderRadius: radii.sm, backgroundColor: c.fill,
  },
}); }

function createTxt(c: ColorPalette) { return {
  title: {
    fontSize: 17, fontWeight: '600', color: c.labelPrimary,
    flex: 1, textAlign: 'center',
  } as TextStyle,
  generatedHint: {
    fontSize: 12, color: c.labelTertiary,
    marginBottom: spacing.md,
  } as TextStyle,
  section: {
    fontSize: 13, fontWeight: '500', color: c.labelSecondary,
    marginBottom: spacing.xs, marginTop: spacing.sm, marginLeft: spacing.xs,
  } as TextStyle,
  sectionTitle: {
    fontSize: 15, fontWeight: '600', color: c.labelPrimary,
    marginBottom: spacing.sm,
  } as TextStyle,
  narrative: { fontSize: 14, color: c.labelPrimary, lineHeight: 21 } as TextStyle,
  bulletText: { flex: 1, fontSize: 14, color: c.labelPrimary, lineHeight: 20 } as TextStyle,
  trendLabel: { fontSize: 14, color: c.labelPrimary, fontWeight: '500' } as TextStyle,
  trendValues: { fontSize: 12, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  trendArrow: { fontSize: 13, fontWeight: '600' } as TextStyle,
  trendPct: { fontSize: 11, marginTop: 2 } as TextStyle,
  hint: { fontSize: 11, color: c.labelTertiary, marginTop: 4 } as TextStyle,
  hitRateLabel: { fontSize: 12, color: c.labelTertiary } as TextStyle,
  hitRateValue: {
    fontSize: 36, fontWeight: '700', color: c.labelPrimary,
    marginVertical: 4,
  } as TextStyle,
  spLabel: { fontSize: 13, color: c.labelPrimary, width: 56 } as TextStyle,
  spRate: { fontSize: 12, fontWeight: '600', color: c.labelPrimary, width: 40, textAlign: 'right' } as TextStyle,
  spCount: { fontSize: 11, color: c.labelTertiary } as TextStyle,
  cardTitle: { fontSize: 14, color: c.labelPrimary, lineHeight: 19 } as TextStyle,
  cardMeta: { fontSize: 11, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  cardScore: { fontSize: 20, fontWeight: '700', minWidth: 40, textAlign: 'right' } as TextStyle,
  ivKind: { fontSize: 11, color: c.labelSecondary } as TextStyle,
  ivTitle: { fontSize: 14, color: c.labelPrimary } as TextStyle,
  ivDate: { fontSize: 11, color: c.labelTertiary, marginTop: 2 } as TextStyle,
  ivDetail: { fontSize: 12, color: c.labelSecondary, marginTop: 4, lineHeight: 17 } as TextStyle,
  empty: { fontSize: 14, color: c.labelTertiary, textAlign: 'center', paddingVertical: spacing.lg } as TextStyle,
}; }
