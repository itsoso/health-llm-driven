import React, { useMemo } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../hooks/useAuth';
import { type ColorPalette, useTheme } from '../hooks/useTheme';
import { radii, spacing } from '../constants/theme';
import { getNotificationDetail } from '../services/notifications';
import { returnToChatWithContext } from '../utils/agentContext';
import { backOrChat } from '../utils/backOrChat';

function displayTime(value: string | null): string {
  if (!value) return '时间未保存';
  // Preserve the recorded offset explicitly: PostgreSQL may return UTC.
  const zone = /(Z|[+-]\d{2}:\d{2})$/.exec(value)?.[1];
  const zoneLabel = zone === 'Z' ? 'UTC' : zone ? `UTC${zone}` : '时区未保存';
  return `${value.slice(0, 16).replace('T', ' ')}（${zoneLabel}）`;
}

export default function NotificationDetailScreen() {
  const { id: rawId } = useLocalSearchParams();
  const parsedId = typeof rawId === 'string' && /^[1-9]\d{0,9}$/.test(rawId) ? Number(rawId) : null;
  const id = parsedId !== null && parsedId <= 2147483647 ? parsedId : null;
  const router = useRouter();
  const { user, isAuthenticated } = useAuth();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const canRead = isAuthenticated && Boolean(user?.id) && id !== null;
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['notificationDetail', user?.id, id],
    queryFn: () => getNotificationDetail(id!),
    enabled: canRead,
    retry: false,
    staleTime: 30_000,
  });
  const detail = canRead && !isError ? data : undefined;
  const error = id === null ? '这条推送链接无效，请返回推送历史重新打开'
    : !isAuthenticated || !user?.id ? '请先登录后查看推送详情'
      : isError ? '暂时无法读取这条推送，可能已不可用。请重试或返回推送历史。' : null;

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.header}>
        <TouchableOpacity accessibilityRole="button" accessibilityLabel="返回" style={styles.back} onPress={() => backOrChat(router)}>
          <Ionicons name="chevron-back" size={24} color={c.labelPrimary} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>推送详情</Text>
        <View style={styles.back} />
      </View>
      {error ? (
        <View style={styles.center}>
          <Ionicons name="information-circle-outline" size={36} color={c.labelSecondary} />
          <Text style={styles.error}>{error}</Text>
          {canRead && <TouchableOpacity accessibilityRole="button" onPress={() => { void refetch(); }} style={styles.retry}>
            <Text style={styles.retryText}>重试</Text>
          </TouchableOpacity>}
        </View>
      ) : isLoading || !detail ? (
        <View style={styles.center} accessibilityLabel="正在读取推送"><ActivityIndicator color={c.brand} /></View>
      ) : (
        <ScrollView contentContainerStyle={styles.body}>
          <View style={styles.card}>
            <Text style={styles.eyebrow}>历史推送</Text>
            <Text style={styles.title}>{detail.title}</Text>
            <Text style={styles.time}>{displayTime(detail.sent_at ?? detail.created_at)}</Text>
            <View style={styles.divider} />
            <Text selectable style={styles.content}>{detail.content}</Text>
          </View>
          <View style={styles.note}>
            <Ionicons name="information-circle-outline" size={19} color={c.labelSecondary} />
            <View style={styles.noteBody}>
              <Text style={styles.noteText}>这是当时保存的推送内容，其中数据和结论未经本次重新核验，不代表当前状态。</Text>
              {detail.content_source === 'saved_notification_text' && (
                <Text style={styles.noteText}>这条历史记录可能仅保留了摘要，未保存的原文无法补全。</Text>
              )}
            </View>
          </View>
          <TouchableOpacity
            accessibilityRole="button"
            style={styles.analyze}
            onPress={() => returnToChatWithContext(router, {
              prompt: '请解读这条历史推送，说明其中指标的含义、结论的局限和需要核实的问题。',
              context: { from: `notification/${id}` },
              badge: '推送解读',
            })}
          >
            <Ionicons name="chatbubble-ellipses-outline" size={20} color={c.bgPrimary} />
            <Text style={styles.analyzeText}>让小气候解读这条推送</Text>
          </TouchableOpacity>
          <Text style={styles.hint}>确认发送后，小气候会解读这条历史推送。</Text>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
    back: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
    headerTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '600', color: c.labelPrimary },
    center: { flex: 1, padding: spacing.xl, alignItems: 'center', justifyContent: 'center', gap: spacing.md },
    error: { fontSize: 15, lineHeight: 23, color: c.labelSecondary, textAlign: 'center' },
    retry: { minHeight: 44, paddingHorizontal: spacing.lg, justifyContent: 'center' },
    retryText: { color: c.brand, fontSize: 16, fontWeight: '600' },
    body: { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xl },
    card: { backgroundColor: c.bgCard, borderRadius: radii.lg, padding: spacing.lg, gap: spacing.sm },
    eyebrow: { fontSize: 13, fontWeight: '500', color: c.brand },
    title: { fontSize: 22, lineHeight: 30, fontWeight: '600', color: c.labelPrimary },
    time: { fontSize: 13, color: c.labelSecondary },
    divider: { height: StyleSheet.hairlineWidth, backgroundColor: c.separator, marginVertical: spacing.sm },
    content: { fontSize: 16, lineHeight: 26, color: c.labelPrimary },
    note: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.sm },
    noteBody: { flex: 1, gap: spacing.sm },
    noteText: { fontSize: 13, lineHeight: 20, color: c.labelSecondary },
    analyze: { minHeight: 52, paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: c.brand, borderRadius: radii.md, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
    analyzeText: { fontSize: 16, fontWeight: '600', color: c.bgPrimary, flexShrink: 1 },
    hint: { fontSize: 12, lineHeight: 18, color: c.labelTertiary, textAlign: 'center' },
  });
}
