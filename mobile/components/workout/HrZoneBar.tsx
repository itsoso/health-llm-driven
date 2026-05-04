import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { HrZoneBucket } from '../../services/workouts';

const ZONE_COLORS: Record<string, string> = {
  Z1: '#A0D8B0',
  Z2: '#5EC380',
  Z3: '#FFB84D',
  Z4: '#FF8A3D',
  Z5: '#FF5B5B',
};
const ZONE_LABELS: Record<string, string> = {
  Z1: '极易', Z2: '有氧', Z3: '耐力', Z4: '阈值', Z5: '冲刺',
};

interface Props {
  zones: HrZoneBucket[];
}

/** HR 区间分布: 水平堆叠条 + 每 zone 的分钟数/百分比 */
export default function HrZoneBar({ zones }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  if (!zones || zones.length === 0) return null;

  const total = zones.reduce((s, z) => s + (z.percentage || 0), 0);
  if (total === 0) return null;

  return (
    <View>
      <View style={styles.barRow}>
        {zones.map((z) => {
          if (!z.percentage) return null;
          const color = ZONE_COLORS[z.zone] || c.fill;
          return (
            <View
              key={z.zone}
              style={{ flex: Math.max(0.001, z.percentage), height: 10, backgroundColor: color }}
            />
          );
        })}
      </View>
      <View style={styles.legend}>
        {zones.map((z) => {
          if (!z.minutes && !z.percentage) return null;
          const color = ZONE_COLORS[z.zone] || c.fill;
          return (
            <View key={z.zone} style={styles.legendItem}>
              <View style={[styles.dot, { backgroundColor: color }]} />
              <Text style={styles.zoneLabel}>
                {z.zone} {ZONE_LABELS[z.zone] ? `· ${ZONE_LABELS[z.zone]}` : ''}
              </Text>
              <Text style={styles.zoneValue}>
                {Math.round(z.minutes)} min · {Math.round(z.percentage)}%
              </Text>
            </View>
          );
        })}
      </View>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    barRow: {
      flexDirection: 'row',
      borderRadius: 5,
      overflow: 'hidden',
      marginBottom: 10,
    },
    legend: { gap: 4 },
    legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
    dot: { width: 10, height: 10, borderRadius: 5 },
    zoneLabel: { fontSize: 12, color: c.labelSecondary, flex: 1 } as TextStyle,
    zoneValue: {
      fontSize: 12, color: c.labelPrimary, fontWeight: '500',
      fontVariant: ['tabular-nums'] as const,
    } as TextStyle,
  });
}
