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
import { normalizeHealthActionRoute } from '../utils/dailyArtifactNavigation';
import {
  revaColors as C,
  revaRadii,
  revaSpacing,
  revaShadows,
  revaFonts,
} from '../constants/revaTheme';

export default function TimelineScreen() {
  const router = useRouter();

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['timeline', 30],
    queryFn: () => fetchTimeline(30, 40),
    staleTime: 60_000,
  });

  const events = data?.events || [];

  // 按"今天 / 昨天 / N 天前"分组
  const grouped = useMemo(() => groupByDay(events), [events]);

  const handleTap = (e: TimelineEvent) => {
    const path = normalizeHealthActionRoute(e.deep_link, `${e.title} ${e.subtitle ?? ''}`);
    if (!path) return;
    router.push(path as any);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={26} color={C.ink1} />
        </TouchableOpacity>
        <Text style={txt.title}>健康事件流</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={<RefreshControl refreshing={isFetching} onRefresh={() => { refetch(); }} tintColor={C.green500} />}
      >
        {isLoading ? (
          <View style={styles.center}><ActivityIndicator color={C.green500} /></View>
        ) : events.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="time-outline" size={48} color={C.ink3} />
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
                        <Ionicons name="chevron-forward" size={16} color={C.ink3} />
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

// Reva 设计语言:暖 paper 底 / 暖白 surface 卡 / r-md / 时间走等宽 mono。
const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.paper },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: revaSpacing.s3, paddingVertical: revaSpacing.s2,
  },
  backBtn: { width: 40, alignItems: 'flex-start' },
  scroll: { paddingHorizontal: revaSpacing.s3, paddingBottom: revaSpacing.s5 },
  center: { paddingTop: 80, alignItems: 'center' },
  empty: { paddingTop: 80, alignItems: 'center', paddingHorizontal: revaSpacing.s4 },
  dayGroup: { marginBottom: revaSpacing.s3 },
  dayList: {
    backgroundColor: C.surface, borderRadius: revaRadii.md,
    ...revaShadows.sm,
  },
  row: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: revaSpacing.s3, paddingVertical: revaSpacing.s2,
    gap: revaSpacing.s2,
    borderBottomWidth: 1, borderBottomColor: C.line,
  },
  rowLast: { borderBottomWidth: 0 },
  iconWrap: {
    width: 36, height: 36, borderRadius: 18,
    alignItems: 'center', justifyContent: 'center',
  },
  content: { flex: 1, gap: 2 },
});

// 时间走 IBM Plex Mono = Reva 等宽 signature;文字走 Manrope/ink。
const txt = {
  title: { fontFamily: revaFonts.sans, fontSize: 17, fontWeight: '600', color: C.ink1 } as TextStyle,
  dayLabel: {
    fontFamily: revaFonts.sans, fontSize: 13, fontWeight: '600', color: C.ink2,
    paddingHorizontal: revaSpacing.s1, paddingVertical: revaSpacing.s2,
  } as TextStyle,
  emptyTitle: { fontFamily: revaFonts.sans, fontSize: 16, fontWeight: '600', color: C.ink1, marginTop: revaSpacing.s3 } as TextStyle,
  emptyHint: { fontFamily: revaFonts.sans, fontSize: 13, color: C.ink2, marginTop: revaSpacing.s1 } as TextStyle,
  evTitle: { fontFamily: revaFonts.sans, fontSize: 15, color: C.ink1, fontWeight: '500' } as TextStyle,
  evSubtitle: { fontFamily: revaFonts.sans, fontSize: 12, color: C.ink3 } as TextStyle,
  evTime: { fontFamily: revaFonts.mono, fontSize: 12, color: C.ink3, marginRight: 4 } as TextStyle,
};
