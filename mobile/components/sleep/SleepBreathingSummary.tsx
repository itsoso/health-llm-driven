import React, { useMemo } from 'react';
import { Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import HealthCard from '../design-system/HealthCard';
import { radii, spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface Props {
  date?: string;
  odi?: number | null;
  minSpO2?: number | null;
  eventCount?: number | null;
  onOpenAnalysis: () => void;
}

function metricTone(metric: 'odi' | 'spo2', value: number | null | undefined, c: ColorPalette): string {
  if (value == null) return c.labelPrimary;
  if (metric === 'odi') {
    if (value >= 15) return '#FF453A';
    if (value >= 5) return '#FF9F0A';
    return '#0A8F8F';
  }
  if (value < 85) return '#FF453A';
  if (value < 90) return '#FF9F0A';
  return '#0A8F8F';
}

export default function SleepBreathingSummary({
  date,
  odi,
  minSpO2,
  eventCount,
  onOpenAnalysis,
}: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);
  return (
    <HealthCard
      title="睡眠呼吸"
      icon="pulse-outline"
      iconColor="#007AFF"
      iconBg="#E6F0FF"
      rightAccessory={date ? <Text style={txt.date}>{date}</Text> : null}
    >
      <View style={styles.metricRow}>
        <BreathingMetric label="ODI" value={odi != null ? odi.toFixed(1) : '--'} unit="/h" color={metricTone('odi', odi, c)} txt={txt} styles={styles} />
        <BreathingMetric label="最低 SpO2" value={minSpO2 != null ? `${minSpO2}` : '--'} unit="%" color={metricTone('spo2', minSpO2, c)} txt={txt} styles={styles} />
        <BreathingMetric label="氧降事件" value={eventCount != null ? String(eventCount) : '--'} unit="次" color={c.labelPrimary} txt={txt} styles={styles} />
      </View>
      <Pressable
        style={({ pressed }) => [styles.actionBtn, pressed && styles.actionBtnPressed]}
        onPress={onOpenAnalysis}
        accessibilityRole="button"
        accessibilityLabel="打开夜间血氧根因分析"
      >
        <Ionicons name="analytics-outline" size={15} color={c.brand} />
        <Text style={txt.action}>查看根因与今晚实验</Text>
        <Ionicons name="chevron-forward" size={15} color={c.brand} />
      </Pressable>
    </HealthCard>
  );
}

function BreathingMetric({
  label, value, unit, color, txt, styles,
}: {
  label: string; value: string; unit: string; color: string;
  txt: ReturnType<typeof createTxt>; styles: ReturnType<typeof createStyles>;
}) {
  return (
    <View style={styles.metric}>
      <Text style={[txt.metricValue, { color }]}>{value}<Text style={txt.metricUnit}>{unit}</Text></Text>
      <Text style={txt.metricLabel}>{label}</Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    metricRow: { flexDirection: 'row', gap: spacing.sm },
    metric: {
      flex: 1,
      minHeight: 68,
      borderRadius: radii.md,
      backgroundColor: c.bgPrimary,
      alignItems: 'center',
      justifyContent: 'center',
      paddingHorizontal: 8,
    },
    actionBtn: {
      minHeight: 40,
      borderRadius: radii.md,
      backgroundColor: c.brandLight,
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      marginTop: spacing.md,
    },
    actionBtnPressed: { opacity: 0.82 },
  });
}

function createTxt(c: ColorPalette) {
  return {
    date: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    metricValue: { fontSize: 20, fontWeight: '800', fontVariant: ['tabular-nums'] as const } as TextStyle,
    metricUnit: { fontSize: 11, fontWeight: '600', color: c.labelTertiary } as TextStyle,
    metricLabel: { fontSize: 11, color: c.labelSecondary, marginTop: 3 } as TextStyle,
    action: { fontSize: 13, fontWeight: '700', color: c.brand } as TextStyle,
  };
}
