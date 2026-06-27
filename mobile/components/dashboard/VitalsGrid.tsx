import React from 'react';
import { View, Text, StyleSheet, TextStyle, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Polyline, Circle } from 'react-native-svg';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';
import { garminSleepHours, type GarminDailyRow } from '../../types/garmin';

// 每指标的装饰性 hue (睡眠紫 / 心率粉 / HRV 青 / 电量绿) —— 这是「区分指标」的色码,
// 不是「指标好坏」的三步临床语义,所以不用 revaSemantic。值即 Reva 亮色调色板原值。
const HUES = {
  purple: { color: '#7C5CBF', bg: '#EDE7F6' },
  pink: { color: '#C2487A', bg: '#F7E4EC' },
  teal: { color: '#2F9E8F', bg: '#E0EFEC' },
  green: { color: C.green500, bg: C.green50 },
} as const;

interface Props {
  sleep?: number | null;
  deepSleep?: number | null;
  sleepScore?: number | null;
  heartRate?: number | null;
  hrv?: number | null;
  bodyBatteryCurrent?: number | null;
  bodyBatteryMax?: number | null;
  garminDays?: GarminDailyRow[];
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

function pickSeries(days: GarminDailyRow[], extract: (d: GarminDailyRow) => number | null | undefined): number[] {
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
  const days = Array.isArray(garminDays) ? garminDays : [];

  // 睡眠单位换算 + 脏数据守卫走 types/garmin 的单一真相源
  const sleepSeries = pickSeries(days, d => garminSleepHours(d));
  const hrSeries = pickSeries(days, d => d.resting_heart_rate);
  const hrvSeries = pickSeries(days, d => d.hrv);
  const batterySeries = pickSeries(days, d => d.body_battery_current ?? d.body_battery_most_charged);

  const tiles: TileData[] = [
    {
      key: 'sleep',
      label: '睡眠', icon: 'moon', color: HUES.purple.color, bg: HUES.purple.bg,
      value: sleep != null ? sleep.toFixed(1) : '--', unit: 'h',
      sub: sleepScore ? `评分 ${sleepScore}` : (deepSleep != null ? `深睡 ${deepSleep.toFixed(1)}h` : undefined),
      series: sleepSeries,
    },
    {
      key: 'heart_rate',
      label: '心率', icon: 'heart', color: HUES.pink.color, bg: HUES.pink.bg,
      value: heartRate != null ? `${heartRate}` : '--', unit: 'bpm',
      sub: '静息心率',
      series: hrSeries,
    },
    {
      key: 'hrv',
      label: 'HRV', icon: 'pulse', color: HUES.teal.color, bg: HUES.teal.bg,
      value: hrv != null ? `${hrv.toFixed(1)}` : '--', unit: 'ms',
      sub: '压力&恢复',
      series: hrvSeries,
    },
    {
      key: 'body_battery',
      label: '电量', icon: 'battery-charging', color: HUES.green.color, bg: HUES.green.bg,
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
            <Text style={txt.label}>{t.label}</Text>
            {onTilePress && <Ionicons name="chevron-forward" size={12} color={C.ink3} style={{ marginLeft: 'auto' }} />}
          </View>
          <View style={styles.valueRow}>
            <Text style={[txt.value, { color: t.color }]}>{t.value}</Text>
            {t.unit ? <Text style={[txt.unit, { color: t.color }]}>{t.unit}</Text> : null}
          </View>
          {t.sub && <Text style={txt.sub}>{t.sub}</Text>}
          <View style={styles.spark}>
            <Sparkline data={t.series} color={t.color} />
            {t.series.length >= 2 && <Text style={txt.sparkHint}>近 7 天</Text>}
          </View>
        </TouchableOpacity>
      ))}
    </View>
  );
}

// Reva 设计语言:暖白 surface / r-lg 18 / 数字等宽 mono。light-first 单态软阴影。
const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row', flexWrap: 'wrap',
    gap: revaSpacing.s3, marginBottom: revaSpacing.s3,
  },
  tile: {
    width: '47.5%',
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    padding: 14,
    ...revaShadows.sm,
  },
  tileHeader: {
    flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6,
  },
  iconDot: {
    width: 24, height: 24, borderRadius: revaRadii.sm,
    alignItems: 'center', justifyContent: 'center',
  },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 3 },
  spark: { marginTop: 8, height: 32, justifyContent: 'flex-end' },
});

// 数字/单位(指标值 / 单位)走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  label: { fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '500', color: C.ink2 } as TextStyle,
  value: { fontFamily: revaFonts.mono, fontSize: 26, fontWeight: '800', fontVariant: ['tabular-nums'] as const, letterSpacing: 0 } as TextStyle,
  unit: { fontFamily: revaFonts.mono, fontSize: 13, fontWeight: '500', letterSpacing: 0 } as TextStyle,
  sub: { fontFamily: revaFonts.sans, fontSize: 11, color: C.ink3, marginTop: 2 } as TextStyle,
  sparkHint: { fontFamily: revaFonts.mono, fontSize: 9, color: C.ink3, marginTop: 1, letterSpacing: 0 } as TextStyle,
};
