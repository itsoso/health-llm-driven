import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, FlatList, ActivityIndicator, TextStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { listConsultations, type ConsultListItem } from '../services/consultations';
import { buildOutcomeReviewMetrics, getMyOutcomeTimeline } from '../services/personalOutcome';
import OutcomeReviewCard from '../components/outcome/OutcomeReviewCard';
import { spacing, radii, shadows } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';

const TYPE_LABEL: Record<string, string> = {
  symptom_advisory: '症状',
  lifestyle_advice: '生活',
  preventive_review: '预防',
  urgent: '紧急',
  followup: '随访',
};

const TYPE_COLOR: Record<string, { bg: string; fg: string }> = {
  urgent: { bg: '#FFEDEC', fg: '#C62828' },
  symptom_advisory: { bg: '#EEF2FF', fg: '#3730A3' },
  lifestyle_advice: { bg: '#E0F2FE', fg: '#075985' },
  preventive_review: { bg: '#D1FAE5', fg: '#065F46' },
  followup: { bg: '#FEF3C7', fg: '#92400E' },
};

const STATUS_COLOR: Record<string, { bg: string; fg: string }> = {
  active: { bg: '#D1FAE5', fg: '#065F46' },
  verified: { bg: '#DBEAFE', fg: '#1E40AF' },
  superseded: { bg: '#E5E7EB', fg: '#4B5563' },
  archived: { bg: '#E5E7EB', fg: '#6B7280' },
};

function fmtDate(s?: string) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return s ? s.slice(0, 10) : '—';
}

function ConsultationRow({ item, onPress }: { item: ConsultListItem; onPress: () => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const typeColor = TYPE_COLOR[item.consultation_type] || { bg: '#F3F4F6', fg: '#374151' };
  const statusColor = STATUS_COLOR[item.status] || { bg: '#F3F4F6', fg: '#4B5563' };
  return (
    <TouchableOpacity onPress={onPress} style={styles.row} activeOpacity={0.7}>
      <View style={styles.rowTopline}>
        <Text style={txt.version}>v{item.version}</Text>
        <View style={[styles.badge, { backgroundColor: statusColor.bg }]}>
          <Text style={[txt.badgeText, { color: statusColor.fg }]}>{item.status}</Text>
        </View>
        <View style={[styles.badge, { backgroundColor: typeColor.bg }]}>
          <Text style={[txt.badgeText, { color: typeColor.fg }]}>
            {TYPE_LABEL[item.consultation_type] || item.consultation_type}
          </Text>
        </View>
        {item.red_flag_count > 0 && (
          <View style={[styles.badge, { backgroundColor: '#FFEDEC' }]}>
            <Text style={[txt.badgeText, { color: '#C62828' }]}>⚠ {item.red_flag_count} 警戒</Text>
          </View>
        )}
        {item.pending_count > 0 && (
          <View style={styles.pendingCount}>
            <Text style={txt.pendingCountNum}>{item.pending_count}</Text>
            <Text style={txt.pendingCountLabel}>pending</Text>
          </View>
        )}
      </View>
      <Text style={txt.title} numberOfLines={1}>{item.title}</Text>
      {item.topic ? <Text style={txt.topic} numberOfLines={1}>🏷 {item.topic}</Text> : null}
      {item.summary ? <Text style={txt.summary} numberOfLines={2}>{item.summary}</Text> : null}

      <View style={styles.statRow}>
        {item.hypothesis_count > 0 && <Text style={txt.stat}>🧠 假设 {item.hypothesis_count}</Text>}
        {item.action_count > 0 && <Text style={txt.stat}>✓ 行动 {item.action_count}</Text>}
        {item.prediction_count > 0 && <Text style={txt.stat}>📊 预测 {item.prediction_count}</Text>}
        {item.red_flag_count > 0 && <Text style={[txt.stat, { color: '#C62828' }]}>⚠ 警戒 {item.red_flag_count}</Text>}
      </View>

      <View style={styles.metaRow}>
        <Text style={txt.meta}>{fmtDate(item.created_at)}</Text>
        {item.verification_scheduled_at && (
          <>
            <Text style={txt.meta}>·</Text>
            <Text style={txt.meta}>下次复盘 {fmtDate(item.verification_scheduled_at)}</Text>
          </>
        )}
      </View>
    </TouchableOpacity>
  );
}

export default function ConsultationsScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  const router = useRouter();
  const { data = [], isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: ['consultations', 'list'],
    queryFn: () => listConsultations(30),
    staleTime: 60_000,
  });
  const { data: outcome } = useQuery({
    queryKey: ['personalOutcome', 'timeline', '6m', 'month'],
    queryFn: () => getMyOutcomeTimeline('6m', 'month'),
    staleTime: 300_000,
  });
  const outcomeMetrics = buildOutcomeReviewMetrics(outcome);
  const outcomeCard = (
    <OutcomeReviewCard
      metrics={outcomeMetrics}
      coveredDays={outcome?.summary?.covered_days}
      totalDays={outcome?.summary?.total_days}
    />
  );

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.headerTitle}>健康咨询中心</Text>
        <View style={styles.backBtn} />
      </View>
      <Text style={txt.headerSub}>
        多层级症状咨询追踪。每次咨询包含假设 / 行动 / 可检验预测 / 警戒信号四类。
        预测会在到期时自动对比 Garmin 和体检数据做回测。
      </Text>

      {isLoading ? (
        <View style={styles.loading}>
          <ActivityIndicator size="large" color={c.brand} />
        </View>
      ) : isError ? (
        <View style={styles.empty}>
          <Text style={txt.emptyText}>加载失败，请下拉重试</Text>
        </View>
      ) : data.length === 0 ? (
        <View style={styles.empty}>
          {outcomeCard}
          <Text style={txt.emptyText}>暂无咨询记录。</Text>
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(it) => String(it.id)}
          contentContainerStyle={styles.list}
          refreshing={isRefetching}
          onRefresh={refetch}
          ListHeaderComponent={outcomeCard}
          renderItem={({ item }) => (
            <ConsultationRow item={item} onPress={() => router.push(`/consultations/${item.id}` as any)} />
          )}
        />
      )}
    </SafeAreaView>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  screen: { flex: 1, backgroundColor: c.bgPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
  },
  backBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl },
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  row: {
    backgroundColor: c.bgCard,
    borderRadius: radii.lg,
    padding: spacing.md,
    gap: 6,
    ...shadows.subtle,
  },
  rowTopline: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6 },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  pendingCount: { marginLeft: 'auto', alignItems: 'center' },
  statRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 },
  metaRow: { flexDirection: 'row', gap: 6, marginTop: 4 },
});

const createTxt = (c: ColorPalette) => ({
  headerTitle: { fontSize: 17, fontWeight: '700', color: c.labelPrimary } as TextStyle,
  headerSub: {
    fontSize: 12, color: c.labelSecondary,
    paddingHorizontal: spacing.lg, paddingBottom: spacing.md, lineHeight: 18,
  } as TextStyle,
  version: { fontSize: 11, fontWeight: '700', color: c.labelTertiary } as TextStyle,
  badgeText: { fontSize: 10, fontWeight: '600' } as TextStyle,
  pendingCountNum: { fontSize: 20, fontWeight: '800', color: '#EA580C' } as TextStyle,
  pendingCountLabel: { fontSize: 9, color: c.labelTertiary } as TextStyle,
  title: { fontSize: 15, fontWeight: '700', color: c.labelPrimary, marginTop: 4 } as TextStyle,
  topic: { fontSize: 10, color: c.labelTertiary } as TextStyle,
  summary: { fontSize: 12, color: c.labelSecondary, lineHeight: 18, marginTop: 2 } as TextStyle,
  stat: { fontSize: 10, color: c.labelSecondary } as TextStyle,
  meta: { fontSize: 10, color: c.labelTertiary } as TextStyle,
  emptyText: { fontSize: 13, color: c.labelTertiary } as TextStyle,
});
