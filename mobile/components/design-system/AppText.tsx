/**
 * AppText —— 统一排版原子 (2026-05-31, docs/mobile-ui-audit.md).
 *
 * 解决两个一致性问题:
 *   1. 字号字面量散落 (22 个不同 fontSize, 标准只 10 级) → 用 `variant` 走 typography 标准级别.
 *   2. maxFontSizeMultiplier 混乱 (1.18/1.3/1.4/无) → 用 `cap` 走 FONT_SIZE_CAPS 统一上限.
 *
 * 颜色默认走主题 c.labelPrimary (暗色自动适配); 可用 `tone` 选语义色, 或 style 覆盖.
 *
 * 用法:
 *   <AppText variant="titleSmall">标题</AppText>
 *   <AppText variant="bodySmall" tone="secondary">副文案</AppText>
 *   <AppText variant="metric" cap="metric">2,967</AppText>
 */
import React from 'react';
import { Text, TextProps, TextStyle } from 'react-native';
import { typography, FONT_SIZE_CAPS } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';

export type TextVariant = keyof typeof typography;
export type TextTone = 'primary' | 'secondary' | 'tertiary' | 'brand' | 'inverse';
export type TextCap = keyof typeof FONT_SIZE_CAPS;

interface Props extends TextProps {
  variant?: TextVariant;
  tone?: TextTone;
  cap?: TextCap;
}

export default function AppText({
  variant = 'bodyMedium',
  tone = 'primary',
  cap = 'default',
  style,
  maxFontSizeMultiplier,
  ...rest
}: Props) {
  const { c } = useTheme();

  const toneColor: Record<TextTone, string> = {
    primary: c.labelPrimary,
    secondary: c.labelSecondary,
    tertiary: c.labelTertiary,
    brand: c.brand,
    inverse: '#FFFFFF',
  };

  return (
    <Text
      maxFontSizeMultiplier={maxFontSizeMultiplier ?? FONT_SIZE_CAPS[cap]}
      style={[typography[variant] as TextStyle, { color: toneColor[tone] }, style]}
      {...rest}
    />
  );
}
