/**
 * StreakBadge —— 首页打卡连续天数徽章 (2026-05-30).
 *
 * 正向激励: 把后端真实计算的连续打卡天数 (checkin/stats) 露在首页顶部,
 * 替代"全是待办/赤字"的叙事. 三种状态都诚实:
 *   - 有连续 (>0): 🔥 连续 N 天 · 最佳 M
 *   - 归零 (=0):   今天开始记录 (引导, 不假装有 streak)
 *   - 加载失败:    连续天数加载失败 (不退化成 0 假成功)
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';

interface Props {
  current: number | null | undefined;
  best: number | null | undefined;
  isError?: boolean;
  onPress?: () => void;
}

export default function StreakBadge({ current, best, isError, onPress }: Props) {
  const { c } = useTheme();

  let icon: keyof typeof Ionicons.glyphMap;
  let iconColor: string;
  let tint: string;
  let title: string;
  let sub: string | null;
  let a11y: string;

  if (isError) {
    icon = 'cloud-offline-outline';
    iconColor = c.labelTertiary;
    tint = c.fill;
    title = '连续天数加载失败';
    sub = '下拉重试';
    a11y = '连续打卡天数加载失败，下拉重试';
  } else if ((current ?? 0) > 0) {
    icon = 'flame';
    iconColor = c.orange;
    tint = c.tintOrange;
    title = `连续 ${current} 天`;
    sub = (best ?? 0) > 0 ? `最佳 ${best}` : null;
    a11y = `已连续打卡 ${current} 天${(best ?? 0) > 0 ? `，历史最佳 ${best} 天` : ''}`;
  } else {
    icon = 'flame-outline';
    iconColor = c.labelSecondary;
    tint = c.fill;
    title = '今天开始记录';
    sub = '完成一次打卡，开启连续天数';
    a11y = '还没有连续打卡，今天完成一次记录即可开启连续天数';
  }

  return (
    <Pressable
      testID="home-streak-badge"
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: c.bgCard, borderColor: c.separator, opacity: pressed && onPress ? 0.78 : 1 },
      ]}
      accessibilityRole={onPress ? 'button' : 'text'}
      accessibilityLabel={a11y}
    >
      <View style={[styles.iconWrap, { backgroundColor: tint }]}>
        <Ionicons name={icon} size={16} color={iconColor} />
      </View>
      <Text
        maxFontSizeMultiplier={1.4}
        style={[styles.title, { color: c.labelPrimary }]}
        numberOfLines={1}
      >
        {title}
      </Text>
      {sub ? (
        <Text
          maxFontSizeMultiplier={1.4}
          style={[styles.sub, { color: c.labelTertiary }]}
          numberOfLines={1}
        >
          · {sub}
        </Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: spacing.md,
    paddingVertical: 9,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    marginBottom: spacing.md,
  },
  iconWrap: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: { fontSize: 13, fontWeight: '800' },
  sub: { fontSize: 12, fontWeight: '600', flexShrink: 1, minWidth: 0 },
});
