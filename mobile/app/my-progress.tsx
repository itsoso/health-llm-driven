/**
 * /my-progress —— 用户视角的执行监测看板 (G-W5, 2026-05-12).
 *
 * 跟 /admin/wscla 区别: 这个是 user 自己看, 数据只是自己的.
 * 核心目的: 让用户感受"AI 给我的建议有没有真的让我变好" — 这是
 * SelfDecode/Rootine 都不做的差异化能力.
 */

import React, { useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchMyProgress, type ProgressDashboard, type ProgressCard } from '../services/myProgress';
import {
  causalMemorySummary,
  fetchHealthOperatingReview,
  predictionBacktestSummary,
  predictionNextStepSummary,
  predictionTimelineSummary,
  type HealthOperatingReview,
  type ReviewWindowDays,
} from '../services/healthOperatingReview';
import { spacing, radii } from '../constants/theme';
import { useTheme, type SemanticTone, type SemanticPalette } from '../hooks/useTheme';
import HeroTile from '../components/dashboard/HeroTile';
import EvidenceChip from '../components/shared/EvidenceChip';

const WINDOW_OPTIONS = [
  { label: '7 天', days: 7 },
  { label: '30 天', days: 30 },
  { label: '90 天', days: 90 },
];

function pct(v: number | null): string {
  if (v == null) return '—';
  return `${(v * 100).toFixed(0)}%`;
}

// 颜色走 semanticColors (useTheme().s), 这里只定 tone + label/arrow.
export const OUTCOME_COLORS: Record<string, { tone: SemanticTone; label: string; arrow: string }> = {
  improved: { tone: 'success', label: '改善', arrow: '↑' },
  unchanged: { tone: 'neutral', label: '稳定', arrow: '—' },
  worsened: { tone: 'danger', label: '反向', arrow: '↓' },
  inconclusive: { tone: 'neutral', label: '数据不足', arrow: '?' },
};

export default function MyProgressScreen() {
  const router = useRouter();
  const { c, s: sem } = useTheme();
  const qc = useQueryClient();
  const [days, setDays] = useState(30);

  const { data, isLoading, isRefetching, error } = useQuery<ProgressDashboard>({
    queryKey: ['my-progress', days],
    queryFn: () => fetchMyProgress(days),
    staleTime: 2 * 60 * 1000,
  });
  const { data: operatingReview } = useQuery<HealthOperatingReview>({
    queryKey: ['daily-plan-review', days],
    queryFn: () => fetchHealthOperatingReview(days as ReviewWindowDays),
    staleTime: 2 * 60 * 1000,
  });

  const onRefresh = () => qc.invalidateQueries({ queryKey: ['my-progress'] });

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }
  if (error || !data) {
    return (
      <View style={styles.center}>
        <Text style={[styles.errorText, { color: c.labelPrimary }]}>加载失败</Text>
        <Text style={[styles.errorSub, { color: c.labelTertiary }]}>{String(error)}</Text>
      </View>
    );
  }

  const s = data.stats;
  const noCards = s.total_surfaced === 0;

  return (
    <>
      <Stack.Screen options={{ title: '我的进度', headerBackTitle: '返回', headerShown: true }} />
      <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['bottom']}>
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={onRefresh} />}
        >
          {/* 时间窗口 chip */}
          <View style={styles.chipRow}>
            {WINDOW_OPTIONS.map(opt => (
              <TouchableOpacity
                key={opt.days}
                onPress={() => setDays(opt.days)}
                style={[
                  styles.chip,
                  {
                    backgroundColor: days === opt.days ? c.brand : c.bgCard,
                    borderColor: days === opt.days ? c.brand : c.separator,
                  },
                ]}
              >
                <Text style={[styles.chipText, { color: days === opt.days ? '#fff' : c.labelSecondary }]}>
                  {opt.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {operatingReview && <OperatingReviewCard review={operatingReview} c={c} />}

          {noCards ? (
            <View style={[styles.emptyCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Ionicons name="leaf-outline" size={32} color={c.labelTertiary} />
              <Text style={[styles.emptyTitle, { color: c.labelPrimary }]}>
                这段时间还没有 AI 建议
              </Text>
              <Text style={[styles.emptySub, { color: c.labelTertiary }]}>
                阿衡主动产建议:{'\n'}
                · Safety 触发的告警 (心率/睡眠/血压异常){'\n'}
                · 周日 21:07 自动生成的本周建议{'\n'}
                · Specialist 在你提问时产出的建议
              </Text>
            </View>
          ) : (
            <>
              {/* 改善叙事 — "AI 让你变好的指标" (2026-05-13) */}
              <NarrativeBlock cards={data.closed_cards} c={c} />

              {/* 顶部核心数 */}
              <View style={[styles.heroCard, { backgroundColor: c.brandLight, borderColor: c.brand }]}>
                <Text style={[styles.heroLabel, { color: c.brand }]}>已闭环且改善的建议</Text>
                <View style={styles.heroNumRow}>
                  <Text style={[styles.heroNum, { color: c.brand }]}>{s.improved}</Text>
                  <Text style={[styles.heroDenom, { color: c.brand }]}> / {s.total_surfaced}</Text>
                </View>
                <Text style={[styles.heroSub, { color: c.brand }]}>
                  AI 这 {days} 天给了 {s.total_surfaced} 条建议, 你做完并改善 {s.improved} 条
                </Text>
              </View>

              {/* 核心 4 数 — 学健康记录 VitalsGrid 2x2 tile 风格 (2026-05-12) */}
              <View style={styles.statGrid}>
                <HeroTile
                  label="接受率"
                  ionIcon="checkmark-circle"
                  value={pct(s.acceptance_rate)}
                  sub={`${s.accepted}/${s.accepted + s.declined}`}
                  color={c.blue}
                  bg={c.tintBlue}
                />
                <HeroTile
                  label="完成率"
                  ionIcon="hourglass"
                  value={pct(s.completed && s.accepted ? s.completed / s.accepted : null)}
                  sub={`${s.completed}/${s.accepted}`}
                  color={c.purple}
                  bg={c.tintPurple}
                />
                <HeroTile
                  label="验证率"
                  ionIcon="search"
                  value={pct(s.verification_rate)}
                  sub={`${s.graded}/${s.completed}`}
                  color={c.orange}
                  bg={c.tintOrange}
                />
                <HeroTile
                  label="改善率"
                  ionIcon="trending-up"
                  value={pct(s.improvement_rate)}
                  sub={`${s.improved}/${s.graded}`}
                  color={c.green}
                  bg={c.tintGreen}
                />
              </View>

              {/* outcome 分布 */}
              <View style={[styles.outcomeRow, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
                <OutcomePill label="改善" count={s.improved} color={sem.success.solid} total={s.graded} />
                <OutcomePill label="稳定" count={s.unchanged} color={sem.neutral.solid} total={s.graded} />
                <OutcomePill label="反向" count={s.worsened} color={sem.danger.solid} total={s.graded} />
                <OutcomePill label="不足" count={s.inconclusive} color={c.labelQuaternary} total={s.graded} />
              </View>

              {/* 验证中 */}
              {data.verifying_cards.length > 0 && (
                <View style={styles.section}>
                  <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>
                    验证中 ({data.verifying_cards.length})
                  </Text>
                  <Text style={[styles.sectionSub, { color: c.labelTertiary }]}>
                    你已接受并做完, 等阿衡拉数据评估
                  </Text>
                  {data.verifying_cards.map(card => (
                    <CardRow
                      key={card.id}
                      card={card}
                      onPress={() => router.push({ pathname: '/card/[id]' as any, params: { id: String(card.id) } })}
                      c={c}
                      sem={sem}
                    />
                  ))}
                </View>
              )}

              {/* 已闭环 */}
              {data.closed_cards.length > 0 && (
                <View style={styles.section}>
                  <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>
                    已闭环 ({data.closed_cards.length})
                  </Text>
                  <Text style={[styles.sectionSub, { color: c.labelTertiary }]}>
                    阿衡自动评估完成, 看 metric 旅程
                  </Text>
                  {data.closed_cards.map(card => (
                    <CardRow
                      key={card.id}
                      card={card}
                      onPress={() => router.push({ pathname: '/card/[id]' as any, params: { id: String(card.id) } })}
                      c={c}
                      sem={sem}
                    />
                  ))}
                </View>
              )}
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

// ─── 子组件 ─────────────────────────────────────────────────────────────

function OutcomePill({ label, count, color, total }: { label: string; count: number; color: string; total: number }) {
  const { c } = useTheme();
  const pctVal = total > 0 ? (count / total) * 100 : 0;
  return (
    <View style={styles.outcomePill}>
      <Text style={[styles.outcomeLabel, { color }]}>{label}</Text>
      <Text style={[styles.outcomeCount, { color }]}>{count}</Text>
      <View style={[styles.outcomeBarBg, { backgroundColor: c.fill }]}>
        <View style={[styles.outcomeBarFill, { width: `${pctVal}%`, backgroundColor: color }]} />
      </View>
    </View>
  );
}

const REVIEW_METRICS: Record<string, { label: string; unit: string; good: 'up' | 'down' }> = {
  weight: { label: '体重', unit: 'kg', good: 'down' },
  waist_cm: { label: '腰围', unit: 'cm', good: 'down' },
  systolic_bp: { label: '收缩压', unit: 'mmHg', good: 'down' },
  diastolic_bp: { label: '舒张压', unit: 'mmHg', good: 'down' },
  sleep_score: { label: '睡眠评分', unit: '', good: 'up' },
  hrv: { label: 'HRV', unit: 'ms', good: 'up' },
};

function OperatingReviewCard({ review, c }: { review: HealthOperatingReview; c: any }) {
  const rows = Object.entries(REVIEW_METRICS)
    .map(([key, meta]) => ({ key, ...meta, change: review.metrics[key] }))
    .filter(row => row.change?.status === 'present' && row.change.delta !== null);
  const predictionSummary = predictionBacktestSummary(review.prediction_backtest);
  const predictionResults = review.prediction_backtest?.results ?? [];
  const nextStepResult = predictionResults.find(result => result.next_step);
  const nextStepSummary = predictionNextStepSummary(nextStepResult);
  const timelineSummary = predictionTimelineSummary(review.prediction_timeline);
  const timelineItems = review.prediction_timeline ?? [];
  const personalPatternSummary = causalMemorySummary(review.causal_memory);
  const personalPatterns = review.causal_memory?.notes ?? [];

  return (
    <View style={[styles.reviewCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.reviewHeader}>
        <View>
          <Text style={[styles.reviewTitle, { color: c.labelPrimary }]}>Daily Plan 复盘</Text>
          <Text style={[styles.reviewSub, { color: c.labelTertiary }]}>
            {review.start_date} → {review.end_date}
          </Text>
        </View>
        <View style={[styles.reviewRate, { backgroundColor: c.tintBlue }]}>
          <Text style={[styles.reviewRateText, { color: c.brand }]}>
            {(review.execution.completion_rate * 100).toFixed(0)}%
          </Text>
          <Text style={[styles.reviewRateLabel, { color: c.brand }]}>完成率</Text>
        </View>
      </View>

      <Text style={[styles.reviewLine, { color: c.labelSecondary }]}>
        {review.execution.completed_events}/{review.execution.total_events} 个行动已完成
        {review.completed_action_keys.length > 0 ? ` · ${review.completed_action_keys.length} 个可学习动作` : ''}
      </Text>

      {rows.length > 0 ? (
        <View style={styles.reviewMetricGrid}>
          {rows.slice(0, 4).map(row => {
            const delta = row.change.delta as number;
            const isGood = row.good === 'down' ? delta < 0 : delta > 0;
            const signed = delta > 0 ? `+${delta}` : String(delta);
            return (
              <View key={row.key} style={[styles.reviewMetric, { backgroundColor: isGood ? c.tintGreen : c.fill }]}>
                <Text style={[styles.reviewMetricLabel, { color: c.labelSecondary }]}>{row.label}</Text>
                <Text style={[styles.reviewMetricValue, { color: isGood ? c.green : c.labelPrimary }]}>
                  {signed}{row.unit ? ` ${row.unit}` : ''}
                </Text>
              </View>
            );
          })}
        </View>
      ) : (
        <Text style={[styles.reviewLine, { color: c.labelTertiary }]}>
          这段窗口内关键指标还不足，继续记录体重、腰围、血压、睡眠和 HRV。
        </Text>
      )}

      {predictionSummary ? (
        <View style={[styles.predictionBacktest, { backgroundColor: c.fill }]}>
          <Text style={[styles.predictionTitle, { color: c.labelPrimary }]}>{predictionSummary}</Text>
          {predictionResults.slice(0, 2).map(result => (
            <Text key={result.prediction_id} style={[styles.predictionLine, { color: c.labelSecondary }]}>
              {(REVIEW_METRICS[result.metric]?.label ?? result.metric)} · {result.verdict === 'met' ? '支持' : result.verdict === 'not_met' ? '未支持' : '数据不足'}
              {typeof result.observed_delta === 'number' ? ` · ${result.observed_delta > 0 ? '+' : ''}${result.observed_delta}` : ''}
            </Text>
          ))}
          <Text style={[styles.predictionBoundary, { color: c.labelTertiary }]}>
            {review.prediction_backtest?.boundary}
          </Text>
        </View>
      ) : null}

      {nextStepSummary && nextStepResult?.next_step ? (
        <View style={[styles.predictionNextStep, { backgroundColor: c.tintBlue }]}>
          <Text style={[styles.predictionNextStepTitle, { color: c.blue }]}>{nextStepSummary}</Text>
          {nextStepResult.inconclusive_reason ? (
            <Text style={[styles.predictionLine, { color: c.labelSecondary }]}>
              为什么暂不判断: {nextStepResult.inconclusive_reason}
            </Text>
          ) : null}
          {nextStepResult.next_step.replan_hint ? (
            <Text style={[styles.predictionBoundary, { color: c.labelTertiary }]}>
              {nextStepResult.next_step.replan_hint}
            </Text>
          ) : null}
        </View>
      ) : null}

      {timelineSummary ? (
        <View style={[styles.predictionTimeline, { backgroundColor: c.fill }]}>
          <Text style={[styles.timelineTitle, { color: c.labelPrimary }]}>{timelineSummary}</Text>
          {timelineItems.slice(0, 4).map(item => (
            <View key={item.id} style={styles.timelineRow}>
              <View style={[styles.timelineDot, { backgroundColor: c.brand }]} />
              <View style={styles.timelineText}>
                <Text style={[styles.timelineItemTitle, { color: c.labelSecondary }]} numberOfLines={1}>
                  {item.title}
                </Text>
                <Text style={[styles.timelineItemSummary, { color: c.labelTertiary }]} numberOfLines={2}>
                  {item.summary}
                </Text>
              </View>
            </View>
          ))}
          <Text style={[styles.predictionBoundary, { color: c.labelTertiary }]}>
            {timelineItems[timelineItems.length - 1]?.boundary}
          </Text>
        </View>
      ) : null}

      {personalPatternSummary ? (
        <View style={[styles.causalMemory, { backgroundColor: c.fill }]}>
          <Text style={[styles.causalTitle, { color: c.labelPrimary }]}>{personalPatternSummary}</Text>
          {personalPatterns.slice(1, 3).map((note, index) => (
            <Text key={`${note.metric}-${index}`} style={[styles.causalLine, { color: c.labelSecondary }]}>
              {note.text}
            </Text>
          ))}
          <Text style={[styles.causalBoundary, { color: c.labelTertiary }]}>
            {review.causal_memory?.claim_boundary}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

function CardRow({ card, onPress, c, sem }: { card: ProgressCard; onPress: () => void; c: any; sem: SemanticPalette }) {
  const oc = card.outcome ? OUTCOME_COLORS[card.outcome] : null;
  const ocTone = oc ? sem[oc.tone] : null;
  return (
    <TouchableOpacity
      onPress={onPress}
      style={[styles.cardRow, { backgroundColor: c.bgCard, borderColor: c.separator }]}
    >
      <View style={{ flex: 1, gap: 4 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Text style={[styles.cardTitle, { color: c.labelPrimary, flex: 1 }]} numberOfLines={2}>
            {card.title}
          </Text>
          <EvidenceChip level={card.evidence_level} />
        </View>
        {card.metric_key && card.baseline_value && card.actual_value && (
          <Text style={[styles.cardMetric, { color: c.labelTertiary }]}>
            {card.metric_key} {card.baseline_value} → {card.actual_value}
          </Text>
        )}
        {card.metric_key && !card.actual_value && (
          <Text style={[styles.cardMetric, { color: c.labelTertiary }]}>
            等待 {card.metric_key} 数据
          </Text>
        )}
      </View>
      {oc && ocTone && (
        <View style={[styles.outcomeChip, { backgroundColor: ocTone.bg }]}>
          <Text style={[styles.outcomeChipText, { color: ocTone.fg }]}>
            {oc.arrow} {oc.label}
            {card.effect_size != null && card.outcome !== 'inconclusive' && (
              ` ${(Math.abs(card.effect_size) * 100).toFixed(0)}%`
            )}
          </Text>
        </View>
      )}
      <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
    </TouchableOpacity>
  );
}

// ─── 改善叙事 (2026-05-13) ─────────────────────────────────────────
// 把 closed_cards.improved 按 metric 聚合成 "LDL 4.1→3.6, SBP 138→128" 形式.
// 让用户一眼看到 "AI 让我变好了多少" 的具体数值证据.

const METRIC_LABEL_SHORT: Record<string, string> = {
  ldl: 'LDL', hdl: 'HDL', hba1c: '糖化', tg: 'TG',
  systolic_bp: '收缩压', sbp: '收缩压', dbp: '舒张压',
  weight_kg: '体重', bmi: 'BMI', hrv: 'HRV', rhr: '静息心率',
  sleep_score: '睡眠', spo2_odi: 'ODI',
  hcy: '同型半胱氨酸', vitamin_d: '维 D', b12: 'B12', ferritin: '铁蛋白',
};

function NarrativeBlock({ cards, c }: { cards: ProgressCard[]; c: any }) {
  const rows = React.useMemo(() => {
    const map = new Map<string, { baseline: string; actual: string; effect: number | null }>();
    for (const card of cards) {
      if (card.outcome !== 'improved') continue;
      if (!card.metric_key || !card.baseline_value || !card.actual_value) continue;
      if (!map.has(card.metric_key)) {
        map.set(card.metric_key, {
          baseline: card.baseline_value,
          actual: card.actual_value,
          effect: card.effect_size,
        });
      }
    }
    return Array.from(map.entries()).map(([metric, v]) => ({
      metric, label: METRIC_LABEL_SHORT[metric] || metric, ...v,
    }));
  }, [cards]);

  if (rows.length === 0) return null;

  return (
    <View style={[styles.narrativeCard, { backgroundColor: c.tintGreen, borderColor: c.green + '60' }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
        <Ionicons name="trending-up" size={16} color={c.green} />
        <Text style={{ fontSize: 13, color: c.green, fontWeight: '600' }}>AI 让你变好的指标</Text>
      </View>
      <View style={{ gap: 6 }}>
        {rows.map(r => (
          <View key={r.metric} style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={{ fontSize: 12, color: c.labelSecondary, minWidth: 70 }}>{r.label}</Text>
            <Text style={{ fontSize: 14, color: c.labelTertiary, fontVariant: ['tabular-nums'] }}>{r.baseline}</Text>
            <Text style={{ fontSize: 12, color: c.labelTertiary }}>→</Text>
            <Text style={{ fontSize: 14, color: c.green, fontWeight: '700', fontVariant: ['tabular-nums'] }}>{r.actual}</Text>
            {r.effect != null && (
              <Text style={{ fontSize: 11, color: c.green, opacity: 0.7, marginLeft: 'auto' }}>
                {(Math.abs(r.effect) * 100).toFixed(0)}%
              </Text>
            )}
          </View>
        ))}
      </View>
    </View>
  );
}

// ─── styles ─────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  errorText: { fontSize: 16, fontWeight: '600' },
  errorSub: { fontSize: 12 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  chipRow: { flexDirection: 'row', gap: 8 },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
  },
  chipText: { fontSize: 13, fontWeight: '500' },
  reviewCard: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: spacing.sm,
  },
  reviewHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.md },
  reviewTitle: { fontSize: 16, fontWeight: '700' },
  reviewSub: { fontSize: 11, marginTop: 2 },
  reviewRate: { borderRadius: radii.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, alignItems: 'center' },
  reviewRateText: { fontSize: 18, fontWeight: '800' },
  reviewRateLabel: { fontSize: 10, fontWeight: '600' },
  reviewLine: { fontSize: 12, lineHeight: 18 },
  reviewMetricGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  reviewMetric: { minWidth: '47%', flex: 1, borderRadius: radii.md, padding: spacing.sm },
  reviewMetricLabel: { fontSize: 11, marginBottom: 2 },
  reviewMetricValue: { fontSize: 15, fontWeight: '700' },
  predictionBacktest: { borderRadius: radii.md, padding: spacing.sm, gap: 4 },
  predictionTitle: { fontSize: 12, fontWeight: '700', lineHeight: 18 },
  predictionLine: { fontSize: 12, lineHeight: 17 },
  predictionBoundary: { fontSize: 11, lineHeight: 15 },
  predictionNextStep: { borderRadius: radii.md, padding: spacing.sm, gap: 4 },
  predictionNextStepTitle: { fontSize: 12, fontWeight: '700', lineHeight: 18 },
  predictionTimeline: { borderRadius: radii.md, padding: spacing.sm, gap: 6 },
  timelineTitle: { fontSize: 12, fontWeight: '700', lineHeight: 18 },
  timelineRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  timelineDot: { width: 7, height: 7, borderRadius: 4, marginTop: 5 },
  timelineText: { flex: 1, minWidth: 0, gap: 2 },
  timelineItemTitle: { fontSize: 12, lineHeight: 16, fontWeight: '600' },
  timelineItemSummary: { fontSize: 11, lineHeight: 15 },
  causalMemory: { borderRadius: radii.md, padding: spacing.sm, gap: 4 },
  causalTitle: { fontSize: 12, fontWeight: '700', lineHeight: 18 },
  causalLine: { fontSize: 12, lineHeight: 17 },
  causalBoundary: { fontSize: 11, lineHeight: 15 },
  emptyCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.xl,
    alignItems: 'center',
    gap: 12,
  },
  emptyTitle: { fontSize: 16, fontWeight: '600' },
  emptySub: { fontSize: 13, lineHeight: 20, textAlign: 'center' },
  heroCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.lg,
    gap: 6,
  },
  narrativeCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  heroLabel: { fontSize: 13, fontWeight: '600' },
  heroNumRow: { flexDirection: 'row', alignItems: 'baseline' },
  heroNum: { fontSize: 36, fontWeight: '700' },
  heroDenom: { fontSize: 18, fontWeight: '500' },
  heroSub: { fontSize: 12, lineHeight: 18, opacity: 0.85 },
  statGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  outcomeRow: {
    flexDirection: 'row',
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 8,
  },
  outcomePill: { flex: 1, gap: 4 },
  outcomeLabel: { fontSize: 11, fontWeight: '600' },
  outcomeCount: { fontSize: 18, fontWeight: '700' },
  outcomeBarBg: { height: 4, borderRadius: 2 },
  outcomeBarFill: { height: '100%', borderRadius: 2 },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  sectionTitle: { fontSize: 15, fontWeight: '600' },
  sectionSub: { fontSize: 12 },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
  },
  cardTitle: { fontSize: 14, fontWeight: '500', lineHeight: 20 },
  cardMetric: { fontSize: 11 },
  outcomeChip: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  outcomeChipText: { fontSize: 11, fontWeight: '700' },
});
