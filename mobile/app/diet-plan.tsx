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
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaSemantic,
  revaFonts,
} from '../constants/revaTheme';
import HeroTile from '../components/dashboard/HeroTile';
import MarkdownText from '../components/shared/MarkdownText';
import EvidenceChip from '../components/shared/EvidenceChip';
import { createDietPlanAgentContext, pushChatWithContext } from '../utils/agentContext';

// 营养四块的类目装饰色(区分"哪类营养",非"好坏"):热量橙 / 蛋白粉 / 饮水蓝 / 补剂紫。
const CAT_HUES = {
  orange: { fg: '#C97A2E', bg: '#F6E9DA' },
  pink: { fg: '#C2487A', bg: '#F7E4EC' },
  blue: { fg: C.blue500, bg: C.blue50 },
  purple: { fg: '#7C5CBF', bg: '#EDE7F6' },
} as const;

// 饮水达标度 → 三步临床语义(好不好):不足红 / 一般琥珀 / 充足绿。
const HYDRATION_COLOR: Record<string, string> = {
  low: revaSemantic.risk.fg,
  ok: revaSemantic.caution.fg,
  full: revaSemantic.normal.fg,
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
        <Text style={[styles.errorText, { color: C.ink1 }]}>加载失败</Text>
        <Text style={[styles.errorSub, { color: C.ink3 }]}>{String(error)}</Text>
      </View>
    );
  }

  const handleChatDietPlan = () => {
    pushChatWithContext(router, {
      prompt: '请基于我当前的饮食方案, 复盘今天饮食、饮水和补剂执行情况, 优化下一餐/今晚安排, 并给出明天最重要的 3 个执行动作。最后请指出需要我反馈哪些体感或记录。',
      context: createDietPlanAgentContext(data),
      badge: '当前饮食方案',
    });
  };

  return (
    <>
      <Stack.Screen options={{ title: '我的饮食方案', headerBackTitle: '返回', headerShown: true }} />
      <SafeAreaView style={[styles.safe, { backgroundColor: C.paper }]} edges={['bottom']}>
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={onRefresh} />}
        >
          {data.summary && (
            <View style={[styles.summary, { backgroundColor: C.green50, borderColor: C.green500 }]}>
              <View style={styles.summaryHead}>
                <Ionicons name="nutrition" size={16} color={C.green500} />
                <Text style={[styles.summaryTitle, { color: C.green500 }]}>今日营养</Text>
              </View>
              <MarkdownText>{data.summary}</MarkdownText>
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
                color={CAT_HUES.orange.fg}
                bg={CAT_HUES.orange.bg}
              />
            )}
            {data.protein && (
              <HeroTile
                label="蛋白质"
                ionIcon="fitness"
                value={`${Math.round(data.protein.today_g)}`}
                unit={` / ${Math.round(data.protein.target_g)}`}
                sub={`g · ${Math.round(data.protein.progress_pct)}%`}
                color={CAT_HUES.pink.fg}
                bg={CAT_HUES.pink.bg}
              />
            )}
            {data.hydration && (
              <HeroTile
                label="饮水"
                ionIcon="water"
                value={`${data.hydration.ml_today}`}
                unit={` / ${data.hydration.goal_ml}`}
                sub={`ml · ${Math.round(data.hydration.progress_pct)}%`}
                color={HYDRATION_COLOR[data.hydration.status] ?? CAT_HUES.blue.fg}
                bg={CAT_HUES.blue.bg}
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
                color={CAT_HUES.purple.fg}
                bg={CAT_HUES.purple.bg}
              />
            )}
          </View>
          <TouchableOpacity
            onPress={handleChatDietPlan}
            style={[styles.agentLink, { backgroundColor: C.green50, borderColor: C.green500 }]}
            activeOpacity={0.75}
            accessibilityRole="button"
            accessibilityLabel="跟 Agent 优化饮食饮水补剂方案"
          >
            <Ionicons name="chatbubble-ellipses-outline" size={16} color={C.green500} />
            <Text style={[styles.agentLinkText, { color: C.green500 }]}>跟 Agent 优化饮食 · 饮水 · 补剂</Text>
            <Ionicons name="chevron-forward" size={15} color={C.green500} />
          </TouchableOpacity>
          {data.next_meal && (
            <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.line }]}>
              <View style={styles.mealHead}>
                <Ionicons name="restaurant-outline" size={16} color={C.green500} />
                <Text style={[styles.cardTitle, { color: C.ink1 }]}>
                  下一餐 · {SLOT_LABEL[data.next_meal.slot] ?? data.next_meal.slot}
                </Text>
              </View>
              <MarkdownText>{data.next_meal.guidance}</MarkdownText>
            </View>
          )}

          {/* 基因驱动饮食 */}
          {data.gene_nudges && data.gene_nudges.length > 0 && (
            <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.line }]}>
              <Text style={[styles.cardTitle, { color: C.ink1 }]}>基因驱动建议</Text>
              {data.gene_nudges.map((g, i) => (
                <View key={i} style={styles.geneRow}>
                  <Ionicons name="cellular-outline" size={14} color={C.green500} />
                  <View style={{ flex: 1 }}>
                    {g.gene && (
                      <Text style={[styles.geneTitle, { color: C.ink1 }]}>
                        {g.gene}{g.genotype ? ` (${g.genotype})` : ''}
                      </Text>
                    )}
                    <Text style={[styles.geneText, { color: C.ink2 }]}>
                      {g.advice ?? g.message ?? Object.entries(g).filter(([k]) => !['type','gene','genotype','advice','message'].includes(k)).map(([k,v]) => `${k}: ${v}`).join(' · ')}
                    </Text>
                  </View>
                </View>
              ))}
            </View>
          )}

          {/* 化验异常关注 */}
          {data.labs_concern && data.labs_concern.items && data.labs_concern.items.length > 0 && (
            <View style={[styles.card, { backgroundColor: revaSemantic.caution.bg, borderColor: revaSemantic.caution.line }]}>
              <Text style={[styles.cardTitle, { color: revaSemantic.caution.fg }]}>化验异常需关注</Text>
              <Text style={[styles.bodyText, { color: revaSemantic.caution.fg }]}>
                {data.labs_concern.items.join(' / ')}
              </Text>
              <Text style={[styles.cardMeta, { color: revaSemantic.caution.fg }]}>
                饮食方案已结合这些指标调整
              </Text>
            </View>
          )}

          {/* 实验建议 */}
          {data.proposed_experiments && data.proposed_experiments.length > 0 && (
            <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.line }]}>
              <Text style={[styles.cardTitle, { color: C.ink1 }]}>Agent 实验建议</Text>
              {data.proposed_experiments.map((e: any, i: number) => (
                <View key={i} style={styles.experimentRow}>
                  <Text style={[styles.experimentTitle, { color: C.ink1 }]}>{e.title}</Text>
                  {e.metric_key && (
                    <Text style={[styles.experimentMeta, { color: C.ink3 }]}>
                      {e.metric_key}: {e.baseline_value} → {e.target_value} · {e.verification_days}天
                    </Text>
                  )}
                </View>
              ))}
            </View>
          )}

          {/* 关联接受过的饮食卡 */}
          {data.related_cards && data.related_cards.length > 0 && (
            <View style={[styles.card, { backgroundColor: C.surface, borderColor: C.line }]}>
              <Text style={[styles.cardTitle, { color: C.ink1 }]}>
                你接受过的饮食/营养建议 ({data.related_cards.length})
              </Text>
              {data.related_cards.map(card => (
                <RelatedCardRow
                  key={card.id}
                  card={card}
                  onPress={() => router.push({ pathname: '/card/[id]' as any, params: { id: String(card.id) } })}
                />
              ))}
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

function RelatedCardRow({ card, onPress }: { card: DietCard; onPress: () => void }) {
  const ocColor = card.outcome === 'improved' ? revaSemantic.normal.fg
    : card.outcome === 'worsened' ? revaSemantic.risk.fg
    : card.outcome === 'unchanged' ? C.ink3 : C.ink4;
  return (
    <TouchableOpacity onPress={onPress} style={[styles.relatedRow, { backgroundColor: C.paper }]}>
      <View style={{ flex: 1 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Text style={[styles.relatedTitle, { color: C.ink1, flex: 1 }]} numberOfLines={2}>{card.title}</Text>
          <EvidenceChip level={card.evidence_level} />
        </View>
        {card.metric_key && card.baseline_value && card.actual_value && (
          <Text style={[styles.relatedMeta, { color: C.ink3 }]}>
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
      <Ionicons name="chevron-forward" size={16} color={C.ink3} />
    </TouchableOpacity>
  );
}

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / 活力绿 / 数字等宽 mono。
const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  errorText: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600' },
  errorSub: { fontFamily: revaFonts.sans, fontSize: 12 },
  content: { padding: revaSpacing.s4, gap: revaSpacing.s3, paddingBottom: revaSpacing.s5 * 2 },
  summary: { borderWidth: 1, borderRadius: revaRadii.md, padding: revaSpacing.s3, gap: 8 },
  summaryHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  summaryTitle: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600' },
  summaryBody: { fontFamily: revaFonts.sans, fontSize: 14, lineHeight: 22 },
  heroGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: revaSpacing.s3 },
  agentLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: revaRadii.md,
    paddingHorizontal: revaSpacing.s3,
    paddingVertical: 12,
  },
  agentLinkText: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600', flex: 1 },
  card: { borderWidth: 1, borderRadius: revaRadii.md, padding: revaSpacing.s3, gap: 8 },
  cardTitle: { fontFamily: revaFonts.sans, fontSize: 14, fontWeight: '600' },
  cardMeta: { fontFamily: revaFonts.sans, fontSize: 12 },
  bodyText: { fontFamily: revaFonts.sans, fontSize: 13, lineHeight: 20 },
  hydHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  hydTitle: { fontFamily: revaFonts.sans, flex: 1, fontSize: 14, fontWeight: '600' },
  hydValue: { fontFamily: revaFonts.mono, fontSize: 14, fontWeight: '600' },

  mealHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  geneRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, paddingVertical: 4 },
  geneTitle: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600' },
  geneText: { fontFamily: revaFonts.sans, fontSize: 12, lineHeight: 18, marginTop: 2 },
  experimentRow: { gap: 4, paddingVertical: 6, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line },
  experimentTitle: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600' },
  experimentMeta: { fontFamily: revaFonts.mono, fontSize: 11 },
  relatedRow: { flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 8, padding: 8, marginTop: 4 },
  relatedTitle: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '500' },
  relatedMeta: { fontFamily: revaFonts.mono, fontSize: 11, marginTop: 2 },
  outcomeText: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '700' },
});
