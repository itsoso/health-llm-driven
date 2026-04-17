import React from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import { colors, spacing, radii, shadows } from '@/constants/theme';

interface RingProps {
  value: number;
  target: number;
  color: string;
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  displayValue: string;
}

function ActivityRing({ value, target, color, icon, label, displayValue }: RingProps) {
  const size = 64;
  const sw = 5;
  const r = (size - sw) / 2;
  const c = 2 * Math.PI * r;
  const progress = Math.min(value / target, 1);
  const off = c * (1 - progress);

  return (
    <View style={styles.ringItem}>
      <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
        <Svg width={size} height={size}>
          <Circle cx={size / 2} cy={size / 2} r={r} stroke={`${color}20`} strokeWidth={sw} fill="none" />
          <Circle cx={size / 2} cy={size / 2} r={r}
            stroke={color} strokeWidth={sw} fill="none"
            strokeLinecap="round" strokeDasharray={c} strokeDashoffset={off}
            transform={`rotate(-90 ${size / 2} ${size / 2})`} />
        </Svg>
        <Ionicons name={icon} size={18} color={color} style={{ position: 'absolute' }} />
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
      <ActivityRing value={steps} target={stepsTarget} color="#FF6723" icon="footsteps-outline" label="步数" displayValue={steps.toLocaleString()} />
      <View style={styles.divider} />
      <ActivityRing value={activeMin} target={activeTarget} color="#FF375F" icon="flame-outline" label="活动" displayValue={`${activeMin}min`} />
      <View style={styles.divider} />
      <ActivityRing value={calories} target={caloriesTarget} color="#FF453A" icon="flash-outline" label="卡路里" displayValue={`${calories}`} />
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    backgroundColor: colors.bgCard,
    borderRadius: radii.xl,
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.md,
    marginBottom: spacing.lg,
    justifyContent: 'space-around',
    alignItems: 'center',
    ...shadows.subtle,
  },
  ringItem: { alignItems: 'center' },
  divider: { width: StyleSheet.hairlineWidth, height: 60, backgroundColor: colors.separator },
});

const txt = {
  value: { fontSize: 16, fontWeight: '700', color: colors.labelPrimary, marginTop: 6, fontVariant: ['tabular-nums'] as const } as TextStyle,
  label: { fontSize: 11, fontWeight: '500', color: colors.labelSecondary, marginTop: 2 } as TextStyle,
  target: { fontSize: 10, color: colors.labelTertiary } as TextStyle,
};
