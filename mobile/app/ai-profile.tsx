/**
 * AI 画像页 — Memory 可视化 + ActionCard 成绩单.
 *
 * 两个 tab:
 *  - 记忆: AI 对你记住了什么 (按 tier 分区, 滑动删除 = dismiss)
 *  - 成绩单: AI 建议近 90 天的命中率 + top 高/低分建议
 */
import React, { useMemo, useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, FlatList, ActivityIndicator,
  Alert, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Swipeable } from 'react-native-gesture-handler';
import * as Haptics from 'expo-haptics';

import {
  listMyFacts, getMyStats, dismissFact,
  TIER_LABEL, TIER_COLOR, predicateLabel, primarySourceType, sourceTypeLabel,
  type MemoryFact, type MemoryTier,
} from '../services/memoryFacts';
import {
  getMyScorecard, specialistLabel,
  type ScorecardCard, type ScorecardSpecialistRow,
} from '../services/personalOutcome';
import { spacing, radii } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createAiProfileAgentContext } from '../utils/agentContext';

const FACTS_QK = ['memoryFacts'] as const;
const STATS_QK = ['memoryStats'] as const;
const SCORE_QK = ['scorecard'] as const;

const TIERS: MemoryTier[] = ['semantic', 'procedural', 'episodic', 'working'];

type TabKey = 'memory' | 'scorecard';

export default function AiProfileScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const router = useRouter();
  const qc = useQueryClient();
  const [tab, setTab] = useState<TabKey>('memory');
  const [activeTier, setActiveTier] = useState<MemoryTier | 'all'>('all');

  const facts = useQuery({
    queryKey: [...FACTS_QK, activeTier],
    queryFn: () => listMyFacts({
      tier: activeTier === 'all' ? undefined : activeTier,
      limit: 200,
    }),
    staleTime: 30_000,
  });

  const stats = useQuery({
    queryKey: STATS_QK,
    queryFn: getMyStats,
    staleTime: 60_000,
  });

  const scorecard = useQuery({
    queryKey: SCORE_QK,
    queryFn: () => getMyScorecard(90, 3),
    staleTime: 5 * 60_000,
    enabled: tab === 'scorecard',
  });

  const dismissMut = useMutation({
    mutationFn: (id: number) => dismissFact(id, 'not_accurate'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: FACTS_QK });
      qc.invalidateQueries({ queryKey: STATS_QK });
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    },
    onError: () => Alert.alert('操作失败', '请稍后再试'),
  });

  const handleDismiss = (fact: MemoryFact) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    Alert.alert(
      '告诉 AI 这条不对?',
      `${fact.subject} ${predicateLabel(fact.predicate)} ${fact.object_value}`,
      [
        { text: '取消', style: 'cancel' },
        { text: '不对, 删掉', style: 'destructive', onPress: () => dismissMut.mutate(fact.id) },
      ],
    );
  };

  const byTierStats = useMemo(() => {
    const m = new Map<string, { total: number; avg: number }>();
    (stats.data?.by_tier || []).forEach(r => {
      m.set(r.tier, { total: r.total, avg: r.avg_confidence });
    });
    return m;
  }, [stats.data]);

  const totalFacts = useMemo(
    () => (stats.data?.by_tier || []).reduce((a, b) => a + b.total, 0),
    [stats.data],
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.title}>AI 对我的画像</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.complianceBanner}>
        <Ionicons name="information-circle-outline" size={14} color={c.labelSecondary} />
        <Text style={styles.complianceText}>
          这是 AI 在跨对话中记住的事实和它给你的建议的命中率. 觉得某条不对, 左滑删掉, AI 下次不会再用它.
        </Text>
      </View>

      <View style={styles.agentWrap}>
        <AgentFeedbackLink
          label="跟小巴校准我的画像"
          accessibilityLabel="跟小巴校准我的画像"
          prompt="请基于 AI 当前记住的事实和建议成绩单，帮我找出可能不准确的画像、建议命中或未中的模式，以及我应该补充哪些反馈。"
          context={createAiProfileAgentContext({
            facts: (facts.data ?? []) as any,
            stats: stats.data as any,
            scorecard: scorecard.data as any,
          })}
          badge={`AI 画像 ${totalFacts} 条记忆`}
        />
      </View>

      <View style={styles.tabBar}>
        {([
          { k: 'memory', label: `记忆 ${totalFacts ? `· ${totalFacts}` : ''}` },
          { k: 'scorecard', label: '成绩单' },
        ] as { k: TabKey; label: string }[]).map(({ k, label }) => (
          <TouchableOpacity
            key={k}
            style={[styles.tabBtn, tab === k && styles.tabBtnActive]}
            onPress={() => setTab(k)}
          >
            <Text style={[styles.tabText, tab === k && styles.tabTextActive]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {tab === 'memory' ? (
        <MemoryTab
          facts={facts.data || []}
          isLoading={facts.isLoading}
          byTierStats={byTierStats}
          activeTier={activeTier}
          onTierChange={setActiveTier}
          onDismiss={handleDismiss}
          onRefresh={() => { facts.refetch(); stats.refetch(); }}
        />
      ) : (
        <ScorecardTab
          data={scorecard.data}
          isLoading={scorecard.isLoading}
          onRefresh={() => scorecard.refetch()}
        />
      )}
    </SafeAreaView>
  );
}

// ───────────────── Memory Tab ─────────────────

function MemoryTab(props: {
  facts: MemoryFact[];
  isLoading: boolean;
  byTierStats: Map<string, { total: number; avg: number }>;
  activeTier: MemoryTier | 'all';
  onTierChange: (t: MemoryTier | 'all') => void;
  onDismiss: (f: MemoryFact) => void;
  onRefresh: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { facts, isLoading, byTierStats, activeTier, onTierChange, onDismiss, onRefresh } = props;

  const renderRight = (fact: MemoryFact) => (
    <TouchableOpacity style={styles.swipeDismiss} onPress={() => onDismiss(fact)}>
      <Ionicons name="close-circle-outline" size={20} color="#fff" />
      <Text style={styles.swipeText}>不对</Text>
    </TouchableOpacity>
  );

  const renderItem = ({ item }: { item: MemoryFact }) => {
    const srcType = primarySourceType(item);
    const confPct = Math.round(item.effective_confidence * 100);
    const confColor = confPct >= 70 ? '#34C759' : confPct >= 40 ? '#FF9500' : '#8E8E93';
    return (
      <Swipeable renderRightActions={() => renderRight(item)}>
        <View style={styles.factRow}>
          <View style={styles.factHeader}>
            <View style={[styles.tierBadge, { backgroundColor: TIER_COLOR[item.tier] + '22' }]}>
              <Text style={[styles.tierBadgeText, { color: TIER_COLOR[item.tier] }]}>
                {TIER_LABEL[item.tier]}
              </Text>
            </View>
            <View style={{ flex: 1 }} />
            <View style={[styles.confBadge, { borderColor: confColor }]}>
              <Text style={[styles.confBadgeText, { color: confColor }]}>{confPct}%</Text>
            </View>
          </View>
          <Text style={styles.factText}>
            <Text style={styles.factSubject}>{item.subject}</Text>
            <Text style={styles.factPredicate}> {predicateLabel(item.predicate)} </Text>
            <Text style={styles.factObject}>{item.object_value}</Text>
            {item.object_unit ? <Text style={styles.factObject}> {item.object_unit}</Text> : null}
          </Text>
          <View style={styles.factMeta}>
            <Text style={styles.factMetaText}>来源: {sourceTypeLabel(srcType)}</Text>
            {item.reinforcement_count > 1 && (
              <Text style={styles.factMetaText}>· 被印证 {item.reinforcement_count} 次</Text>
            )}
            {item.last_reinforced_at && (
              <Text style={styles.factMetaText}>
                · {relativeTime(item.last_reinforced_at)}
              </Text>
            )}
          </View>
        </View>
      </Swipeable>
    );
  };

  return (
    <>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.tierChipScroll}
        contentContainerStyle={styles.tierChipRow}
      >
        <TierChip
          label="全部"
          color={c.labelPrimary}
          count={Array.from(byTierStats.values()).reduce((a, b) => a + b.total, 0)}
          active={activeTier === 'all'}
          onPress={() => onTierChange('all')}
        />
        {TIERS.map(t => {
          const s = byTierStats.get(t);
          return (
            <TierChip
              key={t}
              label={TIER_LABEL[t]}
              color={TIER_COLOR[t]}
              count={s?.total || 0}
              active={activeTier === t}
              onPress={() => onTierChange(t)}
            />
          );
        })}
      </ScrollView>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator /></View>
      ) : facts.length === 0 ? (
        <View style={styles.empty}>
          <Ionicons name="bulb-outline" size={48} color={c.labelTertiary} />
          <Text style={styles.emptyTitle}>还没有记忆</Text>
          <Text style={styles.emptyHint}>
            AI 会在你使用过程中逐步记住: 你的化验异常、对哪些建议响应好、哪些不对口味.
          </Text>
        </View>
      ) : (
        <FlatList
          data={facts}
          keyExtractor={i => String(i.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          onRefresh={onRefresh}
          refreshing={false}
        />
      )}
    </>
  );
}

function TierChip(props: {
  label: string;
  color: string;
  count: number;
  active: boolean;
  onPress: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <TouchableOpacity
      style={[
        styles.tierChip,
        props.active && { backgroundColor: props.color + '22', borderColor: props.color },
      ]}
      onPress={props.onPress}
    >
      <Text style={[styles.tierChipText, props.active && { color: props.color }]}>
        {props.label} · {props.count}
      </Text>
    </TouchableOpacity>
  );
}

// ───────────────── Scorecard Tab ─────────────────

function ScorecardTab(props: {
  data: ReturnType<typeof getMyScorecard> extends Promise<infer T> ? T | undefined : never;
  isLoading: boolean;
  onRefresh: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { data, isLoading } = props;
  if (isLoading) {
    return <View style={styles.center}><ActivityIndicator /></View>;
  }
  if (!data || data.overall.total === 0) {
    return (
      <View style={styles.empty}>
        <Ionicons name="analytics-outline" size={48} color={c.labelTertiary} />
        <Text style={styles.emptyTitle}>暂无可评建议</Text>
        <Text style={styles.emptyHint}>
          AI 给你的建议会在到期复查后自动评分, 形成命中率. 持续使用 2-3 周即可看到结果.
        </Text>
      </View>
    );
  }

  const { overall, by_specialist, top_hits, top_misses } = data;
  const rateColor =
    overall.hit_rate >= 60 ? '#34C759' : overall.hit_rate >= 30 ? '#FF9500' : '#FF3B30';

  return (
    <ScrollView contentContainerStyle={styles.scoreScroll}>
      <View style={styles.overallCard}>
        <Text style={styles.overallLabel}>近 {data.window_days} 天 AI 建议命中率</Text>
        <Text style={[styles.overallValue, { color: rateColor }]}>
          {overall.hit_rate.toFixed(0)}%
        </Text>
        <View style={styles.overallBarWrap}>
          <View style={[styles.overallBar, { width: `${overall.hit_rate}%`, backgroundColor: rateColor }]} />
        </View>
        <View style={styles.overallStats}>
          <Text style={styles.overallStatText}>已评 {overall.total}</Text>
          <Text style={styles.overallStatText}>✅ 命中 {overall.high_count}</Text>
          <Text style={styles.overallStatText}>❌ 未中 {overall.low_count}</Text>
          <Text style={styles.overallStatText}>均分 {overall.avg_score.toFixed(0)}</Text>
        </View>
      </View>

      <AgentFeedbackLink
        label="跟小巴分析建议命中率"
        accessibilityLabel="跟小巴分析建议命中率"
        prompt="请基于这份 AI 建议成绩单，分析哪些方向建议更有效、哪些偏离较多，并提出下阶段反馈和改进策略。"
        context={createAiProfileAgentContext({ scorecard: data as any })}
        badge={`近 ${data.window_days} 天命中率 ${overall.hit_rate.toFixed(0)}%`}
        style={styles.scoreAgentLink}
      />

      {by_specialist.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>各专家命中率</Text>
          <View style={styles.specialistList}>
            {by_specialist.map(row => (
              <SpecialistRow key={row.name} row={row} />
            ))}
          </View>
        </>
      )}

      {top_hits.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>✅ Top 命中建议</Text>
          <View style={styles.cardList}>
            {top_hits.map(c => <CardRow key={c.card_id} card={c} color="#34C759" />)}
          </View>
        </>
      )}

      {top_misses.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>❌ Top 未中建议</Text>
          <View style={styles.cardList}>
            {top_misses.map(c => <CardRow key={c.card_id} card={c} color="#FF3B30" />)}
          </View>
        </>
      )}

      <Text style={styles.scoreFooter}>
        命中阈值: 达成 ≥ 70% 计命中; ≤ 30% 计未中. 中间分不计入, 视为"部分响应".
      </Text>
    </ScrollView>
  );
}

function SpecialistRow({ row }: { row: ScorecardSpecialistRow }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const color =
    row.hit_rate >= 60 ? '#34C759' : row.hit_rate >= 30 ? '#FF9500' : '#FF3B30';
  return (
    <View style={styles.specialistRow}>
      <Text style={styles.specialistName}>{specialistLabel(row.name)}</Text>
      <View style={styles.specialistBarWrap}>
        <View style={[styles.specialistBar, { width: `${row.hit_rate}%`, backgroundColor: color }]} />
      </View>
      <Text style={[styles.specialistRate, { color }]}>
        {row.hit_rate.toFixed(0)}%
      </Text>
      <Text style={styles.specialistCount}>
        {row.hits}/{row.total}
      </Text>
    </View>
  );
}

function CardRow({ card, color }: { card: ScorecardCard; color: string }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  return (
    <View style={[styles.cardRow, { borderLeftColor: color }]}>
      <Text style={styles.cardTitle} numberOfLines={2}>{card.title}</Text>
      <View style={styles.cardMeta}>
        <Text style={[styles.cardScore, { color }]}>{card.score} 分</Text>
        {card.metric && <Text style={styles.cardMetaText}>· {card.metric}</Text>}
        {card.specialist && (
          <Text style={styles.cardMetaText}>· {specialistLabel(card.specialist)}</Text>
        )}
        {card.graded_at && (
          <Text style={styles.cardMetaText}>· {relativeTime(card.graded_at)}</Text>
        )}
      </View>
    </View>
  );
}

// ───────────────── utilities ─────────────────

function relativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (isNaN(t)) return '';
  const days = Math.max(0, Math.floor((Date.now() - t) / 86400_000));
  if (days === 0) return '今天';
  if (days === 1) return '昨天';
  if (days < 7) return `${days} 天前`;
  if (days < 30) return `${Math.floor(days / 7)} 周前`;
  if (days < 365) return `${Math.floor(days / 30)} 月前`;
  return `${Math.floor(days / 365)} 年前`;
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  backBtn: { width: 40, height: 40, justifyContent: 'center' },
  title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary },
  complianceBanner: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 6,
    marginHorizontal: spacing.md, marginBottom: spacing.sm,
    paddingVertical: 8, paddingHorizontal: 10,
    backgroundColor: c.fill, borderRadius: radii.sm,
  },
  complianceText: { flex: 1, fontSize: 12, lineHeight: 17, color: c.labelSecondary },
  agentWrap: {
    marginHorizontal: spacing.md,
    marginBottom: spacing.sm,
  },

  tabBar: {
    flexDirection: 'row', marginHorizontal: spacing.md, marginBottom: spacing.xs,
    backgroundColor: c.fill, borderRadius: radii.sm, padding: 3,
  },
  tabBtn: { flex: 1, paddingVertical: 8, alignItems: 'center', borderRadius: radii.sm - 2 },
  tabBtnActive: { backgroundColor: c.bgCard },
  tabText: { fontSize: 14, color: c.labelSecondary, fontWeight: '500' },
  tabTextActive: { color: c.labelPrimary, fontWeight: '600' },

  tierChipScroll: {
    // 给一个显式高度让 ScrollView 在父 flex 里不被挤扁 (iOS).
    // chip: paddingVertical 6 + fontSize 12 ≈ 26; row: paddingVertical sm(8) * 2 = 16; 总 ~42, 给 48 留余量
    height: 48,
    flexGrow: 0,
    flexShrink: 0,
  },
  tierChipRow: {
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    gap: 8,
    // 不用 alignItems:center — horizontal ScrollView 配 alignItems 在 RN 0.81/iOS 有渲染抖动
  },
  tierChip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: 14,
    borderWidth: 1, borderColor: c.separator, backgroundColor: c.bgCard,
  },
  tierChipText: { fontSize: 12, color: c.labelSecondary },

  list: { paddingHorizontal: spacing.md, paddingBottom: spacing.xl },

  factRow: {
    backgroundColor: c.bgCard, padding: spacing.md,
    borderRadius: radii.md, marginBottom: spacing.sm,
  },
  factHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 6 },
  tierBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  tierBadgeText: { fontSize: 11, fontWeight: '600' },
  confBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4, borderWidth: 1 },
  confBadgeText: { fontSize: 11, fontWeight: '600' },
  factText: { fontSize: 15, lineHeight: 21, color: c.labelPrimary, marginBottom: 6 },
  factSubject: { fontWeight: '600' },
  factPredicate: { color: c.labelSecondary },
  factObject: { color: c.labelPrimary },
  factMeta: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  factMetaText: { fontSize: 11, color: c.labelTertiary },

  swipeDismiss: {
    backgroundColor: '#FF3B30', justifyContent: 'center', alignItems: 'center',
    width: 80, marginBottom: spacing.sm, borderRadius: radii.md,
  },
  swipeText: { color: '#fff', fontSize: 11, marginTop: 2 },

  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.xl, gap: 10 },
  emptyTitle: { fontSize: 16, fontWeight: '600', color: c.labelSecondary },
  emptyHint: { fontSize: 13, color: c.labelTertiary, textAlign: 'center', lineHeight: 19 },

  // Scorecard
  scoreScroll: { padding: spacing.md, paddingBottom: spacing.xl },
  overallCard: {
    backgroundColor: c.bgCard, padding: spacing.lg,
    borderRadius: radii.md, marginBottom: spacing.md, alignItems: 'center',
  },
  overallLabel: { fontSize: 13, color: c.labelSecondary, marginBottom: 4 },
  overallValue: { fontSize: 40, fontWeight: '700', marginBottom: spacing.sm },
  overallBarWrap: {
    width: '100%', height: 6, backgroundColor: c.fill, borderRadius: 3,
    overflow: 'hidden', marginBottom: spacing.sm,
  },
  overallBar: { height: '100%' },
  overallStats: { flexDirection: 'row', gap: 12, flexWrap: 'wrap', justifyContent: 'center' },
  overallStatText: { fontSize: 12, color: c.labelSecondary },
  scoreAgentLink: { marginBottom: spacing.md },

  sectionTitle: {
    fontSize: 14, fontWeight: '600', color: c.labelPrimary,
    marginTop: spacing.md, marginBottom: spacing.sm,
  },

  specialistList: {
    backgroundColor: c.bgCard, borderRadius: radii.md,
    paddingHorizontal: spacing.md,
  },
  specialistRow: {
    flexDirection: 'row', alignItems: 'center', paddingVertical: 10, gap: 8,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.separator,
  },
  specialistName: { width: 70, fontSize: 13, color: c.labelPrimary },
  specialistBarWrap: {
    flex: 1, height: 4, backgroundColor: c.fill,
    borderRadius: 2, overflow: 'hidden',
  },
  specialistBar: { height: '100%' },
  specialistRate: { width: 40, fontSize: 12, fontWeight: '600', textAlign: 'right' },
  specialistCount: { width: 36, fontSize: 11, color: c.labelTertiary, textAlign: 'right' },

  cardList: {},
  cardRow: {
    backgroundColor: c.bgCard, padding: spacing.md,
    borderRadius: radii.md, marginBottom: spacing.sm, borderLeftWidth: 3,
  },
  cardTitle: { fontSize: 14, color: c.labelPrimary, marginBottom: 4, lineHeight: 19 },
  cardMeta: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, alignItems: 'center' },
  cardScore: { fontSize: 13, fontWeight: '600' },
  cardMetaText: { fontSize: 11, color: c.labelTertiary },
  scoreFooter: {
    fontSize: 11, color: c.labelTertiary, textAlign: 'center',
    marginTop: spacing.md, lineHeight: 17,
  },
});
