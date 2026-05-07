import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextStyle, SectionList, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { getLogs, type NotificationLog } from '../services/notifications';
import { colors, spacing, radii, shadows } from '../constants/theme';

const TYPE_META: Record<string, { icon: string; color: string }> = {
  health_alert: { icon: 'warning', color: '#FF453A' },
  morning_briefing: { icon: 'sunny', color: '#FF9F0A' },
  reminder: { icon: 'alarm', color: colors.brand },
  ai_advice: { icon: 'sparkles', color: '#AF52DE' },
  test: { icon: 'flask', color: colors.labelSecondary },
};

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
 * 合并同一条推送的 per-channel log 行 (backend push_service 每通道写一行 NotificationLog,
 * 导致 UI 看到"3 条重复"). 按 (notification_type, title, content, ±30s) 聚合, 保留最早时间 +
 * 合并所有 channel 状态. 2026-05-07 修复.
 */
function collapseMultiChannel(logs: NotificationLog[]): Array<NotificationLog & { channels?: Array<{ name: string; status: string }> }> {
  const buckets: Array<NotificationLog & { channels: Array<{ name: string; status: string }> }> = [];
  for (const log of logs) {
    const logTime = new Date(log.sent_at || log.created_at || 0).getTime();
    // 查是否有"同 title + 同 type + ±60s"的已存条目
    const existing = buckets.find(b =>
      b.notification_type === log.notification_type &&
      b.title === log.title &&
      b.content === log.content &&
      Math.abs(new Date(b.sent_at || b.created_at || 0).getTime() - logTime) <= 60_000,
    );
    if (existing) {
      existing.channels.push({ name: log.channel, status: log.status });
      // 任意一个 channel sent, 视整条 sent
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

export default function NotificationHistoryScreen() {
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
          <Ionicons name="chevron-back" size={24} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.title}>推送历史</Text>
        <View style={{ width: 40 }} />
      </View>

      {isLoading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brand} /></View>
      ) : logs.length === 0 ? (
        <View style={styles.center}>
          <Ionicons name="notifications-off-outline" size={48} color={colors.labelTertiary} />
          <Text style={txt.empty}>暂无推送记录</Text>
        </View>
      ) : (
        <SectionList
          sections={sections}
          keyExtractor={(item) => String(item.id)}
          renderSectionHeader={({ section }) => (
            <Text style={txt.sectionHeader}>{section.title}</Text>
          )}
          renderItem={({ item }) => <LogRow log={item} />}
          contentContainerStyle={styles.list}
          stickySectionHeadersEnabled={false}
        />
      )}
    </SafeAreaView>
  );
}

function LogRow({ log }: { log: NotificationLog & { channels?: Array<{ name: string; status: string }> } }) {
  const meta = TYPE_META[log.notification_type] || TYPE_META.test;
  const time = log.sent_at?.slice(11, 16) || log.created_at?.slice(11, 16) || '';
  const channelIcon: Record<string, string> = {
    ios_apns: '📱',
    wechat: '💬',
    telegram: '✈️',
  };

  return (
    <View style={styles.logRow}>
      <View style={[styles.iconCircle, { backgroundColor: meta.color + '18' }]}>
        <Ionicons name={meta.icon as any} size={16} color={meta.color} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={txt.logTitle} numberOfLines={1}>{log.title}</Text>
        <Text style={txt.logContent} numberOfLines={2}>{log.content}</Text>
        {log.channels && log.channels.length > 0 && (
          <Text style={txt.channelLine}>
            {log.channels.map(ch =>
              `${channelIcon[ch.name] || ch.name}${ch.status === 'sent' ? '' : '❌'}`,
            ).join(' ')}
          </Text>
        )}
      </View>
      <Text style={txt.logTime}>{time}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bgPrimary },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: spacing.md },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  list: { padding: spacing.lg, paddingBottom: 40 },
  logRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: colors.bgCard, borderRadius: radii.lg,
    paddingHorizontal: spacing.md, paddingVertical: 12,
    marginBottom: spacing.xs, ...shadows.subtle,
  },
  iconCircle: { width: 32, height: 32, borderRadius: 16, justifyContent: 'center', alignItems: 'center' },
});

const txt = {
  title: { fontSize: 17, fontWeight: '600', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  empty: { fontSize: 15, color: colors.labelTertiary } as TextStyle,
  sectionHeader: { fontSize: 13, fontWeight: '500', color: colors.labelSecondary, marginBottom: spacing.xs, marginTop: spacing.md } as TextStyle,
  logTitle: { fontSize: 15, fontWeight: '500', color: colors.labelPrimary } as TextStyle,
  logContent: { fontSize: 13, color: colors.labelSecondary, marginTop: 2 } as TextStyle,
  logTime: { fontSize: 12, color: colors.labelTertiary } as TextStyle,
  channelLine: { fontSize: 11, color: colors.labelTertiary, marginTop: 3 } as TextStyle,
};
