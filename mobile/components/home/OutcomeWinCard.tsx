/**
 * OutcomeWinCard —— 首页"AI 让你改善了多少"成果卡 (2026-05-30, P0 #2).
 *
 * 把 /my-progress 的核心 win-metric (improved / graded) 露在首页, 让用户看见
 * 长期成果, 而不只是满屏待办. 之前首页已拉 /my-progress, 但只把 total 喂给
 * chat context, 成果数字对用户不可见.
 *
 * 三态都诚实:
 *   - 有已评估改善 (graded>0): 「已改善 N 项」+ improved/graded 占比, 点击进 /my-progress
 *   - 还没评估出结果 (graded=0): 「成果验证中」引导, 不假装有成果
 *   - 加载失败: 「成果加载失败」, 不退化成 0
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';

interface Props {
  improved: number | null | undefined;
  graded: number | null | undefined;
  totalSurfaced: number | null | undefined;
  isError?: boolean;
  onPress?: () => void;
}

export default function OutcomeWinCard({
  improved,
  graded,
  totalSurfaced,
  isError,
  onPress,
}: Props) {
  const { c } = useTheme();

  let icon: keyof typeof Ionicons.glyphMap;
  let iconColor: string;
  let tint: string;
  let title: string;
  let sub: string;
  let a11y: string;

  const g = graded ?? 0;
  const imp = improved ?? 0;

  if (isError) {
    icon = 'cloud-offline-outline';
    iconColor = c.labelTertiary;
    tint = c.fill;
    title = '成果加载失败';
    sub = '下拉重试';
    a11y = '健康成果加载失败，下拉重试';
  } else if (g > 0) {
    icon = 'trophy';
    iconColor = c.green;
    tint = c.tintGreen;
    title = `AI 已帮你改善 ${imp} 项`;
    sub = `已验证 ${g} 项 · ${imp}/${g} 改善`;
    a11y = `AI 建议里已评估 ${g} 项，其中 ${imp} 项指标改善`;
  } else if ((totalSurfaced ?? 0) > 0) {
    icon = 'hourglass-outline';
    iconColor = c.brand;
    tint = c.brandLight;
    title = '成果验证中';
    sub = `${totalSurfaced ?? 0} 条建议执行中，改善结果待评估`;
    a11y = `已有 ${totalSurfaced ?? 0} 条 AI 建议在执行，改善结果还在评估中`;
  } else {
    icon = 'sparkles-outline';
    iconColor = c.labelSecondary;
    tint = c.fill;
    title = '还没有成果记录';
    sub = '接受并执行 AI 建议，这里会显示改善';
    a11y = '还没有可展示的健康成果，接受并执行 AI 建议后这里会显示改善';
  }

  return (
    <Pressable
      testID="home-outcome-win-card"
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
      <View style={styles.textWrap}>
        <Text
          maxFontSizeMultiplier={1.4}
          style={[styles.title, { color: c.labelPrimary }]}
          numberOfLines={1}
        >
          {title}
        </Text>
        <Text
          maxFontSizeMultiplier={1.4}
          style={[styles.sub, { color: c.labelTertiary }]}
          numberOfLines={1}
        >
          {sub}
        </Text>
      </View>
      {onPress ? (
        <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    marginBottom: spacing.md,
  },
  iconWrap: {
    width: 30,
    height: 30,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
  },
  textWrap: { flex: 1, gap: 2, minWidth: 0 },
  title: { fontSize: 13, fontWeight: '800' },
  sub: { fontSize: 11, fontWeight: '500' },
});
