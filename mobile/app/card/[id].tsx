/**
 * /card/[id] —— ActionCard 详情页面 (Phase 1B P1-6).
 *
 * - 显示卡片标题/内容/severity/source
 * - 三主按钮: 接受 / 拒绝 / 稍后
 * - safety_alert 类卡片额外加 [误报] 按钮
 * - 进入页面时调 click endpoint (P1-5) 回写 push_clicked_at
 *
 * 深链入口: health://card/{id} (P1-3, app.json 已注册 health scheme)
 */

import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/api';
import {
  recordCardDecision,
  recordCardPushClick,
  type ActionCard,
  type CardDecision,
} from '@/services/actionCards';

const SEVERITY_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  critical: { bg: '#FEE2E2', text: '#991B1B', label: '紧急' },
  high: { bg: '#FED7AA', text: '#9A3412', label: '警告' },
  medium: { bg: '#FEF3C7', text: '#92400E', label: '注意' },
  low: { bg: '#DBEAFE', text: '#1E40AF', label: '关注' },
  info: { bg: '#F1F5F9', text: '#475569', label: '提示' },
};

export default function ActionCardDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const cardId = Number(id);
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showDeclineReason, setShowDeclineReason] = useState(false);
  const [reason, setReason] = useState('');

  const { data: card, isLoading, error } = useQuery<ActionCard>({
    queryKey: ['action-card', cardId],
    queryFn: async () => {
      // 2026-05-12: 用单卡 GET, closed/verifying 状态都能拿到
      // (历史上只查 active+archived 列表, 已闭环卡命中不到 → 页面为空)
      const { data } = await api.get<ActionCard>(`/action-cards/${cardId}`);
      return data;
    },
    enabled: Number.isFinite(cardId),
  });

  // P1-5: 进入页面回写 push_clicked_at + seen_at (旁路, 失败静默)
  useEffect(() => {
    if (Number.isFinite(cardId)) {
      recordCardPushClick(cardId);
    }
  }, [cardId]);

  const decisionMutation = useMutation({
    mutationFn: ({ decision, reason: r }: { decision: CardDecision; reason?: string }) =>
      recordCardDecision(cardId, decision, r),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['action-cards'] });
      queryClient.invalidateQueries({ queryKey: ['action-card', cardId] });
      const labels: Record<CardDecision, string> = {
        accepted: '已接受',
        adjusted: '已记录调整',
        declined: '已拒绝',
        dismissed: '已忽略',
        false_positive: '已标记为误报',
      };
      Alert.alert('完成', labels[variables.decision], [
        { text: 'OK', onPress: () => router.back() },
      ]);
    },
    onError: (err: any) => {
      Alert.alert('操作失败', err?.response?.data?.detail || err?.message || '请重试');
    },
  });

  const handleDecision = (decision: CardDecision) => {
    if (decision === 'declined' || decision === 'false_positive') {
      // 这两种需要原因
      setShowDeclineReason(true);
      return;
    }
    decisionMutation.mutate({ decision });
  };

  const handleSubmitReason = (decision: CardDecision) => {
    decisionMutation.mutate({ decision, reason: reason.trim() || undefined });
    setShowDeclineReason(false);
    setReason('');
  };

  if (isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
      </View>
    );
  }

  if (error || !card) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>加载失败</Text>
        <Text style={styles.errorDetail}>{String(error)}</Text>
        <TouchableOpacity style={styles.btnSecondary} onPress={() => router.back()}>
          <Text style={styles.btnSecondaryText}>返回</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const sevConf = SEVERITY_COLORS[card.severity ?? 'info'] ?? SEVERITY_COLORS.info;
  const isSafetyAlert = card.source_type === 'safety_alert';
  const alreadyDecided = !!card.user_decision;

  return (
    <>
      <Stack.Screen options={{ title: '行动卡片', headerBackTitle: '返回' }} />
      <ScrollView style={styles.container} contentContainerStyle={styles.scrollContent}>
        <View style={[styles.severityBadge, { backgroundColor: sevConf.bg }]}>
          <Text style={[styles.severityText, { color: sevConf.text }]}>{sevConf.label}</Text>
        </View>

        <Text style={styles.title}>{card.title}</Text>

        {card.source_type && (
          <Text style={styles.source}>
            来源: {card.source_type}
            {card.source_id ? ` · ${card.source_id}` : ''}
          </Text>
        )}

        <Text style={styles.content}>{card.content}</Text>

        {alreadyDecided && (
          <View style={styles.decidedBanner}>
            <Text style={styles.decidedText}>
              已决策: <Text style={styles.decidedBold}>{card.user_decision}</Text>
              {card.decision_reason ? `\n原因: ${card.decision_reason}` : ''}
            </Text>
          </View>
        )}

        {!alreadyDecided && !showDeclineReason && (
          <View style={styles.actions}>
            <TouchableOpacity
              style={[styles.btnPrimary, decisionMutation.isPending && styles.btnDisabled]}
              disabled={decisionMutation.isPending}
              onPress={() => handleDecision('accepted')}
            >
              <Text style={styles.btnPrimaryText}>接受</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.btnSecondary, decisionMutation.isPending && styles.btnDisabled]}
              disabled={decisionMutation.isPending}
              onPress={() => handleDecision('declined')}
            >
              <Text style={styles.btnSecondaryText}>拒绝</Text>
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.btnTertiary, decisionMutation.isPending && styles.btnDisabled]}
              disabled={decisionMutation.isPending}
              onPress={() => handleDecision('dismissed')}
            >
              <Text style={styles.btnTertiaryText}>稍后</Text>
            </TouchableOpacity>

            {isSafetyAlert && (
              <TouchableOpacity
                style={[styles.btnFalsePositive, decisionMutation.isPending && styles.btnDisabled]}
                disabled={decisionMutation.isPending}
                onPress={() => handleDecision('false_positive')}
              >
                <Text style={styles.btnFalsePositiveText}>误报</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {showDeclineReason && (
          <View style={styles.reasonBlock}>
            <Text style={styles.reasonLabel}>原因 (可选)</Text>
            <TextInput
              style={styles.reasonInput}
              value={reason}
              onChangeText={setReason}
              placeholder="例如: 已经在执行其他方案 / 不准 / ..."
              multiline
              autoFocus
            />
            <View style={styles.reasonActions}>
              <TouchableOpacity
                style={styles.btnPrimary}
                onPress={() =>
                  handleSubmitReason(
                    isSafetyAlert && reason.includes('误报') ? 'false_positive' : 'declined',
                  )
                }
              >
                <Text style={styles.btnPrimaryText}>提交</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.btnTertiary}
                onPress={() => {
                  setShowDeclineReason(false);
                  setReason('');
                }}
              >
                <Text style={styles.btnTertiaryText}>取消</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        <View style={styles.metaBlock}>
          <Text style={styles.metaText}>创建: {fmt(card.created_at)}</Text>
          {card.push_sent_at && <Text style={styles.metaText}>推送: {fmt(card.push_sent_at)}</Text>}
          {card.push_clicked_at && (
            <Text style={styles.metaText}>点击: {fmt(card.push_clicked_at)}</Text>
          )}
          {card.decided_at && <Text style={styles.metaText}>决策: {fmt(card.decided_at)}</Text>}
        </View>
      </ScrollView>
    </>
  );
}

function fmt(s?: string | null): string {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return s;
  }
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#fff' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  errorText: { fontSize: 16, color: '#991B1B', marginBottom: 8 },
  errorDetail: { fontSize: 12, color: '#888', marginBottom: 16 },
  scrollContent: { padding: 20 },
  severityBadge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    marginBottom: 12,
  },
  severityText: { fontSize: 12, fontWeight: '600' },
  title: { fontSize: 22, fontWeight: '700', color: '#0F172A', marginBottom: 8 },
  source: { fontSize: 12, color: '#64748B', marginBottom: 16 },
  content: { fontSize: 15, color: '#1E293B', lineHeight: 24, marginBottom: 24 },
  decidedBanner: {
    backgroundColor: '#F1F5F9',
    padding: 12,
    borderRadius: 8,
    marginBottom: 16,
  },
  decidedText: { fontSize: 14, color: '#475569' },
  decidedBold: { fontWeight: '700', color: '#0F172A' },
  actions: { gap: 12, marginTop: 8 },
  btnPrimary: {
    backgroundColor: '#0A8F8F',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  btnPrimaryText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  btnSecondary: {
    backgroundColor: '#F1F5F9',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
  },
  btnSecondaryText: { color: '#1E293B', fontSize: 16, fontWeight: '500' },
  btnTertiary: {
    paddingVertical: 12,
    alignItems: 'center',
  },
  btnTertiaryText: { color: '#64748B', fontSize: 15 },
  btnFalsePositive: {
    borderWidth: 1,
    borderColor: '#A855F7',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
  },
  btnFalsePositiveText: { color: '#A855F7', fontSize: 15, fontWeight: '500' },
  btnDisabled: { opacity: 0.5 },
  reasonBlock: { gap: 8, marginTop: 8 },
  reasonLabel: { fontSize: 13, color: '#475569' },
  reasonInput: {
    borderWidth: 1,
    borderColor: '#CBD5E1',
    borderRadius: 8,
    padding: 12,
    fontSize: 15,
    minHeight: 80,
    textAlignVertical: 'top',
    color: '#0F172A',
  },
  reasonActions: { flexDirection: 'row', gap: 12 },
  metaBlock: {
    marginTop: 32,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: '#E2E8F0',
    gap: 4,
  },
  metaText: { fontSize: 12, color: '#94A3B8' },
});
