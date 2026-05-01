/**
 * DashboardCard — Home tab 卡片统一外壳
 *
 * 设计规范:
 *   - 圆角 16, padding 14×12, marginH 16, marginV 6, shadow.subtle
 *   - 头部: [iconBox 36×36 r10] [kicker (可选) + title] [trailing] [chevron]
 *   - 触摸: minHeight 36, 整头部可点折叠
 *   - dark mode: 颜色全部走 useTheme(), shadow 在 dark 下变弱 (本就难看见)
 */
import React, { ReactNode, useMemo, useState } from 'react';
import {
  LayoutAnimation, Platform, Pressable, StyleSheet, Text, TextStyle,
  UIManager, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { radii, spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface Props {
  icon: keyof typeof Ionicons.glyphMap;
  iconTint?: string;
  iconColor?: string;
  kicker?: string;
  kickerColor?: string;
  title: string;
  trailing?: ReactNode;
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  controlledCollapsed?: boolean;
  onToggle?: (collapsed: boolean) => void;
  accessibilityLabel?: string;
  children?: ReactNode;
  variant?: 'default' | 'flat';
  testID?: string;
}

export default function DashboardCard({
  icon, iconTint, iconColor,
  kicker, kickerColor,
  title, trailing,
  collapsible = false, defaultCollapsed = false, controlledCollapsed,
  onToggle, accessibilityLabel,
  children, variant = 'default', testID,
}: Props) {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const [internal, setInternal] = useState(defaultCollapsed);
  const collapsed = controlledCollapsed ?? internal;

  const _iconTint = iconTint ?? c.brandLight;
  const _iconColor = iconColor ?? c.brand;
  const _kickerColor = kickerColor ?? c.labelTertiary;

  const toggle = () => {
    if (!collapsible) return;
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    Haptics.selectionAsync();
    const next = !collapsed;
    if (controlledCollapsed === undefined) setInternal(next);
    onToggle?.(next);
  };

  const HeaderWrapper: any = collapsible ? Pressable : View;
  const headerProps = collapsible
    ? {
        onPress: toggle,
        accessibilityRole: 'button' as const,
        accessibilityLabel: accessibilityLabel ?? `${collapsed ? '展开' : '收起'}${title}`,
        accessibilityState: { expanded: !collapsed },
        hitSlop: 6,
      }
    : {};

  return (
    <View style={[styles.card, variant === 'flat' && styles.cardFlat]} testID={testID}>
      <HeaderWrapper style={styles.header} {...headerProps}>
        <View style={[styles.iconBox, { backgroundColor: _iconTint }]}>
          <Ionicons name={icon} size={18} color={_iconColor} />
        </View>
        <View style={styles.titleBlock}>
          {kicker ? (
            <Text style={[styles.kicker, { color: _kickerColor }]} numberOfLines={1}>{kicker}</Text>
          ) : null}
          <Text style={styles.title} numberOfLines={collapsed ? 1 : 2}>{title}</Text>
        </View>
        {trailing ? <View style={styles.trailing}>{trailing}</View> : null}
        {collapsible ? (
          <Ionicons
            name={collapsed ? 'chevron-down' : 'chevron-up'}
            size={18}
            color={c.labelTertiary}
            style={styles.chevron}
          />
        ) : null}
      </HeaderWrapper>

      {!collapsed && children ? <View style={styles.body}>{children}</View> : null}
    </View>
  );
}

export function CardCountBadge({ value }: { value: number | string }) {
  const { c } = useTheme();
  return (
    <View style={{
      backgroundColor: c.fill,
      paddingHorizontal: 7, paddingVertical: 1,
      borderRadius: 8, minWidth: 20, alignItems: 'center',
    }}>
      <Text style={{ fontSize: 11, fontWeight: '700', color: c.labelSecondary }}>{value}</Text>
    </View>
  );
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      marginHorizontal: spacing.lg,
      marginVertical: 6,
      paddingHorizontal: 14,
      paddingVertical: 12,
      // dark mode: shadow 在黑底上几乎不可见, 用细边框替代视觉分隔
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : {
            shadowColor: '#000',
            shadowOffset: { width: 0, height: 1 },
            shadowOpacity: 0.06,
            shadowRadius: 3,
            elevation: 1,
          }),
    },
    cardFlat: {
      shadowOpacity: 0,
      elevation: 0,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    },
    header: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 10,
      minHeight: 36,
    },
    iconBox: {
      width: 36, height: 36,
      borderRadius: 10,
      alignItems: 'center', justifyContent: 'center',
    },
    titleBlock: { flex: 1, gap: 2 },
    trailing: { flexDirection: 'row', alignItems: 'center', gap: 6 },
    chevron: { marginLeft: 4 },
    body: { marginTop: 12, gap: 10 },
    kicker: {
      fontSize: 11, fontWeight: '700' as const, letterSpacing: 0.2,
    } as TextStyle,
    title: {
      fontSize: 16, fontWeight: '700' as const,
      color: c.labelPrimary, lineHeight: 21,
    } as TextStyle,
  });
}
