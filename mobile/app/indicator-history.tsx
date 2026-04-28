import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  RefreshControl,
  TouchableOpacity,
  TextStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, typography, radii } from '../constants/theme';
import type { TimeRange } from '../services/trends';
import { useWeightHistory, useBPHistory, useIndicatorTrend } from '../hooks/useTrendData';
import TrendChart from '../components/charts/TrendChart';
import TimeRangeSelector from '../components/charts/TimeRangeSelector';

const TYPE_TITLES: Record<string, string> = {
  weight: '体重趋势',
  blood_pressure: '血压趋势',
};

function useHistoryData(type: string, range: TimeRange) {
  const weight = useWeightHistory(range);
  const bp = useBPHistory(range);
  const indicator = useIndicatorTrend(
    type !== 'weight' && type !== 'blood_pressure' ? type : '',
    range,
  );

  if (type === 'weight') return weight;
  if (type === 'blood_pressure') return bp;
  return indicator;
}

export default function IndicatorHistoryScreen() {
  const { type = 'weight' } = useLocalSearchParams<{ type: string }>();
  const router = useRouter();
  const [range, setRange] = useState<TimeRange>('1M');

  const { data: series, isLoading, refetch } = useHistoryData(type, range);
  const [refreshing, setRefreshing] = useState(false);

  const title = TYPE_TITLES[type] || `${type}趋势`;

  const onRefresh = async () => {
    setRefreshing(true);
    await refetch();
    setRefreshing(false);
  };

  const latestPoint = series?.[0]?.data?.at(-1);

  return (
    <SafeAreaView style={styles.safe}>
      {/* header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} testID="back-button">
          <Ionicons name="chevron-back" size={28} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{title}</Text>
        <View style={{ width: 28 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
      >
        {/* summary card */}
        {latestPoint && (
          <View style={styles.summaryCard}>
            <Text style={styles.summaryLabel}>最新记录</Text>
            <View style={styles.summaryRow}>
              <Text style={styles.summaryValue}>{latestPoint.value}</Text>
              {latestPoint.unit ? (
                <Text style={styles.summaryUnit}>{latestPoint.unit}</Text>
              ) : null}
            </View>
            <Text style={styles.summaryDate}>{latestPoint.date}</Text>
          </View>
        )}

        <TimeRangeSelector selected={range} onChange={setRange} />

        {isLoading ? (
          <View style={styles.loading}>
            <Text style={styles.loadingText}>加载中...</Text>
          </View>
        ) : (
          <TrendChart series={series ?? []} />
        )}

        {/* reference range legend */}
        {series?.some((s) => s.referenceRange) && (
          <View style={styles.refInfo}>
            {series
              .filter((s) => s.referenceRange)
              .map((s) => (
                <Text key={s.label} style={styles.refText}>
                  {s.label} 正常范围: {s.referenceRange!.low} - {s.referenceRange!.high}
                </Text>
              ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: colors.bgPrimary,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: colors.bgCard,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.separator,
  },
  headerTitle: {
    ...typography.titleSmall,
    color: colors.labelPrimary,
  } as TextStyle,
  content: {
    padding: spacing.lg,
    paddingBottom: 40,
  },
  summaryCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    padding: spacing.lg,
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  summaryLabel: {
    ...typography.caption,
    color: colors.labelTertiary,
    marginBottom: spacing.xs,
  },
  summaryRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: spacing.xs,
  },
  summaryValue: {
    fontSize: typography.metric.fontSize,
    fontWeight: typography.metric.fontWeight,
    lineHeight: typography.metric.lineHeight,
    fontVariant: ['tabular-nums'],
    color: colors.labelPrimary,
  } satisfies TextStyle,
  summaryUnit: {
    ...typography.bodyMedium,
    color: colors.labelSecondary,
  },
  summaryDate: {
    ...typography.caption,
    color: colors.labelTertiary,
    marginTop: spacing.xs,
  },
  loading: {
    height: 220,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    ...typography.bodyMedium,
    color: colors.labelTertiary,
  },
  refInfo: {
    marginTop: spacing.lg,
    padding: spacing.md,
    backgroundColor: colors.bgCard,
    borderRadius: radii.sm,
  },
  refText: {
    ...typography.caption,
    color: colors.labelSecondary,
    marginBottom: 2,
  },
});
