/** Personal progress: execution and observations, without causal attribution. */
import React, { useState } from 'react';
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Stack, useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import type { ProgressDashboard, ProgressCard } from '../services/myProgress';
import {
  causalMemorySummary, predictionBacktestSummary, predictionNextStepSummary, predictionTimelineSummary,
  type HealthOperatingReview, type ReviewWindowDays,
} from '../services/healthOperatingReview';
import { useMyProgress } from '../hooks/useMyProgress';
import { spacing, radii } from '../constants/theme';
import { useTheme, type ColorPalette, type SemanticTone, type SemanticPalette } from '../hooks/useTheme';
import { formatDisplayNumber } from '../utils/displayNumber';
import EvidenceChip from '../components/shared/EvidenceChip';
import HealthWeekNavigation from '../components/home/HealthWeekNavigation';

const WINDOWS: ReviewWindowDays[] = [7, 30, 90];
export const OUTCOME_COLORS: Record<string, { tone: SemanticTone; label: string; arrow: string }> = {
  improved: { tone: 'success', label: '改善', arrow: '↑' },
  unchanged: { tone: 'neutral', label: '稳定', arrow: '—' },
  worsened: { tone: 'danger', label: '未达预期', arrow: '↓' },
  inconclusive: { tone: 'neutral', label: '数据不足', arrow: '?' },
};
const REVIEW_METRICS: Record<string, { label: string; unit: string }> = {
  weight: { label: '体重', unit: 'kg' }, waist_cm: { label: '腰围', unit: 'cm' },
  systolic_bp: { label: '收缩压', unit: 'mmHg' }, diastolic_bp: { label: '舒张压', unit: 'mmHg' },
  sleep_score: { label: '睡眠评分', unit: '' }, hrv: { label: 'HRV', unit: 'ms' },
};
const METRIC_LABELS: Record<string, string> = {
  ...Object.fromEntries(Object.entries(REVIEW_METRICS).map(([key, value]) => [key, value.label])),
  weight_kg: '体重', sbp: '收缩压', dbp: '舒张压', ldl: 'LDL', hdl: 'HDL', hba1c: '糖化血红蛋白',
  tg: '甘油三酯', bmi: 'BMI', rhr: '静息心率', hcy: '同型半胱氨酸', vitamin_d: '维生素 D', b12: '维生素 B12', ferritin: '铁蛋白',
};
function count(value: number): string {
  return Number.isSafeInteger(value) && value >= 0 ? formatDisplayNumber(value) : '—';
}
function reading(value: string | number | null | undefined): string | null {
  if (value == null || (typeof value === 'string' && value.trim() === '')) return null;
  const n = Number(value);
  return Number.isFinite(n) ? formatDisplayNumber(n) : null;
}
function signed(value: number): string {
  const formatted = formatDisplayNumber(value);
  return Number(formatted) > 0 ? `+${formatted}` : formatted;
}

export default function MyProgressScreen() {
  const params = useLocalSearchParams<{ navigation?: string }>();
  return params.navigation === 'week' ? <HealthWeekNavigation /> : <ProgressScreen />;
}
function ProgressScreen() {
  const { c, s: sem } = useTheme();
  const router = useRouter();
  const [days, setDays] = useState<ReviewWindowDays>(30);
  const { progress, review, canRead, refresh, refreshing } = useMyProgress(days);
  return (
    <>
      <Stack.Screen options={{ title: '我的进度', headerBackTitle: '返回', headerShown: true }} />
      <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['bottom']}>
        <ScrollView contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} tintColor={c.brand} />}>
          <View style={[styles.periods, { backgroundColor: c.fill }]} accessibilityRole="tablist">
            {WINDOWS.map(window => (
              <TouchableOpacity key={window} accessibilityRole="button" accessibilityLabel={`最近${window}天`}
                accessibilityState={{ selected: days === window }} onPress={() => setDays(window)}
                style={[styles.period, days === window && { backgroundColor: c.brand }]}>
                <Text style={[styles.periodText, { color: days === window ? c.bgPrimary : c.labelSecondary }]}>{window} 天</Text>
              </TouchableOpacity>
            ))}
          </View>
          {!canRead ? (
            <View style={styles.center}><Text style={[styles.body, { color: c.labelSecondary }]}>登录后查看你的进度</Text></View>
          ) : <>
            {review.error ? <SectionState title="本期回顾" retry={() => { void review.refetch(); }} c={c} />
              : review.isLoading || !review.data ? <SectionState title="本期回顾" c={c} />
              : <ReviewOverview key={days} review={review.data} c={c} />}
            {progress.error ? <SectionState title="建议进展" retry={() => { void progress.refetch(); }} c={c} />
              : progress.isLoading || !progress.data ? <SectionState title="建议进展" c={c} />
              : <SuggestionProgress data={progress.data} c={c} sem={sem}
                  openCard={card => router.push({ pathname: '/card/[id]', params: { id: String(card.id) } })} />}
          </>}
        </ScrollView>
      </SafeAreaView>
    </>
  );
}
function SectionState({ title, retry, c }: { title: string; retry?: () => void; c: ColorPalette }) {
  return <View style={[styles.card, { backgroundColor: c.bgCard }]}>
    <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>{title}</Text>
    {retry ? <>
      <Text style={[styles.body, { color: c.labelSecondary }]}>暂时未能加载，稍后再试。</Text>
      <TouchableOpacity accessibilityRole="button" accessibilityLabel={`重新加载${title}`} onPress={retry} style={styles.retry}>
        <Ionicons name="refresh-outline" size={16} color={c.brand} /><Text style={[styles.link, { color: c.brand }]}>重新加载</Text>
      </TouchableOpacity>
    </> : <View style={styles.inline}><ActivityIndicator color={c.brand} /><Text style={[styles.body, { color: c.labelSecondary }]}>正在加载…</Text></View>}
  </View>;
}
function ReviewOverview({ review, c }: { review: HealthOperatingReview; c: ColorPalette }) {
  const { total_events: total, completed_events: completed } = review.execution;
  const valid = Number.isSafeInteger(total) && Number.isSafeInteger(completed) && total > 0 && completed >= 0 && completed <= total;
  const ratio = valid ? completed / total : null;
  const rows = Object.entries(REVIEW_METRICS).map(([key, meta]) => ({ key, ...meta, change: review.metrics[key] }))
    .filter(row => row.change?.status === 'present' && row.change.count >= 2 &&
      typeof row.change.first === 'number' && Number.isFinite(row.change.first) &&
      typeof row.change.current === 'number' && Number.isFinite(row.change.current) &&
      typeof row.change.delta === 'number' && Number.isFinite(row.change.delta));
  return <>
    <View style={[styles.overview, { backgroundColor: c.brandLight }]}>
      <View style={styles.between}>
        <View style={styles.flex}>
          <Text style={[styles.eyebrow, { color: c.brand }]}>本期回顾</Text>
          <Text style={[styles.date, { color: c.labelSecondary }]}>{review.start_date} — {review.end_date}</Text>
        </View>
        <View style={[styles.overviewIcon, { backgroundColor: c.bgCard }]}><Ionicons name="leaf-outline" size={22} color={c.brand} /></View>
      </View>
      <View style={styles.between}>
        <View style={styles.flex}>
          <Text style={[styles.overviewTitle, { color: c.labelPrimary }]}>{total === 0 ? '本期还没有行动记录' : '每一次行动，都值得回顾'}</Text>
          <Text style={[styles.body, { color: c.labelSecondary }]}>{total === 0 ? '记录之后，在这里回看行动和身体变化。' : `已完成 ${count(completed)} 项，共 ${count(total)} 项`}</Text>
        </View>
        {ratio !== null && <Text style={[styles.rate, { color: c.brand }]}>{formatDisplayNumber(ratio * 100)}%</Text>}
      </View>
      {ratio !== null && <View style={[styles.progressTrack, { backgroundColor: c.bgCard }]}>
        <View style={[styles.progressFill, { width: `${ratio * 100}%`, backgroundColor: c.brand }]} />
      </View>}
    </View>
    <View style={[styles.card, { backgroundColor: c.bgCard }]}>
      <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>身体变化</Text>
      <Text style={[styles.caption, { color: c.labelSecondary }]}>对比这段时间内最早与最近的记录</Text>
      {rows.length ? rows.map((row, index) => <View key={row.key}
        style={[styles.metricRow, index > 0 && { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: c.separator }]}>
        <View style={styles.flex}><Text style={[styles.metricLabel, { color: c.labelPrimary }]}>{row.label}</Text>
          <Text style={[styles.caption, { color: c.labelSecondary }]}>{reading(row.change.first) ?? '—'} → {reading(row.change.current) ?? '—'}{row.unit ? ` ${row.unit}` : ''}</Text>
        </View>
        <Text style={[styles.metricDelta, { color: c.labelPrimary }]}>{signed(row.change.delta as number)}{row.unit ? ` ${row.unit}` : ''}</Text>
      </View>) : <View style={styles.emptyBody}>
        <Text style={[styles.metricLabel, { color: c.labelPrimary }]}>还没有足够的前后记录</Text>
        <Text style={[styles.body, { color: c.labelSecondary }]}>有了同一指标的前后记录，就能在这里查看变化。</Text>
      </View>}
      <Text style={[styles.boundary, { color: c.labelSecondary }]}>指标变化仅供回顾，不代表由某条建议造成。</Text>
      <ReviewEvidence review={review} c={c} />
    </View>
  </>;
}
function SuggestionProgress({ data, c, sem, openCard }: { data: ProgressDashboard; c: ColorPalette; sem: SemanticPalette; openCard: (card: ProgressCard) => void }) {
  const s = data.stats;
  const classified = s.improved + s.unchanged + s.worsened + s.inconclusive;
  const unclassified = Number.isSafeInteger(classified) && s.graded > classified ? s.graded - classified : 0;
  const outcomes = [
    { key: 'improved', value: s.improved }, { key: 'unchanged', value: s.unchanged },
    { key: 'worsened', value: s.worsened }, { key: 'inconclusive', value: s.inconclusive },
  ];
  return <>
    <View style={[styles.card, { backgroundColor: c.bgCard }]}>
      <View style={styles.between}>
        <Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>建议进展</Text>
        <Text style={[styles.caption, { color: c.labelSecondary }]}>本期共 {count(s.total_surfaced)} 条</Text>
      </View>
      {s.total_surfaced === 0 ? <View style={styles.emptyBody}>
        <Text style={[styles.metricLabel, { color: c.labelPrimary }]}>这段时间还没有建议记录</Text>
        <Text style={[styles.body, { color: c.labelSecondary }]}>之后收到的建议和评估结果，会汇总在这里。</Text>
      </View> : <>
        <View style={styles.counts}>
          {[['待回应', s.pending], ['已接受', s.accepted], ['已完成', s.completed]].map(([label, value]) => <View key={label} style={styles.countItem}>
            <Text style={[styles.countValue, { color: c.labelPrimary }]}>{count(value as number)}</Text>
            <Text style={[styles.caption, { color: c.labelSecondary }]}>{label}</Text>
          </View>)}
        </View>
        <View style={[styles.evaluation, { borderTopColor: c.separator }]}>
          <View style={styles.between}>
            <Text style={[styles.metricLabel, { color: c.labelPrimary }]}>评估结果</Text>
            <Text style={[styles.caption, { color: c.labelSecondary }]}>{count(s.graded)} 条纳入统计</Text>
          </View>
          {s.graded > 0 ? <View style={styles.outcomes}>
            {outcomes.map(({ key, value }) => <View key={key} style={[styles.outcomeItem, { backgroundColor: sem[OUTCOME_COLORS[key].tone].bg }]}>
              <Text style={[styles.outcomeLabel, { color: sem[OUTCOME_COLORS[key].tone].fg }]}>{OUTCOME_COLORS[key].label}</Text>
              <Text style={[styles.outcomeCount, { color: sem[OUTCOME_COLORS[key].tone].fg }]}>{count(value)}</Text>
            </View>)}
            {unclassified > 0 && <View style={[styles.outcomeItem, { backgroundColor: c.fill }]}>
              <Text style={[styles.outcomeLabel, { color: c.labelSecondary }]}>待分类</Text>
              <Text style={[styles.outcomeCount, { color: c.labelSecondary }]}>{count(unclassified)}</Text>
            </View>}
          </View> : <Text style={[styles.body, { color: c.labelSecondary }]}>暂时没有可统计的评估结果</Text>}
          <Text style={[styles.caption, { color: c.labelSecondary }]}>完成记录与评估结果分别统计；评估不代表行动已完成。</Text>
        </View>
      </>}
    </View>
    {data.verifying_cards.length > 0 && <CardSection title="等待评估" subtitle="已有完成记录，等待更多观察数据。" cards={data.verifying_cards} c={c} sem={sem} openCard={openCard} />}
    {data.closed_cards.length > 0 && <CardSection title="已评估的建议" subtitle="查看具体记录与评估依据，部分结果不纳入上方统计。" cards={data.closed_cards} c={c} sem={sem} openCard={openCard} />}
  </>;
}
function CardSection({ title, subtitle, cards, c, sem, openCard }: { title: string; subtitle: string; cards: ProgressCard[]; c: ColorPalette; sem: SemanticPalette; openCard: (card: ProgressCard) => void }) {
  return <View style={styles.section}>
    <View style={styles.between}><Text style={[styles.sectionTitle, { color: c.labelPrimary }]}>{title}</Text><Text style={[styles.caption, { color: c.labelSecondary }]}>{cards.length} 条展示中</Text></View>
    <Text style={[styles.caption, { color: c.labelSecondary }]}>{subtitle}</Text>
    {cards.map(card => <CardRow key={card.id} card={card} onPress={() => openCard(card)} c={c} sem={sem} />)}
  </View>;
}
function CardRow({ card, onPress, c, sem }: { card: ProgressCard; onPress: () => void; c: ColorPalette; sem: SemanticPalette }) {
  const outcome = card.outcome ? OUTCOME_COLORS[card.outcome] : undefined;
  const tone = outcome ? sem[outcome.tone] : sem.neutral;
  const before = reading(card.baseline_value), after = reading(card.actual_value);
  const metric = card.metric_key ? METRIC_LABELS[card.metric_key] ?? '观察指标' : null;
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={`查看建议详情：${card.title}`} onPress={onPress}
    style={[styles.cardRow, { backgroundColor: c.bgCard }]}>
    <View style={styles.flex}>
      <View style={styles.between}><View style={[styles.statusChip, { backgroundColor: tone.bg }]}>
        <Text style={[styles.outcomeLabel, { color: tone.fg }]}>{outcome?.label ?? (card.graded_at ? '待分类' : '等待评估')}</Text>
      </View><EvidenceChip level={card.evidence_level} /></View>
      <Text style={[styles.cardTitle, { color: c.labelPrimary }]} numberOfLines={2}>{card.title}</Text>
      {metric && <Text style={[styles.caption, { color: c.labelSecondary }]}>{before !== null && after !== null ? `${metric} ${before} → ${after}` : `${metric}：${after ?? '等待更多记录'}`}</Text>}
    </View>
    <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
  </TouchableOpacity>;
}
function ReviewEvidence({ review, c }: { review: HealthOperatingReview; c: ColorPalette }) {
  const [expanded, setExpanded] = useState(false);
  const predictionSummary = predictionBacktestSummary(review.prediction_backtest);
  const predictionResults = review.prediction_backtest?.results ?? [];
  const nextStepResult = predictionResults.find(result => result.next_step);
  const nextStepSummary = predictionNextStepSummary(nextStepResult);
  const timelineSummary = predictionTimelineSummary(review.prediction_timeline);
  const timelineItems = review.prediction_timeline ?? [];
  const personalPatternSummary = causalMemorySummary(review.causal_memory);
  const personalPatterns = review.causal_memory?.notes ?? [];

  const requiresClinician = predictionResults.some(result => result.requires_clinician || result.next_step?.requires_clinician);
  if (!predictionSummary && !nextStepSummary && !timelineSummary && !personalPatternSummary && !requiresClinician) return null;
  return <View>
    {requiresClinician && <Text style={[styles.boundary, { color: c.labelSecondary }]}>部分结果需要专业人员复核，请勿据此自行调整治疗。</Text>}
    <TouchableOpacity accessibilityRole="button" accessibilityLabel={expanded ? '收起复盘依据' : '展开复盘依据'} accessibilityState={{ expanded }}
      style={styles.evidenceToggle} onPress={() => setExpanded(value => !value)}>
      <Text style={[styles.link, { color: c.brand }]}>{expanded ? '收起复盘依据' : '查看复盘依据'}</Text>
      <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={16} color={c.brand} />
    </TouchableOpacity>
    {expanded && <View style={styles.evidenceBody}>
      {predictionSummary ? (
        <View style={[styles.predictionBacktest, { backgroundColor: c.fill }]}>
          <Text style={[styles.predictionTitle, { color: c.labelPrimary }]}>{predictionSummary}</Text>
          {predictionResults.slice(0, 2).map(result => (
            <Text key={result.prediction_id} style={[styles.predictionLine, { color: c.labelSecondary }]}>
              {(REVIEW_METRICS[result.metric]?.label ?? result.metric)} · {result.verdict === 'met' ? '支持' : result.verdict === 'not_met' ? '未支持' : '数据不足'}
              {typeof result.observed_delta === 'number' && Number.isFinite(result.observed_delta) ? ` · ${signed(result.observed_delta)}` : ''}
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
    </View>}
  </View>;
}
const styles = StyleSheet.create({
  safe: { flex: 1 }, flex: { flex: 1, minWidth: 0, gap: 4 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  center: { paddingVertical: spacing.xl, alignItems: 'center' },
  periods: { flexDirection: 'row', padding: 4, borderRadius: radii.lg, gap: 4 },
  period: { flex: 1, minHeight: 44, alignItems: 'center', justifyContent: 'center', borderRadius: radii.md },
  periodText: { fontSize: 14, fontWeight: '600' },
  card: { borderRadius: radii.lg, padding: spacing.lg, gap: spacing.sm },
  overview: { borderRadius: radii.lg, padding: spacing.lg, gap: spacing.lg },
  between: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  inline: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  eyebrow: { fontSize: 13, fontWeight: '600' }, date: { fontSize: 12, lineHeight: 18 },
  overviewIcon: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  overviewTitle: { fontSize: 19, fontWeight: '700', lineHeight: 27 },
  body: { fontSize: 13, lineHeight: 20 }, caption: { fontSize: 12, lineHeight: 18 },
  sectionTitle: { fontSize: 16, fontWeight: '700', lineHeight: 23 },
  rate: { fontSize: 26, fontWeight: '700', fontVariant: ['tabular-nums'] },
  progressTrack: { height: 5, borderRadius: 3, overflow: 'hidden' }, progressFill: { height: '100%', borderRadius: 3 },
  metricRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingVertical: spacing.sm },
  metricLabel: { fontSize: 13, fontWeight: '600', lineHeight: 20 },
  metricDelta: { fontSize: 18, fontWeight: '600', fontVariant: ['tabular-nums'], flexShrink: 1 },
  emptyBody: { gap: 4, paddingVertical: spacing.sm }, boundary: { fontSize: 11, lineHeight: 17 },
  counts: { flexDirection: 'row', gap: spacing.sm, paddingVertical: spacing.sm }, countItem: { flex: 1, gap: 4 },
  countValue: { fontSize: 25, fontWeight: '600', fontVariant: ['tabular-nums'] },
  evaluation: { borderTopWidth: StyleSheet.hairlineWidth, paddingTop: spacing.md, gap: spacing.sm },
  outcomes: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  outcomeItem: { flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: radii.sm, paddingHorizontal: 8, paddingVertical: 6 },
  outcomeLabel: { fontSize: 12, lineHeight: 18 }, outcomeCount: { fontSize: 13, fontWeight: '600', fontVariant: ['tabular-nums'] },
  section: { gap: spacing.sm, marginTop: spacing.sm },
  cardRow: { flexDirection: 'row', alignItems: 'center', padding: spacing.md, borderRadius: radii.lg, gap: spacing.md },
  cardTitle: { fontSize: 15, fontWeight: '600', lineHeight: 22, marginVertical: 4 },
  statusChip: { alignSelf: 'flex-start', paddingHorizontal: 8, paddingVertical: 3, borderRadius: radii.sm },
  retry: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 6, minHeight: 44 },
  link: { fontSize: 13, fontWeight: '600' },
  evidenceToggle: { flexDirection: 'row', minHeight: 44, alignItems: 'center', justifyContent: 'space-between' },
  evidenceBody: { gap: spacing.sm },
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

});
