/**
 * Reasoning Trace - 决策历史列表
 *
 * 阶段 4.5 (2): 让"AI 为什么这样判断"对用户可见.
 *
 * 每条 trace 回答 3 个问题:
 *   - 什么决策? (规则 / specialist)
 *   - 为什么触发? (数据 + 阈值)
 *   - 结果是什么? (ActionCard / 推送)
 *
 * B 端意义: 可解释性护城河.
 */
import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, FlatList,
  ActivityIndicator, RefreshControl, ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useRecentTraces } from '../../hooks/useReasoningTrace';
import type { ReasoningTrace } from '../../services/reasoningTrace';
import { colors, spacing, radii, typography } from '../../constants/theme';

const SEV_COLOR: Record<string, string> = {
  critical: colors.red,
  warning: colors.amber,
  info: colors.labelTertiary,
};
const SEV_LABEL: Record<string, string> = {
  critical: '紧急',
  warning: '关注',
  info: '提示',
};

function fmtRelative(iso: string | null): string {
  if (!iso) return '';
  const diffD = Math.floor((Date.now() - new Date(iso).getTime()) / 86400_000);
  if (diffD === 0) return '今天';
  if (diffD === 1) return '昨天';
  if (diffD < 7) return `${diffD} 天前`;
  return new Date(iso).toLocaleDateString('zh-CN');
}

function TraceRow({ t, onPress }: { t: ReasoningTrace; onPress: () => void }) {
  const sevColor = SEV_COLOR[t.severity] ?? colors.labelTertiary;
  const hasOutcome = !!t.outcome;
  const hasMemory = t.related_memory.length > 0;
  const isArbitration = t.decision_type === 'llm_arbitration';
  return (
    <TouchableOpacity style={styles.row} onPress={onPress} accessibilityLabel={`${t.title}, ${t.message}`}>
      <View style={styles.rowHeader}>
        {isArbitration ? (
          <View style={[styles.typeBadge, { backgroundColor: `${colors.orange}18` }]}>
            <Ionicons name="people" size={12} color={colors.orange} />
          </View>
        ) : (
          <View style={[styles.sevDot, { backgroundColor: sevColor }]} />
        )}
        <Text style={styles.rowTitle} numberOfLines={1}>{t.title}</Text>
        <View style={[styles.sevChip, { backgroundColor: `${sevColor}18` }]}>
          <Text style={[styles.sevText, { color: sevColor }]}>{SEV_LABEL[t.severity] ?? t.severity}</Text>
        </View>
      </View>

      <Text style={styles.rowMessage} numberOfLines={2}>{t.message}</Text>

      {/* Evidence bar */}
      {t.evidence.current !== null && t.evidence.baseline !== null && (
        <View style={styles.evidenceBar}>
          <View style={styles.evidenceItem}>
            <Text style={styles.evidenceLabel}>当前</Text>
            <Text style={styles.evidenceValueAccent}>{t.evidence.current}</Text>
          </View>
          <Ionicons name="arrow-forward" size={10} color={colors.labelTertiary} />
          <View style={styles.evidenceItem}>
            <Text style={styles.evidenceLabel}>基线</Text>
            <Text style={styles.evidenceValue}>{t.evidence.baseline}</Text>
          </View>
          {t.evidence.deviation_pct !== null && (
            <View style={[styles.evidenceItem, { marginLeft: 'auto' }]}>
              <Text style={styles.evidenceLabel}>偏离</Text>
              <Text style={[styles.evidenceValue, { color: sevColor }]}>
                {t.evidence.deviation_pct > 0 ? '+' : ''}{t.evidence.deviation_pct.toFixed(1)}%
              </Text>
            </View>
          )}
        </View>
      )}

      <View style={styles.rowFooter}>
        <View style={styles.ruleChip}>
          <Ionicons name="construct-outline" size={11} color={colors.labelSecondary} />
          <Text style={styles.ruleChipText}>{t.rule.engine} / {t.rule.id}</Text>
        </View>
        {hasOutcome && (
          <View style={[styles.outcomeChip, { backgroundColor: `${colors.brand}18` }]}>
            <Ionicons name="flag-outline" size={11} color={colors.brand} />
            <Text style={[styles.outcomeChipText, { color: colors.brand }]}>产出行动卡</Text>
          </View>
        )}
        {hasMemory && (
          <View style={styles.memoryChip}>
            <Ionicons name="git-branch-outline" size={11} color={colors.blue} />
            <Text style={[styles.outcomeChipText, { color: colors.blue }]}>{t.related_memory.length} 记忆</Text>
          </View>
        )}
        <Text style={styles.rowTime}>{fmtRelative(t.timestamp)}</Text>
      </View>
    </TouchableOpacity>
  );
}

export default function TraceListScreen() {
  const router = useRouter();
  const [includeSuppressed, setIncludeSuppressed] = useState(false);
  const { data, isLoading, isRefetching, refetch } = useRecentTraces({
    days: 30, limit: 50, include_suppressed: includeSuppressed,
  });

  const traces = data?.traces ?? [];
  const summary = data?.summary;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>推理回放</Text>
        <TouchableOpacity
          onPress={() => setIncludeSuppressed(!includeSuppressed)}
          style={styles.filterBtn}
          accessibilityLabel={includeSuppressed ? '隐藏已静默告警' : '显示已静默告警'}
        >
          <Ionicons
            name={includeSuppressed ? 'eye' : 'eye-off-outline'}
            size={20}
            color={includeSuppressed ? colors.brand : colors.labelTertiary}
          />
        </TouchableOpacity>
      </View>

      {/* Summary bar */}
      {summary && summary.total > 0 && (
        <ScrollView
          horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.summaryBar}
        >
          <View style={styles.summaryChip}>
            <Text style={styles.summaryChipLabel}>总计</Text>
            <Text style={styles.summaryChipValue}>{summary.total}</Text>
          </View>
          {Object.entries(summary.by_severity).map(([sev, n]) => (
            <View key={sev} style={styles.summaryChip}>
              <View style={[styles.sevDot, { backgroundColor: SEV_COLOR[sev] ?? colors.labelTertiary }]} />
              <Text style={styles.summaryChipLabel}>{SEV_LABEL[sev] ?? sev}</Text>
              <Text style={styles.summaryChipValue}>{n}</Text>
            </View>
          ))}
        </ScrollView>
      )}

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.brand} />
        </View>
      ) : traces.length === 0 ? (
        <View style={styles.center}>
          <View style={styles.emptyCircle}>
            <Ionicons name="git-network-outline" size={40} color={colors.labelTertiary} />
          </View>
          <Text style={styles.emptyTitle}>暂无决策记录</Text>
          <Text style={styles.emptySub}>
            AI 每次触发告警、产出行动卡都会在这里留下回放链条.{'\n'}
            打开 "显示已静默" 可以看被过滤掉的低优先级决策.
          </Text>
        </View>
      ) : (
        <FlatList
          data={traces}
          keyExtractor={(t) => t.id}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
          }
          renderItem={({ item }) => (
            <TraceRow t={item} onPress={() => router.push(`/trace/${item.id}`)} />
          )}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  backBtn: { width: 32, height: 32, justifyContent: 'center', alignItems: 'flex-start' },
  headerTitle: {
    flex: 1, textAlign: 'center',
    fontSize: typography.titleSmall.fontSize, fontWeight: '600' as const,
    color: colors.labelPrimary,
  },
  filterBtn: { width: 32, height: 32, justifyContent: 'center', alignItems: 'center' },

  summaryBar: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    gap: spacing.sm, flexDirection: 'row',
  },
  summaryChip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: colors.bgCard,
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 16,
  },
  summaryChipLabel: { fontSize: 11, color: colors.labelSecondary },
  summaryChipValue: { fontSize: 13, fontWeight: '600' as const, color: colors.labelPrimary },

  list: { padding: spacing.md, paddingBottom: 100 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: spacing.lg },
  emptyCircle: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: colors.fill, justifyContent: 'center', alignItems: 'center',
    marginBottom: spacing.md,
  },
  emptyTitle: { fontSize: 18, fontWeight: '600' as const, color: colors.labelPrimary, marginBottom: spacing.xs },
  emptySub: { fontSize: 14, color: colors.labelSecondary, textAlign: 'center', lineHeight: 20 },

  row: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  rowHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  sevDot: { width: 8, height: 8, borderRadius: 4 },
  typeBadge: {
    width: 20, height: 20, borderRadius: 10,
    justifyContent: 'center', alignItems: 'center',
  },
  rowTitle: { flex: 1, fontSize: 15, fontWeight: '600' as const, color: colors.labelPrimary },
  sevChip: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  sevText: { fontSize: 11, fontWeight: '600' as const },
  rowMessage: { fontSize: 13, color: colors.labelSecondary, lineHeight: 18 },

  evidenceBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: colors.bgPrimary, borderRadius: 8,
    paddingHorizontal: 10, paddingVertical: 8,
  },
  evidenceItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  evidenceLabel: { fontSize: 10, color: colors.labelTertiary },
  evidenceValue: { fontSize: 13, fontWeight: '600' as const, color: colors.labelSecondary, fontVariant: ['tabular-nums' as const] },
  evidenceValueAccent: { fontSize: 13, fontWeight: '700' as const, color: colors.labelPrimary, fontVariant: ['tabular-nums' as const] },

  rowFooter: {
    flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' as const,
  },
  ruleChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: colors.fill, borderRadius: 6,
    paddingHorizontal: 6, paddingVertical: 2,
  },
  ruleChipText: { fontSize: 10, color: colors.labelSecondary, fontFamily: 'monospace' },
  outcomeChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: colors.tintTeal, borderRadius: 6,
    paddingHorizontal: 6, paddingVertical: 2,
  },
  memoryChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: colors.tintBlue, borderRadius: 6,
    paddingHorizontal: 6, paddingVertical: 2,
  },
  outcomeChipText: { fontSize: 10, fontWeight: '600' as const },
  rowTime: { marginLeft: 'auto', fontSize: 11, color: colors.labelTertiary },
});
