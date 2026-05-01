/**
 * DashboardCard — Home tab 卡片统一外壳
 *
 * 设计规范 (所有 dashboard 卡片必走):
 *   - 圆角 16, 白底, padding 14, marginH 16, marginV 6, shadow.subtle
 *   - 头部: [iconBox 36×36 r10] [kicker (可选) + title] [trailing (count badge / chevron)]
 *   - 触摸: minHeight 48, 整头部可点折叠
 *   - chevron: 平 18px tertiary, 不带 pill 背景 (旧设计留下的视觉噪声)
 *
 * 用法:
 *   <DashboardCard
 *     icon="alert-circle" iconTint={tintRed} iconColor={red}
 *     kicker="优先处理" kickerColor={red}
 *     title="夜间血氧过低"
 *     count={3}                    // 可选 badge
 *     collapsible defaultCollapsed
 *   >
 *     <Text>...body content...</Text>
 *   </DashboardCard>
 */
import React, { ReactNode, useState } from 'react';
import {
  LayoutAnimation, Platform, Pressable, StyleSheet, Text, TextStyle,
  TouchableOpacity, UIManager, View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';
import { colors, radii, shadows, spacing } from '../../constants/theme';

if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}

interface Props {
  icon: keyof typeof Ionicons.glyphMap;
  iconTint?: string;          // 图标背景色 (e.g. tintRed)
  iconColor?: string;          // 图标本体色 (e.g. red)
  kicker?: string;             // 头部小标签 ("优先处理" / "今日洞察 · HRV 模式")
  kickerColor?: string;        // kicker 文本色, 默认 labelTertiary
  title: string;
  trailing?: ReactNode;         // 自定义右侧 (count badge / 时间戳 等), chevron 自动加在最右
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  controlledCollapsed?: boolean;     // 如果父组件想自己管 collapsed 状态
  onToggle?: (collapsed: boolean) => void;
  accessibilityLabel?: string;
  children?: ReactNode;        // body — collapsed 态隐藏
  variant?: 'default' | 'flat'; // flat = 无 shadow, 用于辅助 meta 卡片
  testID?: string;
}

export default function DashboardCard({
  icon, iconTint = colors.brandLight, iconColor = colors.brand,
  kicker, kickerColor = colors.labelTertiary,
  title, trailing,
  collapsible = false, defaultCollapsed = false, controlledCollapsed,
  onToggle, accessibilityLabel,
  children, variant = 'default', testID,
}: Props) {
  const [internal, setInternal] = useState(defaultCollapsed);
  const collapsed = controlledCollapsed ?? internal;

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
        <View style={[styles.iconBox, { backgroundColor: iconTint }]}>
          <Ionicons name={icon} size={18} color={iconColor} />
        </View>
        <View style={styles.titleBlock}>
          {kicker ? (
            <Text style={[txt.kicker, { color: kickerColor }]} numberOfLines={1}>{kicker}</Text>
          ) : null}
          <Text style={txt.title} numberOfLines={collapsed ? 1 : 2}>{title}</Text>
        </View>
        {trailing ? <View style={styles.trailing}>{trailing}</View> : null}
        {collapsible ? (
          <Ionicons
            name={collapsed ? 'chevron-down' : 'chevron-up'}
            size={18}
            color={colors.labelTertiary}
            style={styles.chevron}
          />
        ) : null}
      </HeaderWrapper>

      {!collapsed && children ? <View style={styles.body}>{children}</View> : null}
    </View>
  );
}

// 通用 count badge — 卡片右侧用
export function CardCountBadge({ value }: { value: number | string }) {
  return (
    <View style={badgeStyles.bg}>
      <Text style={badgeStyles.text}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    marginHorizontal: spacing.lg,
    marginVertical: 6,
    paddingHorizontal: 14,
    paddingVertical: 12,
    ...shadows.subtle,
  },
  cardFlat: {
    shadowOpacity: 0,
    elevation: 0,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.separator,
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
});

const txt = {
  kicker: {
    fontSize: 11, fontWeight: '700' as const, letterSpacing: 0.2,
  } as TextStyle,
  title: {
    fontSize: 16, fontWeight: '700' as const,
    color: colors.labelPrimary, lineHeight: 21,
  } as TextStyle,
};

const badgeStyles = StyleSheet.create({
  bg: {
    backgroundColor: colors.fill,
    paddingHorizontal: 7, paddingVertical: 1,
    borderRadius: 8,
    minWidth: 20, alignItems: 'center',
  },
  text: {
    fontSize: 11, fontWeight: '700',
    color: colors.labelSecondary,
  },
});
