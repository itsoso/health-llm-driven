/**
 * /movement-plan —— 我的运动方案 (G-W6, 2026-05-12).
 *
 * Agent Native Mobile First: MovementCoach 输出包装成消费者级页面.
 * SelfDecode/Rootine 都没有"基因 + 可穿戴 + N-of-1" 的训练闭环, 这是差异化.
 */

import React from 'react';
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

import { fetchMovementPlan, type MovementPlan, type MovementCard } from '../services/movementPlan';
import { spacing, radii } from '../constants/theme';
import { useTheme } from '../hooks/useTheme';

const STATUS_COLOR: Record<string, { bg: string; text: string }> = {
  optimal: { bg: '#D1FAE5', text: '#065F46' },
  peaking: { bg: '#FEF3C7', text: '#92400E' },
  overload: { bg: '#FEE2E2', text: '#991B1B' },
  undertrained: { bg: '#DBEAFE', text: '#1E40AF' },
  detraining: { bg: '#F1F5F9', text: '#475569' },
  building: { bg: '#E0E7FF', text: '#3730A3' },
  unknown: { bg: '#F1F5F9', text: '#94A3B8' },
};

const INTENSITY_COLOR: Record<string, string> = {
  high: '#EF4444',
  moderate: '#F59E0B',
  low: '#10B981',
  rest: '#94A3B8',
  active_recovery: '#3B82F6',
  deload: '#A855F7',
};

export default function MovementPlanScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const qc = useQueryClient();

  const { data, isLoading, isRefetching, error } = useQuery<MovementPlan>({
    queryKey: ['movement-plan'],
    queryFn: fetchMovementPlan,
    staleTime: 5 * 60 * 1000,
  });

  const onRefresh = () => qc.invalidateQueries({ queryKey: ['movement-plan'] });

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

  const ts = data.training_status;
  const today = data.today;
  const sc = ts ? STATUS_COLOR[ts.status] ?? STATUS_COLOR.unknown : STATUS_COLOR.unknown;
  const ic = today ? INTENSITY_COLOR[today.intensity] ?? '#94A3B8' : '#94A3B8';

  return (
    <>
      <Stack.Screen options={{ title: '我的运动方案', headerBackTitle: '返回', headerShown: true }} />
      <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['bottom']}>
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={onRefresh} />}
        >
          {data.summary && (
            <View style={[styles.summary, { backgroundColor: c.brandLight, borderColor: c.brand }]}>
              <View style={styles.summaryHead}>
                <Ionicons name="fitness" size={16} color={c.brand} />
                <Text style={[styles.summaryTitle, { color: c.brand }]}>本周综合</Text>
              </View>
              <Text style={[styles.summaryBody, { color: c.labelPrimary }]}>{data.summary}</Text>
            </View>
          )}

          {/* 训练状态 + 今日处方 二并排 */}
          {(ts || today) && (
            <View style={styles.row}>
              {ts && (
                <View style={[styles.cardHalf, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
                  <Text style={[styles.cardHalfLabel, { color: c.labelTertiary }]}>训练状态</Text>
                  <View style={[styles.statusBadge, { backgroundColor: sc.bg, alignSelf: 'flex-start' }]}>
                    <Text style={[styles.statusText, { color: sc.text }]}>{ts.status_zh}</Text>
                  </View>
                  {ts.acwr != null && (
                    <Text style={[styles.cardHalfMeta, { color: c.labelSecondary }]}>
                      ACWR {ts.acwr.toFixed(2)}
                    </Text>
                  )}
                  {ts.workouts_this_week != null && (
                    <Text style={[styles.cardHalfMeta, { color: c.labelSecondary }]}>
                      本周 {ts.workouts_this_week} 次
                    </Text>
                  )}
                  {ts.source && (
                    <Text style={[styles.cardHalfHint, { color: c.labelTertiary }]}>
                      {ts.source === 'garmin' ? 'Garmin 官方' : '自算'}
                    </Text>
                  )}
                </View>
              )}
              {today && (
                <View style={[styles.cardHalf, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
                  <Text style={[styles.cardHalfLabel, { color: c.labelTertiary }]}>今日建议</Text>
                  <Text style={[styles.intensityValue, { color: ic }]}>{today.intensity_zh}</Text>
                  <Text style={[styles.cardHalfMeta, { color: c.labelSecondary }]} numberOfLines={3}>
                    {today.guidance}
                  </Text>
                </View>
              )}
            </View>
          )}

          {/* Fitness snapshot */}
          {data.fitness && (data.fitness.vo2max_running || data.fitness.resting_hr) && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>体能快照</Text>
              <View style={styles.fitnessRow}>
                {data.fitness.vo2max_running != null && (
                  <FitnessCell label="VO2max 跑" value={`${data.fitness.vo2max_running}`} unit="ml/kg/min" c={c} />
                )}
                {data.fitness.vo2max_cycling != null && (
                  <FitnessCell label="VO2max 骑" value={`${data.fitness.vo2max_cycling}`} unit="ml/kg/min" c={c} />
                )}
                {data.fitness.resting_hr != null && (
                  <FitnessCell label="静息心率" value={`${data.fitness.resting_hr}`} unit="bpm" c={c} />
                )}
              </View>
            </View>
          )}

          {/* 基因偏好 */}
          {data.gene_biases && data.gene_biases.length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>基因偏好</Text>
              {data.gene_biases.map((g, i) => (
                <View key={i} style={styles.geneRow}>
                  <Ionicons name="flash-outline" size={14} color={c.brand} />
                  <Text style={[styles.geneText, { color: c.labelSecondary }]}>
                    {Object.entries(g).filter(([k]) => k !== 'type').map(([k, v]) => `${k}: ${v}`).join(' · ')}
                  </Text>
                </View>
              ))}
            </View>
          )}

          {/* 本周调整 */}
          {data.week_adjustment && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>本周调整</Text>
              <Text style={[styles.bodyText, { color: c.labelSecondary }]}>{data.week_adjustment}</Text>
            </View>
          )}

          {/* 近 7 天训练 */}
          {data.recent_workouts && data.recent_workouts.count > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>
                近 7 天训练 · {data.recent_workouts.count} 次
              </Text>
              {data.recent_workouts.avg_perceived_exertion != null && (
                <Text style={[styles.cardMeta, { color: c.labelTertiary }]}>
                  主观疲劳均值 RPE {data.recent_workouts.avg_perceived_exertion}/10
                </Text>
              )}
              {data.recent_workouts.high_intensity_minutes_7d != null && (
                <Text style={[styles.cardMeta, { color: c.labelTertiary }]}>
                  高强度 (Z4-Z5) {data.recent_workouts.high_intensity_minutes_7d.toFixed(0)} 分钟
                </Text>
              )}
              {data.recent_workouts.workouts.slice(0, 5).map((w: any, i: number) => (
                <View key={i} style={styles.workoutRow}>
                  <Text style={[styles.workoutDate, { color: c.labelTertiary }]}>{w.date}</Text>
                  <Text style={[styles.workoutType, { color: c.labelPrimary }]}>{w.type}</Text>
                  <Text style={[styles.workoutMeta, { color: c.labelSecondary }]}>
                    {w.duration_min}min
                    {w.distance_km ? ` · ${w.distance_km}km` : ''}
                    {w.avg_hr ? ` · 心率${w.avg_hr}` : ''}
                  </Text>
                </View>
              ))}
            </View>
          )}

          {/* 实验建议 */}
          {data.proposed_experiments && data.proposed_experiments.length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>Agent 实验建议</Text>
              {data.proposed_experiments.map((e: any, i: number) => (
                <View key={i} style={styles.experimentRow}>
                  <Text style={[styles.experimentTitle, { color: c.labelPrimary }]}>{e.title}</Text>
                  {e.metric_key && (
                    <Text style={[styles.experimentMeta, { color: c.labelTertiary }]}>
                      {e.metric_key}: {e.baseline_value} → {e.target_value} · {e.verification_days}天
                    </Text>
                  )}
                </View>
              ))}
            </View>
          )}

          {/* 关联接受过的训练卡 */}
          {data.related_cards && data.related_cards.length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>
                你接受过的训练建议 ({data.related_cards.length})
              </Text>
              {data.related_cards.map(card => (
                <RelatedCardRow
                  key={card.id}
                  card={card}
                  onPress={() => router.push({ pathname: '/card/[id]' as any, params: { id: String(card.id) } })}
                  c={c}
                />
              ))}
            </View>
          )}

          {!data.has_data && (
            <View style={[styles.emptyCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.emptyText, { color: c.labelTertiary }]}>
                暂无运动数据 — 连接 Garmin / Apple Health 后自动同步
              </Text>
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

function FitnessCell({ label, value, unit, c }: any) {
  return (
    <View style={styles.fitnessCell}>
      <Text style={[styles.fitnessLabel, { color: c.labelTertiary }]}>{label}</Text>
      <Text style={[styles.fitnessValue, { color: c.labelPrimary }]}>
        {value}
        <Text style={[styles.fitnessUnit, { color: c.labelTertiary }]}> {unit}</Text>
      </Text>
    </View>
  );
}

function RelatedCardRow({ card, onPress, c }: { card: MovementCard; onPress: () => void; c: any }) {
  const ocColor = card.outcome === 'improved' ? '#10B981'
    : card.outcome === 'worsened' ? '#EF4444'
    : card.outcome === 'unchanged' ? '#94A3B8' : '#CBD5E1';
  return (
    <TouchableOpacity onPress={onPress} style={[styles.relatedRow, { backgroundColor: c.bgPrimary }]}>
      <View style={{ flex: 1 }}>
        <Text style={[styles.relatedTitle, { color: c.labelPrimary }]} numberOfLines={2}>{card.title}</Text>
        {card.metric_key && card.baseline_value && card.actual_value && (
          <Text style={[styles.relatedMeta, { color: c.labelTertiary }]}>
            {card.metric_key} {card.baseline_value} → {card.actual_value}
          </Text>
        )}
      </View>
      {card.outcome && (
        <Text style={[styles.outcomeText, { color: ocColor }]}>
          {card.outcome === 'improved' ? '↑改善' : card.outcome === 'worsened' ? '↓反向' : card.outcome === 'unchanged' ? '稳定' : '不足'}
          {card.effect_size != null && card.outcome !== 'inconclusive' && ` ${(Math.abs(card.effect_size) * 100).toFixed(0)}%`}
        </Text>
      )}
      <Ionicons name="chevron-forward" size={16} color={c.labelTertiary} />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  errorText: { fontSize: 16, fontWeight: '600' },
  errorSub: { fontSize: 12 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  summary: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 8,
  },
  summaryHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  summaryTitle: { fontSize: 13, fontWeight: '600' },
  summaryBody: { fontSize: 14, lineHeight: 22 },
  row: { flexDirection: 'row', gap: spacing.sm },
  cardHalf: {
    flex: 1,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 6,
  },
  cardHalfLabel: { fontSize: 11, fontWeight: '500' },
  cardHalfMeta: { fontSize: 12 },
  cardHalfHint: { fontSize: 10, fontStyle: 'italic' },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  statusText: { fontSize: 14, fontWeight: '700' },
  intensityValue: { fontSize: 22, fontWeight: '700' },
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 8,
  },
  cardTitle: { fontSize: 14, fontWeight: '600' },
  cardMeta: { fontSize: 12 },
  bodyText: { fontSize: 13, lineHeight: 20 },
  fitnessRow: { flexDirection: 'row', gap: spacing.lg, flexWrap: 'wrap' },
  fitnessCell: { gap: 2 },
  fitnessLabel: { fontSize: 10 },
  fitnessValue: { fontSize: 18, fontWeight: '700' },
  fitnessUnit: { fontSize: 10, fontWeight: '400' },
  geneRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  geneText: { fontSize: 12, flex: 1 },
  workoutRow: { flexDirection: 'row', gap: 8, alignItems: 'center', paddingVertical: 4 },
  workoutDate: { fontSize: 11, width: 80 },
  workoutType: { fontSize: 13, fontWeight: '500' },
  workoutMeta: { fontSize: 11, flex: 1, textAlign: 'right' },
  experimentRow: { gap: 4, paddingVertical: 6, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#E2E8F0' },
  experimentTitle: { fontSize: 13, fontWeight: '600' },
  experimentMeta: { fontSize: 11 },
  relatedRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 8,
    padding: 8,
    marginTop: 4,
  },
  relatedTitle: { fontSize: 13, fontWeight: '500' },
  relatedMeta: { fontSize: 11, marginTop: 2 },
  outcomeText: { fontSize: 11, fontWeight: '700' },
  emptyCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.xl,
    alignItems: 'center',
  },
  emptyText: { fontSize: 13, textAlign: 'center' },
});
