import React from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import Svg, { Polyline, Rect, Line, Text as SvgText } from 'react-native-svg';
import { colors, typography, spacing, radii, shadows } from '@/constants/theme';

interface ChartData {
  label: string;
  value: number;
}

interface Props {
  title: string;
  data: ChartData[];
  color: string;
  type?: 'bar' | 'line';
  unit?: string;
}

function MiniChart({ title, data, color, type = 'bar', unit = '' }: Props) {
  const chartW = 200;
  const chartH = 60;
  const pad = 4;
  const maxVal = Math.max(...data.map(d => d.value), 1);

  const barWidth = (chartW - pad * 2) / data.length - 4;

  const points = data.map((d, i) => {
    const x = pad + (i / (data.length - 1 || 1)) * (chartW - pad * 2);
    const y = chartH - pad - (d.value / maxVal) * (chartH - pad * 2);
    return `${x},${y}`;
  }).join(' ');

  const latest = data.length > 0 ? data[data.length - 1].value : 0;
  const displayVal = Number.isInteger(latest) ? `${latest}` : latest.toFixed(1);

  return (
    <View style={styles.chartCard}>
      <View style={styles.chartHeader}>
        <Text style={styles.chartTitle}>{title}</Text>
        <Text style={[styles.chartValue, { color }]}>{displayVal}{unit}</Text>
      </View>
      <Svg width={chartW} height={chartH}>
        {type === 'bar' ? (
          data.map((d, i) => {
            const x = pad + i * ((chartW - pad * 2) / data.length) + 2;
            const h = (d.value / maxVal) * (chartH - pad * 2);
            const y = chartH - pad - h;
            return (
              <Rect
                key={i}
                x={x}
                y={y}
                width={barWidth}
                height={Math.max(h, 2)}
                rx={barWidth / 2}
                fill={i === data.length - 1 ? color : `${color}60`}
              />
            );
          })
        ) : (
          <>
            <Polyline
              points={points}
              fill="none"
              stroke={color}
              strokeWidth={2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            {/* Latest point dot */}
            {data.length > 0 && (() => {
              const lastX = pad + ((data.length - 1) / (data.length - 1 || 1)) * (chartW - pad * 2);
              const lastY = chartH - pad - (latest / maxVal) * (chartH - pad * 2);
              return <Rect x={lastX - 3} y={lastY - 3} width={6} height={6} rx={3} fill={color} />;
            })()}
          </>
        )}
      </Svg>
      <View style={styles.chartLabels}>
        {data.length > 0 && <Text style={styles.chartLabel}>{data[0].label}</Text>}
        {data.length > 1 && <Text style={styles.chartLabel}>{data[data.length - 1].label}</Text>}
      </View>
    </View>
  );
}

interface TrendProps {
  garminDays: any[];
}

export default function TrendMiniCharts({ garminDays }: TrendProps) {
  if (!garminDays || garminDays.length < 2) return null;

  const days = garminDays.slice(0, 7).reverse(); // oldest first for chart
  const fmt = (d: string) => d?.slice(5) || ''; // MM-DD

  const sleepData = days.map(d => ({ label: fmt(d.record_date), value: (d.total_sleep_duration || 0) / 60 }));
  const hrData = days.map(d => ({ label: fmt(d.record_date), value: d.resting_heart_rate || 0 }));
  const stepsData = days.map(d => ({ label: fmt(d.record_date), value: d.steps || 0 }));
  const hrvData = days.map(d => ({ label: fmt(d.record_date), value: d.hrv || 0 }));

  return (
    <View style={styles.container}>
      <Text style={styles.sectionTitle}>本周趋势</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
        <MiniChart title="睡眠" data={sleepData} color="#BF5AF2" type="bar" unit="h" />
        <MiniChart title="心率" data={hrData} color="#FF375F" type="line" unit="bpm" />
        <MiniChart title="步数" data={stepsData} color="#FF6723" type="bar" />
        <MiniChart title="HRV" data={hrvData} color="#5AC8FA" type="line" unit="ms" />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { marginBottom: spacing.md },
  sectionTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: colors.labelPrimary,
    marginBottom: spacing.md,
    paddingHorizontal: 2,
  },
  scrollContent: { gap: spacing.md, paddingRight: spacing.xl },
  chartCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    padding: spacing.md,
    width: 220,
    ...shadows.subtle,
  },
  chartHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  chartTitle: { fontSize: 13, fontWeight: '600', color: colors.labelSecondary },
  chartValue: { fontSize: 17, fontWeight: '700' },
  chartLabels: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  chartLabel: { fontSize: 10, color: colors.labelTertiary },
});
