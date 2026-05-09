/**
 * Home 顶部 Open Episode 卡 — Agent-Native v3 闭环单元入口.
 *
 * 显示最近一个 status='open' 的 Episode (跑后恢复 / 睡眠 / 症状追踪 ...).
 * 点击跳详情页, 完成所有 actions 后端会把 status 翻 closed, 卡自然消失.
 *
 * 没 open episode 时不渲染 (家里没事的时候不打扰用户).
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useMyEpisodes } from '../../hooks/useEpisode';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { EpisodeListItem, RiskLevel } from '../../services/episodes';

export default function OpenEpisodeCard() {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const { data: episodes = [] } = useMyEpisodes({ status: 'open', limit: 3, days: 3 });

  if (episodes.length === 0) return null;

  // 头一条 (最近的 open). 多条以后再做 carousel.
  const ep = episodes[0];

  const onPress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    router.push(`/episode/${ep.id}` as any);
  };

  const progress = ep.actions_total > 0
    ? Math.round((ep.actions_done / ep.actions_total) * 100)
    : 0;

  return (
    <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={styles.card}>
      <View style={styles.row}>
        <View style={styles.iconWrap}>
          <Ionicons name={_iconForType(ep.episode_type)} size={20} color={c.brand} />
        </View>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={txt.title}>{_titleForType(ep.episode_type)}</Text>
            <RiskDot level={ep.risk_level} c={c} />
          </View>
          <Text style={txt.headline} numberOfLines={2}>
            {ep.headline || '查看本次的恢复方案'}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
      </View>

      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${progress}%` }]} />
      </View>
      <Text style={txt.progressText}>
        进度 {ep.actions_done}/{ep.actions_total}
        {ep.actions_done === ep.actions_total && ep.actions_total > 0 ? ' · 已完成 ✓' : ''}
      </Text>
    </TouchableOpacity>
  );
}

function _titleForType(t: string): string {
  const map: Record<string, string> = {
    run_recovery: '跑后恢复',
    run: '跑后恢复',
    sleep: '睡眠复盘',
    symptom: '症状追踪',
    meal: '饮食复盘',
    weight: '体重变化',
    bp: '血压关注',
    glucose: '血糖关注',
  };
  return map[t] || '健康闭环';
}

function _iconForType(t: string): any {
  const map: Record<string, string> = {
    run_recovery: 'trail-sign-outline',
    run: 'trail-sign-outline',
    sleep: 'bed-outline',
    symptom: 'medkit-outline',
    meal: 'restaurant-outline',
    weight: 'scale-outline',
    bp: 'pulse-outline',
    glucose: 'water-outline',
  };
  return (map[t] || 'fitness-outline') as any;
}

function RiskDot({ level, c }: { level: RiskLevel; c: ColorPalette }) {
  const color =
    level === 'L4' || level === 'L3' ? c.red :
    level === 'L2' ? c.orange :
    level === 'L1' ? c.amber :
    c.green;
  return (
    <View style={{
      width: 7, height: 7, borderRadius: 3.5, backgroundColor: color,
    }} />
  );
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.md,
      marginBottom: spacing.md,
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : { shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.06, shadowRadius: 3, elevation: 1 }),
    },
    row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    iconWrap: {
      width: 36, height: 36, borderRadius: radii.md,
      alignItems: 'center', justifyContent: 'center',
      backgroundColor: c.brandLight,
    },
    progressTrack: {
      marginTop: 12,
      height: 4, borderRadius: 2,
      backgroundColor: c.fill,
      overflow: 'hidden',
    },
    progressFill: {
      height: 4, borderRadius: 2, backgroundColor: c.brand,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 15, fontWeight: '700', color: c.labelPrimary } as TextStyle,
    headline: { fontSize: 13, color: c.labelSecondary, marginTop: 2, lineHeight: 18 } as TextStyle,
    progressText: { fontSize: 11, color: c.labelTertiary, marginTop: 6, fontWeight: '500' } as TextStyle,
  };
}
