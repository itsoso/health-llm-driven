/**
 * AgentSurface — 首页单卡优先级选择器.
 *
 * 按优先级从高到低选 1 张卡展示:
 * 1. Critical/High safety alert (红/橙)
 * 2. Open Episode (跑后恢复等闭环未完成)
 * 3. Today Coach (今日重点)
 * 4. 空 (都没有时不渲染)
 *
 * 目标: 首页只露 1 张"阿衡当前最想说的话",不是 8 张卡堆叠.
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import * as Haptics from 'expo-haptics';
import { useQuery } from '@tanstack/react-query';
import { getSafetyReport, type SafetyAlert } from '../../services/safety';
import { useMyEpisodes } from '../../hooks/useEpisode';
import { useTodayCoach } from '../../hooks/useTodayCoach';
import { queryKeys } from '../../applib/queryKeys';
import { spacing, radii } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { EpisodeListItem, RiskLevel } from '../../services/episodes';
import type { TodayCoachFocus } from '../../services/todayCoach';

function getSeverityKey(s: any): string {
  return typeof s === 'string' ? s : s?.label ?? 'info';
}

export default function AgentSurface() {
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);

  const { data: safetyData, isLoading: safetyLoading } = useQuery({
    queryKey: queryKeys.safety,
    queryFn: getSafetyReport,
    staleTime: 300_000,
  });
  const { data: episodes = [], isLoading: episodesLoading } = useMyEpisodes({
    status: 'open',
    limit: 1,
    days: 3,
  });
  const todayCoach = useTodayCoach();

  const isLoading = safetyLoading || episodesLoading || todayCoach.isLoading;

  // Priority 1: Critical/High alert
  const alerts = safetyData?.alerts || [];
  const criticalAlert = alerts.find((a: SafetyAlert) => {
    const sev = getSeverityKey(a.severity);
    return sev === 'critical' || sev === 'high';
  });

  if (isLoading) {
    return (
      <View style={styles.card}>
        <ActivityIndicator size="small" color={c.brand} />
      </View>
    );
  }

  if (criticalAlert) {
    return <SafetyAlertCard alert={criticalAlert} c={c} isDark={isDark} />;
  }

  // Priority 2: Open Episode
  if (episodes.length > 0) {
    return <EpisodeCard episode={episodes[0]} c={c} isDark={isDark} />;
  }

  // Priority 3: Today Coach
  if (todayCoach.data) {
    return <TodayCoachCard focus={todayCoach.data} c={c} isDark={isDark} />;
  }

  // Priority 4: 空
  return null;
}

// ── Safety Alert Card ──
function SafetyAlertCard({ alert, c, isDark }: { alert: SafetyAlert; c: ColorPalette; isDark: boolean }) {
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);
  const sev = getSeverityKey(alert.severity);
  const color = sev === 'critical' ? c.red : c.amber;
  const bg = sev === 'critical' ? c.tintRed : c.tintAmber;

  const onPress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    router.push('/(tabs)/alerts' as any);
  };

  return (
    <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={styles.card}>
      <View style={styles.row}>
        <View style={[styles.iconWrap, { backgroundColor: bg }]}>
          <Ionicons name="alert-circle" size={20} color={color} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={[txt.kicker, { color }]}>安全告警</Text>
          <Text style={txt.title} numberOfLines={2}>
            {alert.title}
          </Text>
          <Text style={txt.body} numberOfLines={2}>
            {alert.message}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
      </View>
    </TouchableOpacity>
  );
}

// ── Episode Card ──
function EpisodeCard({ episode, c, isDark }: { episode: EpisodeListItem; c: ColorPalette; isDark: boolean }) {
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const onPress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    router.push(`/episode/${episode.id}` as any);
  };

  const progress =
    episode.actions_total > 0 ? Math.round((episode.actions_done / episode.actions_total) * 100) : 0;

  return (
    <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={styles.card}>
      <View style={styles.row}>
        <View style={styles.iconWrap}>
          <Ionicons name={_iconForType(episode.episode_type)} size={20} color={c.brand} />
        </View>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={txt.kicker}>{_titleForType(episode.episode_type)}</Text>
            <RiskDot level={episode.risk_level} c={c} />
          </View>
          <Text style={txt.title} numberOfLines={2}>
            {episode.headline || '查看本次的恢复方案'}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
      </View>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${progress}%` }]} />
      </View>
      <Text style={txt.progressText}>
        进度 {episode.actions_done}/{episode.actions_total}
        {episode.actions_done === episode.actions_total && episode.actions_total > 0 ? ' · 已完成 ✓' : ''}
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
    level === 'L4' || level === 'L3'
      ? c.red
      : level === 'L2'
      ? c.orange
      : level === 'L1'
      ? c.amber
      : c.green;
  return <View style={{ width: 7, height: 7, borderRadius: 3.5, backgroundColor: color }} />;
}

// ── Today Coach Card ──
function TodayCoachCard({ focus, c, isDark }: { focus: TodayCoachFocus; c: ColorPalette; isDark: boolean }) {
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);

  const meta = statusMeta(focus.status, c);

  const onPress = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    if (focus.actionRoute) {
      router.push(focus.actionRoute as any);
    }
  };

  return (
    <TouchableOpacity activeOpacity={0.85} onPress={onPress} style={styles.card}>
      <View style={styles.row}>
        <View style={[styles.iconWrap, { backgroundColor: meta.bg }]}>
          <Ionicons name={meta.icon} size={20} color={meta.color} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={[txt.kicker, { color: meta.color }]}>{meta.label}</Text>
          <Text style={txt.title} numberOfLines={2}>
            {focus.title}
          </Text>
          <Text style={txt.body} numberOfLines={2}>
            {focus.reason}
          </Text>
        </View>
        <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />
      </View>
    </TouchableOpacity>
  );
}

function statusMeta(status: TodayCoachFocus['status'], c: ColorPalette) {
  switch (status) {
    case 'ok':
      return { icon: 'checkmark-circle' as const, color: c.brand, bg: c.brandLight, label: '稳定' };
    case 'attention':
      return { icon: 'radio-button-on' as const, color: '#0A84FF', bg: c.tintBlue, label: '执行中' };
    case 'risk':
      return { icon: 'alert-circle' as const, color: c.red, bg: c.tintRed, label: '优先处理' };
    case 'missing_data':
      return { icon: 'cloud-offline' as const, color: c.amber, bg: c.tintAmber, label: '补数据' };
  }
}

// ── Styles ──
function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      padding: spacing.md,
      marginHorizontal: spacing.lg,
      marginBottom: spacing.md,
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
    row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
    iconWrap: {
      width: 36,
      height: 36,
      borderRadius: radii.md,
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: c.brandLight,
    },
    progressTrack: {
      marginTop: 12,
      height: 4,
      borderRadius: 2,
      backgroundColor: c.fill,
      overflow: 'hidden',
    },
    progressFill: {
      height: 4,
      borderRadius: 2,
      backgroundColor: c.brand,
    },
  });
}

function createTxt(c: ColorPalette) {
  return {
    kicker: { fontSize: 11, fontWeight: '600', color: c.brand, marginBottom: 2 } as TextStyle,
    title: { fontSize: 15, fontWeight: '700', color: c.labelPrimary, lineHeight: 20 } as TextStyle,
    body: { fontSize: 13, color: c.labelSecondary, marginTop: 4, lineHeight: 18 } as TextStyle,
    progressText: {
      fontSize: 11,
      color: c.labelTertiary,
      marginTop: 6,
      fontWeight: '500',
    } as TextStyle,
  };
}
