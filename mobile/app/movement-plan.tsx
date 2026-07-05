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
import HeroTile from '../components/dashboard/HeroTile';
import { EvidenceRefsRow } from '../components/knowledge';
import MarkdownText from '../components/shared/MarkdownText';
import EvidenceChip from '../components/shared/EvidenceChip';
import { createMovementPlanAgentContext, pushChatWithContext } from '../utils/agentContext';

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
  const handleChatMovementPlan = () => {
    pushChatWithContext(router, {
      prompt: '请基于我当前的运动方案和近期训练记录, 复盘训练负荷与恢复风险, 给出今天怎么练/是否该休息, 并提供跑步、骑行、力量或低冲击替代方案。最后请问我需要反馈哪些体感信息。',
      context: createMovementPlanAgentContext(data),
      badge: '当前运动方案',
    });
  };

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
              <MarkdownText>{data.summary}</MarkdownText>
            </View>
          )}

          {/* 训练状态 / 今日建议 / VO2max / 静息心率 — 2x2 grid (2026-05-12 redesign,
              同 home + my-progress + diet-plan 风格) */}
          <View style={styles.heroGrid}>
            {ts && (
              <HeroTile
                label="训练状态"
                ionIcon="speedometer"
                value={ts.status_zh ?? '—'}
                sub={ts.acwr != null ? `ACWR ${ts.acwr.toFixed(2)} · 本周 ${ts.workouts_this_week ?? 0} 次` : (ts.workouts_this_week != null ? `本周 ${ts.workouts_this_week} 次` : undefined)}
                color={sc.text}
                bg={sc.bg}
              />
            )}
            {today && (
              <HeroTile
                label="今日建议"
                ionIcon="flame"
                value={today.intensity_zh ?? '—'}
                sub={today.guidance ? today.guidance.slice(0, 24) : undefined}
                color={ic}
                bg={c.tintOrange}
              />
            )}
            {data.fitness?.vo2max_running != null && (
              <HeroTile
                label="VO2max 跑"
                ionIcon="walk"
                value={`${data.fitness.vo2max_running}`}
                unit=" ml/kg"
                sub="有氧上限"
                color={c.teal}
                bg={c.tintTeal}
              />
            )}
            {data.fitness?.resting_hr != null && (
              <HeroTile
                label="静息心率"
                ionIcon="heart"
                value={`${data.fitness.resting_hr}`}
                unit=" bpm"
                sub="恢复指征"
                color={c.pink}
                bg={c.tintPink}
              />
            )}
          </View>
          <TouchableOpacity
            onPress={handleChatMovementPlan}
            style={[styles.agentLink, { backgroundColor: c.brandLight, borderColor: c.brand }]}
            activeOpacity={0.75}
            accessibilityRole="button"
            accessibilityLabel="跟小巴调整本周训练方案"
          >
            <Ionicons name="chatbubble-ellipses-outline" size={16} color={c.brand} />
            <Text style={[styles.agentLinkText, { color: c.brand }]}>跟小巴调整本周训练</Text>
            <Ionicons name="chevron-forward" size={15} color={c.brand} />
          </TouchableOpacity>

          {/* 基因偏好 — chip 化 (2026-05-12) */}
          {data.gene_biases && data.gene_biases.length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="flash" size={14} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>基因偏好</Text>
              </View>
              {data.gene_biases.map((g: any, i: number) => {
                const tip = g.tip;
                const others = Object.entries(g).filter(([k]) => k !== 'type' && k !== 'tip');
                return (
                  <View key={i} style={styles.geneItem}>
                    <View style={styles.geneChipRow}>
                      {others.map(([k, v]) => (
                        <View key={k} style={[styles.geneChip, { backgroundColor: c.tintTeal, borderColor: c.teal }]}>
                          <Text style={[styles.geneChipKey, { color: c.labelTertiary }]}>{k}</Text>
                          <Text style={[styles.geneChipVal, { color: c.teal }]}>{String(v)}</Text>
                        </View>
                      ))}
                    </View>
                    {tip && (
                      <Text style={[styles.geneTip, { color: c.labelSecondary }]}>{String(tip)}</Text>
                    )}
                  </View>
                );
              })}
            </View>
          )}

          {/* 本周调整 */}
          {data.week_adjustment && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="repeat" size={14} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>本周调整</Text>
              </View>
              <MarkdownText>{data.week_adjustment}</MarkdownText>
            </View>
          )}

          {/* 近 7 天训练 — 加 HR zone 色点 (2026-05-12) */}
          {data.recent_workouts && data.recent_workouts.count > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="trail-sign" size={14} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>
                  近 7 天训练
                </Text>
                <Text style={[styles.cardMeta, { color: c.labelTertiary }]}>
                  {data.recent_workouts.count} 次
                </Text>
              </View>
              {(data.recent_workouts.high_intensity_minutes_7d != null || data.recent_workouts.avg_perceived_exertion != null) && (
                <View style={styles.workoutSummaryRow}>
                  {data.recent_workouts.high_intensity_minutes_7d != null && (
                    <View style={[styles.summaryPill, { backgroundColor: c.tintOrange }]}>
                      <Text style={[styles.summaryPillText, { color: c.orange }]}>
                        Z4-Z5 · {data.recent_workouts.high_intensity_minutes_7d.toFixed(0)}min
                      </Text>
                    </View>
                  )}
                  {data.recent_workouts.avg_perceived_exertion != null && (
                    <View style={[styles.summaryPill, { backgroundColor: c.tintPurple }]}>
                      <Text style={[styles.summaryPillText, { color: c.purple }]}>
                        RPE {data.recent_workouts.avg_perceived_exertion}/10
                      </Text>
                    </View>
                  )}
                </View>
              )}
              {data.recent_workouts.workouts.slice(0, 5).map((w: any, i: number) => {
                const zone = hrToZone(w.avg_hr);
                return (
                  <View key={i} style={styles.workoutRow}>
                    <View style={[styles.zoneDot, { backgroundColor: zone.color }]} />
                    <Text style={[styles.workoutDate, { color: c.labelTertiary }]}>{w.date?.slice(5) ?? ''}</Text>
                    <Text style={[styles.workoutType, { color: c.labelPrimary }]} numberOfLines={1}>{w.type}</Text>
                    <View style={styles.workoutMetaCol}>
                      <Text style={[styles.workoutMetaPrimary, { color: c.labelSecondary }]}>
                        {w.duration_min}min
                        {w.distance_km ? ` · ${w.distance_km}km` : ''}
                      </Text>
                      {w.avg_hr && (
                        <Text style={[styles.workoutMetaSec, { color: c.labelTertiary }]}>
                          {zone.label} · {w.avg_hr}bpm
                        </Text>
                      )}
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {/* 小巴实验建议 — metric badge (2026-05-12) */}
          {data.proposed_experiments && data.proposed_experiments.length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="flask" size={14} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>小巴实验建议</Text>
              </View>
              {data.proposed_experiments.map((e: any, i: number) => (
                <View key={i} style={[styles.experimentRow, { backgroundColor: c.bgPrimary, borderColor: c.separator }]}>
                  <Text style={[styles.experimentTitle, { color: c.labelPrimary }]}>{e.title}</Text>
                  {e.metric_key && (
                    <View style={styles.experimentMetricRow}>
                      <View style={[styles.metricBadge, { backgroundColor: c.brandLight }]}>
                        <Text style={[styles.metricBadgeText, { color: c.brand }]}>{e.metric_key}</Text>
                      </View>
                      <Text style={[styles.experimentArrow, { color: c.labelSecondary }]}>
                        {e.baseline_value} → {e.target_value}
                      </Text>
                      {e.verification_days != null && (
                        <Text style={[styles.experimentDays, { color: c.labelTertiary }]}>
                          · {e.verification_days} 天
                        </Text>
                      )}
                    </View>
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

// HR avg → 5-zone 色 + 标签 (粗略阈值, 按一般跑者最大心率 ~180 估)
function hrToZone(avg?: number | null): { color: string; label: string } {
  if (avg == null) return { color: '#94A3B8', label: '—' };
  if (avg < 130) return { color: '#10B981', label: 'Z1' };  // 热身/恢复
  if (avg < 150) return { color: '#3B82F6', label: 'Z2' };  // 有氧基础
  if (avg < 165) return { color: '#F59E0B', label: 'Z3' };  // 节奏
  if (avg < 180) return { color: '#FB923C', label: 'Z4' };  // 阈值
  return { color: '#EF4444', label: 'Z5' };                  // VO2max
}

function RelatedCardRow({ card, onPress, c }: { card: MovementCard; onPress: () => void; c: any }) {
  const ocColor = card.outcome === 'improved' ? '#10B981'
    : card.outcome === 'worsened' ? '#EF4444'
    : card.outcome === 'unchanged' ? '#94A3B8' : '#CBD5E1';
  return (
    <TouchableOpacity onPress={onPress} style={[styles.relatedRow, { backgroundColor: c.bgPrimary }]}>
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Text style={[styles.relatedTitle, { color: c.labelPrimary, flex: 1 }]} numberOfLines={2}>{card.title}</Text>
          <EvidenceChip level={card.evidence_level} />
        </View>
        {card.metric_key && card.baseline_value && card.actual_value && (
          <Text style={[styles.relatedMeta, { color: c.labelTertiary }]}>
            {card.metric_key} {card.baseline_value} → {card.actual_value}
          </Text>
        )}
        <EvidenceRefsRow refs={card.evidence_refs} testID={`movement-related-evidence-${card.id}`} />
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
  heroGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
  agentLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
  },
  agentLinkText: { fontSize: 14, fontWeight: '600', flex: 1 },
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 8,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  cardTitle: { fontSize: 14, fontWeight: '600', flex: 1 },
  cardMeta: { fontSize: 12 },
  bodyText: { fontSize: 13, lineHeight: 20 },
  // 基因偏好 chip
  geneItem: { gap: 6 },
  geneChipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  geneChip: {
    flexDirection: 'row', alignItems: 'baseline', gap: 4,
    paddingHorizontal: 8, paddingVertical: 4,
    borderRadius: 8, borderWidth: StyleSheet.hairlineWidth,
  },
  geneChipKey: { fontSize: 10, fontWeight: '500', textTransform: 'uppercase' },
  geneChipVal: { fontSize: 12, fontWeight: '600' },
  geneTip: { fontSize: 12, lineHeight: 18 },
  // 训练 row
  workoutSummaryRow: { flexDirection: 'row', gap: 6, marginVertical: 2 },
  summaryPill: {
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8,
  },
  summaryPillText: { fontSize: 11, fontWeight: '600' },
  zoneDot: { width: 6, height: 6, borderRadius: 3 },
  workoutRow: {
    flexDirection: 'row', gap: 8, alignItems: 'center', paddingVertical: 6,
    borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#E2E8F0',
  },
  workoutDate: { fontSize: 11, width: 36, fontFamily: 'Courier' },
  workoutType: { fontSize: 13, fontWeight: '500', flex: 1 },
  workoutMetaCol: { alignItems: 'flex-end', gap: 1 },
  workoutMetaPrimary: { fontSize: 12 },
  workoutMetaSec: { fontSize: 10 },
  // experiment
  experimentRow: {
    gap: 6, padding: 10,
    borderRadius: 10, borderWidth: StyleSheet.hairlineWidth,
  },
  experimentTitle: { fontSize: 13, fontWeight: '600' },
  experimentMetricRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  metricBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  metricBadgeText: { fontSize: 10, fontWeight: '700', fontFamily: 'Courier' },
  experimentArrow: { fontSize: 12, fontVariant: ['tabular-nums'] as const },
  experimentDays: { fontSize: 11 },
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
