import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import { radii, spacing } from '../../constants/theme';

interface Props {
  distanceKm: number | null;
  durationMin: number;
  avgPaceDisplay: string | null;   // e.g. "5:30"
  avgHr: number | null;
  workoutTypeLabel: string;
  dateLabel: string;
}

/**
 * 运动详情 Hero 卡: 顶部大字突出关键数据, 渐变底色.
 * 做分享海报时会重用这个组件的设计语言.
 */
export default function HeroMetrics({
  distanceKm, durationMin, avgPaceDisplay, avgHr, workoutTypeLabel, dateLabel,
}: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  return (
    <LinearGradient
      colors={[c.brand, '#15A5A5']}
      start={{ x: 0, y: 0 }}
      end={{ x: 1, y: 1 }}
      style={styles.hero}
    >
      <View style={styles.topRow}>
        <View style={styles.badge}>
          <Ionicons name="fitness" size={12} color="#fff" />
          <Text style={styles.badgeText}>{workoutTypeLabel}</Text>
        </View>
        <Text style={styles.dateText}>{dateLabel}</Text>
      </View>

      <View style={styles.distRow}>
        <Text style={styles.distValue}>{distanceKm != null ? distanceKm.toFixed(2) : '--'}</Text>
        <Text style={styles.distUnit}>km</Text>
      </View>

      <View style={styles.subRow}>
        <SubMetric label="配速" value={avgPaceDisplay || '--'} unit="/km" />
        <View style={styles.divider} />
        <SubMetric label="时长" value={String(durationMin)} unit="min" />
        <View style={styles.divider} />
        <SubMetric label="心率" value={avgHr != null ? String(avgHr) : '--'} unit="bpm" />
      </View>
    </LinearGradient>
  );
}

function SubMetric({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <View style={subStyles.col}>
      <Text style={subStyles.label}>{label}</Text>
      <View style={subStyles.valRow}>
        <Text style={subStyles.value}>{value}</Text>
        <Text style={subStyles.unit}>{unit}</Text>
      </View>
    </View>
  );
}

const subStyles = StyleSheet.create({
  col: { flex: 1, alignItems: 'center' },
  label: { fontSize: 11, color: 'rgba(255,255,255,0.75)', marginBottom: 2 } as TextStyle,
  valRow: { flexDirection: 'row', alignItems: 'baseline', gap: 2 },
  value: {
    fontSize: 20, fontWeight: '700', color: '#fff',
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  unit: { fontSize: 11, color: 'rgba(255,255,255,0.75)' } as TextStyle,
});

function createStyles(_c: ColorPalette) {
  return StyleSheet.create({
    hero: {
      borderRadius: radii.lg,
      padding: spacing.lg,
      marginBottom: spacing.md,
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.12,
      shadowRadius: 6,
      elevation: 3,
    },
    topRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
    badge: {
      flexDirection: 'row', alignItems: 'center', gap: 4,
      backgroundColor: 'rgba(255,255,255,0.18)',
      paddingHorizontal: 8, paddingVertical: 3,
      borderRadius: radii.full,
    },
    badgeText: { color: '#fff', fontSize: 11, fontWeight: '600' } as TextStyle,
    dateText: { color: 'rgba(255,255,255,0.8)', fontSize: 12 } as TextStyle,
    distRow: { flexDirection: 'row', alignItems: 'baseline', marginBottom: 14 },
    distValue: {
      fontSize: 52, fontWeight: '800', color: '#fff',
      fontVariant: ['tabular-nums'] as const,
      letterSpacing: -1,
    } as TextStyle,
    distUnit: { fontSize: 18, color: 'rgba(255,255,255,0.8)', marginLeft: 6, fontWeight: '500' } as TextStyle,
    subRow: {
      flexDirection: 'row',
      paddingTop: 12,
      borderTopWidth: StyleSheet.hairlineWidth,
      borderTopColor: 'rgba(255,255,255,0.25)',
    },
    divider: { width: StyleSheet.hairlineWidth, backgroundColor: 'rgba(255,255,255,0.25)', marginVertical: 4 },
  });
}
