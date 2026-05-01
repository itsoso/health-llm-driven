/**
 * Clinical Journal - Case Timeline 详情
 *
 * 按时间倒序展示一个 case_thread 下的所有 SOAP entries.
 * 每条 entry 可展开查看 subjective / objective / assessment / plan 四字段.
 */
import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  ActivityIndicator, RefreshControl, LayoutAnimation, Platform, UIManager,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { useCaseDetail } from '../../../hooks/useClinicalJournal';
import type { JournalEntry } from '../../../services/clinicalJournal';
import { colors, spacing, radii, typography } from '../../../constants/theme';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

const STATUS_COLOR: Record<string, string> = {
  active: colors.amber,
  monitoring: colors.blue,
  resolved: colors.green,
};
const STATUS_LABEL: Record<string, string> = {
  active: '跟进中',
  monitoring: '观察中',
  resolved: '已收尾',
};

const CREATED_BY_LABEL: Record<string, string> = {
  briefing_task: '每日简报',
  doctor_weekly_task: '医生周报',
  orchestrator: 'AI 对话',
};

function fmtDate(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  if (isToday) {
    return `今天 ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`;
  }
  const diffDays = Math.floor((today.getTime() - d.getTime()) / 86400_000);
  if (diffDays === 1) return `昨天 ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`;
  if (diffDays < 7) return `${diffDays} 天前`;
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' });
}

function SoapField({ label, value, color }: { label: string; value: string | null; color: string }) {
  if (!value) return null;
  return (
    <View style={styles.soapField}>
      <View style={[styles.soapLabelWrap, { backgroundColor: `${color}18` }]}>
        <Text style={[styles.soapLabel, { color }]}>{label}</Text>
      </View>
      <Text style={styles.soapValue}>{value}</Text>
    </View>
  );
}

function EntryCard({ entry }: { entry: JournalEntry }) {
  const [expanded, setExpanded] = useState(false);
  const createdByLabel = CREATED_BY_LABEL[entry.created_by ?? ''] ?? entry.created_by ?? '';

  // 折叠态: 只显示 assessment 首行 + plan 首行
  const assessmentPreview = (entry.assessment ?? '').split('\n')[0];
  const planPreview = (entry.plan ?? '').split('\n')[0];

  return (
    <View style={styles.entryCard}>
      <View style={styles.entryHeader}>
        <View style={styles.entryDot} />
        <Text style={styles.entryDate}>{fmtDate(entry.generated_at)}</Text>
        {createdByLabel && (
          <View style={styles.sourceChip}>
            <Text style={styles.sourceText}>{createdByLabel}</Text>
          </View>
        )}
      </View>

      <TouchableOpacity
        onPress={() => {
          LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
          setExpanded(!expanded);
        }}
        activeOpacity={0.7}
      >
        {expanded ? (
          <View style={styles.soapBody}>
            <SoapField label="S 主诉" value={entry.subjective} color={colors.blue} />
            <SoapField label="O 数据" value={entry.objective} color={colors.teal} />
            <SoapField label="A 评估" value={entry.assessment} color={colors.amber} />
            <SoapField label="P 计划" value={entry.plan} color={colors.green} />
            {entry.used_specialists.length > 0 && (
              <View style={styles.metaRow}>
                <Ionicons name="people-outline" size={12} color={colors.labelTertiary} />
                <Text style={styles.metaText}>
                  由 {entry.used_specialists.join(' / ')} 生成
                </Text>
              </View>
            )}
            {entry.related_action_card_ids.length > 0 && (
              <View style={styles.metaRow}>
                <Ionicons name="bookmark-outline" size={12} color={colors.labelTertiary} />
                <Text style={styles.metaText}>关联行动卡: {entry.related_action_card_ids.length} 张</Text>
              </View>
            )}
          </View>
        ) : (
          <View style={styles.collapsedBody}>
            {!!assessmentPreview && (
              <Text style={styles.collapsedLine} numberOfLines={2}>
                <Text style={{ color: colors.amber, fontWeight: '600' as const }}>评估 </Text>
                {assessmentPreview}
              </Text>
            )}
            {!!planPreview && (
              <Text style={styles.collapsedLine} numberOfLines={1}>
                <Text style={{ color: colors.green, fontWeight: '600' as const }}>计划 </Text>
                {planPreview}
              </Text>
            )}
            <Text style={styles.expandHint}>点击展开完整 SOAP →</Text>
          </View>
        )}
      </TouchableOpacity>
    </View>
  );
}

export default function CaseDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const caseId = id ? parseInt(id, 10) : null;
  const { data: caseData, isLoading, isRefetching, refetch } = useCaseDetail(caseId);

  if (isLoading) {
    return (
      <SafeAreaView style={styles.safe}>
        <Stack.Screen options={{ headerShown: false }} />
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.brand} />
        </View>
      </SafeAreaView>
    );
  }

  if (!caseData) {
    return (
      <SafeAreaView style={styles.safe}>
        <Stack.Screen options={{ headerShown: false }} />
        <View style={styles.center}>
          <Text style={styles.emptyTitle}>找不到该案例</Text>
          <TouchableOpacity onPress={() => router.back()} style={styles.backLink}>
            <Text style={styles.backLinkText}>返回</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const statusColor = STATUS_COLOR[caseData.status] ?? colors.labelTertiary;

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} accessibilityLabel="返回">
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>{caseData.title ?? caseData.theme}</Text>
        <View style={{ width: 32 }} />
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />}
      >
        <View style={styles.hero}>
          <View style={[styles.statusChipLarge, { backgroundColor: `${statusColor}18` }]}>
            <Ionicons name="ellipse" size={8} color={statusColor} />
            <Text style={[styles.statusTextLarge, { color: statusColor }]}>
              {STATUS_LABEL[caseData.status] ?? caseData.status}
            </Text>
          </View>
          {!!caseData.summary && (
            <Text style={styles.summary}>{caseData.summary}</Text>
          )}
          <View style={styles.heroMeta}>
            <Ionicons name="time-outline" size={13} color={colors.labelTertiary} />
            <Text style={styles.heroMetaText}>
              开案 {caseData.opened_at ? new Date(caseData.opened_at).toLocaleDateString('zh-CN') : '-'}
              · 共 {caseData.entries.length} 条记录
            </Text>
          </View>
        </View>

        {caseData.entries.length === 0 ? (
          <View style={styles.emptyEntries}>
            <Text style={styles.emptySub}>暂无记录</Text>
          </View>
        ) : (
          <View style={styles.timeline}>
            {caseData.entries.map((e) => (
              <EntryCard key={e.id} entry={e} />
            ))}
          </View>
        )}
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
  scrollContent: { padding: spacing.md, paddingBottom: 120 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.lg },
  emptyTitle: { fontSize: 16, color: colors.labelSecondary },
  emptySub: { fontSize: 14, color: colors.labelTertiary },
  backLink: { marginTop: spacing.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backLinkText: { fontSize: 15, color: colors.brand, fontWeight: '500' as const },

  hero: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.md,
    padding: spacing.md,
    marginBottom: spacing.md,
    gap: spacing.sm,
  },
  statusChipLarge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    alignSelf: 'flex-start',
    paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10,
  },
  statusTextLarge: { fontSize: 12, fontWeight: '600' as const },
  summary: { fontSize: 14, color: colors.labelPrimary, lineHeight: 20 },
  heroMeta: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  heroMetaText: { fontSize: 12, color: colors.labelTertiary },

  timeline: { gap: spacing.sm },
  emptyEntries: { padding: spacing.lg, alignItems: 'center' },
  entryCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  entryHeader: {
    flexDirection: 'row', alignItems: 'center', gap: spacing.sm,
  },
  entryDot: {
    width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brand,
  },
  entryDate: {
    fontSize: 13, fontWeight: '600' as const, color: colors.labelPrimary,
  },
  sourceChip: {
    marginLeft: 'auto',
    backgroundColor: colors.fill,
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8,
  },
  sourceText: { fontSize: 11, color: colors.labelSecondary },

  collapsedBody: { gap: 4 },
  collapsedLine: { fontSize: 13, color: colors.labelSecondary, lineHeight: 18 },
  expandHint: { fontSize: 11, color: colors.labelTertiary, marginTop: 4 },

  soapBody: { gap: spacing.sm },
  soapField: { gap: 4 },
  soapLabelWrap: {
    alignSelf: 'flex-start',
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 6,
  },
  soapLabel: { fontSize: 11, fontWeight: '600' as const },
  soapValue: { fontSize: 13, color: colors.labelPrimary, lineHeight: 20 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 },
  metaText: { fontSize: 11, color: colors.labelTertiary },
});
