/**
 * /genetic-report —— Mobile 基因报告页 (G-W2, 2026-05-12).
 *
 * Agent Native Mobile First: 不堆数据, 主动呈现.
 *   1. 顶部"基因 Agent 对你说" LLM 一段总结 + [一键接受 top-3]
 *   2. 关键命中位点 (risk 高→低), 每个 SNP 卡折叠展开
 *   3. 未命中位点 (灰色, "你这条还没测")
 *   4. 按 category 筛选 chip
 *
 * 现状: 用 KNOWN_SNPS 字典 52 SNP. 命中 = 用户测过 & 在字典里; 未命中 = 字典里有但
 * 用户没测. itsoso profile_id=4 命中 38, profile=5 (605 variants) 暂未深度解读.
 */

import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
  RefreshControl,
} from 'react-native';
import { Stack, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  fetchGeneticPredictions,
  fetchGeneticReport,
  type GeneticReport,
  type GeneticReportItem,
  type GeneticPredictions,
  type RelatedCard,
  type Cluster,
  CATEGORY_LABELS,
  RISK_COLORS,
} from '../services/geneticReport';
import { spacing, radii } from '../constants/theme';
import { useTheme } from '../hooks/useTheme';
import MarkdownText from '../components/shared/MarkdownText';
import EvidenceChip from '../components/shared/EvidenceChip';

export default function GeneticReportScreen() {
  const { c } = useTheme();
  const qc = useQueryClient();
  const router = useRouter();
  const [filterCat, setFilterCat] = useState<string | null>(null);
  const [showMisses, setShowMisses] = useState(false);
  const [expandedRsid, setExpandedRsid] = useState<Set<string>>(new Set());

  const { data, isLoading, isRefetching, error } = useQuery<GeneticReport>({
    queryKey: ['genetic-report'],
    queryFn: () => fetchGeneticReport(true),
    staleTime: 5 * 60 * 1000,
  });
  const { data: predictions } = useQuery<GeneticPredictions>({
    queryKey: ['genetic-predictions'],
    queryFn: fetchGeneticPredictions,
    enabled: !!data?.profile,
    staleTime: 10 * 60 * 1000,
  });

  const onRefresh = () => qc.invalidateQueries({ queryKey: ['genetic-report'] });

  const toggleExpand = (rsid: string) => {
    setExpandedRsid(prev => {
      const next = new Set(prev);
      if (next.has(rsid)) next.delete(rsid);
      else next.add(rsid);
      return next;
    });
  };

  const filteredItems = useMemo(() => {
    if (!data) return [];
    let items = data.items;
    if (filterCat) items = items.filter(it => it.category === filterCat);
    if (!showMisses) items = items.filter(it => it.hit);
    return items;
  }, [data, filterCat, showMisses]);

  const categories = useMemo(() => {
    if (!data) return [];
    const set = new Set(data.items.map(it => it.category));
    return Array.from(set);
  }, [data]);

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
        <Text style={[styles.loadingText, { color: c.labelTertiary }]}>加载基因报告…</Text>
      </View>
    );
  }

  if (error || !data) {
    return (
      <View style={styles.center}>
        <Ionicons name="warning-outline" size={32} color={c.amber} />
        <Text style={[styles.errorText, { color: c.labelPrimary }]}>加载失败</Text>
        <Text style={[styles.errorSub, { color: c.labelTertiary }]}>{String(error)}</Text>
      </View>
    );
  }

  if (!data.profile) {
    return (
      <>
        <Stack.Screen options={{ title: '我的基因', headerShown: true }} />
        <View style={styles.center}>
          <Ionicons name="cellular-outline" size={48} color={c.labelTertiary} />
          <Text style={[styles.emptyTitle, { color: c.labelPrimary }]}>还没上传基因数据</Text>
          <Text style={[styles.emptySub, { color: c.labelTertiary }]}>
            支持 WeGene / 23andMe TXT 原始数据{'\n'}上传后, AI 自动解读 52+ 关键位点
          </Text>
        </View>
      </>
    );
  }

  return (
    <>
      <Stack.Screen options={{ title: '我的基因', headerBackTitle: '返回', headerShown: true }} />
      <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['bottom']}>
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={onRefresh} />}
        >
          {/* Header meta */}
          <View style={[styles.metaCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
            <Text style={[styles.metaTitle, { color: c.labelPrimary }]}>
              {data.profile.test_provider}
            </Text>
            <Text style={[styles.metaSub, { color: c.labelTertiary }]}>
              {data.profile.test_date ?? '—'} · 命中 {data.stats.hits} / {data.stats.total_known}
            </Text>
          </View>

          {/* Agent Summary */}
          {data.agent_summary && (
            <View style={[styles.agentCard, { backgroundColor: c.brandLight, borderColor: c.brand }]}>
              <View style={styles.agentHead}>
                <Ionicons name="sparkles" size={16} color={c.brand} />
                <Text style={[styles.agentTitle, { color: c.brand }]}>基因 Agent 对你说</Text>
              </View>
              <MarkdownText>{data.agent_summary}</MarkdownText>
            </View>
          )}

          {predictions && <PredictionBoundaryCard predictions={predictions} c={c} />}

          {/* G-W4 Cluster 头部: 按 category 聚合, 高风险靠前. tap 切到对应 filter. */}
          {data.clusters && data.clusters.length > 0 && (
            <View style={styles.clusterRow}>
              {data.clusters.map(cl => (
                <ClusterChip
                  key={cl.category}
                  cluster={cl}
                  active={filterCat === cl.category}
                  onPress={() => setFilterCat(cl.category === filterCat ? null : cl.category)}
                  c={c}
                />
              ))}
            </View>
          )}

          {/* Category filter chips */}
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow}>
            <Chip label="全部" active={filterCat === null} onPress={() => setFilterCat(null)} c={c} />
            {categories.map(cat => (
              <Chip
                key={cat}
                label={CATEGORY_LABELS[cat] ?? cat}
                active={filterCat === cat}
                onPress={() => setFilterCat(cat === filterCat ? null : cat)}
                c={c}
              />
            ))}
          </ScrollView>

          {/* Toggle: 显示未命中 */}
          <TouchableOpacity
            style={styles.toggleRow}
            onPress={() => setShowMisses(v => !v)}
          >
            <Ionicons
              name={showMisses ? 'checkbox' : 'square-outline'}
              size={18}
              color={c.brand}
            />
            <Text style={[styles.toggleText, { color: c.labelSecondary }]}>
              显示未测出的位点 ({data.stats.miss} 条)
            </Text>
          </TouchableOpacity>

          {/* Items */}
          {filteredItems.map(it => (
            <SnpCard
              key={it.rsid}
              item={it}
              expanded={expandedRsid.has(it.rsid)}
              onToggle={() => toggleExpand(it.rsid)}
              onPressDetail={() => router.push(`/snp/${it.rsid}` as never)}
              c={c}
            />
          ))}

          {filteredItems.length === 0 && (
            <Text style={[styles.empty, { color: c.labelTertiary }]}>这个分类下暂无数据</Text>
          )}
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

function PredictionBoundaryCard({
  predictions,
  c,
}: {
  predictions: GeneticPredictions;
  c: any;
}) {
  const topRisks = predictions.disease_risk.top_risks.slice(0, 3);
  return (
    <View style={[styles.predictionCard, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
      <View style={styles.agentHead}>
        <Ionicons name="shield-checkmark-outline" size={16} color={c.brand} />
        <Text style={[styles.agentTitle, { color: c.brand }]}>基因预测边界</Text>
      </View>
      {topRisks.length > 0 ? (
        <View style={styles.predictionRiskList}>
          {topRisks.map(risk => {
            const color = RISK_COLORS[risk.risk_level] ?? RISK_COLORS.info;
            return (
              <View key={`${risk.rsid}-${risk.gene}`} style={styles.predictionRiskRow}>
                <Text style={[styles.predictionRiskGene, { color: c.labelPrimary }]}>
                  {risk.gene}
                </Text>
                <Text style={[styles.predictionRiskLabel, { color: c.labelSecondary }]} numberOfLines={1}>
                  {risk.result_label}
                </Text>
                <View style={[styles.riskBadge, { backgroundColor: color.bg }]}>
                  <Text style={[styles.riskText, { color: color.text }]}>{color.label}</Text>
                </View>
              </View>
            );
          })}
        </View>
      ) : (
        <Text style={[styles.predictionText, { color: c.labelSecondary }]}>
          暂无命中的疾病风险位点；这不等于没有疾病风险。
        </Text>
      )}
      <Text style={[styles.predictionText, { color: c.labelTertiary }]}>
        身高: {predictions.height.message}
      </Text>
      <Text style={[styles.predictionText, { color: c.labelTertiary }]}>
        教育: {predictions.education.message}
      </Text>
    </View>
  );
}

// ─── 子组件 ─────────────────────────────────────────────────────────────

function Chip({ label, active, onPress, c }: any) {
  return (
    <TouchableOpacity
      style={[
        styles.chip,
        { backgroundColor: active ? c.brand : c.bgCard, borderColor: active ? c.brand : c.separator },
      ]}
      onPress={onPress}
    >
      <Text style={[styles.chipText, { color: active ? '#fff' : c.labelSecondary }]}>{label}</Text>
    </TouchableOpacity>
  );
}

// G-W4: cluster 头部 — 一眼看到 nutrition/exercise/drug 等组占比, tap 可筛选.
function ClusterChip({
  cluster,
  active,
  onPress,
  c,
}: {
  cluster: Cluster;
  active: boolean;
  onPress: () => void;
  c: any;
}) {
  const hasHigh = cluster.high_count > 0;
  const hasMed = cluster.medium_count > 0;
  const accent = hasHigh ? '#FEE2E2' : hasMed ? '#FEF3C7' : c.bgCard;
  const accentText = hasHigh ? '#991B1B' : hasMed ? '#92400E' : c.labelSecondary;
  return (
    <TouchableOpacity
      style={[
        styles.clusterChip,
        {
          backgroundColor: active ? c.brand : accent,
          borderColor: active ? c.brand : c.separator,
        },
      ]}
      onPress={onPress}
    >
      <Text
        style={[
          styles.clusterCategoryText,
          { color: active ? '#fff' : accentText },
        ]}
      >
        {cluster.category_zh}
      </Text>
      <Text
        style={[
          styles.clusterCountText,
          { color: active ? '#fff' : c.labelTertiary },
        ]}
      >
        {cluster.hits}/{cluster.total}
      </Text>
    </TouchableOpacity>
  );
}

function SnpCard({
  item,
  expanded,
  onToggle,
  onPressDetail,
  c,
}: {
  item: GeneticReportItem;
  expanded: boolean;
  onToggle: () => void;
  onPressDetail: () => void;
  c: any;
}) {
  const isMiss = !item.hit;
  const riskColor = item.risk_level ? RISK_COLORS[item.risk_level] : null;

  return (
    <TouchableOpacity
      activeOpacity={0.85}
      onPress={onToggle}
      style={[
        styles.snpCard,
        {
          backgroundColor: c.bgCard,
          borderColor: c.separator,
          opacity: isMiss ? 0.5 : 1,
        },
      ]}
    >
      <View style={styles.snpHead}>
        <Text style={styles.snpEmoji}>🧬</Text>
        <View style={{ flex: 1 }}>
          <Text style={[styles.snpGene, { color: c.labelPrimary }]}>
            {item.gene}
            <Text style={[styles.snpVariant, { color: c.labelTertiary }]}> · {item.variant_name}</Text>
          </Text>
          {!isMiss ? (
            <Text style={[styles.snpResult, { color: c.labelSecondary }]} numberOfLines={1}>
              {item.genotype} · {item.result_label}
            </Text>
          ) : (
            <Text style={[styles.snpResult, { color: c.labelTertiary }]}>
              你这条还没测 / 数据缺失
            </Text>
          )}
        </View>
        {riskColor && (
          <View style={[styles.riskBadge, { backgroundColor: riskColor.bg }]}>
            <Text style={[styles.riskText, { color: riskColor.text }]}>{riskColor.label}</Text>
          </View>
        )}
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={16}
          color={c.labelTertiary}
        />
      </View>
      {expanded && (
        <View style={styles.snpExpand}>
          <Text style={[styles.snpDesc, { color: c.labelSecondary }]}>{item.description}</Text>
          <Text style={[styles.snpMeta, { color: c.labelTertiary }]}>
            {item.rsid} · {CATEGORY_LABELS[item.category] ?? item.category}
          </Text>

          {/* G-W3 Why 面板: related_cards 当前生效建议 + outcome chip */}
          {!isMiss && item.related_cards.length > 0 && (
            <View style={styles.relatedSection}>
              <Text style={[styles.relatedTitle, { color: c.labelTertiary }]}>
                基于这条基因, 当前已生效的建议:
              </Text>
              {item.related_cards.map(rc => (
                <RelatedCardRow key={rc.id} card={rc} c={c} />
              ))}
            </View>
          )}
          {!isMiss && item.related_cards.length === 0 && (
            <Text style={[styles.relatedNone, { color: c.labelTertiary }]}>
              暂无基于这条基因的活跃建议
            </Text>
          )}

          {/* G-W4: 跳详情页 (LLM 个性化建议在那里) */}
          {!isMiss && (
            <TouchableOpacity style={styles.detailLink} onPress={onPressDetail}>
              <Text style={[styles.detailLinkText, { color: c.brand }]}>查看 AI 详细解读</Text>
              <Ionicons name="chevron-forward" size={14} color={c.brand} />
            </TouchableOpacity>
          )}
        </View>
      )}
    </TouchableOpacity>
  );
}

// G-W3 Why 面板里单条建议行 — 显示 title + outcome chip + effect_size
function RelatedCardRow({ card, c }: { card: RelatedCard; c: any }) {
  const stage = stageOf(card);
  const stageColor = STAGE_COLORS[stage];
  return (
    <View style={[styles.relatedRow, { backgroundColor: c.bgPrimary }]}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Text style={[styles.relatedCardTitle, { color: c.labelPrimary, flex: 1 }]} numberOfLines={2}>
          {card.title}
        </Text>
        <EvidenceChip level={card.evidence_level} />
      </View>
      <View style={styles.relatedMetaRow}>
        <View style={[styles.stageChip, { backgroundColor: stageColor.bg }]}>
          <Text style={[styles.stageText, { color: stageColor.text }]}>{stageColor.label}</Text>
        </View>
        {card.outcome === 'improved' && card.effect_size != null && (
          <Text style={[styles.effectText, { color: '#15803D' }]}>
            ↑ {(Math.abs(card.effect_size) * 100).toFixed(0)}%
          </Text>
        )}
        {card.outcome === 'worsened' && card.effect_size != null && (
          <Text style={[styles.effectText, { color: '#B91C1C' }]}>
            ↓ {(Math.abs(card.effect_size) * 100).toFixed(0)}%
          </Text>
        )}
        {card.metric_key && card.actual_value && card.baseline_value && (
          <Text style={[styles.effectMeta, { color: c.labelTertiary }]}>
            {card.metric_key} {card.baseline_value} → {card.actual_value}
          </Text>
        )}
      </View>
    </View>
  );
}

type CardStage = 'pending' | 'accepted' | 'verifying' | 'closed_safe' | 'closed_worsened' | 'closed_inconclusive' | 'declined';

const STAGE_COLORS: Record<CardStage, { bg: string; text: string; label: string }> = {
  pending: { bg: '#F1F5F9', text: '#475569', label: '未决策' },
  accepted: { bg: '#DBEAFE', text: '#1E40AF', label: '已接受' },
  verifying: { bg: '#FEF3C7', text: '#92400E', label: '验证中' },
  closed_safe: { bg: '#D1FAE5', text: '#065F46', label: '✓ 已闭环' },
  closed_worsened: { bg: '#FEE2E2', text: '#991B1B', label: '⚠ 反向' },
  closed_inconclusive: { bg: '#F1F5F9', text: '#475569', label: '数据不足' },
  declined: { bg: '#F1F5F9', text: '#94A3B8', label: '已拒绝' },
};

function stageOf(card: RelatedCard): CardStage {
  if (card.user_decision === 'declined' || card.user_decision === 'dismissed' ||
      card.user_decision === 'false_positive') {
    return 'declined';
  }
  if (card.outcome === 'improved' || card.outcome === 'unchanged') return 'closed_safe';
  if (card.outcome === 'worsened') return 'closed_worsened';
  if (card.outcome === 'inconclusive' && card.graded_at) return 'closed_inconclusive';
  if (card.user_decision === 'accepted' && card.completed_at && !card.graded_at) return 'verifying';
  if (card.user_decision === 'accepted') return 'accepted';
  return 'pending';
}

// ─── styles ─────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32, gap: 12 },
  loadingText: { fontSize: 13 },
  errorText: { fontSize: 16, fontWeight: '600' },
  errorSub: { fontSize: 12, textAlign: 'center' },
  emptyTitle: { fontSize: 18, fontWeight: '600' },
  emptySub: { fontSize: 13, textAlign: 'center', lineHeight: 20 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  metaCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
  },
  metaTitle: { fontSize: 16, fontWeight: '600' },
  metaSub: { fontSize: 12, marginTop: 4 },
  agentCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 8,
  },
  agentHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  agentTitle: { fontSize: 13, fontWeight: '600' },
  agentBody: { fontSize: 14, lineHeight: 22 },
  predictionCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 8,
  },
  predictionRiskList: { gap: 6 },
  predictionRiskRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  predictionRiskGene: { fontSize: 13, fontWeight: '700', width: 68 },
  predictionRiskLabel: { flex: 1, fontSize: 12 },
  predictionText: { fontSize: 12, lineHeight: 18 },
  chipRow: { flexGrow: 0, marginVertical: spacing.xs },
  chip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 16,
    borderWidth: 1,
    marginRight: 8,
  },
  chipText: { fontSize: 12, fontWeight: '500' },
  toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  toggleText: { fontSize: 13 },
  snpCard: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: 8,
  },
  snpHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  snpEmoji: { fontSize: 18 },
  snpGene: { fontSize: 15, fontWeight: '600' },
  snpVariant: { fontSize: 13, fontWeight: '400' },
  snpResult: { fontSize: 13, marginTop: 2 },
  riskBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6 },
  riskText: { fontSize: 11, fontWeight: '600' },
  snpExpand: { gap: 6, paddingTop: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#E2E8F0' },
  snpDesc: { fontSize: 13, lineHeight: 18 },
  snpMeta: { fontSize: 11, fontFamily: 'Courier' },
  // G-W3 Why 面板
  relatedSection: { gap: 6, marginTop: 6 },
  relatedTitle: { fontSize: 11, fontWeight: '600' },
  relatedNone: { fontSize: 11, fontStyle: 'italic', marginTop: 4 },
  relatedRow: {
    borderRadius: 8,
    padding: 8,
    gap: 6,
  },
  relatedCardTitle: { fontSize: 13, fontWeight: '500', lineHeight: 18 },
  relatedMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  stageChip: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 4 },
  stageText: { fontSize: 10, fontWeight: '600' },
  effectText: { fontSize: 12, fontWeight: '700' },
  effectMeta: { fontSize: 10 },
  // G-W4 cluster 头 + 详情链接
  clusterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginVertical: spacing.xs,
  },
  clusterChip: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 10,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  clusterCategoryText: { fontSize: 12, fontWeight: '600' },
  clusterCountText: { fontSize: 11, fontFamily: 'Courier' },
  detailLink: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 4,
    paddingTop: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#E2E8F0',
    marginTop: 4,
  },
  detailLinkText: { fontSize: 12, fontWeight: '600' },
  empty: { textAlign: 'center', padding: spacing.xl, fontSize: 13 },
});
