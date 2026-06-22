import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, SectionList, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { getLogs, type NotificationLog } from '../services/notifications';
import { resolveNotificationRoute } from '../services/notificationRoutes';
import { spacing, radii, shadows } from '../constants/theme';
import { ColorPalette, useTheme } from '../hooks/useTheme';

function buildTypeMeta(c: ColorPalette): Record<string, { icon: string; color: string }> {
  return {
    health_alert: { icon: 'warning', color: '#FF453A' },
    morning_briefing: { icon: 'sunny', color: '#FF9F0A' },
    reminder: { icon: 'alarm', color: c.brand },
    ai_advice: { icon: 'sparkles', color: '#AF52DE' },
    test: { icon: 'flask', color: c.labelSecondary },
  };
}

function groupByDate(logs: NotificationLog[]) {
  const map = new Map<string, NotificationLog[]>();
  for (const log of logs) {
    const date = log.sent_at?.slice(0, 10) || log.created_at?.slice(0, 10) || '未知';
    const arr = map.get(date) || [];
    arr.push(log);
    map.set(date, arr);
  }
  return Array.from(map.entries()).map(([title, data]) => ({ title, data }));
}

/**
 * 兼容旧 row (per-channel 独立行) 的合并 fallback.
 * 新 row 已经自带 channels JSON, 不走这里.
 * 旧 row 按 (notification_type, title, content, ±60s) 聚合.
 */
function collapseMultiChannel(logs: NotificationLog[]): Array<NotificationLog & { channels?: Array<{ name: string; status: string }> }> {
  const buckets: Array<NotificationLog & { channels: Array<{ name: string; status: string }> }> = [];
  for (const log of logs) {
    // 新 row: 已携带 channels 字段, 直接透传
    if ((log as any).channels && Array.isArray((log as any).channels)) {
      buckets.push({ ...log, channels: (log as any).channels });
      continue;
    }
    const logTime = new Date(log.sent_at || log.created_at || 0).getTime();
    const existing = buckets.find(b =>
      b.notification_type === log.notification_type &&
      b.title === log.title &&
      b.content === log.content &&
      Math.abs(new Date(b.sent_at || b.created_at || 0).getTime() - logTime) <= 60_000,
    );
    if (existing) {
      existing.channels.push({ name: log.channel, status: log.status });
      if (log.status === 'sent' && existing.status !== 'sent') {
        existing.status = 'sent';
        existing.sent_at = log.sent_at || existing.sent_at;
      }
    } else {
      buckets.push({
        ...log,
        channels: [{ name: log.channel, status: log.status }],
      });
    }
  }
  return buckets;
}

/**
 * 历史行的目的地: 走与活推送同一个 resolveNotificationRoute (含 scheme 归一 + legacy screen).
 * 该 log 的 deep_link 既可能在 data.deep_link, 也可能在顶层列 log.deep_link — 合并后再解析.
 * 解析不出再退到 workout_analysis 的 workout_id 兜底; 都没有 → null (行不可点).
 */
function getLogDeepLink(log: NotificationLog): string | null {
  const merged = { ...(log.data ?? {}), deep_link: log.deep_link ?? log.data?.deep_link };
  const route = resolveNotificationRoute(merged);
  if (route) return route;
  if (log.notification_type === 'workout_analysis' && log.data?.workout_id) {
    return `/workout-detail?id=${log.data.workout_id}`;
  }
  return null;
}

export default function NotificationHistoryScreen() {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const router = useRouter();

  const { data: logs = [], isLoading } = useQuery({
    queryKey: ['notificationLogs'],
    queryFn: () => getLogs(100),
    staleTime: 30_000,
  });

  const collapsed = React.useMemo(() => collapseMultiChannel(logs), [logs]);
  const sections = groupByDate(collapsed);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.title}>推送历史</Text>
        <View style={{ width: 40 }} />
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator color={c.brand} /></View>
      ) : logs.length === 0 ? (
        <View style={styles.center}>
          <Ionicons name="notifications-off-outline" size={48} color={c.labelTertiary} />
          <Text style={styles.empty}>暂无推送记录</Text>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => String(item.id)}
          renderSectionHeader={({ section }) => (
            <Text style={styles.sectionHeader}>{section.title}</Text>
          )}
          renderItem={({ item }) => <LogRow log={item} />}
          contentContainerStyle={styles.list}
          stickySectionHeadersEnabled={false}
        />
      )}
    </SafeAreaView>
  );
}

function LogRow({ log }: { log: NotificationLog }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const router = useRouter();
  const typeMeta = buildTypeMeta(c);
  const meta = typeMeta[log.notification_type] || typeMeta.test;
  const time = log.sent_at?.slice(11, 16) || log.created_at?.slice(11, 16) || '';
  const deepLink = getLogDeepLink(log);
  const channelIcon: Record<string, string> = {
    ios_apns: '📱',
    wechat: '💬',
    telegram: '✈️',
  };

  return (
    <TouchableOpacity
      style={styles.logRow}
      disabled={!deepLink}
      onPress={() => { if (deepLink) router.push(deepLink as any); }}
      accessibilityRole={deepLink ? 'button' : undefined}
      accessibilityLabel={deepLink ? `打开 ${log.title}` : undefined}
    >
      <View style={[styles.iconCircle, { backgroundColor: meta.color + '18' }]}>
        <Ionicons name={meta.icon as any} size={16} color={meta.color} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.logTitle} numberOfLines={1}>{log.title}</Text>
        <Text style={styles.logContent} numberOfLines={2}>{log.content}</Text>
        {log.channels && log.channels.length > 0 && (
          <Text style={styles.channelLine}>
            {log.channels.map(ch =>
              `${channelIcon[ch.name] || ch.name}${ch.status === 'sent' ? '' : '❌'}`,
            ).join(' ')}
          </Text>
        )}
      </View>
      <View style={styles.trailing}>
        <Text style={styles.logTime}>{time}</Text>
        {deepLink && <Ionicons name="chevron-forward" size={16} color={c.labelTertiary} />}
      </View>
    </TouchableOpacity>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: spacing.md },
    header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
    backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
    list: { padding: spacing.lg, paddingBottom: 40 },
    logRow: {
      flexDirection: 'row', alignItems: 'center', gap: 10,
      backgroundColor: c.bgCard, borderRadius: radii.lg,
      paddingHorizontal: spacing.md, paddingVertical: 12,
      marginBottom: spacing.xs, ...shadows.subtle,
    },
    iconCircle: { width: 32, height: 32, borderRadius: 16, justifyContent: 'center', alignItems: 'center' },
    trailing: { alignItems: 'flex-end', gap: 4 },
    title: { fontSize: 17, fontWeight: '600', color: c.labelPrimary, flex: 1, textAlign: 'center' },
    empty: { fontSize: 15, color: c.labelTertiary },
    sectionHeader: { fontSize: 13, fontWeight: '500', color: c.labelSecondary, marginBottom: spacing.xs, marginTop: spacing.md },
    logTitle: { fontSize: 15, fontWeight: '500', color: c.labelPrimary },
    logContent: { fontSize: 13, color: c.labelSecondary, marginTop: 2 },
    logTime: { fontSize: 12, color: c.labelTertiary },
    channelLine: { fontSize: 11, color: c.labelTertiary, marginTop: 3 },
  });
}
