/**
 * HomeTimelinePreview — 主页紧凑事件流 (H Phase 2).
 *
 * 故事流: 从"卡片堆"→ "故事感". 显示最近 3 条事件 + '全部' 入口.
 * Karpathy 启发: 健康问题本质是时间序列, 主页应该有时间感.
 *
 * 复用 components/dashboard/DashboardCard 外壳, 与其它主页卡片一致.
 */
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { fetchTimeline, type TimelineEvent } from '../../services/timeline';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import { spacing } from '../../constants/theme';
import DashboardCard from './DashboardCard';
import { normalizeHealthActionRoute } from '../../utils/dailyArtifactNavigation';

export default function HomeTimelinePreview() {
  const { c } = useTheme();
  const router = useRouter();
  const styles = useMemo(() => createStyles(c), [c]);
  const txt = useMemo(() => createTxt(c), [c]);

  const { data, isLoading } = useQuery({
    queryKey: ['timeline', 'preview'],
    queryFn: () => fetchTimeline(7, 5),  // 最近 7 天上限 5 条
    staleTime: 60_000,
  });

  const events = data?.events || [];
  if (!isLoading && events.length === 0) return null;

  const previewEvents = events.slice(0, 3);

  const onTap = (e: TimelineEvent) => {
    const path = normalizeHealthActionRoute(e.deep_link, `${e.title} ${e.subtitle ?? ''}`);
    if (!path) return;
    router.push(path as any);
  };

  return (
    <DashboardCard
      icon="time-outline"
      iconColor={c.purple}
      title="最近事件"
      trailing={
        <TouchableOpacity
          onPress={() => router.push('/timeline' as any)}
          hitSlop={8}
        >
          <Text style={txt.viewAll}>全部</Text>
        </TouchableOpacity>
      }
    >
      {isLoading ? (
        <Text style={txt.loading}>加载中...</Text>
      ) : (
        <View style={styles.list}>
          {previewEvents.map((e, idx) => (
            <TouchableOpacity
              key={e.id}
              style={[styles.row, idx === previewEvents.length - 1 && styles.rowLast]}
              onPress={() => onTap(e)}
              activeOpacity={e.deep_link ? 0.7 : 1}
            >
              <View style={[styles.iconWrap, { backgroundColor: hexToBg(e.color) }]}>
                <Ionicons name={e.icon as any} size={16} color={e.color} />
              </View>
              <View style={styles.content}>
                <Text style={txt.title} numberOfLines={1}>{e.title}</Text>
                {e.subtitle ? <Text style={txt.subtitle} numberOfLines={1}>{e.subtitle}</Text> : null}
              </View>
              <Text style={txt.time}>{relativeTime(e.occurred_at)}</Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
    </DashboardCard>
  );
}

function relativeTime(iso: string): string {
  try {
    const d = new Date(iso);
    const now = new Date();
    const todayMidnight = new Date(now); todayMidnight.setHours(0, 0, 0, 0);
    const dMidnight = new Date(d); dMidnight.setHours(0, 0, 0, 0);
    const diffDays = Math.round((todayMidnight.getTime() - dMidnight.getTime()) / 86400000);
    if (diffDays === 0) {
      return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    }
    if (diffDays === 1) return '昨天';
    if (diffDays < 7) return `${diffDays}天前`;
    return `${d.getMonth() + 1}/${d.getDate()}`;
  } catch { return ''; }
}

function hexToBg(hex: string): string {
  if (/^#[0-9a-fA-F]{6}$/.test(hex)) return hex + '22';
  return hex;
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    list: { gap: 0 },
    row: {
      flexDirection: 'row',
      alignItems: 'center',
      paddingVertical: spacing.sm,
      gap: spacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: c.separator,
    },
    rowLast: { borderBottomWidth: 0 },
    iconWrap: {
      width: 32, height: 32, borderRadius: 16,
      alignItems: 'center', justifyContent: 'center',
    },
    content: { flex: 1, gap: 2 },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 14, color: c.labelPrimary, fontWeight: '500' } as TextStyle,
    subtitle: { fontSize: 11, color: c.labelTertiary } as TextStyle,
    time: { fontSize: 11, color: c.labelTertiary, marginRight: 2 } as TextStyle,
    viewAll: { fontSize: 13, color: c.brand, fontWeight: '500' } as TextStyle,
    loading: { fontSize: 12, color: c.labelTertiary, paddingVertical: spacing.sm } as TextStyle,
  };
}
