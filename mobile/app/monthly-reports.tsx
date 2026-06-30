import React, { useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, TextStyle,
  FlatList, ActivityIndicator, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';

import { spacing, radii, shadows } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import {
  listMyMonthlyReports, formatMonth, relativeTime,
  type MonthlyReportSummary,
} from '../services/monthlyReports';

const QK = ['monthlyReports'];

export default function MonthlyReportsScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();

  const { data, isLoading, isRefetching, refetch } = useQuery<MonthlyReportSummary[]>({
    queryKey: QK,
    queryFn: () => listMyMonthlyReports(24),
    staleTime: 60_000,
  });

  const now = new Date();
  // 默认展示近 12 个月占位（包含未生成的月份，点进去 lazy-generate）
  const placeholderMonths = buildRecentMonths(12, now);
  const byKey = new Map<string, MonthlyReportSummary>();
  (data || []).forEach(r => byKey.set(`${r.year}-${r.month}`, r));

  const rows = placeholderMonths.map(({ year, month }) => {
    const key = `${year}-${month}`;
    return byKey.get(key) ?? {
      year, month, generated_at: null,
      coverage_pct: 0, hit_rate: 0, total_graded: 0,
      narrative: '',
    };
  });

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>月度复盘</Text>
        <View style={{ width: 40 }} />
      </View>

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={c.brand} />
        </View>
      ) : (
        <FlatList
          data={rows}
          keyExtractor={(r) => `${r.year}-${r.month}`}
          contentContainerStyle={styles.content}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />
          }
          renderItem={({ item }) => (
            <ReportRow
              item={item}
              onPress={() => router.push({
                pathname: '/monthly-report/[year]/[month]' as any,
                params: { year: String(item.year), month: String(item.month) },
              })}
            />
          )}
          ListHeaderComponent={
            <Text style={txt.intro}>
              每月 1 日自动生成上月复盘 · 点击查看详情（未生成的会在点击后即时构建）
            </Text>
          }
        />
      )}
    </SafeAreaView>
  );
}

function ReportRow({ item, onPress }: {
  item: MonthlyReportSummary; onPress: () => void;
}) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const notReady = item.generated_at === null;
  return (
    <TouchableOpacity style={styles.card} onPress={onPress} activeOpacity={0.7}>
      <View style={styles.rowTop}>
        <Text style={txt.monthLabel}>{formatMonth(item.year, item.month)}</Text>
        {notReady ? (
          <Text style={txt.pending}>未生成</Text>
        ) : (
          <Text style={txt.generatedAt}>
            {relativeTime(item.generated_at)}
          </Text>
        )}
      </View>
      {!notReady && (
        <View style={styles.rowMeta}>
          <Stat label="数据覆盖" value={`${item.coverage_pct.toFixed(0)}%`} />
          <Stat label="AI 命中率" value={item.total_graded ? `${item.hit_rate.toFixed(0)}%` : '—'} />
          <Stat label="评分条数" value={String(item.total_graded)} />
        </View>
      )}
      {item.narrative ? (
        <Text style={txt.narrative} numberOfLines={2}>{item.narrative}</Text>
      ) : notReady ? (
        <Text style={txt.placeholder}>点击查看本月数据</Text>
      ) : null}
    </TouchableOpacity>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <View>
      <Text style={txt.statLabel}>{label}</Text>
      <Text style={txt.statValue}>{value}</Text>
    </View>
  );
}

function buildRecentMonths(n: number, now: Date): { year: number; month: number }[] {
  const out: { year: number; month: number }[] = [];
  let y = now.getFullYear();
  let m = now.getMonth() + 1;  // JS month is 0-indexed
  // 从当前月开始向前 n 个月 (含当前月，若是 1 号就排除)
  // 实际只显示已结束的月份：若今天是 1 号则排除当月
  if (now.getDate() === 1) {
    m -= 1; if (m === 0) { m = 12; y -= 1; }
  }
  for (let i = 0; i < n; i++) {
    out.push({ year: y, month: m });
    m -= 1; if (m === 0) { m = 12; y -= 1; }
  }
  return out;
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: { flex: 1, backgroundColor: c.bgPrimary },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  content: { padding: spacing.lg, paddingBottom: 60 },
  card: {
    backgroundColor: c.bgCard, borderRadius: radii.lg,
    padding: spacing.lg, marginBottom: spacing.md,
    ...shadows.subtle,
  },
  rowTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  rowMeta: {
    flexDirection: 'row', justifyContent: 'space-between',
    marginTop: spacing.md, paddingVertical: spacing.sm,
  },
});

const createTxt = (c: ColorPalette) => ({
  title: {
    fontSize: 17, fontWeight: '600', color: c.labelPrimary,
    flex: 1, textAlign: 'center',
  } as TextStyle,
  intro: {
    fontSize: 12, color: c.labelTertiary,
    marginBottom: spacing.md, lineHeight: 18,
  } as TextStyle,
  monthLabel: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
  generatedAt: { fontSize: 12, color: c.labelTertiary } as TextStyle,
  pending: { fontSize: 12, color: c.brand, fontWeight: '500' } as TextStyle,
  statLabel: { fontSize: 11, color: c.labelTertiary, marginBottom: 2 } as TextStyle,
  statValue: { fontSize: 15, fontWeight: '600', color: c.labelPrimary } as TextStyle,
  narrative: {
    fontSize: 13, color: c.labelSecondary, lineHeight: 19,
    marginTop: spacing.sm,
  } as TextStyle,
  placeholder: {
    fontSize: 13, color: c.labelTertiary,
    marginTop: spacing.sm, fontStyle: 'italic',
  } as TextStyle,
});
