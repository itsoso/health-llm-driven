import React, { useMemo } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import HealthCard from '../design-system/HealthCard';
import { radii, spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { OutcomeReviewMetric } from '../../services/personalOutcome';

interface Props {
  metrics: OutcomeReviewMetric[];
  coveredDays?: number;
  totalDays?: number;
}

function metricTone(metric: OutcomeReviewMetric, c: ColorPalette): string {
  if (!metric.delta) return c.labelSecondary;
  const firstDelta = Number(metric.delta.split('/')[0]);
  if (Number.isNaN(firstDelta) || firstDelta === 0) return c.labelSecondary;
  const improved = metric.desirable === 'down' ? firstDelta < 0 : metric.desirable === 'up' ? firstDelta > 0 : Math.abs(firstDelta) < 1;
  return improved ? '#0A8F8F' : '#FF9F0A';
}

export default function OutcomeReviewCard({ metrics, coveredDays, totalDays }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  if (metrics.length === 0) return null;

  return (
    <HealthCard
      title="阶段变化"
      icon="trending-up-outline"
      iconColor={c.brand}
      iconBg={c.brandLight}
      rightAccessory={coveredDays && totalDays ? <Text style={styles.coverage}>{coveredDays}/{totalDays}天</Text> : null}
    >
      <View style={styles.grid}>
        {metrics.slice(0, 5).map(metric => {
          const tone = metricTone(metric, c);
          return (
            <View key={metric.key} style={styles.metric}>
              <View style={styles.metricHeader}>
                <Text style={styles.label}>{metric.label}</Text>
                {metric.delta ? <Ionicons name="swap-vertical" size={12} color={tone} /> : null}
              </View>
              <Text style={styles.value}>{metric.value}<Text style={styles.unit}>{metric.unit}</Text></Text>
              {metric.delta ? <Text style={[styles.delta, { color: tone }]}>{metric.delta}</Text> : null}
            </View>
          );
        })}
      </View>
    </HealthCard>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    grid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
    metric: {
      width: '31.8%',
      minHeight: 72,
      borderRadius: radii.md,
      backgroundColor: c.bgPrimary,
      padding: spacing.sm,
      justifyContent: 'space-between',
    },
    metricHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
    coverage: { fontSize: 11, color: c.labelTertiary },
    label: { fontSize: 11, color: c.labelSecondary },
    value: { fontSize: 17, fontWeight: '800', color: c.labelPrimary, fontVariant: ['tabular-nums'] },
    unit: { fontSize: 10, color: c.labelTertiary, fontWeight: '600' },
    delta: { fontSize: 11, fontWeight: '700' },
  });
}
