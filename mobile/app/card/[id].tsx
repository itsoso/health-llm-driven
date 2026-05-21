/**
 * /card/[id] —— ActionCard 详情页 (Phase 1B P1-6, 2026-05-12 redesign).
 *
 * 改造前: 白底, 标题 + 大段正文 + 3 大按钮, metric/checklist/outcome 全没渲染.
 * 改造后:
 *   - Theme 适配 (dark/light), 用 Stack header 不顶状态栏
 *   - Severity badge + creator_specialist / source / week meta 一行
 *   - Metric 旅程行 (有 metric_key 时): Baseline → Target → Actual 三列
 *   - Checklist (有时): 圆角 row, ✓ / ☐
 *   - Outcome 块 (closed 卡): 改善/反向 chip + effect_size % + accuracy_score + 评分备注
 *   - Decision 按钮 + 已决策 banner 同前 + safety_alert 误报扩展
 *   - 底部 meta (创建/推送/决策时间) 小字
 *
 * 深链入口: health://card/{id}
 */

import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TextStyle,
  TouchableOpacity,
  View,
} from 'react-native';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import api from '@/services/api';
import {
  recordCardDecision,
  recordCardPushClick,
  type ActionCard,
  type CardDecision,
} from '@/services/actionCards';
import { spacing, radii } from '@/constants/theme';
import { useTheme } from '@/hooks/useTheme';
import MarkdownText from '@/components/shared/MarkdownText';
import { EvidenceRefsRow } from '@/components/knowledge';
import AgentFeedbackLink from '@/components/agent/AgentFeedbackLink';
import { createActionCardAgentContext } from '@/utils/agentContext';

const SEVERITY_CONF: Record<string, { bg: string; text: string; label: string; icon: keyof typeof Ionicons.glyphMap }> = {
  critical: { bg: '#FEE2E2', text: '#991B1B', label: '紧急', icon: 'alert-circle' },
  high: { bg: '#FED7AA', text: '#9A3412', label: '警告', icon: 'warning' },
  medium: { bg: '#FEF3C7', text: '#92400E', label: '注意', icon: 'information-circle' },
  low: { bg: '#DBEAFE', text: '#1E40AF', label: '关注', icon: 'bookmark' },
  info: { bg: '#F1F5F9', text: '#475569', label: '提示', icon: 'chatbubble-ellipses' },
};

const SOURCE_LABEL: Record<string, string> = {
  weekly_advisor: '本周建议',
  safety_alert: '安全告警',
  orchestrator: 'AI 综合分析',
  conversation: '对话固化',
  anomaly_alert: '异常检测',
  medical_exam_analysis: '化验分析',
  sleep_spo2: '夜间血氧',
};

const EVIDENCE_CONF: Record<string, { bg: string; text: string; label: string; icon: keyof typeof Ionicons.glyphMap }> = {
  high: { bg: '#D1FAE5', text: '#065F46', label: '强证据', icon: 'shield-checkmark' },
  medium: { bg: '#FEF3C7', text: '#92400E', label: '中等证据', icon: 'shield-half' },
  low: { bg: '#F1F5F9', text: '#475569', label: '弱证据', icon: 'help-circle' },
  medical_grade: { bg: '#FEE2E2', text: '#991B1B', label: '需医生介入', icon: 'medkit' },
};

const OUTCOME_CONF: Record<string, { color: string; bg: string; label: string; icon: keyof typeof Ionicons.glyphMap }> = {
  improved: { color: '#10B981', bg: '#D1FAE5', label: '改善', icon: 'trending-up' },
  unchanged: { color: '#64748B', bg: '#F1F5F9', label: '稳定', icon: 'remove' },
  worsened: { color: '#EF4444', bg: '#FEE2E2', label: '反向', icon: 'trending-down' },
  inconclusive: { color: '#94A3B8', bg: '#F1F5F9', label: '数据不足', icon: 'help-circle' },
};

export default function ActionCardDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const cardId = Number(id);
  const router = useRouter();
  const queryClient = useQueryClient();
  const { c } = useTheme();
  const [showDeclineReason, setShowDeclineReason] = useState(false);
  const [reason, setReason] = useState('');

  const { data: card, isLoading, error } = useQuery<ActionCard>({
    queryKey: ['action-card', cardId],
    queryFn: async () => {
      const { data } = await api.get<ActionCard>(`/action-cards/${cardId}`);
      return data;
    },
    enabled: Number.isFinite(cardId),
  });

  // P1-5: 进入页面回写 push_clicked_at + seen_at (旁路)
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
      <SafeAreaView style={[styles.center, { backgroundColor: c.bgPrimary }]}>
        <ActivityIndicator color={c.brand} />
      </SafeAreaView>
    );
  }

  if (error || !card) {
    return (
      <SafeAreaView style={[styles.center, { backgroundColor: c.bgPrimary }]}>
        <Ionicons name="warning-outline" size={32} color={c.amber} />
        <Text style={{ color: c.labelPrimary, fontSize: 16, marginTop: 8 }}>加载失败</Text>
        <Text style={{ color: c.labelTertiary, fontSize: 12, marginTop: 4 }}>
          {String(error ?? '卡片不存在')}
        </Text>
      </SafeAreaView>
    );
  }

  const sev = SEVERITY_CONF[card.severity ?? 'info'] ?? SEVERITY_CONF.info;
  const isSafetyAlert = card.source_type === 'safety_alert';
  const alreadyDecided = !!card.user_decision;
  const sourceLabel = card.source_type ? SOURCE_LABEL[card.source_type] ?? card.source_type : null;
  const evidenceConf = card.evidence_level ? EVIDENCE_CONF[card.evidence_level] : null;
  const outcomeConf = card.outcome ? OUTCOME_CONF[card.outcome] : null;
  const isClosed = !!card.outcome || !!card.graded_at;
  const hasMetric = !!card.metric_key && (card.baseline_value || card.target_value || card.actual_value);
  const hasChecklist = Array.isArray(card.checklist) && card.checklist.length > 0;
  const agentActionLabel = isClosed
    ? '跟 Agent 复盘这个建议'
    : alreadyDecided
      ? '跟 Agent 调整执行方案'
      : '跟 Agent 讨论这个建议';

  return (
    <>
      <Stack.Screen
        options={{ title: '行动卡片', headerBackTitle: '返回', headerShown: true }}
      />
      <SafeAreaView style={[styles.safe, { backgroundColor: c.bgPrimary }]} edges={['bottom']}>
        <ScrollView contentContainerStyle={styles.scroll}>
          {/* Hero: severity + source meta + title */}
          <View style={[styles.hero, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
            <View style={styles.heroChips}>
              <View style={[styles.sevChip, { backgroundColor: sev.bg }]}>
                <Ionicons name={sev.icon} size={12} color={sev.text} />
                <Text style={[styles.sevText, { color: sev.text }]}>{sev.label}</Text>
              </View>
              {evidenceConf && (
                <View style={[styles.sevChip, { backgroundColor: evidenceConf.bg }]}>
                  <Ionicons name={evidenceConf.icon} size={12} color={evidenceConf.text} />
                  <Text style={[styles.sevText, { color: evidenceConf.text }]}>{evidenceConf.label}</Text>
                </View>
              )}
              {sourceLabel && (
                <View style={[styles.sourceChip, { backgroundColor: c.bgPrimary, borderColor: c.separator }]}>
                  <Text style={[styles.sourceText, { color: c.labelTertiary }]}>{sourceLabel}</Text>
                </View>
              )}
            </View>
            <Text style={[styles.title, { color: c.labelPrimary }]}>{card.title}</Text>
            {(card.creator_specialist || card.source_id) && (
              <Text style={[styles.metaSub, { color: c.labelTertiary }]}>
                {card.creator_specialist ? `${card.creator_specialist}` : ''}
                {card.creator_specialist && card.source_id ? ' · ' : ''}
                {card.source_id ?? ''}
              </Text>
            )}
            {card.evidence_level === 'medical_grade' && (
              <View style={[styles.medicalWarn, { backgroundColor: '#FEE2E2', borderColor: '#991B1B' }]}>
                <Ionicons name="warning" size={14} color="#991B1B" />
                <Text style={[styles.medicalWarnText, { color: '#991B1B' }]}>
                  此建议涉及医疗决策, 请咨询持证医生后再执行
                </Text>
              </View>
            )}
            <EvidenceRefsRow refs={card.evidence_refs} />
          </View>

          <AgentFeedbackLink
            label={agentActionLabel}
            accessibilityLabel={agentActionLabel}
            prompt="请基于这张行动卡, 判断这个建议现在是否仍适合我, 如果我没做到请帮我调整执行方案；如果已经执行, 请帮我复盘指标和体感反馈, 并给出下一步行动。"
            context={createActionCardAgentContext(card)}
            badge={`行动卡 · ${card.title}`}
          />

          {/* 正文 — markdown 渲染 (用户报多页 markdown 显示原文) */}
          {card.content && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <MarkdownText>{card.content}</MarkdownText>
            </View>
          )}

          {/* Metric 旅程 — Baseline → Target → Actual */}
          {hasMetric && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="trending-up" size={16} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>指标旅程</Text>
                {card.metric_key && (
                  <Text style={[styles.cardMeta, { color: c.labelTertiary }]}>{card.metric_key}</Text>
                )}
              </View>
              <View style={styles.metricRow}>
                <MetricCell label="起点" value={card.baseline_value} c={c} />
                <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
                <MetricCell label="目标" value={card.target_value} c={c} accent={c.brand} />
                <Ionicons name="chevron-forward" size={14} color={c.labelTertiary} />
                <MetricCell label="实测" value={card.actual_value} c={c} accent={outcomeConf?.color} />
              </View>
              {card.verification_days != null && (
                <Text style={[styles.cardMetaSmall, { color: c.labelTertiary }]}>
                  验证窗口 {card.verification_days} 天
                  {card.check_back_date ? ` · ${card.check_back_date}` : ''}
                </Text>
              )}
            </View>
          )}

          {/* Checklist */}
          {hasChecklist && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="checkbox-outline" size={16} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>检查清单</Text>
                <Text style={[styles.cardMeta, { color: c.labelTertiary }]}>
                  {card.checklist!.filter(it => it.done).length} / {card.checklist!.length}
                </Text>
              </View>
              {card.checklist!.map((it, idx) => (
                <View key={idx} style={styles.checkRow}>
                  <Ionicons
                    name={it.done ? 'checkmark-circle' : 'ellipse-outline'}
                    size={16}
                    color={it.done ? c.green : c.labelTertiary}
                  />
                  <Text
                    style={[
                      styles.checkText,
                      {
                        color: it.done ? c.labelTertiary : c.labelPrimary,
                        textDecorationLine: it.done ? 'line-through' : 'none',
                      },
                    ]}
                  >
                    {it.item}
                  </Text>
                </View>
              ))}
            </View>
          )}

          {/* Outcome (closed) */}
          {isClosed && outcomeConf && (
            <View style={[styles.card, { backgroundColor: outcomeConf.bg, borderColor: outcomeConf.color }]}>
              <View style={styles.cardHead}>
                <Ionicons name={outcomeConf.icon} size={16} color={outcomeConf.color} />
                <Text style={[styles.cardTitle, { color: outcomeConf.color }]}>{outcomeConf.label}</Text>
                {card.effect_size != null && (
                  <Text style={[styles.effectText, { color: outcomeConf.color }]}>
                    {card.effect_size > 0 ? '+' : ''}
                    {(card.effect_size * 100).toFixed(0)}%
                  </Text>
                )}
              </View>
              {card.accuracy_score != null && (
                <Text style={[styles.cardMetaSmall, { color: outcomeConf.color }]}>
                  Specialist 准确度 {card.accuracy_score}/10
                </Text>
              )}
              {card.grading_notes && (
                <MarkdownText>{card.grading_notes}</MarkdownText>
              )}
            </View>
          )}

          {/* Latest assessment */}
          {card.latest_assessment && (card.latest_assessment.score != null || card.latest_assessment.summary) && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <View style={styles.cardHead}>
                <Ionicons name="sparkles-outline" size={16} color={c.brand} />
                <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>Agent 评估</Text>
                {card.latest_assessment.score != null && (
                  <Text style={[styles.cardMeta, { color: c.brand }]}>
                    {card.latest_assessment.score}/10
                  </Text>
                )}
              </View>
              {card.latest_assessment.summary && (
                <MarkdownText>{card.latest_assessment.summary}</MarkdownText>
              )}
              {card.latest_assessment.evidence && card.latest_assessment.evidence.length > 0 && (
                <View style={{ gap: 4, marginTop: 6 }}>
                  {card.latest_assessment.evidence.map((e, i) => (
                    <Text key={i} style={[styles.cardMetaSmall, { color: c.labelTertiary }]}>
                      · {e}
                    </Text>
                  ))}
                </View>
              )}
            </View>
          )}

          {/* 决策 banner */}
          {alreadyDecided && (
            <View style={[styles.decidedBanner, { backgroundColor: c.brandLight, borderColor: c.brand }]}>
              <Ionicons name="checkmark-done" size={14} color={c.brand} />
              <Text style={[styles.decidedText, { color: c.brand }]}>
                已决策 · {decisionLabel(card.user_decision)}
                {card.decision_reason ? ` — ${card.decision_reason}` : ''}
              </Text>
            </View>
          )}

          {/* Decision 按钮 */}
          {!alreadyDecided && !showDeclineReason && (
            <View style={styles.actions}>
              <TouchableOpacity
                style={[styles.btnPrimary, { backgroundColor: c.brand }, decisionMutation.isPending && styles.btnDisabled]}
                disabled={decisionMutation.isPending}
                onPress={() => handleDecision('accepted')}
              >
                <Ionicons name="checkmark" size={18} color="#fff" />
                <Text style={styles.btnPrimaryText}>接受</Text>
              </TouchableOpacity>
              <View style={styles.btnRow}>
                <TouchableOpacity
                  style={[styles.btnSecondary, { backgroundColor: c.bgCard, borderColor: c.separator, flex: 1 }, decisionMutation.isPending && styles.btnDisabled]}
                  disabled={decisionMutation.isPending}
                  onPress={() => handleDecision('declined')}
                >
                  <Text style={[styles.btnSecondaryText, { color: c.labelPrimary }]}>拒绝</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.btnSecondary, { backgroundColor: c.bgCard, borderColor: c.separator, flex: 1 }, decisionMutation.isPending && styles.btnDisabled]}
                  disabled={decisionMutation.isPending}
                  onPress={() => handleDecision('dismissed')}
                >
                  <Text style={[styles.btnSecondaryText, { color: c.labelSecondary }]}>稍后</Text>
                </TouchableOpacity>
                {isSafetyAlert && (
                  <TouchableOpacity
                    style={[styles.btnSecondary, { backgroundColor: c.bgCard, borderColor: '#A855F7', flex: 1 }, decisionMutation.isPending && styles.btnDisabled]}
                    disabled={decisionMutation.isPending}
                    onPress={() => handleDecision('false_positive')}
                  >
                    <Text style={[styles.btnSecondaryText, { color: '#A855F7' }]}>误报</Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          )}

          {/* Decline reason */}
          {showDeclineReason && (
            <View style={[styles.card, { backgroundColor: c.bgCard, borderColor: c.separator }]}>
              <Text style={[styles.cardTitle, { color: c.labelPrimary }]}>原因 (可选)</Text>
              <TextInput
                style={[styles.reasonInput, { borderColor: c.separator, color: c.labelPrimary, backgroundColor: c.bgPrimary }]}
                value={reason}
                onChangeText={setReason}
                placeholder="例如: 已经在执行其他方案 / 不准 / ..."
                placeholderTextColor={c.labelTertiary}
                multiline
                autoFocus
              />
              <View style={styles.btnRow}>
                <TouchableOpacity
                  style={[styles.btnPrimary, { backgroundColor: c.brand, flex: 1 }]}
                  onPress={() =>
                    handleSubmitReason(
                      isSafetyAlert && reason.includes('误报') ? 'false_positive' : 'declined',
                    )
                  }
                >
                  <Text style={styles.btnPrimaryText}>提交</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.btnSecondary, { backgroundColor: c.bgCard, borderColor: c.separator, flex: 1 }]}
                  onPress={() => {
                    setShowDeclineReason(false);
                    setReason('');
                  }}
                >
                  <Text style={[styles.btnSecondaryText, { color: c.labelSecondary }]}>取消</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* 底部 meta */}
          <View style={styles.metaBlock}>
            {card.created_at && (
              <Text style={[styles.metaTime, { color: c.labelTertiary }]}>创建 · {fmt(card.created_at)}</Text>
            )}
            {card.push_sent_at && (
              <Text style={[styles.metaTime, { color: c.labelTertiary }]}>推送 · {fmt(card.push_sent_at)}</Text>
            )}
            {card.decided_at && (
              <Text style={[styles.metaTime, { color: c.labelTertiary }]}>决策 · {fmt(card.decided_at)}</Text>
            )}
            {card.graded_at && (
              <Text style={[styles.metaTime, { color: c.labelTertiary }]}>评估 · {fmt(card.graded_at)}</Text>
            )}
          </View>
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

function MetricCell({ label, value, c, accent }: { label: string; value?: string | null; c: any; accent?: string }) {
  return (
    <View style={styles.metricCell}>
      <Text style={[styles.metricLabel, { color: c.labelTertiary }]}>{label}</Text>
      <Text style={[styles.metricValue, { color: accent ?? c.labelPrimary }]} numberOfLines={1}>
        {value ?? '—'}
      </Text>
    </View>
  );
}

function decisionLabel(d?: string | null): string {
  switch (d) {
    case 'accepted': return '接受';
    case 'declined': return '拒绝';
    case 'dismissed': return '稍后';
    case 'adjusted': return '调整后接受';
    case 'false_positive': return '误报';
    default: return d ?? '';
  }
}

function fmt(s?: string | null): string {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    });
  } catch {
    return s;
  }
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 8 },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xl * 2 },
  hero: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radii.lg, padding: spacing.md, gap: 6 },
  heroChips: { flexDirection: 'row', gap: 6, alignItems: 'center', flexWrap: 'wrap' },
  medicalWarn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    borderWidth: 1, borderRadius: 8,
    paddingHorizontal: 10, paddingVertical: 6,
    marginTop: 6,
  },
  medicalWarnText: { fontSize: 12, fontWeight: '500', flex: 1 },
  sevChip: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10,
  },
  sevText: { fontSize: 11, fontWeight: '600' },
  sourceChip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, borderWidth: StyleSheet.hairlineWidth },
  sourceText: { fontSize: 11, fontWeight: '500' },
  title: { fontSize: 19, fontWeight: '700', marginTop: 2 } as TextStyle,
  metaSub: { fontSize: 11, marginTop: 2 },
  card: { borderWidth: StyleSheet.hairlineWidth, borderRadius: radii.lg, padding: spacing.md, gap: 6 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  cardTitle: { fontSize: 14, fontWeight: '600' },
  cardMeta: { fontSize: 12, marginLeft: 'auto', fontWeight: '500' },
  cardMetaSmall: { fontSize: 11 },
  bodyText: { fontSize: 14, lineHeight: 22 },
  metricRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingVertical: 6, gap: 4,
  },
  metricCell: { flex: 1, alignItems: 'center', gap: 2 },
  metricLabel: { fontSize: 10, fontWeight: '500', letterSpacing: 0.3 },
  metricValue: { fontSize: 16, fontWeight: '700', fontVariant: ['tabular-nums'] } as TextStyle,
  effectText: { fontSize: 14, fontWeight: '700', marginLeft: 'auto' },
  checkRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  checkText: { fontSize: 14, lineHeight: 20, flex: 1 },
  decidedBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    borderWidth: 1, borderRadius: radii.md,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  decidedText: { fontSize: 13, fontWeight: '500', flex: 1 },
  actions: { gap: 8, marginTop: 4 },
  btnRow: { flexDirection: 'row', gap: 8 },
  btnPrimary: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    paddingVertical: 14, borderRadius: radii.md,
  },
  btnPrimaryText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  btnSecondary: {
    paddingVertical: 12, borderRadius: radii.md,
    borderWidth: StyleSheet.hairlineWidth, alignItems: 'center',
  },
  btnSecondaryText: { fontSize: 15, fontWeight: '500' },
  btnDisabled: { opacity: 0.5 },
  reasonInput: {
    borderWidth: 1, borderRadius: radii.md,
    padding: spacing.sm, fontSize: 14,
    minHeight: 80, textAlignVertical: 'top',
    marginTop: 4, marginBottom: 8,
  },
  metaBlock: { gap: 4, marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#E2E8F0' },
  metaTime: { fontSize: 11, fontFamily: 'Courier' },
});
