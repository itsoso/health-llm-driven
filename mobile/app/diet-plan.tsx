/**
 * /diet-plan —— 我的饮食方案 (G-W7, 2026-05-12).
 *
 * 包装 FuelStrategist 输出 → 消费者级页面.
 * 跟 G-W6 运动方案对称, 完成"基因 → 营养+运动+补剂 → 监测闭环"的最后一块.
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

import { fetchDietPlan, type DietPlan, type DietCard } from '../services/dietPlan';
import { spacing, radii } from '../constants/theme';
import { useTheme } from '../hooks/useTheme';

const HYDRATION_COLOR: Record<string, string> = {
  low: '#EF4444',
  ok: '#F59E0B',
  full: '#10B981',
};

const SLOT_LABEL: Record<string, string> = {
  breakfast: '早餐',
  morning_snack: '上午加餐',
  lunch: '午餐',
  afternoon_snack: '下午加餐',
  dinner: '晚餐',
  evening_snack: '宵夜',
};

export default function DietPlanScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const qc = useQueryClient();

  const { data, isLoading, isRefetching, error } = useQuery<DietPlan>({
    queryKey: ['diet-plan'],
    queryFn: fetchDietPlan,
    staleTime: 5 * 60 * 1000,
  });

  const onRefresh = () => qc.invalidateQueries({ queryKey: ['diet-plan'] });

  if (isLoading) {
    return <View style={styles.center}><ActivityIndicator /></View>;
  }
  if (error || !data) {
    return (
      <View style={styles.center}>
        <Text style={[styles.errorText, { color: c.labelPrimary }]}>加载失败</Text>
        <Text style={[styles.errorSub, { color: c.labelTertiary }]}>{String(error)}</Text>
      </View>
    );
  }

  return (
    <>
      <Stack.Screen options={{ title: '我的饮食方案', headerBackTitle: '返回' }} />
      <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['bottom']}>
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={onRefresh} />}
        >
          {data.summary && (
            <View style={[styles.summary, { backgroundColor: c.brandLight, borderColor: c.brand }]}>
              <View style={styles.summaryHead}>
                <Ionicons name="nutrition" size={16} color={c.brand} />
                <Text style={[styles.summaryTitle, { color: c.brand }]}>今日营养</Text>
              </View>
              <Text style={[styles.summaryBody, { color: c.labelPrimary }]}>{data.summary}</Text>
            </View>
          )}

          {/* 三大宏量 二并排 */}
          <View style={styles.row}>
            {data.energy && (
              <RingCell
                label="热量"
                primary={`${Math.round(data.energy.intake_kcal)}`}
                secondary={`/ ${Math.round(data.energy.tdee_kcal)} kcal`}
                pct={data.energy.progress_pct}
                color="#FF6723"
                c={c}
              />
            )}
            {data.protein && (
              <RingCell
                label="蛋白质"
                primary={`${Math.round(data.protein.today_g)}`}
                secondary={`/ ${Math.round(data.protein.target_g)} g`}
                pct={data.protein.progress_pct}
                color="#FF375F"
                c={c}
              />
            )}
          </View>

          {/* 饮水 */}
          {data.hydration && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.hydHead}>
                <Ionicons name="water" size={18} color={HYDRATION_COLOR[data.hydration.status]} />
                <Text style={[styles.hydTitle, { color: c.labelPrimary }]}>饮水</Text>
                <Text style={[styles.hydValue, { color: HYDRATION_COLOR[data.hydration.status] }]}>
                  {data.hydration.ml_today} / {data.hydration.goal_ml} ml
                </Text>
              </View>
              <View style={styles.barBg}>
                <View
                  style={[
                    styles.barFill,
                    {
                      width: `${Math.min(100, data.hydration.progress_pct)}%`,
                      backgroundColor: HYDRATION_COLOR[data.hydration.status],
                    },
                  ]}
                />
              </View>
            </View>
          )}

          {/* 下一餐 */}
          {data.next_meal && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.mealHead}>
                <Ionicons name="restaurant-outline" size={16} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>
                  下一餐 · {SLOT_LABEL[data.next_meal.slot] ?? data.next_meal.slot}
                </Text>
              </View>
              <Text style={[styles.bodyText, { color: c.labelSecondary }]}>{data.next_meal.guidance}</Text>
            </View>
          )}

          {/* 补剂完成度 */}
          {data.supplement && data.supplement.total > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>
                补剂 · {data.supplement.taken_today} / {data.supplement.total}
              </Text>
              {data.supplement.pending && data.supplement.pending.length > 0 && (
                <Text style={[styles.cardMeta, { color: c.labelTertiary }]}>
                  待服: {data.supplement.pending.join(' / ')}
                </Text>
              )}
            </View>
          )}

          {/* 基因驱动饮食 */}
          {data.gene_nudges && data.gene_nudges.length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>基因驱动建议</Text>
              {data.gene_nudges.map((g, i) => (
                <View key={i} style={styles.geneRow}>
                  <Ionicons name="cellular-outline" size={14} color={c.brand} />
                  <View style={{ flex: 1 }}>
                    {g.gene && (
                      <Text style={[styles.geneTitle, { color: c.labelPrimary }]}>
                        {g.gene}{g.genotype ? ` (${g.genotype})` : ''}
                      </Text>
                    )}
                    <Text style={[styles.geneText, { color: c.labelSecondary }]}>
                      {g.advice ?? g.message ?? Object.entries(g).filter(([k]) => !['type','gene','genotype','advice','message'].includes(k)).map(([k,v]) => `${k}: ${v}`).join(' · ')}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          )}

          {/* 化验异常关注 */}
          {data.labs_concern && data.labs_concern.items && data.labs_concern.items.length > 0 && (
            <View style={[styles.card, { backgroundColor: '#FEF3C7', borderColor: '#F59E0B' }]}>
              <Text style={[styles.cardTitle, { color: '#92400E' }]}>化验异常需关注</Text>
              <Text style={[styles.bodyText, { color: '#92400E' }]}>
                {data.labs_concern.items.join(' / ')}
              </Text>
              <Text style={[styles.cardMeta, { color: '#92400E' }]}>
                饮食方案已结合这些指标调整
              </Text>
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

          {/* 关联接受过的饮食卡 */}
          {data.related_cards && data.related_cards.length > 0 && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>
                你接受过的饮食/营养建议 ({data.related_cards.length})
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
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

function RingCell({ label, primary, secondary, pct, color, c }: any) {
  return (
    <View style={[styles.ringCell, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <Text style={[styles.ringLabel, { color: c.labelTertiary }]}>{label}</Text>
      <Text style={[styles.ringPrimary, { color }]}>{primary}</Text>
      <Text style={[styles.ringSecondary, { color: c.labelSecondary }]}>{secondary}</Text>
      <View style={styles.barBg}>
        <View style={[styles.barFill, { width: `${Math.min(100, pct)}%`, backgroundColor: color }]} />
      </View>
      <Text style={[styles.ringPct, { color: c.labelTertiary }]}>{Math.round(pct)}%</Text>
    </View>
  );
}

function RelatedCardRow({ card, onPress, c }: { card: DietCard; onPress: () => void; c: any }) {
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
  summary: { borderWidth: 1, borderRadius: radii.md, padding: spacing.md, gap: 8 },
  summaryHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  summaryTitle: { fontSize: 13, fontWeight: '600' },
  summaryBody: { fontSize: 14, lineHeight: 22 },
  row: { flexDirection: 'row', gap: spacing.sm },
  ringCell: {
    flex: 1,
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 4,
  },
  ringLabel: { fontSize: 11, fontWeight: '500' },
  ringPrimary: { fontSize: 26, fontWeight: '700' },
  ringSecondary: { fontSize: 11 },
  ringPct: { fontSize: 10, textAlign: 'right' },
  barBg: { height: 6, borderRadius: 3, backgroundColor: '#F1F5F9', marginTop: 4 },
  barFill: { height: '100%', borderRadius: 3 },
  card: { borderWidth: 1, borderRadius: radii.md, padding: spacing.md, gap: 8 },
  cardTitle: { fontSize: 14, fontWeight: '600' },
  cardMeta: { fontSize: 12 },
  bodyText: { fontSize: 13, lineHeight: 20 },
  hydHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  hydTitle: { flex: 1, fontSize: 14, fontWeight: '600' },
  hydValue: { fontSize: 14, fontWeight: '600' },
  mealHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  geneRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 4 },
  geneTitle: { fontSize: 13, fontWeight: '600' },
  geneText: { fontSize: 12, lineHeight: 18, marginTop: 2 },
  experimentRow: { gap: 4, paddingVertical: 6, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#E2E8F0' },
  experimentTitle: { fontSize: 13, fontWeight: '600' },
  experimentMeta: { fontSize: 11 },
  relatedRow: { flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 8, padding: 8, marginTop: 4 },
  relatedTitle: { fontSize: 13, fontWeight: '500' },
  relatedMeta: { fontSize: 11, marginTop: 2 },
  outcomeText: { fontSize: 11, fontWeight: '700' },
});
