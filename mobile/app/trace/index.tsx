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

// rule.id → 人话标题 + 主题图标. 后端 title 是 "metric_name rule_id" 的字面拼接 (如 "spo2_avg spo2_low"),
// 这里重写为用户可读的一行. 未知 rule.id 降级为 t.title (能显示就行).
const RULE_LABEL: Record<string, { title: string; icon: keyof typeof Ionicons.glyphMap; color: string }> = {
  spo2_low: { title: '血氧偏低', icon: 'medkit-outline', color: colors.red },
  spo2_drop: { title: '血氧下降', icon: 'trending-down-outline', color: colors.red },
  battery_low: { title: '身体电量不足', icon: 'battery-dead-outline', color: colors.amber },
  hrv_drop: { title: 'HRV 下降', icon: 'pulse-outline', color: colors.amber },
  hrv_low: { title: 'HRV 偏低', icon: 'pulse-outline', color: colors.amber },
  resting_hr_high: { title: '静息心率偏高', icon: 'heart-outline', color: colors.red },
  resting_hr_drop: { title: '静息心率下降', icon: 'heart-outline', color: colors.labelTertiary },
  sleep_short: { title: '睡眠偏短', icon: 'moon-outline', color: colors.amber },
  sleep_debt: { title: '睡眠负债累积', icon: 'moon-outline', color: colors.amber },
  stress_high: { title: '压力偏高', icon: 'alert-circle-outline', color: colors.amber },
  steps_low: { title: '活动不足', icon: 'walk-outline', color: colors.labelTertiary },
  weight_gain: { title: '体重上升', icon: 'trending-up-outline', color: colors.amber },
  weight_loss: { title: '体重下降', icon: 'trending-down-outline', color: colors.amber },
  bp_high: { title: '血压偏高', icon: 'heart-circle-outline', color: colors.red },
  bp_low: { title: '血压偏低', icon: 'heart-circle-outline', color: colors.amber },
};

function humanize(t: ReasoningTrace): { title: string; icon: keyof typeof Ionicons.glyphMap; color: string } {
  const cfg = RULE_LABEL[t.rule.id];
  if (cfg) return cfg;
  // 降级: 用原始 title, 按 severity 涂色, 通用图标
  return {
    title: t.title || t.rule.id || '未分类决策',
    icon: 'information-circle-outline',
    color: SEV_COLOR[t.severity] ?? colors.labelTertiary,
  };
}

// 剥消息尾部的礼貌冗余: "...,请注意" / "...,请关注" 等
const MESSAGE_SUFFIX_RE = /[,，]?\s*请(注意|关注|留意|观察)[。.!！]?\s*$/;
function cleanMessage(msg: string): string {
  return (msg || '').replace(MESSAGE_SUFFIX_RE, '').trim();
}

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
  const { title, icon, color } = humanize(t);
  const cleanMsg = cleanMessage(t.message);

  return (
    <TouchableOpacity style={styles.row} onPress={onPress} accessibilityLabel={`${title}, ${cleanMsg}`}>
      <View style={styles.rowHeader}>
        {isArbitration ? (
          <View style={[styles.typeBadge, { backgroundColor: `${colors.orange}18` }]}>
            <Ionicons name="people" size={14} color={colors.orange} />
          </View>
        ) : (
          <View style={[styles.typeBadge, { backgroundColor: `${color}18` }]}>
            <Ionicons name={icon} size={14} color={color} />
          </View>
        )}
        <Text style={styles.rowTitle} numberOfLines={1}>{title}</Text>
        <View style={[styles.sevChip, { backgroundColor: `${sevColor}18` }]}>
          <Text style={[styles.sevText, { color: sevColor }]}>{SEV_LABEL[t.severity] ?? t.severity}</Text>
        </View>
      </View>

      {cleanMsg ? <Text style={styles.rowMessage} numberOfLines={2}>{cleanMsg}</Text> : null}

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
    width: 24, height: 24, borderRadius: 8,
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
