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
import { Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useQuery, useQueryClient } from '@tanstack/react-query';

import {
  fetchGeneticReport,
  type GeneticReport,
  type GeneticReportItem,
  CATEGORY_LABELS,
  RISK_COLORS,
} from '../services/geneticReport';
import { spacing, radii } from '../constants/theme';
import { useTheme } from '../hooks/useTheme';

export default function GeneticReportScreen() {
  const { c } = useTheme();
  const qc = useQueryClient();
  const [filterCat, setFilterCat] = useState<string | null>(null);
  const [showMisses, setShowMisses] = useState(false);
  const [expandedRsid, setExpandedRsid] = useState<Set<string>>(new Set());

  const { data, isLoading, isRefetching, error } = useQuery<GeneticReport>({
    queryKey: ['genetic-report'],
    queryFn: () => fetchGeneticReport(true),
    staleTime: 5 * 60 * 1000,
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
        <Stack.Screen options={{ title: '我的基因' }} />
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
      <Stack.Screen options={{ title: '我的基因', headerBackTitle: '返回' }} />
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
              <Text style={[styles.agentBody, { color: c.labelPrimary }]}>{data.agent_summary}</Text>
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

function SnpCard({
  item,
  expanded,
  onToggle,
  c,
}: {
  item: GeneticReportItem;
  expanded: boolean;
  onToggle: () => void;
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
          {/* G-W3 此处加: Why 面板 + 当前生效建议 link + outcome chip */}
        </View>
      )}
    </TouchableOpacity>
  );
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
  empty: { textAlign: 'center', padding: spacing.xl, fontSize: 13 },
});
