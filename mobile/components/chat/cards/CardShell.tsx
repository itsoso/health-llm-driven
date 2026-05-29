/**
 * 卡片基础容器 - 统一视觉规范
 * - 圆角 + 主题感知背景 + hairline 边
 * - 支持标题 + 子内容 + 可选右上角 badge / 点击跳转
 *
 * 2026-05-29: 改用 useTheme 让暗色模式可读. 旧 prop `bg` 仍兼容
 * (调用方可以传 c.tintGreen 之类的主题 token), 但默认值改成 c.bgCard.
 */
import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { radii } from '../../../constants/theme';
import { useTheme } from '../../../hooks/useTheme';

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
  const { c } = useTheme();
  const cardBg = bg ?? c.bgCard;
  const Inner = (
    <View
      style={[
        styles.card,
        { backgroundColor: cardBg, borderColor: c.separator },
        style,
      ]}
    >
      <View style={styles.header}>
        <Ionicons name={icon as any} size={14} color={iconColor} />
        <Text maxFontSizeMultiplier={1.3} style={[styles.title, { color: c.labelSecondary }]}>
          {title}
        </Text>
        {badge && (
          <View style={[styles.badge, { backgroundColor: badgeColor || c.fill }]}>
            <Text maxFontSizeMultiplier={1.2} style={styles.badgeText}>{badge}</Text>
          </View>
        )}
        {onPress && (
          <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} style={{ marginLeft: 'auto' }} />
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
    borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginVertical: 6,
    minWidth: 240,
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
  title: { fontSize: 12, fontWeight: '600' } as TextStyle,
  badgeText: { fontSize: 10, fontWeight: '700', color: '#fff' } as TextStyle,
});
