import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import {
  revaColors as C,
  revaRadii,
  revaSemantic,
  revaShadows,
  revaSpacing,
} from '../../constants/revaTheme';
import { Icon, ReadinessRing } from '../reva/RevaKit';
import type { AgendaSkipReason } from '../../services/agenda';
import type { DailyArtifact, DailyArtifactTone } from '../../services/dailyArtifact';
import type { SkipReasonOption } from '../../constants/skipReasons';

interface DailyArtifactCardProps {
  artifact: DailyArtifact;
  completing?: boolean;
  onPressAction?: () => void;
  onComplete?: () => void;
  onSkip?: () => void;
  onAskReva?: () => void;
  showSkipReasons?: boolean;
  skipReasons?: readonly SkipReasonOption[];
  onSkipReason?: (reason: AgendaSkipReason) => void;
}

const TONE: Record<DailyArtifactTone, { fg: string; bg: string; line: string }> = {
  normal: revaSemantic.normal,
  caution: revaSemantic.caution,
  risk: revaSemantic.risk,
  info: revaSemantic.info,
};

export default function DailyArtifactCard({
  artifact,
  completing,
  onPressAction,
  onComplete,
  onSkip,
  onAskReva,
  showSkipReasons,
  skipReasons = [],
  onSkipReason,
}: DailyArtifactCardProps) {
  const action = artifact.topAction;

  return (
    <View style={styles.card} testID="daily-artifact-card">
      <View style={styles.header}>
        <View style={styles.titleBlock}>
          <Text style={styles.overline}>{artifact.stateLabel}</Text>
          <Text style={styles.title}>今日最重要行动</Text>
        </View>
        <View style={[styles.freshness, { borderColor: TONE[artifact.freshness.tone].line, backgroundColor: TONE[artifact.freshness.tone].bg }]}>
          <Text style={[styles.freshnessText, { color: TONE[artifact.freshness.tone].fg }]}>
            {artifact.freshness.label}
          </Text>
        </View>
      </View>

      <View style={styles.body}>
        <View style={styles.readiness}>
          {artifact.readiness.score != null ? (
            <ReadinessRing score={artifact.readiness.score} dark={false} size={68} stroke={7} />
          ) : (
            <View style={styles.readinessPlaceholder}>
              <Text style={styles.readinessPlaceholderText}>待同步</Text>
            </View>
          )}
          <Text style={styles.readinessLabel} numberOfLines={1}>
            {artifact.readiness.label}
          </Text>
        </View>

        <Pressable
          style={({ pressed }) => [styles.actionMain, pressed && { opacity: 0.84 }]}
          onPress={onPressAction}
          accessibilityRole="button"
          accessibilityLabel={`今日最重要行动:${action?.title ?? '无'}`}
        >
          <View style={styles.actionCopy}>
            {action?.scheduledFor ? <Text style={styles.actionTime}>{action.scheduledFor}</Text> : null}
            <Text style={styles.actionTitle} numberOfLines={2}>
              {action?.title ?? '补齐今天记录'}
            </Text>
            {action?.subtitle ? (
              <Text style={styles.actionSubtitle} numberOfLines={2}>
                {action.subtitle}
              </Text>
            ) : null}
          </View>
          <Icon name="chevron-right" size={18} color={C.ink3} />
        </Pressable>
      </View>

      <View style={styles.evidenceRow}>
        {artifact.evidence.slice(0, 3).map((item) => {
          const tone = TONE[item.tone];
          return (
            <View key={item.id} style={[styles.evidenceChip, { backgroundColor: tone.bg, borderColor: tone.line }]}>
              <Text style={[styles.evidenceLabel, { color: tone.fg }]}>{item.label}</Text>
              <Text style={[styles.evidenceValue, { color: tone.fg }]} numberOfLines={1}>
                {item.value}
              </Text>
            </View>
          );
        })}
      </View>

      <View style={styles.boundaryRow}>
        <Icon
          name={artifact.safetyBoundary.level === 'risk' ? 'alert-triangle' : 'shield'}
          size={15}
          color={artifact.safetyBoundary.level === 'risk' ? revaSemantic.risk.fg : C.green600}
        />
        <Text style={styles.boundaryText}>{artifact.safetyBoundary.label}</Text>
      </View>

      <View style={styles.actions}>
        {artifact.actions.canComplete ? (
          <Pressable
            style={[styles.actionButton, styles.primaryButton, completing && styles.disabledButton]}
            onPress={completing ? undefined : onComplete}
            disabled={completing}
            accessibilityRole="button"
            accessibilityLabel="完成今日最重要行动"
          >
            <Icon name="check" size={15} color={C.greenOn} />
            <Text style={styles.primaryButtonText}>{completing ? '保存中' : '完成'}</Text>
          </Pressable>
        ) : null}
        {artifact.actions.canSkip ? (
          <Pressable
            style={[styles.actionButton, styles.secondaryButton]}
            onPress={onSkip}
            accessibilityRole="button"
            accessibilityLabel="跳过今日最重要行动"
          >
            <Text style={styles.secondaryButtonText}>跳过</Text>
          </Pressable>
        ) : null}
        {artifact.actions.canAskReva ? (
          <Pressable
            style={[styles.actionButton, styles.ghostButton]}
            onPress={onAskReva}
            accessibilityRole="button"
            accessibilityLabel="问 Reva 解释今日行动"
          >
            <Text style={styles.ghostButtonText}>问 Reva</Text>
          </Pressable>
        ) : null}
      </View>

      {showSkipReasons && artifact.actions.skipRequiresReason ? (
        <View style={styles.skipPanel}>
          <Text style={styles.skipTitle}>为什么跳过?</Text>
          <View style={styles.skipReasons}>
            {skipReasons.map((reason) => (
              <Pressable
                key={reason.value}
                style={({ pressed }) => [styles.skipReasonButton, pressed && { opacity: 0.78 }]}
                onPress={() => onSkipReason?.(reason.value)}
                accessibilityRole="button"
                accessibilityLabel={`跳过原因:${reason.label}`}
              >
                <Text style={styles.skipReasonText}>{reason.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.xl,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: 18,
    gap: revaSpacing.s4,
    ...revaShadows.md,
  },
  header: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: revaSpacing.s3 },
  titleBlock: { flex: 1, minWidth: 0 },
  overline: { fontFamily: 'IBMPlexMono', fontSize: 10.5, letterSpacing: 0.9, color: C.ink3 },
  title: { fontFamily: 'Manrope', fontSize: 19, lineHeight: 24, fontWeight: '800', color: C.ink1, marginTop: 3 },
  freshness: { borderWidth: 1, borderRadius: revaRadii.pill, paddingHorizontal: 10, paddingVertical: 5 },
  freshnessText: { fontSize: 11.5, fontWeight: '700' },
  body: { flexDirection: 'row', alignItems: 'center', gap: revaSpacing.s4 },
  readiness: { width: 78, alignItems: 'center', gap: 6 },
  readinessPlaceholder: {
    width: 68,
    height: 68,
    borderRadius: 34,
    borderWidth: 7,
    borderColor: C.green100,
    alignItems: 'center',
    justifyContent: 'center',
  },
  readinessPlaceholderText: { fontFamily: 'IBMPlexMono', fontSize: 10.5, color: C.ink3 },
  readinessLabel: { fontSize: 12, fontWeight: '700', color: C.green600 },
  actionMain: {
    flex: 1,
    minWidth: 0,
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: revaRadii.lg,
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: 14,
    gap: revaSpacing.s2,
  },
  actionCopy: { flex: 1, minWidth: 0 },
  actionTime: { fontFamily: 'IBMPlexMono', fontSize: 12, fontWeight: '700', color: C.green600, marginBottom: 3 },
  actionTitle: { fontFamily: 'Manrope', fontSize: 18, lineHeight: 23, fontWeight: '800', color: C.ink1 },
  actionSubtitle: { fontSize: 13, lineHeight: 18, color: C.ink2, marginTop: 4 },
  evidenceRow: { flexDirection: 'row', gap: revaSpacing.s2 },
  evidenceChip: {
    flex: 1,
    minWidth: 0,
    borderWidth: 1,
    borderRadius: revaRadii.md,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  evidenceLabel: { fontSize: 11.5, fontWeight: '700', marginBottom: 2 },
  evidenceValue: { fontFamily: 'IBMPlexMono', fontSize: 13, fontWeight: '600' },
  boundaryRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  boundaryText: { flex: 1, fontSize: 12.5, color: C.ink2 },
  actions: { flexDirection: 'row', gap: revaSpacing.s2 },
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 5,
    borderRadius: revaRadii.md,
    paddingHorizontal: 14,
    paddingVertical: 11,
  },
  primaryButton: { flex: 1.1, backgroundColor: C.green500 },
  secondaryButton: { flex: 0.9, backgroundColor: C.paper2 },
  ghostButton: { flex: 1, backgroundColor: C.green50 },
  disabledButton: { opacity: 0.68 },
  primaryButtonText: { color: C.greenOn, fontWeight: '800', fontSize: 14 },
  secondaryButtonText: { color: C.ink2, fontWeight: '800', fontSize: 14 },
  ghostButtonText: { color: C.green600, fontWeight: '800', fontSize: 14 },
  skipPanel: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
    paddingTop: revaSpacing.s3,
    gap: revaSpacing.s2,
  },
  skipTitle: { fontFamily: 'Manrope', fontSize: 13, fontWeight: '800', color: C.ink2 },
  skipReasons: { flexDirection: 'row', flexWrap: 'wrap', gap: revaSpacing.s2 },
  skipReasonButton: {
    borderRadius: revaRadii.pill,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.surface2,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  skipReasonText: { fontSize: 12.5, fontWeight: '800', color: C.ink2 },
});
