/**
 * 卡片基础容器 - 统一视觉规范 (Reva 设计语言)
 * - 圆角 + surface 背景 + hairline 边 + 软阴影
 * - 支持标题 + 子内容 + 可选右上角 badge / 点击跳转
 *
 * 2026-06-27: P1 设计语言统一 — 从 legacy useTheme 迁到 revaTheme 单一真源.
 * 旧 prop `bg` 仍兼容 (调用方可传 C.green50 之类的 token), 默认值改成 C.surface.
 * 标题走 Manrope; 类目/装饰色由调用方传入, 此容器不做"好坏"语义判断.
 */
import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaRadii,
  revaShadows,
  revaFonts,
} from '../../../constants/revaTheme';

interface CardShellProps {
  icon: string;
  iconColor: string;
  title: string;
  badge?: string;
  badgeColor?: string;
  onPress?: () => void;
  children: React.ReactNode;
  bg?: string;
  style?: ViewStyle;
}

export function CardShell({
  icon, iconColor, title, badge, badgeColor, onPress, children, bg, style,
}: CardShellProps) {
  const cardBg = bg ?? C.surface;
  const Inner = (
    <View
      style={[
        styles.card,
        { backgroundColor: cardBg, borderColor: C.line },
        style,
      ]}
    >
      <View style={styles.header}>
        <Ionicons name={icon as any} size={14} color={iconColor} />
        <Text maxFontSizeMultiplier={1.3} style={styles.title}>
          {title}
        </Text>
        {badge && (
          <View style={[styles.badge, { backgroundColor: badgeColor || C.paper2 }]}>
            <Text maxFontSizeMultiplier={1.2} style={styles.badgeText}>{badge}</Text>
          </View>
        )}
        {onPress && (
          <Ionicons name="chevron-forward" size={14} color={C.ink3} style={{ marginLeft: 'auto' }} />
        )}
      </View>
      {children}
    </View>
  );

  if (onPress) {
    return <TouchableOpacity activeOpacity={0.75} onPress={onPress}>{Inner}</TouchableOpacity>;
  }
  return Inner;
}

const styles = StyleSheet.create({
  card: {
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginVertical: 6,
    minWidth: 240,
    ...revaShadows.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 8,
  },
  badge: {
    paddingHorizontal: 6,
    paddingVertical: 1,
    borderRadius: 8,
  },
  title: { fontFamily: revaFonts.sans, fontSize: 12, fontWeight: '600', color: C.ink2 } as TextStyle,
  badgeText: { fontFamily: revaFonts.sans, fontSize: 10, fontWeight: '700', color: '#fff' } as TextStyle,
});
