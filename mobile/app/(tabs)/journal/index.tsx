/**
 * Clinical Journal - Case List
 *
 * 阶段 4.5 (1): 让 Sprint 5 的记忆层对用户可见.
 * 列出所有 case_threads (按最近活跃排序), 点进去看时间线.
 */
import React from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, FlatList,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, Stack } from 'expo-router';
import { useCaseList } from '../../../hooks/useClinicalJournal';
import type { CaseSummary } from '../../../services/clinicalJournal';
import { colors, spacing, radii, typography } from '../../../constants/theme';

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

const THEME_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  daily_briefing: 'today-outline',
  doctor_weekly_summary: 'medical-outline',
  sleep: 'moon-outline',
  hrv: 'pulse-outline',
  rhr: 'heart-outline',
  weight: 'scale-outline',
  bp: 'heart-circle-outline',
  spo2: 'cloud-outline',
  rhinitis: 'rainy-outline',
  mental: 'chatbubbles-outline',
};

function fmtRelative(iso: string | null): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  const diffMin = Math.floor((Date.now() - t) / 60_000);
  if (diffMin < 2) return '刚刚';
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} 小时前`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD} 天前`;
  return new Date(iso).toLocaleDateString('zh-CN');
}

function CaseRow({ c, onPress }: { c: CaseSummary; onPress: () => void }) {
  const icon = THEME_ICON[c.theme] ?? 'document-text-outline';
  const statusColor = STATUS_COLOR[c.status] ?? colors.labelTertiary;
  return (
    <TouchableOpacity style={styles.row} onPress={onPress} accessibilityLabel={`${c.title ?? c.theme}, ${c.entry_count} 条记录`}>
      <View style={[styles.iconBox, { backgroundColor: `${statusColor}18` }]}>
        <Ionicons name={icon} size={20} color={statusColor} />
      </View>
      <View style={styles.rowMain}>
        <View style={styles.rowTop}>
          <Text style={styles.title} numberOfLines={1}>{c.title ?? c.theme}</Text>
          <View style={[styles.statusChip, { backgroundColor: `${statusColor}18` }]}>
            <Text style={[styles.statusText, { color: statusColor }]}>{STATUS_LABEL[c.status] ?? c.status}</Text>
          </View>
        </View>
        {!!c.summary && (
          <Text style={styles.summary} numberOfLines={2}>{c.summary}</Text>
        )}
        <View style={styles.rowMeta}>
          <Text style={styles.meta}>{c.entry_count} 条记录</Text>
          <Text style={styles.metaDot}>·</Text>
          <Text style={styles.meta}>{fmtRelative(c.last_updated_at)}</Text>
        </View>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.labelTertiary} />
    </TouchableOpacity>
  );
}

export default function JournalListScreen() {
  const router = useRouter();
  const { data: cases, isLoading, isRefetching, refetch } = useCaseList();

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.header}>
        <Text style={styles.headerTitle}>案例时间线</Text>
      </View>

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={colors.brand} />
        </View>
      ) : !cases || cases.length === 0 ? (
        <View style={styles.center}>
          <View style={styles.emptyCircle}>
            <Ionicons name="document-text-outline" size={40} color={colors.labelTertiary} />
          </View>
          <Text style={styles.emptyTitle}>暂无案例记录</Text>
          <Text style={styles.emptySub}>
            每次 AI 分析、每日简报、医生周报都会在这里自动记录 SOAP 笔记.{'\n'}
            系统会按主题 (睡眠 / HRV / 鼻炎 等) 自动归类.
          </Text>
        </View>
      ) : (
        <FlatList
          data={cases}
          keyExtractor={(c) => String(c.id)}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brand} />
          }
          renderItem={({ item }) => (
            <CaseRow c={item} onPress={() => router.push(`/journal/${item.id}`)} />
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
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  headerTitle: {
    fontSize: typography.titleSmall.fontSize, fontWeight: '600' as const,
    color: colors.labelPrimary,
  },
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
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
    backgroundColor: colors.bgCard, borderRadius: radii.md,
    padding: spacing.md,
  },
  iconBox: {
    width: 40, height: 40, borderRadius: 20,
    justifyContent: 'center', alignItems: 'center',
  },
  rowMain: { flex: 1, gap: 4 },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  title: { flex: 1, fontSize: 15, fontWeight: '600' as const, color: colors.labelPrimary },
  summary: { fontSize: 13, color: colors.labelSecondary, lineHeight: 18 },
  rowMeta: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
  meta: { fontSize: 11, color: colors.labelTertiary },
  metaDot: { fontSize: 11, color: colors.labelTertiary },
  statusChip: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  statusText: { fontSize: 11, fontWeight: '600' as const },
});
