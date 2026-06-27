import React from 'react';
import { View, Text, StyleSheet, Pressable, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../../constants/revaTheme';

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

// Reva 设计语言:暖白 surface 卡 / r-md / 数字等宽 mono / light-first 软阴影。
const styles = StyleSheet.create({
  tile: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.md,
    padding: revaSpacing.s3,
    width: '48%',
    ...revaShadows.sm,
  },
  pressed: { opacity: 0.85, transform: [{ scale: 0.97 }] },
  iconCircle: {
    width: 28,
    height: 28,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: revaSpacing.s2,
  },
  valueRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    gap: 2,
  },
});

// 指标值/单位走 IBM Plex Mono = Reva 等宽 signature;标签/副标走 Manrope/ink。
const txt = {
  label: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '500', color: C.ink2, marginBottom: 2 } as TextStyle,
  value: { fontFamily: revaFonts.mono, fontSize: 20, fontWeight: '700', fontVariant: ['tabular-nums'] } as TextStyle,
  unit: { fontFamily: revaFonts.mono, fontSize: 13, color: C.ink2 } as TextStyle,
  subtitle: { fontFamily: revaFonts.sans, fontSize: 11, fontWeight: '500', color: C.ink3, marginTop: 2 } as TextStyle,
};
