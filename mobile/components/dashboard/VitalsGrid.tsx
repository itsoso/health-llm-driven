import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface Props {
  sleep?: number | null;
  deepSleep?: number | null;
  sleepScore?: number | null;
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

export default function VitalsGrid({ sleep, deepSleep, sleepScore, heartRate, hrv, bodyBattery, batteryMax }: Props) {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);

  const tiles: TileData[] = [
    {
      label: '睡眠', icon: 'moon', color: c.purple, bg: c.tintPurple,
      value: sleep != null ? sleep.toFixed(1) : '--', unit: 'h',
      sub: sleepScore ? `评分 ${sleepScore}` : (deepSleep != null ? `深睡 ${deepSleep.toFixed(1)}h` : undefined),
    },
    {
      label: '心率', icon: 'heart', color: c.pink, bg: c.tintPink,
      value: heartRate != null ? `${heartRate}` : '--', unit: 'bpm',
      sub: '静息心率',
    },
    {
      label: 'HRV', icon: 'pulse', color: c.teal, bg: c.tintTeal,
      value: hrv != null ? `${hrv.toFixed(1)}` : '--', unit: 'ms',
    },
    {
      label: '电量', icon: 'battery-charging', color: c.green, bg: c.tintGreen,
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
            <Text style={styles.label}>{t.label}</Text>
          </View>
          <View style={styles.valueRow}>
            <Text style={[styles.value, { color: t.color }]}>{t.value}</Text>
            {t.unit ? <Text style={[styles.unit, { color: t.color }]}>{t.unit}</Text> : null}
          </View>
          {t.sub && <Text style={styles.sub}>{t.sub}</Text>}
        </View>
      ))}
    </View>
  );
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    grid: {
      flexDirection: 'row', flexWrap: 'wrap',
      gap: spacing.md, marginBottom: spacing.lg,
    },
    tile: {
      width: '47.5%',
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: 14,
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : {
            shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
            shadowOpacity: 0.06, shadowRadius: 3, elevation: 1,
          }),
    },
    tileHeader: {
      flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8,
    },
    iconDot: {
      width: 26, height: 26, borderRadius: 8,
      alignItems: 'center', justifyContent: 'center',
    },
    valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 3 },
    label: { fontSize: 13, fontWeight: '500', color: c.labelSecondary } as TextStyle,
    value: { fontSize: 28, fontWeight: '800', fontVariant: ['tabular-nums'] as const, letterSpacing: -1 } as TextStyle,
    unit: { fontSize: 14, fontWeight: '500' } as TextStyle,
    sub: { fontSize: 11, color: c.labelTertiary, marginTop: 4 } as TextStyle,
  });
}
