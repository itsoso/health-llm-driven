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
import HeroTile from '../components/dashboard/HeroTile';

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
      <Stack.Screen options={{ title: '我的饮食方案', headerBackTitle: '返回', headerShown: true }} />
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

          {/* 4 块 hero — 学健康记录 VitalsGrid 2x2 (2026-05-12). 替代旧 2 RingCell
              + 单独 hydration 进度条 + 单独 supplement 行, 视觉一致 */}
          <View style={styles.heroGrid}>
            {data.energy && (
              <HeroTile
                label="热量"
                ionIcon="flame"
                value={`${Math.round(data.energy.intake_kcal)}`}
                unit={` / ${Math.round(data.energy.tdee_kcal)}`}
                sub={`kcal · ${Math.round(data.energy.progress_pct)}%`}
                color={c.orange}
                bg={c.tintOrange}
              />
            )}
            {data.protein && (
              <HeroTile
                label="蛋白质"
                ionIcon="fitness"
                value={`${Math.round(data.protein.today_g)}`}
                unit={` / ${Math.round(data.protein.target_g)}`}
                sub={`g · ${Math.round(data.protein.progress_pct)}%`}
                color={c.pink}
                bg={c.tintPink}
              />
            )}
            {data.hydration && (
              <HeroTile
                label="饮水"
                ionIcon="water"
                value={`${data.hydration.ml_today}`}
                unit={` / ${data.hydration.goal_ml}`}
                sub={`ml · ${Math.round(data.hydration.progress_pct)}%`}
                color={HYDRATION_COLOR[data.hydration.status] ?? c.blue}
                bg={c.tintBlue}
              />
            )}
            {data.supplement && data.supplement.total > 0 && (
              <HeroTile
                label="补剂"
                ionIcon="medkit"
                value={`${data.supplement.taken_today}`}
                unit={` / ${data.supplement.total}`}
                sub={
                  data.supplement.pending && data.supplement.pending.length > 0
                    ? `待服 ${data.supplement.pending.length}`
                    : '今日完成'
                }
                color={c.purple}
                bg={c.tintPurple}
              />
            )}
          </View>
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
  heroGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md },
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
