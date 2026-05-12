/**
 * HeroTile —— 2x2 grid 通用 tile, 学健康记录 VitalsGrid 风格 (2026-05-12).
 *
 * 用法: 4 个并排放在 <View style={{flexDirection:'row',flexWrap:'wrap',gap:12}}>.
 */

import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useTheme } from '../../hooks/useTheme';
import { radii } from '../../constants/theme';

interface Props {
  label: string;
  value: string;
  unit?: string;
  sub?: string;
  emoji?: string;
  ionIcon?: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
  onPress?: () => void;
}

export default function HeroTile({
  label, value, unit, sub, emoji, ionIcon, color, bg, onPress,
}: Props) {
  const { c } = useTheme();
  const Wrap = onPress ? TouchableOpacity : View;
  return (
    <Wrap
      // @ts-ignore TouchableOpacity 接 activeOpacity, View 不接 — 安全无视
      activeOpacity={0.75}
      style={[styles.tile, { backgroundColor: c.bgCard, borderColor: c.separator }]}
      onPress={onPress}
      accessibilityLabel={`${label} ${value}${unit ?? ''}`}
    >
      <View style={styles.header}>
        <View style={[styles.iconDot, { backgroundColor: bg }]}>
          {emoji ? (
            <Text style={{ fontSize: 13 }}>{emoji}</Text>
          ) : ionIcon ? (
            <Ionicons name={ionIcon} size={14} color={color} />
          ) : null}
        </View>
        <Text style={[styles.label, { color: c.labelSecondary }]}>{label}</Text>
        {onPress && (
          <Ionicons
            name="chevron-forward"
            size={12}
            color={c.labelTertiary}
            style={{ marginLeft: 'auto' }}
          />
        )}
      </View>
      <View style={styles.valueRow}>
        <Text style={[styles.value, { color }]} numberOfLines={1}>
          {value}
        </Text>
        {unit ? <Text style={[styles.unit, { color }]}>{unit}</Text> : null}
      </View>
      {sub ? (
        <Text style={[styles.sub, { color: c.labelTertiary }]} numberOfLines={1}>
          {sub}
        </Text>
      ) : null}
    </Wrap>
  );
}

const styles = StyleSheet.create({
  tile: {
    width: '47.5%',
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: radii.lg,
    padding: 14,
  },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  iconDot: {
    width: 24, height: 24, borderRadius: 7,
    alignItems: 'center', justifyContent: 'center',
  },
  label: { fontSize: 13, fontWeight: '500' },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 1 },
  value: { fontSize: 24, fontWeight: '800', fontVariant: ['tabular-nums'], letterSpacing: -0.6 },
  unit: { fontSize: 13, fontWeight: '500' },
  sub: { fontSize: 11, marginTop: 4 },
});
