/**
 * 卡片基础容器 - 统一视觉规范
 * - 圆角 + 浅色背景 + 小投影
 * - 支持标题 + 子内容 + 可选右上角 badge / 点击跳转
 */
import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, ViewStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { colors, radii, spacing } from '@/constants/theme';

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
  icon, iconColor, title, badge, badgeColor, onPress, children, bg = '#F8FFFE', style,
}: CardShellProps) {
  const Inner = (
    <View style={[styles.card, { backgroundColor: bg }, style]}>
      <View style={styles.header}>
        <Ionicons name={icon as any} size={14} color={iconColor} />
        <Text style={txt.title}>{title}</Text>
        {badge && (
          <View style={[styles.badge, { backgroundColor: badgeColor || '#E5E5EA' }]}>
            <Text style={txt.badgeText}>{badge}</Text>
          </View>
        )}
        {onPress && <Ionicons name="chevron-forward" size={14} color="#C7C7CC" style={{ marginLeft: 'auto' }} />}
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
});

const txt = {
  title: { fontSize: 12, fontWeight: '600', color: colors.labelSecondary } as TextStyle,
  badgeText: { fontSize: 10, fontWeight: '700', color: '#fff' } as TextStyle,
};
