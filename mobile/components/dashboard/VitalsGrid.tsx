import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Polyline, Circle } from 'react-native-svg';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface GarminDay {
  record_date?: string;
  total_sleep_duration?: number | null;
  resting_heart_rate?: number | null;
  hrv?: number | null;
  body_battery_current?: number | null;
  body_battery_most_charged?: number | null;
}

interface Props {
  sleep?: number | null;
  deepSleep?: number | null;
  sleepScore?: number | null;
  heartRate?: number | null;
  hrv?: number | null;
  bodyBatteryCurrent?: number | null;
  bodyBatteryMax?: number | null;
  garminDays?: GarminDay[];
  onTilePress?: (metric: 'sleep' | 'heart_rate' | 'hrv' | 'body_battery') => void;
}

interface TileData {
  key: 'sleep' | 'heart_rate' | 'hrv' | 'body_battery';
  label: string;
  value: string;
  unit: string;
  sub?: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
  series: number[];
}

function pickSeries(days: GarminDay[], extract: (d: GarminDay) => number | null | undefined): number[] {
  return days
    .slice(0, 7)
    .reverse()
    .map(d => extract(d) ?? 0)
    .filter(v => Number.isFinite(v));
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  const w = 140;
  const h = 28;
  const pad = 3;

  if (!data || data.length < 2) {
    return <View style={{ height: h }} />;
  }

  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;

  const points = data.map((v, i) => {
    const x = pad + (i / (data.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  const lastX = pad + (w - pad * 2);
  const lastY = h - pad - ((data[data.length - 1] - min) / range) * (h - pad * 2);

  return (
    <Svg width={w} height={h}>
      <Polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.6}
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity={0.85}
      />
      <Circle cx={lastX} cy={lastY} r={2.5} fill={color} />
    </Svg>
  );
}

export default function VitalsGrid({
  sleep, deepSleep, sleepScore, heartRate, hrv,
  bodyBatteryCurrent, bodyBatteryMax, garminDays, onTilePress,
}: Props) {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);

  const days = Array.isArray(garminDays) ? garminDays : [];

  const sleepSeries = pickSeries(days, d => d.total_sleep_duration ? d.total_sleep_duration / 60 : null);
  const hrSeries = pickSeries(days, d => d.resting_heart_rate);
  const hrvSeries = pickSeries(days, d => d.hrv);
  const batterySeries = pickSeries(days, d => d.body_battery_current ?? d.body_battery_most_charged);

  const tiles: TileData[] = [
    {
      key: 'sleep',
      label: '睡眠', icon: 'moon', color: c.purple, bg: c.tintPurple,
      value: sleep != null ? sleep.toFixed(1) : '--', unit: 'h',
      sub: sleepScore ? `评分 ${sleepScore}` : (deepSleep != null ? `深睡 ${deepSleep.toFixed(1)}h` : undefined),
      series: sleepSeries,
    },
    {
      key: 'heart_rate',
      label: '心率', icon: 'heart', color: c.pink, bg: c.tintPink,
      value: heartRate != null ? `${heartRate}` : '--', unit: 'bpm',
      sub: '静息心率',
      series: hrSeries,
    },
    {
      key: 'hrv',
      label: 'HRV', icon: 'pulse', color: c.teal, bg: c.tintTeal,
      value: hrv != null ? `${hrv.toFixed(1)}` : '--', unit: 'ms',
      sub: '压力&恢复',
      series: hrvSeries,
    },
    {
      key: 'body_battery',
      label: '电量', icon: 'battery-charging', color: c.green, bg: c.tintGreen,
      value: bodyBatteryCurrent != null ? `${bodyBatteryCurrent}` : '--', unit: '',
      sub: bodyBatteryMax != null ? `今日峰值 ${bodyBatteryMax}` : '当前',
      series: batterySeries,
    },
  ];

  return (
    <View style={styles.grid}>
      {tiles.map(t => (
        <TouchableOpacity
          key={t.key}
          style={styles.tile}
          onPress={() => onTilePress?.(t.key)}
          activeOpacity={onTilePress ? 0.7 : 1}
          disabled={!onTilePress}
          accessibilityRole={onTilePress ? 'button' : undefined}
          accessibilityLabel={`${t.label} ${t.value}${t.unit}`}
        >
          <View style={styles.tileHeader}>
            <View style={[styles.iconDot, { backgroundColor: t.bg }]}>
              <Ionicons name={t.icon as any} size={14} color={t.color} />
            </View>
            <Text style={styles.label}>{t.label}</Text>
            {onTilePress && <Ionicons name="chevron-forward" size={12} color={c.labelTertiary} style={{ marginLeft: 'auto' }} />}
          </View>
          <View style={styles.valueRow}>
            <Text style={[styles.value, { color: t.color }]}>{t.value}</Text>
            {t.unit ? <Text style={[styles.unit, { color: t.color }]}>{t.unit}</Text> : null}
          </View>
          {t.sub && <Text style={styles.sub}>{t.sub}</Text>}
          <View style={styles.spark}>
            <Sparkline data={t.series} color={t.color} />
            {t.series.length >= 2 && <Text style={styles.sparkHint}>近 7 天</Text>}
          </View>
        </TouchableOpacity>
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
      flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6,
    },
    iconDot: {
      width: 24, height: 24, borderRadius: 7,
      alignItems: 'center', justifyContent: 'center',
    },
    valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 3 },
    label: { fontSize: 13, fontWeight: '500', color: c.labelSecondary } as TextStyle,
    value: { fontSize: 26, fontWeight: '800', fontVariant: ['tabular-nums'] as const, letterSpacing: -0.8 } as TextStyle,
    unit: { fontSize: 13, fontWeight: '500' } as TextStyle,
    sub: { fontSize: 11, color: c.labelTertiary, marginTop: 2 } as TextStyle,
    spark: { marginTop: 8, height: 32, justifyContent: 'flex-end' },
    sparkHint: { fontSize: 9, color: c.labelTertiary, marginTop: 1 } as TextStyle,
  });
}
