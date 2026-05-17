/**
 * ClaimSheet — bottom drawer展示 N 条 system-KB claim 的完整内容 + 关联 entity.
 *
 * 输入: claimIds (1-3 个 claim doc_id), visible, onClose.
 * 数据: useKnowledgeClaims hook 并发 fetch.
 * 内容: 每条 claim 显示 标题 + evidence_level + 置信度 + summary + sources
 *       + 关联 entity 列表 (EntityCard).
 * 操作: 底部 "这条证据不对" → POST feedback, 逐条标记 disagree.
 *
 * 用于:
 *   - genetic-report.tsx SnpCard 展开后点 "系统证据 N 条"
 *   - EvidenceRefsRow 重构后内嵌 (重构在最后一步独立 commit)
 */
import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useKnowledgeClaims } from '../../hooks/useKnowledgeClaim';
import {
  submitKnowledgeClaimFeedback,
  type KnowledgeClaimBundle,
  type KnowledgeDocument,
  type KnowledgeSourceDetail,
} from '../../services/systemKnowledge';
import { useTheme, type ColorPalette } from '../../hooks/useTheme';
import { EntityCard } from './EntityCard';

type FeedbackStatus = 'idle' | 'sending' | 'sent' | 'error';

const EVIDENCE_LABEL: Record<string, string> = {
  A: 'A级',
  B: 'B级',
  C: 'C级',
  D: 'D级',
};

export function ClaimSheet({
  visible,
  onClose,
  claimIds,
}: {
  visible: boolean;
  onClose: () => void;
  claimIds: string[];
}) {
  const { c } = useTheme();
  const router = useRouter();
  const styles = useMemo(() => createStyles(c), [c]);
  const ids = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const id of claimIds) {
      const normalized = String(id || '').trim();
      if (!normalized || seen.has(normalized)) continue;
      seen.add(normalized);
      out.push(normalized);
      if (out.length >= 3) break;
    }
    return out;
  }, [claimIds]);
  const { bundles, errors, isLoading } = useKnowledgeClaims(ids, {
    enabled: visible,
  });
  const [feedbackStatus, setFeedbackStatus] = useState<FeedbackStatus>('idle');

  useEffect(() => {
    if (!visible) setFeedbackStatus('idle');
  }, [visible]);

  if (!visible) return null;

  async function sendDisagreeFeedback() {
    if (feedbackStatus === 'sending' || bundles.length === 0) return;
    setFeedbackStatus('sending');
    try {
      await Promise.allSettled(
        bundles.map((b) =>
          submitKnowledgeClaimFeedback(
            b.claim.doc_id,
            '用户在移动端反馈这条系统知识库证据不适用',
          ),
        ),
      );
      setFeedbackStatus('sent');
    } catch {
      setFeedbackStatus('error');
    }
  }

  const feedbackLabel =
    feedbackStatus === 'sending'
      ? '提交中…'
      : feedbackStatus === 'sent'
        ? '已记录反馈'
        : feedbackStatus === 'error'
          ? '提交失败, 再试一次'
          : '这条证据不对';

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <Pressable style={styles.backdrop} onPress={onClose}>
        <Pressable style={styles.sheet} onPress={(e) => e.stopPropagation()}>
          <View style={styles.handle} />
          <View style={styles.headerRow}>
            <View style={styles.titleWrap}>
              <Ionicons name="library" size={16} color={c.brand} />
              <Text style={styles.title}>系统知识库证据</Text>
            </View>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="关闭证据详情"
              onPress={onClose}
              hitSlop={8}
            >
              <Ionicons name="close" size={20} color={c.labelSecondary} />
            </Pressable>
          </View>

          {isLoading && bundles.length === 0 ? (
            <View style={styles.center}>
              <ActivityIndicator color={c.brand} />
              <Text style={styles.meta}>读取证据中</Text>
            </View>
          ) : null}

          {!isLoading && bundles.length === 0 && errors.length > 0 ? (
            <Text style={styles.err}>暂时无法读取证据详情</Text>
          ) : null}

          {bundles.length > 0 ? (
            <ScrollView
              style={{ maxHeight: 480 }}
              contentContainerStyle={{ paddingBottom: 8 }}
            >
              {bundles.map((b, i) => (
                <ClaimBlock
                  key={b.claim.doc_id}
                  bundle={b}
                  styles={styles}
                  c={c}
                  isLast={i === bundles.length - 1}
                  onClose={onClose}
                  router={router}
                />
              ))}
            </ScrollView>
          ) : null}

          {bundles.length > 0 ? (
            <Pressable
              testID="claim-feedback-button"
              onPress={sendDisagreeFeedback}
              disabled={feedbackStatus === 'sending' || feedbackStatus === 'sent'}
              style={({ pressed }) => [
                styles.feedbackBtn,
                feedbackStatus === 'sent' && styles.feedbackBtnSent,
                pressed && { opacity: 0.7 },
              ]}
            >
              <Ionicons
                name={feedbackStatus === 'sent' ? 'checkmark-circle' : 'thumbs-down-outline'}
                size={14}
                color={feedbackStatus === 'sent' ? c.green : c.labelSecondary}
              />
              <Text
                style={[
                  styles.feedbackLabel,
                  feedbackStatus === 'sent' && { color: c.green },
                ]}
              >
                {feedbackLabel}
              </Text>
            </Pressable>
          ) : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function ClaimBlock({
  bundle,
  styles,
  c,
  isLast,
  onClose,
  router,
}: {
  bundle: KnowledgeClaimBundle;
  styles: ReturnType<typeof createStyles>;
  c: ColorPalette;
  isLast: boolean;
  onClose: () => void;
  router: ReturnType<typeof useRouter>;
}) {
  const claim = bundle.claim;
  const evidenceText =
    claim.evidence_level_detail?.label ||
    (claim.evidence_level ? EVIDENCE_LABEL[claim.evidence_level] : null);
  const confidencePct = typeof claim.confidence === 'number' ? Math.round(claim.confidence * 100) : null;
  const sources = (claim.sources || []).slice(0, 3);
  const sourceDetails = (claim.source_details || []).slice(0, 3);
  const entityNeighbors: KnowledgeDocument[] = (bundle.neighbors || []).filter(
    (n) => n.doc_type === 'entity',
  );

  return (
    <View style={[styles.claimBlock, !isLast && styles.claimDivider]}>
      <View style={styles.claimHeader}>
        <Text style={styles.claimTitle} numberOfLines={3}>
          {claim.title || claim.doc_id}
        </Text>
        {evidenceText ? (
          <View style={styles.levelChip}>
            <Text style={styles.levelText}>{evidenceText}</Text>
          </View>
        ) : null}
      </View>

      {confidencePct != null ? (
        <Text style={styles.meta}>置信度 {confidencePct}%</Text>
      ) : null}
      {claim.evidence_level_detail?.description ? (
        <Text style={styles.evidenceDescription}>
          {claim.evidence_level_detail.description}
        </Text>
      ) : null}

      {claim.summary ? <Text style={styles.body}>{claim.summary}</Text> : null}

      {bundle.claim_boundary ? (
        <View style={styles.boundaryBox}>
          <Ionicons name="information-circle" size={12} color={c.amber} />
          <Text style={styles.boundaryText}>{bundle.claim_boundary}</Text>
        </View>
      ) : null}

      {sourceDetails.length > 0 ? (
        <View style={styles.sourcesWrap}>
          <Text style={styles.sourcesLabel}>来源</Text>
          <View style={styles.sourceChipRow}>
            {sourceDetails.map((src, idx) => (
              <SourceChip key={`${src.source}-${idx}`} source={src} styles={styles} />
            ))}
          </View>
        </View>
      ) : sources.length > 0 ? (
        <View style={styles.sourcesWrap}>
          <Text style={styles.sourcesLabel}>来源</Text>
          {sources.map((src, idx) => (
            <Text key={idx} style={styles.sourceItem} numberOfLines={1}>
              · {src}
            </Text>
          ))}
        </View>
      ) : null}

      {entityNeighbors.length > 0 ? (
        <View style={styles.entitiesWrap}>
          <Text style={styles.entitiesLabel}>相关条目</Text>
          {entityNeighbors.map((n) => (
            <EntityCard
              key={n.doc_id}
              entity={n}
              onPress={() => {
                if (!n.entity_type || !n.entity_id) return;
                onClose();
                router.push({
                  pathname: '/knowledge/entity' as any,
                  params: { type: n.entity_type, id: n.entity_id },
                });
              }}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}

function SourceChip({
  source,
  styles,
}: {
  source: KnowledgeSourceDetail;
  styles: ReturnType<typeof createStyles>;
}) {
  return (
    <View style={styles.sourceChip}>
      <Text style={styles.sourceChipLabel} numberOfLines={1}>
        {source.label || '来源'}
      </Text>
      <Text style={styles.sourceChipName} numberOfLines={1}>
        {source.display_name || source.source}
      </Text>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    backdrop: {
      flex: 1,
      backgroundColor: 'rgba(0,0,0,0.4)',
      justifyContent: 'flex-end',
    },
    sheet: {
      backgroundColor: c.bgCard,
      borderTopLeftRadius: 16,
      borderTopRightRadius: 16,
      paddingHorizontal: 20,
      paddingTop: 8,
      paddingBottom: 28,
    },
    handle: {
      alignSelf: 'center',
      width: 40,
      height: 4,
      borderRadius: 2,
      backgroundColor: c.separator,
      marginBottom: 12,
    },
    headerRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      marginBottom: 12,
    },
    titleWrap: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: 7,
    },
    title: {
      fontSize: 16,
      fontWeight: '600',
      color: c.labelPrimary,
    },
    center: {
      alignItems: 'center',
      paddingVertical: 28,
      gap: 8,
    },
    meta: {
      fontSize: 11,
      color: c.labelTertiary,
    },
    err: {
      fontSize: 13,
      color: c.red,
      paddingVertical: 18,
      textAlign: 'center',
    },
    claimBlock: {
      paddingVertical: 12,
    },
    claimDivider: {
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: c.separator,
    },
    claimHeader: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 8,
      marginBottom: 4,
    },
    claimTitle: {
      flex: 1,
      fontSize: 14,
      fontWeight: '600',
      color: c.labelPrimary,
      lineHeight: 19,
    },
    levelChip: {
      paddingHorizontal: 6,
      paddingVertical: 2,
      borderRadius: 4,
      backgroundColor: c.brandLight,
    },
    levelText: {
      fontSize: 10,
      color: c.brand,
      fontWeight: '600',
    },
    body: {
      marginTop: 6,
      fontSize: 13,
      color: c.labelPrimary,
      lineHeight: 18,
    },
    evidenceDescription: {
      marginTop: 4,
      fontSize: 11,
      color: c.labelSecondary,
      lineHeight: 15,
    },
    boundaryBox: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: 6,
      marginTop: 8,
      paddingVertical: 6,
      paddingHorizontal: 8,
      borderRadius: 6,
      backgroundColor: c.tintAmber,
    },
    boundaryText: {
      flex: 1,
      fontSize: 11,
      color: c.labelSecondary,
      lineHeight: 15,
    },
    sourcesWrap: {
      marginTop: 8,
    },
    sourcesLabel: {
      fontSize: 10,
      fontWeight: '600',
      color: c.labelTertiary,
      marginBottom: 2,
      textTransform: 'uppercase',
      letterSpacing: 0.3,
    },
    sourceItem: {
      fontSize: 11,
      color: c.labelSecondary,
      lineHeight: 15,
    },
    sourceChipRow: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 6,
    },
    sourceChip: {
      maxWidth: '100%',
      paddingHorizontal: 8,
      paddingVertical: 5,
      borderRadius: 6,
      backgroundColor: c.bgPrimary,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    },
    sourceChipLabel: {
      fontSize: 10,
      color: c.brand,
      fontWeight: '700',
      lineHeight: 13,
    },
    sourceChipName: {
      maxWidth: 240,
      marginTop: 1,
      fontSize: 11,
      color: c.labelSecondary,
      lineHeight: 14,
    },
    entitiesWrap: {
      marginTop: 10,
      gap: 6,
    },
    entitiesLabel: {
      fontSize: 10,
      fontWeight: '600',
      color: c.labelTertiary,
      marginBottom: 4,
      textTransform: 'uppercase',
      letterSpacing: 0.3,
    },
    feedbackBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      marginTop: 16,
      paddingVertical: 10,
      borderRadius: 8,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      backgroundColor: c.bgPrimary,
    },
    feedbackBtnSent: {
      backgroundColor: c.tintGreen,
      borderColor: c.tintGreen,
    },
    feedbackLabel: {
      fontSize: 12,
      color: c.labelSecondary,
      fontWeight: '500',
    },
  });
}
