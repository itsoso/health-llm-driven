/**
 * Clinical Journal - Timeline (Task 5)
 *
 * 基于 /clinical-journal/timeline API: 按 case_thread 分组的 SOAP timeline,
 * 无主題 bucket (thread_id=null) 展示周度简报等没挂 thread 的 entry.
 */
import React, { useMemo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, FlatList,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, Stack } from 'expo-router';
import { useJournalTimeline } from '../../../hooks/useJournalTimeline';
import type { TimelineThread, TimelineEntry } from '../../../services/clinicalJournal';
import { spacing, radii, typography } from '../../../constants/theme';
import { ColorPalette, useTheme } from '../../../hooks/useTheme';

const STATUS_LABEL: Record<string, string> = {
  active: '跟进中',
  monitoring: '观察中',
  resolved: '已收尾',
};

const THEME_ICON: Record<string, keyof typeof Ionicons.glyphMap> = {
  daily_briefing: 'today-outline',
  doctor_weekly_summary: 'medical-outline',
  sleep: 'moon-outline',
  hrv: 'pulse-outline',
  rhr: 'heart-outline',
  weight: 'scale-outline',
  bp: 'heart-circle-outline',
  spo2: 'cloud-outline',
  rhinitis: 'rainy-outline',
  mental: 'chatbubbles-outline',
};

const CREATED_BY_LABEL: Record<string, string> = {
  briefing_task: '每日简报',
  doctor_weekly_task: '医生周报',
  orchestrator: 'AI 对话',
};

function statusColor(status: string | null, c: ColorPalette): string {
  switch (status) {
    case 'active': return c.amber;
    case 'monitoring': return c.blue;
    case 'resolved': return c.green;
    default: return c.labelTertiary;
  }
}

function fmtRelative(iso: string | null): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  const diffMin = Math.floor((Date.now() - t) / 60_000);
  if (diffMin < 2) return '刚刚';
  if (diffMin < 60) return `${diffMin} 分钟前`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} 小时前`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD} 天前`;
  return new Date(iso).toLocaleDateString('zh-CN');
}

function EntryPreviewRow({ entry, c }: { entry: TimelineEntry; c: ColorPalette }) {
  const styles = useMemo(() => createPreviewStyles(c), [c]);
  return (
    <View style={styles.preview}>
      <Text style={styles.previewSubj} numberOfLines={2}>
        {entry.subjective_short || '(空主诉)'}
      </Text>
      <View style={styles.previewMeta}>
        {entry.created_by && (
          <Text style={styles.previewSource}>
            {CREATED_BY_LABEL[entry.created_by] ?? entry.created_by}
          </Text>
        )}
        <Text style={styles.previewDate}>{fmtRelative(entry.generated_at)}</Text>
      </View>
    </View>
  );
}

function ThreadCard({ thread, onPress }: { thread: TimelineThread; onPress?: () => void }) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const icon = THEME_ICON[thread.theme] ?? 'document-text-outline';
  const sc = statusColor(thread.status, c);
  const previewEntries = thread.entries.slice(0, 3);
  const remaining = thread.entry_count - previewEntries.length;

  const content = (
    <>
      <View style={styles.header}>
        <View style={[styles.iconBox, { backgroundColor: `${sc}18` }]}>
          <Ionicons name={icon} size={20} color={sc} />
        </View>
        <View style={styles.headerMain}>
          <View style={styles.headerTop}>
            <Text style={styles.title} numberOfLines={1}>
              {thread.title ?? thread.theme}
            </Text>
            {thread.status && (
              <View style={[styles.statusChip, { backgroundColor: `${sc}18` }]}>
                <Text style={[styles.statusText, { color: sc }]}>
                  {STATUS_LABEL[thread.status] ?? thread.status}
                </Text>
              </View>
            )}
          </View>
          <Text style={styles.meta}>{fmtRelative(thread.last_updated)}</Text>
        </View>
        {onPress && <Ionicons name="chevron-forward" size={18} color={c.labelTertiary} />}
      </View>

      <View style={styles.divider} />

      {previewEntries.map((e) => (
        <EntryPreviewRow key={e.id} entry={e} c={c} />
      ))}

      {remaining > 0 && (
        <Text style={styles.moreHint}>+ {remaining} 条更多...</Text>
      )}
    </>
  );

  if (onPress) {
    return (
      <TouchableOpacity
        style={styles.card}
        onPress={onPress}
        activeOpacity={0.7}
        accessibilityLabel={`${thread.title ?? thread.theme}, ${thread.entry_count} 条记录`}
      >
        {content}
      </TouchableOpacity>
    );
  }
  return <View style={styles.card}>{content}</View>;
}

export default function JournalTimelineScreen() {
  const router = useRouter();
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);
  const { data, isLoading, isRefetching, refetch } = useJournalTimeline(30);
  const threads = data?.threads ?? [];

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.topbar}>
        <Text style={styles.topbarTitle}>案例时间线</Text>
      </View>

      {isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator size="large" color={c.brand} />
        </View>
      ) : threads.length === 0 ? (
        <View style={styles.center}>
          <View style={styles.emptyCircle}>
            <Ionicons name="document-text-outline" size={40} color={c.labelTertiary} />
          </View>
          <Text style={styles.emptyTitle}>暂无案例记录</Text>
          <Text style={styles.emptySub}>
            每次 AI 分析 / 每日简报 / 医生周报都会自动记为 SOAP 笔记.{'\n'}
            去 AI 对话聊一聊症状或目标, 系统会自动归类生成 case.
          </Text>
        </View>
      ) : (
        <FlatList
          data={threads}
          keyExtractor={(t) => String(t.thread_id ?? `other-${t.last_updated}`)}
          contentContainerStyle={styles.list}
          refreshControl={
            <RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={c.brand} />
          }
          renderItem={({ item }) => (
            <ThreadCard
              thread={item}
              onPress={
                item.thread_id !== null
                  ? () => router.push(`/journal/${item.thread_id}`)
                  : undefined
              }
            />
          )}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
        />
      )}
    </SafeAreaView>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary },
    topbar: {
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
      paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    },
    topbarTitle: {
      fontSize: typography.titleSmall.fontSize, fontWeight: '600' as const,
      color: c.labelPrimary,
    },
    list: { padding: spacing.md, paddingBottom: 100 },
    center: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: spacing.lg },
    emptyCircle: {
      width: 72, height: 72, borderRadius: 36, backgroundColor: c.fill,
      justifyContent: 'center', alignItems: 'center', marginBottom: spacing.md,
    },
    emptyTitle: {
      fontSize: typography.bodyLarge.fontSize, fontWeight: '600' as const,
      color: c.labelPrimary, marginBottom: spacing.xs,
    },
    emptySub: {
      fontSize: typography.bodySmall.fontSize, color: c.labelSecondary,
      textAlign: 'center', lineHeight: 18,
    },
    card: {
      backgroundColor: c.bgCard, borderRadius: radii.md,
      padding: spacing.md,
    },
    header: { flexDirection: 'row', alignItems: 'center' },
    iconBox: {
      width: 36, height: 36, borderRadius: 18,
      justifyContent: 'center', alignItems: 'center', marginRight: spacing.sm,
    },
    headerMain: { flex: 1 },
    headerTop: { flexDirection: 'row', alignItems: 'center', gap: 6 },
    title: {
      flex: 1, fontSize: typography.bodyMedium.fontSize, fontWeight: '600' as const,
      color: c.labelPrimary,
    },
    statusChip: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 },
    statusText: { fontSize: 11, fontWeight: '500' as const },
    meta: { fontSize: typography.caption.fontSize, color: c.labelTertiary, marginTop: 2 },
    divider: { height: StyleSheet.hairlineWidth, backgroundColor: c.separator, marginVertical: spacing.sm },
    moreHint: {
      fontSize: typography.caption.fontSize, color: c.labelTertiary,
      marginTop: spacing.xs,
    },
  });
}

function createPreviewStyles(c: ColorPalette) {
  return StyleSheet.create({
    preview: { marginTop: spacing.xs },
    previewSubj: { fontSize: typography.bodySmall.fontSize, color: c.labelPrimary, lineHeight: 18 },
    previewMeta: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 2 },
    previewSource: { fontSize: 11, color: c.brand },
    previewDate: { fontSize: 11, color: c.labelTertiary },
  });
}
