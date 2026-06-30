import React, { useState, useMemo } from 'react';
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
import { spacing, typography, radii } from '../constants/theme'
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import type { TimeRange } from '../services/trends';
import { useWeightHistory, useBPHistory, useIndicatorTrend, useGarminMetricTrend, isGarminMetric } from '../hooks/useTrendData';
import TrendChart from '../components/charts/TrendChart';
import TimeRangeSelector from '../components/charts/TimeRangeSelector';
import AgentFeedbackLink from '../components/agent/AgentFeedbackLink';
import { createTrendAgentContext } from '../utils/agentContext';

const TYPE_TITLES: Record<string, string> = {
  weight: '体重趋势',
  blood_pressure: '血压趋势',
  heart_rate: '静息心率',
  hrv: 'HRV 趋势',
  body_battery: '身体电量',
  sleep: '睡眠时长',
  sleep_score: '睡眠评分',
  steps: '步数趋势',
};

function useHistoryData(type: string, range: TimeRange) {
  const weight = useWeightHistory(range);
  const bp = useBPHistory(range);
  const garmin = useGarminMetricTrend(isGarminMetric(type) ? type : '', range);
  const indicator = useIndicatorTrend(
    type !== 'weight' && type !== 'blood_pressure' && !isGarminMetric(type) ? type : '',
    range,
  );

  if (type === 'weight') return weight;
  if (type === 'blood_pressure') return bp;
  if (isGarminMetric(type)) return garmin;
  return indicator;
}

export default function IndicatorHistoryScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
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
          <Ionicons name="chevron-back" size={28} color={c.labelPrimary} />
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

        {series && series.length > 0 && (
          <AgentFeedbackLink
            label="跟 Agent 解读这个趋势"
            accessibilityLabel="跟 Agent 解读这个趋势"
            prompt={`请基于我的${title}做一次趋势复盘: 解释最近变化、可能诱因、接下来 7 天的行动和还需要补充记录的数据。`}
            context={createTrendAgentContext({ type, title, range, series })}
            badge={`基于${title} · ${range}`}
            style={styles.agentLink}
          />
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

const createStyles = (c: ColorPalette) => StyleSheet.create({
  safe: {
    flex: 1,
    backgroundColor: c.bgPrimary,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    backgroundColor: c.bgCard,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: c.separator,
  },
  headerTitle: {
    ...typography.titleSmall,
    color: c.labelPrimary,
  } as TextStyle,
  content: {
    padding: spacing.lg,
    paddingBottom: 40,
  },
  summaryCard: {
    backgroundColor: c.bgCard,
    borderRadius: radii.lg,
    padding: spacing.lg,
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  summaryLabel: {
    ...typography.caption,
    color: c.labelTertiary,
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
    color: c.labelPrimary,
  } satisfies TextStyle,
  summaryUnit: {
    ...typography.bodyMedium,
    color: c.labelSecondary,
  },
  summaryDate: {
    ...typography.caption,
    color: c.labelTertiary,
    marginTop: spacing.xs,
  },
  agentLink: {
    marginBottom: spacing.md,
  },
  loading: {
    height: 220,
    justifyContent: 'center',
    alignItems: 'center',
  },
  loadingText: {
    ...typography.bodyMedium,
    color: c.labelTertiary,
  },
  refInfo: {
    marginTop: spacing.lg,
    padding: spacing.md,
    backgroundColor: c.bgCard,
    borderRadius: radii.sm,
  },
  refText: {
    ...typography.caption,
    color: c.labelSecondary,
    marginBottom: 2,
  },
});
