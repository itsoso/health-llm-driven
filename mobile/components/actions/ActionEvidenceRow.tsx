import React, { useMemo } from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

interface Props {
  label: string;
  value: string;
  tone?: 'default' | 'good' | 'warn' | 'bad';
  icon?: keyof typeof Ionicons.glyphMap;
}

function toneColor(c: ColorPalette, tone: NonNullable<Props['tone']>): string {
  switch (tone) {
    case 'good': return c.brand;
    case 'warn': return c.amber;
    case 'bad': return c.red;
    case 'default':
    default: return c.labelSecondary;
  }
}

export default function ActionEvidenceRow({ label, value, tone = 'default', icon = 'analytics-outline' }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const color = toneColor(c, tone);
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={13} color={color} />
      <Text style={styles.label}>{label}</Text>
      <Text style={[styles.value, { color }]} numberOfLines={1}>{value}</Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    row: {
      minHeight: 28,
      borderRadius: radii.sm,
      backgroundColor: c.bgPrimary,
      flexDirection: 'row',
      alignItems: 'center',
      gap: 6,
      paddingHorizontal: 9,
      paddingVertical: 5,
    },
    label: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    value: { flex: 1, textAlign: 'right', fontSize: 11, fontWeight: '700' } as TextStyle,
  });
}
