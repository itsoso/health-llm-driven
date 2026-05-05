/**
 * 健康事件流 Timeline 页 (产品改进 H, MVP).
 *
 * 从多源聚合的统一时间线: 运动 / 告警 / 睡眠低分 / 用药 / 体检.
 * 每条事件可点击跳详情 (deep_link).
 *
 * 入口: settings → 健康事件流; 主页未来会嵌入摘要版.
 */
import React, { useMemo } from 'react';
import {
  View, Text, ScrollView, StyleSheet, TouchableOpacity, TextStyle, ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { fetchTimeline, type TimelineEvent } from '../services/timeline';
import { useTheme, type ColorPalette } from '../hooks/useTheme';
import { spacing, radii, shadows } from '../constants/theme';

export default function TimelineScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['timeline', 30],
    queryFn: () => fetchTimeline(30, 40),
    staleTime: 60_000,
  });

  const events = data?.events || [];

  // 按"今天 / 昨天 / N 天前"分组
  const grouped = useMemo(() => groupByDay(events), [events]);

  const handleTap = (e: TimelineEvent) => {
    if (!e.deep_link) return;
    const path = e.deep_link.startsWith('/') ? e.deep_link : `/${e.deep_link}`;
    router.push(path as any);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>健康事件流</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={isFetching} onRefresh={() => { refetch(); }} tintColor={c.brand} />}
      >
        {isLoading ? (
          <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
        ) : events.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="time-outline" size={48} color={c.labelTertiary} />
            <Text style={txt.emptyTitle}>近 30 天无事件</Text>
            <Text style={txt.emptyHint}>跑步、告警、体检都会出现在这里</Text>
          </View>
        ) : (
          <View>
            {grouped.map(([dateLabel, items]) => (
              <View key={dateLabel} style={styles.dayGroup}>
                <Text style={txt.dayLabel}>{dateLabel}</Text>
                <View style={styles.dayList}>
                  {items.map((e, idx) => (
                    <TouchableOpacity
                      key={e.id}
                      style={[styles.row, idx === items.length - 1 && styles.rowLast]}
                      onPress={() => handleTap(e)}
                      activeOpacity={e.deep_link ? 0.7 : 1}
                    >
                      <View style={[styles.iconWrap, { backgroundColor: hexToBg(e.color) }]}>
                        <Ionicons name={e.icon as any} size={18} color={e.color} />
                      </View>
                      <View style={styles.content}>
                        <Text style={txt.evTitle} numberOfLines={1}>{e.title}</Text>
                        {e.subtitle ? (
                          <Text style={txt.evSubtitle} numberOfLines={1}>{e.subtitle}</Text>
                        ) : null}
                      </View>
                      <Text style={txt.evTime}>{formatTime(e.occurred_at)}</Text>
                      {e.deep_link ? (
                        <Ionicons name="chevron-forward" size={16} color={c.labelTertiary} />
                      ) : null}
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function groupByDay(events: TimelineEvent[]): [string, TimelineEvent[]][] {
  const groups = new Map<string, TimelineEvent[]>();
  const today = new Date(); today.setHours(0, 0, 0, 0);
  for (const e of events) {
    const d = new Date(e.occurred_at); d.setHours(0, 0, 0, 0);
    const diffDays = Math.round((today.getTime() - d.getTime()) / (24 * 3600 * 1000));
    let key: string;
    if (diffDays === 0) key = '今天';
    else if (diffDays === 1) key = '昨天';
    else if (diffDays < 7) key = `${diffDays} 天前`;
    else key = `${d.getMonth() + 1}/${d.getDate()}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(e);
  }
  return Array.from(groups.entries());
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  } catch { return ''; }
}

// hex 颜色 → 同色调浅底色 (用于 icon 容器)
function hexToBg(hex: string): string {
  // 简单加 22 (~13% 透明) 后缀, iOS 解析支持 #RRGGBBAA
  if (/^#[0-9a-fA-F]{6}$/.test(hex)) return hex + '22';
  return hex;
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: {
      flexDirection: 'row', alignItems: 'center',
      paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    },
    backBtn: { width: 40, alignItems: 'flex-start' },
    scroll: { paddingHorizontal: spacing.md, paddingBottom: spacing.xl },
    center: { paddingTop: 80, alignItems: 'center' },
    empty: { paddingTop: 80, alignItems: 'center', paddingHorizontal: spacing.lg },
    dayGroup: { marginBottom: spacing.md },
    dayList: {
      backgroundColor: c.bgCard, borderRadius: radii.md,
      ...shadows.subtle,
    },
    row: {
      flexDirection: 'row', alignItems: 'center',
      paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
      gap: spacing.sm,
      borderBottomWidth: 1, borderBottomColor: c.separator,
    },
    rowLast: { borderBottomWidth: 0 },
    iconWrap: {
      width: 36, height: 36, borderRadius: 18,
      alignItems: 'center', justifyContent: 'center',
    },
    content: { flex: 1, gap: 2 },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary } as TextStyle,
    dayLabel: {
      fontSize: 13, fontWeight: '600', color: c.labelSecondary,
      paddingHorizontal: spacing.xs, paddingVertical: spacing.sm,
    } as TextStyle,
    emptyTitle: { fontSize: 16, fontWeight: '600', color: c.labelPrimary, marginTop: spacing.md } as TextStyle,
    emptyHint: { fontSize: 13, color: c.labelSecondary, marginTop: spacing.xs } as TextStyle,
    evTitle: { fontSize: 15, color: c.labelPrimary, fontWeight: '500' } as TextStyle,
    evSubtitle: { fontSize: 12, color: c.labelTertiary } as TextStyle,
    evTime: { fontSize: 12, color: c.labelTertiary, marginRight: 4 } as TextStyle,
  };
}
