import React from 'react';
import { View, Text, StyleSheet, Pressable, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, typography, spacing, radii, shadows } from '../../constants/theme';

interface Props {
  label: string;
  value: string | number;
  unit?: string;
  subtitle?: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  tintColor: string;
  onPress?: () => void;
}

export default function MetricTile({ label, value, unit, subtitle, icon, color, tintColor, onPress }: Props) {
  const Wrapper = onPress ? Pressable : View;
  return (
    <Wrapper
      style={({ pressed }: any) => [styles.tile, pressed && styles.pressed]}
      onPress={onPress}
    >
      <View style={[styles.iconCircle, { backgroundColor: tintColor }]}>
        <Ionicons name={icon} size={14} color={color} />
      </View>
      <Text style={txt.label}>{label}</Text>
      <View style={styles.valueRow}>
        <Text style={[txt.value, { color }]}>{value}</Text>
        {unit ? <Text style={[txt.unit, { color }]}>{unit}</Text> : null}
      </View>
      {subtitle ? <Text style={txt.subtitle}>{subtitle}</Text> : null}
    </Wrapper>
  );
}

const styles = StyleSheet.create({
  tile: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.md,
    padding: spacing.md,
    width: '48%',
    ...shadows.subtle,
  },
  pressed: { opacity: 0.85, transform: [{ scale: 0.97 }] },
  iconCircle: {
    width: 28,
    height: 28,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.sm,
  },
  valueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 2,
  },
});

const txt = {
  label: { fontSize: 11, fontWeight: '500', color: colors.labelSecondary, marginBottom: 2 } as TextStyle,
  value: { fontSize: 20, fontWeight: '700', fontVariant: ['tabular-nums'] } as TextStyle,
  unit: { fontSize: 13, color: colors.labelSecondary } as TextStyle,
  subtitle: { fontSize: 11, fontWeight: '500', color: colors.labelTertiary, marginTop: 2 } as TextStyle,
};
