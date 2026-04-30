/**
 * Reasoning Trace 详情 - "为什么 AI 这样判断?"
 *
 * 展开单条决策: evidence + 置信度 + rule + outcome + 关联记忆
 */
import React from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useTraceDetail } from '../../hooks/useReasoningTrace';
import type { TraceMemoryFact } from '../../services/reasoningTrace';
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
const TIER_COLOR: Record<string, string> = {
  working: colors.blue,
  episodic: colors.teal,
  semantic: colors.brand,
  procedural: colors.purple,
};
const TIER_LABEL: Record<string, string> = {
  working: '临时',
  episodic: '情节',
  semantic: '语义',
  procedural: '操作',
};

function Section({ icon, title, color, children }: {
  icon: keyof typeof Ionicons.glyphMap; title: string; color: string; children: React.ReactNode;
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeader}>
        <View style={[styles.sectionIcon, { backgroundColor: `${color}18` }]}>
          <Ionicons name={icon} size={16} color={color} />
        </View>
        <Text style={styles.sectionTitle}>{title}</Text>
      </View>
      <View style={styles.sectionBody}>{children}</View>
    </View>
  );
}

function FactRow({ f }: { f: TraceMemoryFact }) {
  const tierColor = TIER_COLOR[f.tier] ?? colors.labelTertiary;
  return (
    <View style={styles.factRow}>
      <View style={[styles.tierBadge, { backgroundColor: `${tierColor}18` }]}>
        <Text style={[styles.tierBadgeText, { color: tierColor }]}>{TIER_LABEL[f.tier] ?? f.tier}</Text>
      </View>
      <View style={styles.factBody}>
        <Text style={styles.factSentence}>
          <Text style={styles.factSubject}>{f.subject}</Text>
          <Text style={styles.factPredicate}> {f.predicate} </Text>
          <Text style={styles.factObject}>
            {f.object_value}{f.object_unit ? ` ${f.object_unit}` : ''}
          </Text>
        </Text>
        <Text style={styles.factConf}>置信度 {(f.confidence * 100).toFixed(0)}%</Text>
      </View>
    </View>
  );
}

export default function TraceDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { data: t, isLoading, isRefetching, refetch } = useTraceDetail(id ?? null);

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe}><View style={styles.center}>
        <ActivityIndicator size="large" color={colors.brand} />
      </View></SafeAreaView>
    );
  }
  if (!t) {
    return (
      <SafeAreaView style={styles.safe}><View style={styles.center}>
        <Text style={styles.emptyTitle}>找不到该决策记录</Text>
        <TouchableOpacity onPress={() => router.back()} style={{ marginTop: spacing.md }}>
          <Text style={{ color: colors.brand, fontSize: 15 }}>返回</Text>
        </TouchableOpacity>
      </View></SafeAreaView>
    );
  }

  const sevColor = SEV_COLOR[t.severity] ?? colors.labelTertiary;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>决策回放</Text>
        <View style={{ width: 32 }} />
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />}
      >
        {/* Hero */}
        <View style={[styles.hero, { borderLeftColor: sevColor }]}>
          <View style={styles.heroTop}>
            <View style={[styles.sevChip, { backgroundColor: `${sevColor}18` }]}>
              <View style={[styles.sevDot, { backgroundColor: sevColor }]} />
              <Text style={[styles.sevText, { color: sevColor }]}>{SEV_LABEL[t.severity] ?? t.severity}</Text>
            </View>
            <View style={{ flex: 1 }} />
            <View style={styles.confBadge}>
              <Text style={styles.confBadgeLabel}>置信度</Text>
              <Text style={styles.confBadgeValue}>{(t.confidence * 100).toFixed(0)}%</Text>
            </View>
          </View>
          <Text style={styles.heroTitle}>{t.title}</Text>
          <Text style={styles.heroMessage}>{t.message}</Text>
          <Text style={styles.heroTime}>
            {t.timestamp ? new Date(t.timestamp).toLocaleString('zh-CN') : ''}
          </Text>
        </View>

        {/* 2. 为什么 - Evidence */}
        <Section icon="pulse-outline" title="为什么 · 触发数据" color={colors.blue}>
          {t.evidence.metric && (
            <View style={styles.evidenceGrid}>
              <View style={styles.evidenceCell}>
                <Text style={styles.evidenceCellLabel}>指标</Text>
                <Text style={styles.evidenceCellValue}>{t.evidence.metric}</Text>
              </View>
              {t.evidence.current !== null && (
                <View style={styles.evidenceCell}>
                  <Text style={styles.evidenceCellLabel}>当前值</Text>
                  <Text style={[styles.evidenceCellValue, { color: sevColor, fontSize: 18 }]}>
                    {t.evidence.current}
                  </Text>
                </View>
              )}
              {t.evidence.baseline !== null && (
                <View style={styles.evidenceCell}>
                  <Text style={styles.evidenceCellLabel}>基线</Text>
                  <Text style={styles.evidenceCellValue}>{t.evidence.baseline}</Text>
                </View>
              )}
              {t.evidence.deviation_pct !== null && (
                <View style={styles.evidenceCell}>
                  <Text style={styles.evidenceCellLabel}>偏离</Text>
                  <Text style={[styles.evidenceCellValue, { color: sevColor }]}>
                    {t.evidence.deviation_pct > 0 ? '+' : ''}{t.evidence.deviation_pct.toFixed(1)}%
                  </Text>
                </View>
              )}
              {t.evidence.threshold !== null && (
                <View style={styles.evidenceCell}>
                  <Text style={styles.evidenceCellLabel}>阈值</Text>
                  <Text style={styles.evidenceCellValue}>{t.evidence.threshold}%</Text>
                </View>
              )}
            </View>
          )}
        </Section>

        {/* 1. 什么决策 - Rule */}
        <Section icon="construct-outline" title="决策规则" color={colors.labelSecondary}>
          <View style={styles.ruleBox}>
            <View style={styles.ruleRow}>
              <Text style={styles.ruleLabel}>规则 ID</Text>
              <Text style={styles.ruleValueMono}>{t.rule.id}</Text>
            </View>
            <View style={styles.ruleRow}>
              <Text style={styles.ruleLabel}>执行引擎</Text>
              <Text style={styles.ruleValueMono}>{t.rule.engine}</Text>
            </View>
            <View style={styles.ruleRow}>
              <Text style={styles.ruleLabel}>类别</Text>
              <Text style={styles.ruleValueMono}>{t.rule.category}</Text>
            </View>
          </View>
        </Section>

        {/* 3. 结果 - Outcome */}
        {t.outcome && (
          <Section icon="flag-outline" title="产出的行动" color={colors.brand}>
            <TouchableOpacity
              style={styles.outcomeCard}
              accessibilityLabel="查看行动卡详情"
            >
              <View style={styles.outcomeRow}>
                <Ionicons name="bookmark" size={18} color={colors.brand} />
                <Text style={styles.outcomeTitle} numberOfLines={2}>{t.outcome.title}</Text>
              </View>
              <View style={styles.outcomeMeta}>
                <View style={styles.outcomeStatusChip}>
                  <Text style={styles.outcomeStatusText}>{t.outcome.status}</Text>
                </View>
                {t.outcome.check_back_date && (
                  <Text style={styles.outcomeDate}>
                    复查日期: {new Date(t.outcome.check_back_date).toLocaleDateString('zh-CN')}
                  </Text>
                )}
              </View>
            </TouchableOpacity>
          </Section>
        )}

        {/* Arbitration extra: specialists + caveats */}
        {t.decision_type === 'llm_arbitration' && t.arbitration_extra && (
          <Section icon="people-outline" title="冲突仲裁详情" color={colors.orange}>
            <View style={styles.arbRow}>
              <Text style={styles.arbLabel}>裁决</Text>
              <Text style={styles.arbValue}>{t.arbitration_extra.winning_side}</Text>
            </View>
            <View style={styles.arbRow}>
              <Text style={styles.arbLabel}>处理冲突</Text>
              <Text style={styles.arbValue}>{t.arbitration_extra.conflicts_addressed} 个</Text>
            </View>
            {t.arbitration_extra.specialists_involved.length > 0 && (
              <View style={styles.arbSpecialists}>
                <Text style={styles.arbLabel}>涉及 specialist</Text>
                <View style={styles.arbChipRow}>
                  {t.arbitration_extra.specialists_involved.map((s) => (
                    <View key={s} style={styles.arbChip}>
                      <Text style={styles.arbChipText}>{s}</Text>
                    </View>
                  ))}
                </View>
              </View>
            )}
            {t.arbitration_extra.caveats.length > 0 && (
              <View style={{ marginTop: spacing.sm, gap: 6 }}>
                <Text style={styles.arbLabel}>注意事项</Text>
                {t.arbitration_extra.caveats.map((c, i) => (
                  <View key={i} style={styles.caveatRow}>
                    <Ionicons name="alert-circle-outline" size={14} color={colors.orange} />
                    <Text style={styles.caveatText}>{c}</Text>
                  </View>
                ))}
              </View>
            )}
          </Section>
        )}

        {/* 4. 关联记忆 - Memory Facts (Sprint 5 KG) */}
        {t.related_memory.length > 0 && (
          <Section icon="git-branch-outline" title={`关联记忆 · ${t.related_memory.length} 条`} color={colors.purple}>
            <Text style={styles.sectionSubtitle}>
              系统在做这个判断时参考了以下相关事实 (个人知识图谱 Sprint 5):
            </Text>
            <View style={styles.factList}>
              {t.related_memory.map((f) => <FactRow key={f.id} f={f} />)}
            </View>
          </Section>
        )}

        {/* Footer hint */}
        <View style={styles.footerHint}>
          <Ionicons name="shield-checkmark-outline" size={14} color={colors.labelTertiary} />
          <Text style={styles.footerHintText}>
            这是一次确定性规则的决策, 不是 LLM 的"黑盒判断".
            {'\n'}如果你不同意这个判断, 可以到"行动"页面忽略.
          </Text>
        </View>
      </ScrollView>
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
  scroll: { flex: 1 },
  scrollContent: { padding: spacing.md, paddingBottom: 100 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.lg },
  emptyTitle: { fontSize: 16, color: colors.labelSecondary },

  hero: {
    backgroundColor: colors.bgCard, borderRadius: radii.md,
    padding: spacing.md, marginBottom: spacing.md,
    borderLeftWidth: 4, gap: spacing.sm,
  },
  heroTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  sevChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 },
  sevDot: { width: 6, height: 6, borderRadius: 3 },
  sevText: { fontSize: 12, fontWeight: '600' as const },
  confBadge: { alignItems: 'flex-end' },
  confBadgeLabel: { fontSize: 10, color: colors.labelTertiary },
  confBadgeValue: { fontSize: 16, fontWeight: '700' as const, color: colors.labelPrimary, fontVariant: ['tabular-nums' as const] },
  heroTitle: { fontSize: 18, fontWeight: '700' as const, color: colors.labelPrimary },
  heroMessage: { fontSize: 14, color: colors.labelSecondary, lineHeight: 20 },
  heroTime: { fontSize: 11, color: colors.labelTertiary },

  section: {
    backgroundColor: colors.bgCard, borderRadius: radii.md,
    padding: spacing.md, marginBottom: spacing.md, gap: spacing.sm,
  },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sectionIcon: { width: 28, height: 28, borderRadius: 14, justifyContent: 'center', alignItems: 'center' },
  sectionTitle: { fontSize: 14, fontWeight: '600' as const, color: colors.labelPrimary },
  sectionSubtitle: { fontSize: 12, color: colors.labelTertiary, lineHeight: 16 },
  sectionBody: { gap: spacing.sm },

  evidenceGrid: { flexDirection: 'row', flexWrap: 'wrap' as const, gap: spacing.sm },
  evidenceCell: {
    minWidth: '30%', padding: spacing.sm, borderRadius: 8,
    backgroundColor: colors.bgPrimary,
  },
  evidenceCellLabel: { fontSize: 10, color: colors.labelTertiary, marginBottom: 2 },
  evidenceCellValue: { fontSize: 14, fontWeight: '600' as const, color: colors.labelPrimary, fontVariant: ['tabular-nums' as const] },

  ruleBox: { gap: 6 },
  ruleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  ruleLabel: { fontSize: 12, color: colors.labelSecondary },
  ruleValueMono: { fontSize: 12, color: colors.labelPrimary, fontFamily: 'monospace' },

  outcomeCard: {
    backgroundColor: colors.brandLight, borderRadius: 10, padding: spacing.sm, gap: 6,
  },
  outcomeRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  outcomeTitle: { flex: 1, fontSize: 14, fontWeight: '600' as const, color: colors.labelPrimary },
  outcomeMeta: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginLeft: 26 },
  outcomeStatusChip: { backgroundColor: colors.bgCard, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
  outcomeStatusText: { fontSize: 10, color: colors.labelSecondary },
  outcomeDate: { fontSize: 11, color: colors.labelTertiary },

  factList: { gap: 6 },
  factRow: { flexDirection: 'row', gap: 8, alignItems: 'flex-start' },
  tierBadge: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, minWidth: 40, alignItems: 'center' },
  tierBadgeText: { fontSize: 10, fontWeight: '600' as const },
  factBody: { flex: 1 },
  factSentence: { fontSize: 13, lineHeight: 18 },
  factSubject: { fontWeight: '600' as const, color: colors.labelPrimary },
  factPredicate: { color: colors.labelTertiary, fontStyle: 'italic' as const },
  factObject: { color: colors.labelPrimary },
  factConf: { fontSize: 10, color: colors.labelTertiary, marginTop: 2 },

  footerHint: {
    flexDirection: 'row', gap: 8, padding: spacing.md,
    backgroundColor: colors.fill, borderRadius: 8,
  },
  footerHintText: { flex: 1, fontSize: 11, color: colors.labelSecondary, lineHeight: 16 },

  arbRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  arbLabel: { fontSize: 12, color: colors.labelSecondary },
  arbValue: { fontSize: 13, fontWeight: '600' as const, color: colors.labelPrimary },
  arbSpecialists: { gap: 4 },
  arbChipRow: { flexDirection: 'row', gap: 6, flexWrap: 'wrap' as const },
  arbChip: { backgroundColor: colors.fill, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  arbChipText: { fontSize: 11, color: colors.labelSecondary, fontFamily: 'monospace' },
  caveatRow: { flexDirection: 'row', gap: 6, alignItems: 'flex-start' },
  caveatText: { flex: 1, fontSize: 12, color: colors.labelPrimary, lineHeight: 16 },
});
