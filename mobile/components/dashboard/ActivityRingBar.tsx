import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

// 每环的装饰性 hue (步数橙 / 活动粉 / 卡路里红) —— 区分指标的色码,
// 不是「指标好坏」的三步临床语义。值即 Reva 亮色调色板原值。
const HUES = {
  orange: '#C97A2E',
  pink: '#C2487A',
  red: '#D5503A',
} as const;

interface RingProps {
  value: number;
  target: number;
  color: string;
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  displayValue: string;
}

function ActivityRing({ value, target, color, icon, label, displayValue }: RingProps) {
  const size = 52;
  const sw = 4.5;
  const r = (size - sw) / 2;
  const circ = 2 * Math.PI * r;
  const progress = Math.min(value / target, 1);
  const off = circ * (1 - progress);

  return (
    <View style={styles.ringItem}>
      <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
        <Svg width={size} height={size}>
          <Circle cx={size / 2} cy={size / 2} r={r} stroke={`${color}20`} strokeWidth={sw} fill="none" />
          <Circle cx={size / 2} cy={size / 2} r={r}
            stroke={color} strokeWidth={sw} fill="none"
            strokeLinecap="round" strokeDasharray={circ} strokeDashoffset={off}
            transform={`rotate(-90 ${size / 2} ${size / 2})`} />
        </Svg>
        <Ionicons name={icon} size={15} color={color} style={{ position: 'absolute' }} />
      </View>
      <Text style={txt.value}>{displayValue}</Text>
      <Text style={txt.label}>{label}</Text>
      <Text style={txt.target}>/ {target.toLocaleString()}</Text>
    </View>
  );
}

interface Props {
  steps?: number;
  stepsTarget?: number;
  activeMin?: number;
  activeTarget?: number;
  calories?: number;
  caloriesTarget?: number;
}

export default function ActivityRingBar({
  steps = 0, stepsTarget = 8000,
  activeMin = 0, activeTarget = 30,
  calories = 0, caloriesTarget = 500,
}: Props) {
  return (
    <View style={styles.card}>
      <ActivityRing value={steps} target={stepsTarget} color={HUES.orange} icon="footsteps-outline" label="步数" displayValue={steps.toLocaleString()} />
      <View style={styles.divider} />
      <ActivityRing value={activeMin} target={activeTarget} color={HUES.pink} icon="flame-outline" label="活动" displayValue={`${activeMin}min`} />
      <View style={styles.divider} />
      <ActivityRing value={calories} target={caloriesTarget} color={HUES.red} icon="flash-outline" label="卡路里" displayValue={`${calories}`} />
    </View>
  );
}

// Reva 设计语言:暖白 surface / r-lg 18 / 数字等宽 mono / light-first 软阴影。
const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: C.surface,
    borderRadius: revaRadii.lg,
    paddingVertical: revaSpacing.s3,
    paddingHorizontal: revaSpacing.s3,
    marginBottom: revaSpacing.s3,
    justifyContent: 'space-around',
    alignItems: 'center',
    ...revaShadows.sm,
  },
  ringItem: { alignItems: 'center' },
  divider: { width: StyleSheet.hairlineWidth, height: 46, backgroundColor: C.line },
});

// 环数值(步数 / 活动 / 卡路里)与目标值走 IBM Plex Mono = Reva 等宽 signature;标签走 Manrope/ink。
const txt = {
  value: { fontFamily: revaFonts.mono, fontSize: 16, fontWeight: '700', color: C.ink1, marginTop: 6, fontVariant: ['tabular-nums'] as const } as TextStyle,
  label: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '500', color: C.ink2, marginTop: 2 } as TextStyle,
  target: { fontFamily: revaFonts.mono, fontSize: 10, color: C.ink3 } as TextStyle,
};
