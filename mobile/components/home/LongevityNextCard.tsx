/**
 * LongevityNextCard —— 抗衰主页 v1(plan-toward-goal-v2 第一刀)。
 *
 * 把已上线但无 UI 的两个后端能力接到用户面前:
 *   - 冷启动信息增益(/twin/me/next-data):下一步补哪项数据解锁最多
 *   - 因果记忆(/personal-outcome/me/causal-notes):事件×指标变化(相关非因果)
 *
 * 诚实:无数据/无建议 → 不渲染(返回 null),不占位造声势;因果文案带"相关非因果"。
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';
import type { NextDataSuggestion, CausalNote } from '../../services/longevityHome';

interface Props {
  next?: NextDataSuggestion | null;
  causal?: CausalNote | null;
  onPress?: () => void;
}

export default function LongevityNextCard({ next, causal, onPress }: Props) {
  const { c, s } = useTheme();
  if (!next && !causal) return null; // 无内容不占位

  return (
    <Pressable
      testID="home-longevity-next-card"
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [
        styles.row,
        { backgroundColor: c.bgCard, borderColor: c.separator, opacity: pressed && onPress ? 0.78 : 1 },
      ]}
      accessibilityRole={onPress ? 'button' : 'text'}
      accessibilityLabel={
        (next ? `抗衰下一步:${next.item},解锁${next.unlocks}。` : '') +
        (causal ? causal.text : '')
      }
    >
      <View style={[styles.iconWrap, { backgroundColor: c.brandLight }]}>
        <Ionicons name="navigate-outline" size={16} color={c.brand} />
      </View>
      <View style={styles.textWrap}>
        {next ? (
          <>
            <Text style={[styles.title, { color: c.labelPrimary }]} numberOfLines={1} maxFontSizeMultiplier={1.3}>
              抗衰下一步:{next.item}
            </Text>
            <Text style={[styles.sub, { color: c.labelTertiary }]} numberOfLines={1} maxFontSizeMultiplier={1.3}>
              解锁 {next.unlocks}
            </Text>
          </>
        ) : (
          <Text style={[styles.title, { color: c.labelPrimary }]} numberOfLines={1} maxFontSizeMultiplier={1.3}>
            抗衰洞察
          </Text>
        )}
        {causal ? (
          <View style={[styles.causalRow, { backgroundColor: causal.direction === '改善' ? s.success.bg : s.neutral?.bg ?? c.fill }]}>
            <Ionicons
              name={causal.direction === '改善' ? 'trending-up' : 'trending-down'}
              size={11}
              color={causal.direction === '改善' ? s.success.fg : c.labelTertiary}
            />
            <Text
              style={[styles.causalText, { color: causal.direction === '改善' ? s.success.fg : c.labelSecondary }]}
              numberOfLines={2}
              maxFontSizeMultiplier={1.2}
            >
              {causal.text}
            </Text>
          </View>
        ) : null}
      </View>
      {onPress ? <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} /> : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    marginBottom: spacing.md,
  },
  iconWrap: { width: 30, height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center' },
  textWrap: { flex: 1, gap: 3, minWidth: 0 },
  title: { fontSize: 14, fontWeight: '800' },
  sub: { fontSize: 11, fontWeight: '500' },
  causalRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    alignSelf: 'flex-start',
    paddingHorizontal: 7,
    paddingVertical: 3,
    borderRadius: 8,
    marginTop: 2,
  },
  causalText: { fontSize: 10.5, fontWeight: '600', flexShrink: 1 },
});
