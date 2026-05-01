import React, { useMemo, useState } from 'react';
import { LayoutAnimation, Pressable, StyleSheet, Text, TextStyle, View } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import {
  getActionCardProgress,
  getActionCardVerificationLabel,
  type ActionCard,
} from '../../services/actionCards';
import { buildActionCardOutcomeDraft } from '../../services/outcomeReview';
import type { OutcomeReviewDraft } from '../../services/outcomeReview';
import { radii, spacing } from '../../constants/theme';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import ActionEvidenceRow from './ActionEvidenceRow';
import OutcomeVerificationSheet from './OutcomeVerificationSheet';

interface Props {
  card: ActionCard;
  onComplete: () => void;
  onReview?: (draft: OutcomeReviewDraft) => void | Promise<void>;
}

function cardTypeMeta(c: ColorPalette): Record<string, { color: string; bg: string; icon: keyof typeof Ionicons.glyphMap; label: string }> {
  return {
    guide:          { color: c.brand,  bg: c.brandLight, icon: 'compass-outline',         label: '指南' },
    plan:           { color: '#0A84FF', bg: c.tintBlue,  icon: 'calendar-outline',         label: '计划' },
    recommendation: { color: c.green,   bg: c.tintGreen, icon: 'bulb-outline',             label: '建议' },
    reminder:       { color: c.amber,   bg: c.tintAmber, icon: 'alarm-outline',            label: '提醒' },
    insight:        { color: '#5856D6', bg: c.tintPurple,icon: 'analytics-outline',        label: '洞察' },
    note:           { color: c.labelTertiary, bg: c.bgPrimary, icon: 'document-text-outline', label: '笔记' },
  };
}

export default function InterventionCard({ card, onComplete, onReview }: Props) {
  const router = useRouter();
  const { c, isDark } = useTheme();
  const styles = useMemo(() => createStyles(c, isDark), [c, isDark]);
  const txt = useMemo(() => createTxt(c), [c]);
  const mdStyles = useMemo(() => createMdStyles(c), [c]);
  const CARD_TYPE = useMemo(() => cardTypeMeta(c), [c]);
  const [expanded, setExpanded] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const cfg = CARD_TYPE[card.card_type] || CARD_TYPE.insight;
  const progress = getActionCardProgress(card);
  const verification = getActionCardVerificationLabel(card);
  const assessment = card.latest_assessment;
  const reviewDraft = verification ? buildActionCardOutcomeDraft(card) : null;
  // 反查推理 trace: anomaly_alert 类源 source_id 与后端 trace id 一一对应
  const traceHref =
    card.source_type === 'anomaly_alert' && card.source_id
      ? `/trace/anomaly_${card.source_id}`
      : '/trace';

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
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-forward'} size={15} color={c.labelTertiary} />
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
                    color={item.done ? '#30D158' : c.labelTertiary}
                  />
                  <Text style={[txt.checkText, item.done && txt.checkDone]}>{item.item}</Text>
                </View>
              ))}
            </View>
          ) : null}

          <View style={styles.markdownWrap}>
            <Markdown style={mdStyles}>{card.content || ''}</Markdown>
          </View>

          <Pressable
            style={({ pressed }) => [styles.traceLink, pressed && styles.traceLinkPressed]}
            onPress={event => {
              event?.stopPropagation?.();
              router.push(traceHref as any);
            }}
            accessibilityRole="link"
            accessibilityLabel="查看 AI 决策推理"
          >
            <Ionicons name="git-network-outline" size={13} color={c.brand} />
            <Text style={txt.traceLinkText}>查看推理</Text>
            <Ionicons name="chevron-forward" size={12} color={c.brand} />
          </Pressable>

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
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c, false), [c]);
  if (!card.metric_key || !card.target_value) return null;
  const graded = card.accuracy_score != null && card.graded_at;

  if (graded) {
    const score = card.accuracy_score!;
    const tone = score >= 70 ? c.green : score >= 40 ? c.amber : c.red;
    const label = score >= 70 ? '命中' : score >= 40 ? '部分' : '未达';
    return (
      <View style={[styles.trustRow, { backgroundColor: tone + '15', borderColor: tone + '40' }]}>
        <Text style={{ fontSize: 12, fontWeight: '700', marginRight: 8, color: tone }}>
          {label} {score}
        </Text>
        <Text style={{ fontSize: 11, color: c.labelSecondary, flex: 1 }}>
          {card.baseline_value} → {card.actual_value} (目标 {card.target_value})
        </Text>
      </View>
    );
  }

  if (card.check_back_date) {
    const days = Math.max(0, Math.ceil((new Date(card.check_back_date).getTime() - Date.now()) / 86400000));
    const tone = days <= 1 ? c.red : c.labelSecondary;
    return (
      <View style={[styles.trustRow, { backgroundColor: c.bgPrimary, borderColor: c.separator }]}>
        <Text style={{ fontSize: 11, color: c.labelSecondary, flex: 1 }}>
          {card.baseline_value} → 目标 {card.target_value}
        </Text>
        <Text style={{ fontSize: 11, fontWeight: '600', color: tone }}>
          {days === 0 ? '今天评分' : `${days}天后评分`}
        </Text>
      </View>
    );
  }

  return null;
}

function createStyles(c: ColorPalette, isDark: boolean) {
  return StyleSheet.create({
    card: {
      backgroundColor: c.bgCard,
      borderRadius: radii.lg,
      marginBottom: 8,
      ...(isDark
        ? { borderWidth: StyleSheet.hairlineWidth, borderColor: c.separator }
        : {
            shadowColor: '#000', shadowOffset: { width: 0, height: 1 },
            shadowOpacity: 0.06, shadowRadius: 3, elevation: 1,
          }),
    },
    cardPressed: { opacity: 0.88 },
    header: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14 },
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
      borderTopColor: c.separator,
      paddingHorizontal: 14, paddingBottom: 14, paddingTop: 12,
      gap: 10,
    },
    checklist: { gap: 7 },
    checkRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
    markdownWrap: { marginTop: 2 },
    completeBtn: {
      minHeight: 40, borderRadius: radii.md, backgroundColor: c.green,
      flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
      gap: 6, marginTop: spacing.xs,
    },
    completeBtnPressed: { opacity: 0.82 },
    traceLink: {
      flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start',
      gap: 4, paddingHorizontal: 10, paddingVertical: 6,
      backgroundColor: c.brandLight, borderRadius: 12,
    },
    traceLinkPressed: { opacity: 0.7 },
  });
}

function createTxt(c: ColorPalette) {
  return {
    title: { fontSize: 15, fontWeight: '700', color: c.labelPrimary, lineHeight: 20 } as TextStyle,
    typeBadge: { fontSize: 11, fontWeight: '700' } as TextStyle,
    timeStamp: { fontSize: 10, color: c.labelTertiary } as TextStyle,
    progress: { fontSize: 11, color: c.labelSecondary, fontWeight: '700' } as TextStyle,
    specialist: {
      fontSize: 10, color: c.labelSecondary,
      fontFamily: 'Menlo', fontWeight: '600',
      backgroundColor: c.bgPrimary, paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4,
    } as TextStyle,
    checkText: { flex: 1, fontSize: 13, color: c.labelSecondary } as TextStyle,
    checkDone: { color: c.labelTertiary, textDecorationLine: 'line-through' } as TextStyle,
    completeBtnText: { fontSize: 14, fontWeight: '700', color: '#fff' } as TextStyle,
    traceLinkText: { fontSize: 12, fontWeight: '600', color: c.brand } as TextStyle,
  };
}

function createMdStyles(c: ColorPalette) {
  return StyleSheet.create({
    body: { fontSize: 14, lineHeight: 20, color: c.labelSecondary },
    heading1: { fontSize: 16, fontWeight: '700', color: c.labelPrimary, marginTop: 8, marginBottom: 4 },
    heading2: { fontSize: 15, fontWeight: '700', color: c.labelPrimary, marginTop: 8, marginBottom: 4 },
    heading3: { fontSize: 14, fontWeight: '600', color: c.labelPrimary, marginTop: 6, marginBottom: 2 },
    strong: { fontWeight: '700', color: c.labelPrimary },
    paragraph: { marginVertical: 3 },
    bullet_list: { marginVertical: 4 },
    ordered_list: { marginVertical: 4 },
    list_item: { flexDirection: 'row', marginVertical: 2 },
    link: { color: c.brand },
  });
}
