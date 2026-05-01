import React, { useState } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator, Alert, TextStyle, RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as Haptics from 'expo-haptics';
import Markdown from 'react-native-markdown-display';
import {
  getConsultation, updateConsultationItem, verifyPredictions,
  type ConsultationItem, type ConsultationPredictionVerification,
} from '../../services/consultations';
import { colors, spacing, radii, shadows } from '../../constants/theme';

const ITEM_TYPE_LABEL: Record<string, string> = {
  hypothesis: '🧠 假设',
  action: '✓ 行动',
  prediction: '📊 预测',
  red_flag: '⚠ 警戒',
  note: '📝 备注',
};

const ITEM_TYPE_COLOR: Record<string, { bg: string; fg: string; accent: string }> = {
  hypothesis: { bg: '#EEF2FF', fg: '#3730A3', accent: '#6366F1' },
  action: { bg: '#ECFDF5', fg: '#065F46', accent: '#10B981' },
  prediction: { bg: '#FEF3C7', fg: '#92400E', accent: '#F59E0B' },
  red_flag: { bg: '#FEE2E2', fg: '#991B1B', accent: '#EF4444' },
  note: { bg: '#F3F4F6', fg: '#4B5563', accent: '#6B7280' },
};

// 后端 ALLOWED_STATUS_BY_TYPE 按 item_type 限制状态机, 这里必须按 type 决策
// 否则 hypothesis/prediction 上点 "标记为 in_progress" 会被后端 400 拒.
const STATUS_LABEL_CN: Record<string, string> = {
  in_progress: '执行中',
  completed: '已完成',
  confirmed: '已确认',
  refuted: '已排除',
  resolved: '已解决',
  met: '达标',
  not_met: '未达标',
  triggered: '触发',
};

function getNextStatus(itemType: string, current: string): string | null {
  if (itemType === 'action') {
    if (current === 'pending') return 'in_progress';
    if (current === 'in_progress') return 'completed';
    return null;
  }
  if (itemType === 'hypothesis') {
    return current === 'pending' ? 'confirmed' : null;
  }
  if (itemType === 'prediction') {
    return current === 'pending' ? 'met' : null;
  }
  if (itemType === 'red_flag') {
    return current === 'watching' ? 'resolved' : null;
  }
  if (itemType === 'note') {
    return current === 'pending' ? 'resolved' : null;
  }
  return null;
}

function StatusPill({ status }: { status: string }) {
  const bg =
    status === 'completed' || status === 'verified' || status === 'met' ? '#D1FAE5' :
    status === 'in_progress' || status === 'active' ? '#DBEAFE' :
    status === 'violated' || status === 'monitoring' ? '#FEE2E2' :
    '#F3F4F6';
  const fg =
    status === 'completed' || status === 'verified' || status === 'met' ? '#065F46' :
    status === 'in_progress' || status === 'active' ? '#1E40AF' :
    status === 'violated' || status === 'monitoring' ? '#991B1B' :
    '#4B5563';
  return (
    <View style={[styles.statusPill, { backgroundColor: bg }]}>
      <Text style={[txt.statusText, { color: fg }]}>{status}</Text>
    </View>
  );
}

function ItemCard({
  item,
  verification,
  onAdvance,
  onConfirmVerification,
}: {
  item: ConsultationItem;
  verification?: ConsultationPredictionVerification;
  onAdvance: () => void;
  onConfirmVerification: () => void;
}) {
  const c = ITEM_TYPE_COLOR[item.item_type] || ITEM_TYPE_COLOR.note;
  const canAdvance = getNextStatus(item.item_type, item.status);
  return (
    <View style={[styles.itemCard, { borderLeftColor: c.accent }]}>
      <View style={styles.itemHeader}>
        <View style={[styles.itemTypeTag, { backgroundColor: c.bg }]}>
          <Text style={[txt.itemTypeText, { color: c.fg }]}>
            {ITEM_TYPE_LABEL[item.item_type]}
            {item.item_code ? ` · ${item.item_code}` : ''}
          </Text>
        </View>
        <StatusPill status={item.status} />
      </View>
      <Text style={txt.itemTitle}>{item.title}</Text>
      {item.content_markdown ? (
        <Markdown style={mdStyle}>{item.content_markdown}</Markdown>
      ) : null}

      {item.due_date ? (
        <Text style={txt.itemMeta}>截止 {item.due_date}</Text>
      ) : null}
      {item.outcome ? (
        <Text style={[txt.itemMeta, { color: colors.labelSecondary }]}>结果：{item.outcome}</Text>
      ) : null}
      {item.actual_value ? (
        <Text style={[txt.itemMeta, { color: colors.labelSecondary }]}>实测：{item.actual_value}</Text>
      ) : null}

      {verification ? (
        <View style={styles.verificationBox}>
          <Text style={txt.verificationTitle}>验证建议：{verification.suggested_status}</Text>
          <Text style={txt.verificationText}>
            {verification.metric_name ? `${verification.metric_name} ` : ''}
            {verification.actual_value != null ? `实测 ${verification.actual_value}` : '暂无实测数据'}
            {verification.target ? ` · 目标 ${verification.target}` : ''}
          </Text>
          {verification.note ? <Text style={txt.verificationNote}>{verification.note}</Text> : null}
          <TouchableOpacity style={styles.confirmBtn} onPress={onConfirmVerification} activeOpacity={0.75}>
            <Ionicons name="checkmark-done-outline" size={14} color="#fff" />
            <Text style={txt.confirmText}>确认写入结果</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {canAdvance ? (
        <TouchableOpacity style={styles.advanceBtn} onPress={onAdvance} activeOpacity={0.75}>
          <Ionicons name="checkmark-circle-outline" size={14} color={c.accent} />
          <Text style={[txt.advanceText, { color: c.accent }]}>
            标记为 {STATUS_LABEL_CN[canAdvance] ?? canAdvance}
          </Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );
}

export default function ConsultationDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const consultationId = Number(id);
  const router = useRouter();
  const qc = useQueryClient();
  const [verifying, setVerifying] = useState(false);
  const [verificationSuggestions, setVerificationSuggestions] = useState<Record<number, ConsultationPredictionVerification>>({});

  const { data, isLoading, isError, refetch, isRefetching } = useQuery({
    queryKey: ['consultation', consultationId],
    queryFn: () => getConsultation(consultationId),
    enabled: !Number.isNaN(consultationId),
    staleTime: 30_000,
  });

  const advanceMut = useMutation({
    mutationFn: async (item: ConsultationItem) => {
      const next = getNextStatus(item.item_type, item.status);
      if (!next) return null;
      return updateConsultationItem(item.id, { status: next });
    },
    onSuccess: () => {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      qc.invalidateQueries({ queryKey: ['consultation', consultationId] });
      qc.invalidateQueries({ queryKey: ['consultations', 'list'] });
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail
        ?? err?.message
        ?? '请检查网络后重试';
      Alert.alert('更新失败', String(detail));
    },
  });

  const handleVerify = async () => {
    setVerifying(true);
    try {
      const result = await verifyPredictions(consultationId);
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      setVerificationSuggestions(Object.fromEntries(
        result.predictions.map(prediction => [prediction.item_id, prediction]),
      ));
      const lines = result.predictions
        .map((p) => `${p.item_code || `#${p.item_id}`} → ${p.suggested_status}${p.actual_value != null ? ` (${p.actual_value})` : ''}`)
        .join('\n');
      Alert.alert(
        `生成验证建议 · ${result.verified_count} 条`,
        lines || '无待验证预测',
      );
      qc.invalidateQueries({ queryKey: ['consultation', consultationId] });
      qc.invalidateQueries({ queryKey: ['consultations', 'list'] });
    } catch {
      Alert.alert('验证失败', '请检查网络后重试');
    } finally {
      setVerifying(false);
    }
  };

  if (isLoading) {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        <View style={styles.loading}>
          <ActivityIndicator size="large" color={colors.brand} />
        </View>
      </SafeAreaView>
    );
  }

  if (isError || !data) {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={8}>
            <Ionicons name="chevron-back" size={22} color={colors.labelPrimary} />
          </TouchableOpacity>
          <Text style={txt.headerTitle}>咨询详情</Text>
          <View style={styles.backBtn} />
        </View>
        <View style={styles.empty}>
          <Text style={txt.emptyText}>加载失败</Text>
          <TouchableOpacity onPress={() => refetch()} style={styles.retry}>
            <Text style={txt.retryText}>重试</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // 按 item_type 分组
  const grouped = groupByType(data.items);

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn} hitSlop={8}>
          <Ionicons name="chevron-back" size={22} color={colors.labelPrimary} />
        </TouchableOpacity>
        <Text style={txt.headerTitle} numberOfLines={1}>{data.title}</Text>
        <TouchableOpacity onPress={handleVerify} style={styles.backBtn} hitSlop={8} disabled={verifying}>
          {verifying
            ? <ActivityIndicator size="small" color={colors.brand} />
            : <Ionicons name="refresh" size={22} color={colors.brand} />}
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControlShim refreshing={isRefetching} onRefresh={refetch} />
        }
      >
        <View style={styles.metaBox}>
          <Text style={txt.metaItem}>版本 v{data.version}</Text>
          <Text style={txt.metaItem}>· {data.consultation_type}</Text>
          <Text style={txt.metaItem}>· {data.status}</Text>
          {data.verification_scheduled_at ? (
            <Text style={txt.metaItem}>· 下次复盘 {data.verification_scheduled_at}</Text>
          ) : null}
        </View>

        {data.topic ? (
          <View style={styles.section}>
            <Text style={txt.sectionLabel}>话题</Text>
            <Text style={txt.body}>{data.topic}</Text>
          </View>
        ) : null}

        {data.chief_complaint ? (
          <View style={styles.section}>
            <Text style={txt.sectionLabel}>主诉</Text>
            <Text style={txt.body}>{data.chief_complaint}</Text>
          </View>
        ) : null}

        {data.summary ? (
          <View style={styles.section}>
            <Text style={txt.sectionLabel}>摘要</Text>
            <Text style={txt.body}>{data.summary}</Text>
          </View>
        ) : null}

        <TouchableOpacity
          style={styles.verifyBtn}
          onPress={handleVerify}
          activeOpacity={0.8}
          disabled={verifying}
        >
          {verifying ? (
            <ActivityIndicator size="small" color="#fff" />
          ) : (
            <Ionicons name="flash" size={16} color="#fff" />
          )}
          <Text style={txt.verifyBtnText}>
            {verifying ? '验证中...' : '一键验证到期预测'}
          </Text>
        </TouchableOpacity>

        {(['hypothesis', 'action', 'prediction', 'red_flag', 'note'] as const).map((t) => {
          const list = grouped[t] || [];
          if (list.length === 0) return null;
          return (
            <View key={t} style={styles.section}>
              <Text style={txt.sectionLabel}>{ITEM_TYPE_LABEL[t]} · {list.length}</Text>
              <View style={{ gap: spacing.sm }}>
                {list.map((item) => (
                  <ItemCard
                    key={item.id}
                    item={item}
                    verification={verificationSuggestions[item.id]}
                    onAdvance={() => advanceMut.mutate(item)}
                    onConfirmVerification={async () => {
                      const suggestion = verificationSuggestions[item.id];
                      if (!suggestion) return;
                      try {
                        await updateConsultationItem(item.id, {
                          status: suggestion.suggested_status,
                          actual_value: suggestion.actual_value == null ? undefined : String(suggestion.actual_value),
                          outcome: suggestion.note,
                        });
                        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
                        setVerificationSuggestions(prev => {
                          const next = { ...prev };
                          delete next[item.id];
                          return next;
                        });
                        qc.invalidateQueries({ queryKey: ['consultation', consultationId] });
                        qc.invalidateQueries({ queryKey: ['consultations', 'list'] });
                      } catch {
                        Alert.alert('写入失败', '请检查网络后重试');
                      }
                    }}
                  />
                ))}
              </View>
            </View>
          );
        })}

        <View style={styles.section}>
          <Text style={txt.sectionLabel}>完整分析</Text>
          <View style={styles.markdownCard}>
            <Markdown style={mdStyle}>{data.rationale_markdown}</Markdown>
          </View>
        </View>

        <View style={{ height: spacing.xxxl }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function RefreshControlShim(props: { refreshing: boolean; onRefresh: () => void }) {
  return <RefreshControl refreshing={props.refreshing} onRefresh={props.onRefresh} tintColor={colors.brand} />;
}

function groupByType(items: ConsultationItem[]): Record<string, ConsultationItem[]> {
  const out: Record<string, ConsultationItem[]> = {};
  for (const it of items) {
    (out[it.item_type] ||= []).push(it);
  }
  for (const key of Object.keys(out)) {
    out[key].sort((a, b) => a.priority - b.priority);
  }
  return out;
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bgPrimary },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    backgroundColor: colors.bgPrimary,
  },
  backBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md, padding: spacing.xl },
  retry: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, backgroundColor: colors.brand, borderRadius: radii.md },
  scrollContent: { padding: spacing.lg, gap: spacing.lg },
  metaBox: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  section: { gap: spacing.sm },
  markdownCard: {
    backgroundColor: colors.bgCard, borderRadius: radii.lg, padding: spacing.md, ...shadows.subtle,
  },
  verifyBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: colors.brand, borderRadius: radii.md,
    paddingVertical: spacing.md,
  },
  itemCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    borderLeftWidth: 3,
    padding: spacing.md,
    gap: 6,
    ...shadows.subtle,
  },
  itemHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  itemTypeTag: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  statusPill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  advanceBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    alignSelf: 'flex-start', marginTop: 4,
    paddingHorizontal: 10, paddingVertical: 4,
    borderRadius: radii.sm, borderWidth: 1, borderColor: colors.separator,
  },
  verificationBox: {
    backgroundColor: '#F8FAFC',
    borderRadius: radii.md,
    padding: spacing.sm,
    gap: 4,
    marginTop: 4,
  },
  confirmBtn: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: colors.brand,
    borderRadius: radii.sm,
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginTop: 4,
  },
});

const txt = {
  headerTitle: { fontSize: 17, fontWeight: '700', color: colors.labelPrimary, flex: 1, textAlign: 'center' } as TextStyle,
  metaItem: { fontSize: 11, color: colors.labelTertiary } as TextStyle,
  sectionLabel: { fontSize: 12, fontWeight: '700', color: colors.labelSecondary, textTransform: 'uppercase' } as TextStyle,
  body: { fontSize: 14, color: colors.labelPrimary, lineHeight: 20 } as TextStyle,
  itemTypeText: { fontSize: 10, fontWeight: '700' } as TextStyle,
  itemTitle: { fontSize: 14, fontWeight: '700', color: colors.labelPrimary, marginTop: 2 } as TextStyle,
  itemMeta: { fontSize: 11, color: colors.labelTertiary, marginTop: 2 } as TextStyle,
  statusText: { fontSize: 9, fontWeight: '700', textTransform: 'uppercase' } as TextStyle,
  advanceText: { fontSize: 11, fontWeight: '600' } as TextStyle,
  verificationTitle: { fontSize: 12, fontWeight: '700', color: colors.labelPrimary } as TextStyle,
  verificationText: { fontSize: 12, color: colors.labelSecondary, lineHeight: 17 } as TextStyle,
  verificationNote: { fontSize: 11, color: colors.labelTertiary, lineHeight: 16 } as TextStyle,
  confirmText: { fontSize: 12, fontWeight: '700', color: '#fff' } as TextStyle,
  verifyBtnText: { fontSize: 14, fontWeight: '700', color: '#fff' } as TextStyle,
  emptyText: { fontSize: 13, color: colors.labelTertiary } as TextStyle,
  retryText: { fontSize: 13, fontWeight: '600', color: '#fff' } as TextStyle,
};

const mdStyle: any = {
  body: { color: colors.labelPrimary, fontSize: 13, lineHeight: 20 },
  heading1: { fontSize: 17, fontWeight: '700', marginTop: 8, marginBottom: 4 },
  heading2: { fontSize: 15, fontWeight: '700', marginTop: 8, marginBottom: 4 },
  heading3: { fontSize: 13, fontWeight: '700', marginTop: 6, marginBottom: 3 },
  strong: { fontWeight: '700' },
  em: { fontStyle: 'italic' },
  bullet_list: { marginVertical: 4 },
  list_item: { marginVertical: 2 },
};
