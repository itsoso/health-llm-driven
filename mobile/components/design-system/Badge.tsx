/**
 * Badge —— 统一状态徽章原子 (2026-05-31, docs/mobile-ui-audit.md).
 *
 * 取代各屏自造的硬编码 status 色字典 (genetic-report STAGE_COLORS / movement-plan
 * STATUS_COLOR / BPCard 阈值色 …, 共 3+ 套并行、~70 个重复 hex、暗色全不适配).
 * 用 `tone` 选语义档, 颜色一律从主题 c.* 取 → 自动暗色适配.
 *
 * 用法: <Badge tone="danger" label="高风险" />  <Badge tone="ok" label="正常" icon="checkmark" />
 */
import React from 'react';
import { View, StyleSheet, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii, spacing, FONT_SIZE_CAPS } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import AppText from './AppText';

export type BadgeTone = 'neutral' | 'brand' | 'ok' | 'warn' | 'danger' | 'info';

interface Props {
  label: string;
  tone?: BadgeTone;
  icon?: keyof typeof Ionicons.glyphMap;
  style?: ViewStyle;
}

function toneColors(c: ColorPalette, tone: BadgeTone): { fg: string; bg: string } {
  switch (tone) {
    case 'brand': return { fg: c.brand, bg: c.brandLight };
    case 'ok': return { fg: c.green, bg: c.tintGreen };
    case 'warn': return { fg: c.amber, bg: c.tintAmber };
    case 'danger': return { fg: c.red, bg: c.tintRed };
    case 'info': return { fg: c.blue, bg: c.tintBlue };
    case 'neutral':
    default: return { fg: c.labelSecondary, bg: c.fill };
  }
}

export default function Badge({ label, tone = 'neutral', icon, style }: Props) {
  const { c } = useTheme();
  const { fg, bg } = toneColors(c, tone);

  return (
    <View style={[styles.badge, { backgroundColor: bg }, style]}>
      {icon ? <Ionicons name={icon} size={11} color={fg} /> : null}
      <AppText
        variant="caption"
        cap="compact"
        style={{ color: fg, fontWeight: '700' }}
        numberOfLines={1}
      >
        {label}
      </AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radii.full,
    alignSelf: 'flex-start',
  },
});
