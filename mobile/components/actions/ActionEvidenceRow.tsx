import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii } from '@/constants/theme';

interface Props {
  label: string;
  value: string;
  tone?: 'default' | 'good' | 'warn' | 'bad';
  icon?: keyof typeof Ionicons.glyphMap;
}

const TONE_COLOR = {
  default: colors.labelSecondary,
  good: '#0A8F8F',
  warn: '#FF9F0A',
  bad: '#FF453A',
};

export default function ActionEvidenceRow({ label, value, tone = 'default', icon = 'analytics-outline' }: Props) {
  const color = TONE_COLOR[tone];
  return (
    <View style={styles.row}>
      <Ionicons name={icon} size={13} color={color} />
      <Text style={txt.label}>{label}</Text>
      <Text style={[txt.value, { color }]} numberOfLines={1}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    minHeight: 28,
    borderRadius: radii.sm,
    backgroundColor: colors.bgPrimary,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
});

const txt = {
  label: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
  value: { flex: 1, textAlign: 'right', fontSize: 11, fontWeight: '700' } as TextStyle,
};
