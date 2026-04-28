import React, { useState } from 'react';
import { LayoutAnimation, Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { Ionicons } from '@expo/vector-icons';
import {
  getActionCardProgress,
  getActionCardVerificationLabel,
  type ActionCard,
} from '../../services/actionCards';
import { buildActionCardOutcomeDraft } from '../../services/outcomeReview';
import type { OutcomeReviewDraft } from '../../services/outcomeReview';
import { colors, radii, shadows, spacing } from '../../constants/theme';
import ActionEvidenceRow from './ActionEvidenceRow';
import OutcomeVerificationSheet from './OutcomeVerificationSheet';

interface Props {
  card: ActionCard;
  onComplete: () => void;
  onReview?: (draft: OutcomeReviewDraft) => void | Promise<void>;
}

const CARD_TYPE: Record<string, { color: string; bg: string; icon: keyof typeof Ionicons.glyphMap; label: string }> = {
  guide: { color: '#0A8F8F', bg: '#E6F5F5', icon: 'compass-outline', label: '指南' },
  plan: { color: '#007AFF', bg: '#E6F0FF', icon: 'calendar-outline', label: '计划' },
  recommendation: { color: '#30D158', bg: '#E8FAF0', icon: 'bulb-outline', label: '建议' },
  reminder: { color: '#FF9F0A', bg: '#FFF5E6', icon: 'alarm-outline', label: '提醒' },
  insight: { color: '#5856D6', bg: '#EEEEFF', icon: 'analytics-outline', label: '洞察' },
  note: { color: '#8E8E93', bg: '#F2F2F7', icon: 'document-text-outline', label: '笔记' },
};

export default function InterventionCard({ card, onComplete, onReview }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const cfg = CARD_TYPE[card.card_type] || CARD_TYPE.insight;
  const progress = getActionCardProgress(card);
  const verification = getActionCardVerificationLabel(card);
  const assessment = card.latest_assessment;
  const reviewDraft = verification ? buildActionCardOutcomeDraft(card) : null;

  const toggle = () => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setExpanded(value => !value);
  };

  return (
    <>
      <Pressable
        style={({ pressed }) => [styles.card, pressed && styles.cardPressed]}
        onPress={toggle}
        accessibilityRole="button"
        accessibilityLabel={card.title}
        accessibilityState={{ expanded }}
      >
      <View style={styles.header}>
        <View style={[styles.iconWrap, { backgroundColor: cfg.bg }]}>
          <Ionicons name={cfg.icon} size={16} color={cfg.color} />
        </View>
        <View style={styles.titleBlock}>
          <Text style={txt.title} numberOfLines={expanded ? undefined : 2}>{card.title}</Text>
          <View style={styles.metaRow}>
            <Text style={[txt.typeBadge, { color: cfg.color }]}>{cfg.label}</Text>
            {card.created_at ? <Text style={txt.timeStamp}>{card.created_at.slice(0, 10)}</Text> : null}
            {progress ? <Text style={txt.progress}>{progress.completed}/{progress.total}</Text> : null}
            {card.creator_specialist ? (
              <Text style={txt.specialist}>{card.creator_specialist}</Text>
            ) : null}
          </View>
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-forward'} size={15} color={colors.labelTertiary} />
      </View>

      <TrustLoopBadge card={card} />

      {verification ? (
        <View style={styles.inlineEvidence}>
          <ActionEvidenceRow label="验证" value={verification} tone={assessment ? 'good' : 'warn'} icon="checkmark-done-outline" />
        </View>
      ) : null}

      {expanded ? (
        <View style={styles.expanded}>
          {card.grading_notes ? (
            <ActionEvidenceRow
              label="评分"
              value={card.grading_notes}
              tone={card.accuracy_score != null && card.accuracy_score >= 70 ? 'good' : 'warn'}
              icon="trophy-outline"
            />
          ) : null}
          {assessment?.summary ? (
            <ActionEvidenceRow label="最近评估" value={assessment.summary} tone="good" icon="pulse-outline" />
          ) : null}

          {progress && card.checklist ? (
            <View style={styles.checklist}>
              {card.checklist.map((item, index) => (
                <View key={`${item.item}-${index}`} style={styles.checkRow}>
                  <Ionicons
                    name={item.done ? 'checkmark-circle' : 'ellipse-outline'}
                    size={15}
                    color={item.done ? '#30D158' : colors.labelTertiary}
                  />
                  <Text style={[txt.checkText, item.done && txt.checkDone]}>{item.item}</Text>
                </View>
              ))}
            </View>
          ) : null}

          <View style={styles.markdownWrap}>
            <Markdown style={mdStyles}>{card.content || ''}</Markdown>
          </View>

          {reviewDraft ? (
            <Pressable
              style={({ pressed }) => [styles.completeBtn, pressed && styles.completeBtnPressed]}
              onPress={event => {
                event?.stopPropagation?.();
                setReviewOpen(true);
              }}
              accessibilityRole="button"
              accessibilityLabel="复盘结果"
            >
              <Ionicons name="checkmark-done" size={16} color="#fff" />
              <Text style={txt.completeBtnText}>复盘结果</Text>
            </Pressable>
          ) : (
            <Pressable
              style={({ pressed }) => [styles.completeBtn, pressed && styles.completeBtnPressed]}
              onPress={event => {
                event?.stopPropagation?.();
                onComplete();
              }}
              accessibilityRole="button"
              accessibilityLabel="标记完成"
            >
              <Ionicons name="checkmark-circle" size={16} color="#fff" />
              <Text style={txt.completeBtnText}>标记完成</Text>
            </Pressable>
          )}
        </View>
      ) : null}
      </Pressable>
      <OutcomeVerificationSheet
        visible={reviewOpen}
        title={card.title}
        draft={reviewDraft}
        onClose={() => setReviewOpen(false)}
        onSubmit={async draft => {
          await onReview?.(draft);
          setReviewOpen(false);
        }}
      />
    </>
  );
}

function TrustLoopBadge({ card }: { card: ActionCard }) {
  if (!card.metric_key || !card.target_value) return null;
  const graded = card.accuracy_score != null && card.graded_at;

  if (graded) {
    const score = card.accuracy_score!;
    const tone = score >= 70 ? '#30D158' : score >= 40 ? '#FF9F0A' : '#FF453A';
    const label = score >= 70 ? '命中' : score >= 40 ? '部分' : '未达';
    return (
      <View style={[styles.trustRow, { backgroundColor: tone + '15', borderColor: tone + '40' }]}>
        <Text style={[trustTxt.score, { color: tone }]}>
          {label} {score}
        </Text>
        <Text style={trustTxt.detail}>
          {card.baseline_value} → {card.actual_value} (目标 {card.target_value})
        </Text>
      </View>
    );
  }

  if (card.check_back_date) {
    const days = Math.max(0, Math.ceil((new Date(card.check_back_date).getTime() - Date.now()) / 86400000));
    const tone = days <= 1 ? '#FF453A' : colors.labelSecondary;
    return (
      <View style={[styles.trustRow, { backgroundColor: '#F2F2F7', borderColor: '#D1D1D6' }]}>
        <Text style={trustTxt.detail}>
          {card.baseline_value} → 目标 {card.target_value}
        </Text>
        <Text style={[trustTxt.countdown, { color: tone }]}>
          {days === 0 ? '今天评分' : `${days}天后评分`}
        </Text>
      </View>
    );
  }

  return null;
}

const trustTxt = {
  score: { fontSize: 12, fontWeight: '700' as const, marginRight: 8 } as TextStyle,
  detail: { fontSize: 11, color: colors.labelSecondary, flex: 1 } as TextStyle,
  countdown: { fontSize: 11, fontWeight: '600' as const } as TextStyle,
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radii.lg,
    marginBottom: 8,
    ...shadows.subtle,
  },
  cardPressed: { opacity: 0.88 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 14,
  },
  iconWrap: { width: 32, height: 32, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  titleBlock: { flex: 1 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 3 },
  inlineEvidence: { paddingHorizontal: 14, paddingBottom: 12, marginTop: -4 },
  trustRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    marginHorizontal: 14, marginBottom: 10,
    paddingHorizontal: 10, paddingVertical: 6,
    borderRadius: 8, borderWidth: 1,
  },
  expanded: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.separator,
    paddingHorizontal: 14,
    paddingBottom: 14,
    paddingTop: 12,
    gap: 10,
  },
  checklist: { gap: 7 },
  checkRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  markdownWrap: { marginTop: 2 },
  completeBtn: {
    minHeight: 40,
    borderRadius: radii.md,
    backgroundColor: '#30D158',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    marginTop: spacing.xs,
  },
  completeBtnPressed: { opacity: 0.82 },
});

const txt = {
  title: { fontSize: 15, fontWeight: '700', color: colors.labelPrimary, lineHeight: 20 } as TextStyle,
  typeBadge: { fontSize: 11, fontWeight: '700' } as TextStyle,
  timeStamp: { fontSize: 10, color: colors.labelTertiary } as TextStyle,
  progress: { fontSize: 11, color: colors.labelSecondary, fontWeight: '700' } as TextStyle,
  specialist: {
    fontSize: 10, color: colors.labelSecondary,
    fontFamily: 'Menlo', fontWeight: '600',
    backgroundColor: '#F2F2F7', paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4,
  } as TextStyle,
  checkText: { flex: 1, fontSize: 13, color: colors.labelSecondary } as TextStyle,
  checkDone: { color: colors.labelTertiary, textDecorationLine: 'line-through' } as TextStyle,
  completeBtnText: { fontSize: 14, fontWeight: '700', color: '#fff' } as TextStyle,
};

const mdStyles = StyleSheet.create({
  body: { fontSize: 14, lineHeight: 20, color: colors.labelSecondary },
  heading1: { fontSize: 16, fontWeight: '700', color: colors.labelPrimary, marginTop: 8, marginBottom: 4 },
  heading2: { fontSize: 15, fontWeight: '700', color: colors.labelPrimary, marginTop: 8, marginBottom: 4 },
  heading3: { fontSize: 14, fontWeight: '600', color: colors.labelPrimary, marginTop: 6, marginBottom: 2 },
  strong: { fontWeight: '700', color: colors.labelPrimary },
  paragraph: { marginVertical: 3 },
  bullet_list: { marginVertical: 4 },
  ordered_list: { marginVertical: 4 },
  list_item: { flexDirection: 'row', marginVertical: 2 },
  link: { color: colors.brand },
});
