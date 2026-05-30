import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface RingProps {
  value: number;
  target: number;
  color: string;
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  displayValue: string;
}

function ActivityRing({ value, target, color, icon, label, displayValue }: RingProps) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c, false), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

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
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);

  return (
    <View style={styles.card}>
      <ActivityRing value={steps} target={stepsTarget} color={c.orange} icon="footsteps-outline" label="步数" displayValue={steps.toLocaleString()} />
      <View style={styles.divider} />
      <ActivityRing value={activeMin} target={activeTarget} color={c.pink} icon="flame-outline" label="活动" displayValue={`${activeMin}min`} />
      <View style={styles.divider} />
      <ActivityRing value={calories} target={caloriesTarget} color={c.red} icon="flash-outline" label="卡路里" displayValue={`${calories}`} />
    </View>
  );
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      flexDirection: 'row',
      backgroundColor: c.bgCard,
      borderRadius: radii.xl,
      paddingVertical: spacing.md,
      paddingHorizontal: spacing.md,
      marginBottom: spacing.md,
      justifyContent: 'space-around',
      alignItems: 'center',
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : { shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, shadowRadius: 3, elevation: 1 }),
    },
    ringItem: { alignItems: 'center' },
    divider: { width: StyleSheet.hairlineWidth, height: 46, backgroundColor: c.separator },
  });
}

function createTxt(c: ColorPalette) {
  return {
    value: { fontSize: 16, fontWeight: '700', color: c.labelPrimary, marginTop: 6, fontVariant: ['tabular-nums'] as const } as TextStyle,
    label: { fontSize: 11, fontWeight: '500', color: c.labelSecondary, marginTop: 2 } as TextStyle,
    target: { fontSize: 10, color: c.labelTertiary } as TextStyle,
  };
}
