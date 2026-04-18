import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, radii, shadows } from '@/constants/theme';

interface Props {
  sleep?: number | null;
  deepSleep?: number | null;
  heartRate?: number | null;
  hrv?: number | null;
  bodyBattery?: number | null;
  batteryMax?: number | null;
}

interface TileData {
  label: string;
  value: string;
  unit: string;
  sub?: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
}

export default function VitalsGrid({ sleep, deepSleep, heartRate, hrv, bodyBattery, batteryMax }: Props) {
  const tiles: TileData[] = [
    {
      label: '睡眠', icon: 'moon', color: '#BF5AF2', bg: '#F5E6FF',
      value: sleep != null ? sleep.toFixed(1) : '--', unit: 'h',
      sub: deepSleep != null ? `深睡 ${deepSleep.toFixed(1)}h` : undefined,
    },
    {
      label: '心率', icon: 'heart', color: '#FF375F', bg: '#FFE6EE',
      value: heartRate != null ? `${heartRate}` : '--', unit: 'bpm',
      sub: '静息心率',
    },
    {
      label: 'HRV', icon: 'pulse', color: '#5AC8FA', bg: '#E6F8FF',
      value: hrv != null ? `${hrv.toFixed(1)}` : '--', unit: 'ms',
    },
    {
      label: '电量', icon: 'battery-charging', color: '#30D158', bg: '#E8FAF0',
      value: bodyBattery != null ? `${bodyBattery}` : '--', unit: '',
      sub: batteryMax != null ? `最高 ${batteryMax}` : undefined,
    },
  ];

  return (
    <View style={styles.grid}>
      {tiles.map(t => (
        <View key={t.label} style={styles.tile}>
          <View style={styles.tileHeader}>
            <View style={[styles.iconDot, { backgroundColor: t.bg }]}>
              <Ionicons name={t.icon as any} size={14} color={t.color} />
            </View>
            <Text style={txt.label}>{t.label}</Text>
          </View>
          <View style={styles.valueRow}>
            <Text style={[txt.value, { color: t.color }]}>{t.value}</Text>
            {t.unit ? <Text style={[txt.unit, { color: t.color }]}>{t.unit}</Text> : null}
          </View>
          {t.sub && <Text style={txt.sub}>{t.sub}</Text>}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row', flexWrap: 'wrap',
    gap: spacing.md, marginBottom: spacing.lg,
  },
  tile: {
    width: '47.5%',
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    padding: 14,
    ...shadows.subtle,
  },
  tileHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8,
  },
  iconDot: {
    width: 26, height: 26, borderRadius: 8,
    alignItems: 'center', justifyContent: 'center',
  },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 3 },
});

const txt = {
  label: { fontSize: 13, fontWeight: '500', color: colors.labelSecondary } as TextStyle,
  value: { fontSize: 28, fontWeight: '800', fontVariant: ['tabular-nums'] as const, letterSpacing: -1 } as TextStyle,
  unit: { fontSize: 14, fontWeight: '500' } as TextStyle,
  sub: { fontSize: 11, color: colors.labelTertiary, marginTop: 4 } as TextStyle,
};
