import React from 'react';
import { View, Text, StyleSheet, Pressable, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii, shadows } from '../../constants/theme';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';

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
  const { c } = useTheme();
  const styles = React.useMemo(() => createStyles(c), [c]);
  const txt = React.useMemo(() => createTxt(c), [c]);
  const content = (
    <>
      <View style={[styles.iconCircle, { backgroundColor: tintColor }]}>
        <Ionicons name={icon} size={14} color={color} />
      </View>
      <Text style={txt.label}>{label}</Text>
      <View style={styles.valueRow}>
        <Text
          style={[txt.value, { color }]}
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.75}
        >
          {value}
        </Text>
        {unit ? <Text style={[txt.unit, { color }]}>{unit}</Text> : null}
      </View>
      {subtitle ? <Text style={txt.subtitle}>{subtitle}</Text> : null}
    </>
  );

  if (onPress) {
    return (
      <Pressable
        style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={`${label} ${value}${unit ? unit : ''}`}
      >
        {content}
      </Pressable>
    );
  }

  return (
    <View style={styles.tile} accessibilityLabel={`${label} ${value}${unit ? unit : ''}`}>
      {content}
    </View>
  );
}

const createStyles = (c: ColorPalette) => StyleSheet.create({
  tile: {
    backgroundColor: c.bgCard,
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

const createTxt = (c: ColorPalette) => ({
  label: { fontSize: 11, fontWeight: '500', color: c.labelSecondary, marginBottom: 2 } as TextStyle,
  value: { fontSize: 20, fontWeight: '700', fontVariant: ['tabular-nums'] } as TextStyle,
  unit: { fontSize: 13, color: c.labelSecondary } as TextStyle,
  subtitle: { fontSize: 11, fontWeight: '500', color: c.labelTertiary, marginTop: 2 } as TextStyle,
});
