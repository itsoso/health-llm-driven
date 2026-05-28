/**
 * AgentTopicsRow —— 今日 Tab 后台观察横向滚动话题区 (2026-05-26 重构).
 *
 * 之前的 AgentFollowUpQueue 是一张扁平的"运行状态条", 信息密度过高且占整宽;
 * 这里改成 3 张色彩分组的小卡横向滚动, 每张主题独立 (轨迹 / 建议 / 结果),
 * 视觉更轻、可发现性更好. 用户可以横滑看更多.
 */

import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { spacing, radii } from '../../constants/theme';
import { useTheme } from '../../hooks/useTheme';

export interface TopicCard {
  key: string;
  icon: keyof typeof Ionicons.glyphMap;
  iconColor: string;
  iconTint: string;
  label: string;
  title: string;
  detail: string;
  badge?: string | null;
  badgeColor?: string;
  badgeTint?: string;
  onPress: () => void;
}

interface Props {
  cards: TopicCard[];
  loading?: boolean;
  title?: string;
  rightHint?: string;
  onPressMore?: () => void;
}

function HomeText({
  maxFontSizeMultiplier = 1.18,
  ...rest
}: React.ComponentProps<typeof Text>) {
  return <Text maxFontSizeMultiplier={maxFontSizeMultiplier} {...rest} />;
}

export default function AgentTopicsRow({
  cards,
  loading,
  title = '今日话题',
  rightHint,
  onPressMore,
}: Props) {
  const { c } = useTheme();

  if (!loading && cards.length === 0) return null;

  return (
    <View style={styles.wrapper}>
      <View style={styles.titleRow}>
        <View style={styles.titleLeft}>
          <View style={[styles.titleDot, { backgroundColor: c.brand }]} />
          <HomeText style={[styles.titleText, { color: c.labelPrimary }]}>
            {title}
          </HomeText>
          {rightHint ? (
            <HomeText
              style={[styles.titleHint, { color: c.labelTertiary }]}
              numberOfLines={1}
            >
              · {rightHint}
            </HomeText>
          ) : null}
        </View>
        {onPressMore ? (
          <Pressable
            onPress={onPressMore}
            hitSlop={8}
            accessibilityLabel="查看更多话题"
          >
            <Ionicons
              name="chevron-forward"
              size={15}
              color={c.labelTertiary}
            />
          </Pressable>
        ) : null}
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {loading && cards.length === 0
          ? Array.from({ length: 3 }).map((_, i) => (
              <View
                key={`skeleton-${i}`}
                style={[
                  styles.card,
                  {
                    backgroundColor: c.bgCard,
                    borderColor: c.separator,
                  },
                ]}
              >
                <View
                  style={[
                    styles.cardIcon,
                    { backgroundColor: c.separator },
                  ]}
                />
                <View
                  style={[
                    styles.skeletonLine,
                    { backgroundColor: c.separator, width: '70%' },
                  ]}
                />
                <View
                  style={[
                    styles.skeletonLine,
                    { backgroundColor: c.separator, width: '90%' },
                  ]}
                />
              </View>
            ))
          : cards.map((card) => (
              <Pressable
                key={card.key}
                onPress={card.onPress}
                style={({ pressed }) => [
                  styles.card,
                  {
                    backgroundColor: c.bgCard,
                    borderColor: c.separator,
                    opacity: pressed ? 0.78 : 1,
                  },
                ]}
                accessibilityRole="button"
                accessibilityLabel={`${card.label}: ${card.title}`}
              >
                <View style={styles.cardHeader}>
                  <View
                    style={[
                      styles.cardIcon,
                      { backgroundColor: card.iconTint },
                    ]}
                  >
                    <Ionicons
                      name={card.icon}
                      size={14}
                      color={card.iconColor}
                    />
                  </View>
                  {card.badge ? (
                    <View
                      style={[
                        styles.cardBadge,
                        {
                          backgroundColor:
                            card.badgeTint ?? card.iconTint,
                          borderColor:
                            card.badgeColor ?? card.iconColor,
                        },
                      ]}
                    >
                      <HomeText
                        style={[
                          styles.cardBadgeText,
                          { color: card.badgeColor ?? card.iconColor },
                        ]}
                        numberOfLines={1}
                      >
                        {card.badge}
                      </HomeText>
                    </View>
                  ) : null}
                </View>
                <HomeText
                  style={[styles.cardLabel, { color: card.iconColor }]}
                  numberOfLines={1}
                >
                  {card.label}
                </HomeText>
                <HomeText
                  style={[styles.cardTitle, { color: c.labelPrimary }]}
                  numberOfLines={2}
                >
                  {card.title}
                </HomeText>
                <HomeText
                  style={[styles.cardDetail, { color: c.labelTertiary }]}
                  numberOfLines={2}
                >
                  {card.detail}
                </HomeText>
              </Pressable>
            ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    marginBottom: spacing.md,
    gap: 10,
  },
  titleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.xs,
  },
  titleLeft: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  titleDot: { width: 6, height: 6, borderRadius: 3 },
  titleText: { fontSize: 14, fontWeight: '800' },
  titleHint: { fontSize: 11, fontWeight: '500', flex: 1, minWidth: 0 },

  scrollContent: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: 2,
    paddingBottom: 2,
  },
  card: {
    width: 168,
    minHeight: 124,
    borderRadius: radii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    gap: 6,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 6,
  },
  cardIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cardBadge: {
    minHeight: 18,
    paddingHorizontal: 7,
    paddingVertical: 1,
    borderRadius: radii.full,
    borderWidth: StyleSheet.hairlineWidth,
    flexShrink: 1,
    minWidth: 0,
  },
  cardBadgeText: { fontSize: 10, fontWeight: '700', lineHeight: 14 },

  cardLabel: { fontSize: 10, fontWeight: '800', letterSpacing: 0.2 },
  cardTitle: {
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 17,
    minHeight: 17,
  },
  cardDetail: { fontSize: 11, lineHeight: 14, fontWeight: '500' },

  skeletonLine: {
    height: 8,
    borderRadius: 4,
    opacity: 0.6,
  },
});
