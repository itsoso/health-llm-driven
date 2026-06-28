import React, { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import {
  revaColors as C,
  revaRadii,
  revaSemantic,
  revaShadows,
} from '../../constants/revaTheme';
import { SKIP_REASONS } from '../../constants/skipReasons';
import type { AgendaSkipReason } from '../../services/agenda';
import type {
  DailyArtifact,
  DailyArtifactTopAction,
} from '../../services/dailyArtifact';
import {
  buildTrajectorySummary,
  buildVerifySummary,
} from '../../services/trajectoryDisplay';
import { Icon } from '../reva/RevaKit';

export default function DailyArtifactCard({
  artifact,
  loading = false,
  completing = false,
  skipping = false,
  onComplete,
  onSkip,
  onAskReva,
  onPressAction,
}: {
  artifact?: DailyArtifact | null;
  loading?: boolean;
  completing?: boolean;
  skipping?: boolean;
  onComplete?: (action: DailyArtifactTopAction) => void;
  onSkip?: (reason: AgendaSkipReason, action: DailyArtifactTopAction | null) => void;
  onAskReva?: (artifact: DailyArtifact) => void;
  onPressAction?: (action: DailyArtifactTopAction) => void;
}) {
  const [showSkipReasons, setShowSkipReasons] = useState(false);
  const state = artifact?.state;
  const topAction = artifact?.top_action ?? null;
  const evidence = (artifact?.evidence ?? []).slice(0, 3);
  const canComplete = Boolean(topAction?.actions?.complete?.enabled);
  const busy = completing || skipping;
  const trajectorySummary = topAction ? buildTrajectorySummary(topAction) : null;
  const verifySummary = topAction ? buildVerifySummary(topAction) : null;

  if (loading && !artifact) {
    return (
      <View style={styles.card} testID="daily-artifact-card">
        <View style={styles.loadingRow}>
          <ActivityIndicator size="small" color={C.green500} />
          <Text style={styles.loadingText}>正在生成今日状态</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.card} testID="daily-artifact-card">
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Text style={styles.overline}>DAILY ARTIFACT</Text>
          <Text style={styles.stateLabel}>{state?.label ?? '今日状态'}</Text>
        </View>
        <View style={[styles.statusPill, toneStyle(state?.tone)]}>
          <Text style={[styles.statusPillText, toneTextStyle(state?.tone)]}>
            {confidenceLabel(artifact?.confidence)}
          </Text>
        </View>
      </View>

      {topAction ? (
        <Pressable
          style={({ pressed }) => [styles.actionBlock, pressed && { opacity: 0.88 }]}
          onPress={() => onPressAction?.(topAction)}
          accessibilityRole="button"
          accessibilityLabel={`今日最重要行动:${topAction.title}`}
        >
          <View style={styles.actionHead}>
            <Text style={styles.actionTag}>{topAction.priority_tier ?? 'TOP'}</Text>
            <Text style={styles.freshnessText} numberOfLines={1}>
              {freshnessLabel(artifact)}
            </Text>
          </View>
          <Text style={styles.title} numberOfLines={2}>{topAction.title}</Text>
          {topAction.do_now || topAction.why_now ? (
            <Text style={styles.summary} numberOfLines={3}>
              {topAction.do_now || topAction.why_now}
            </Text>
          ) : null}
          {trajectorySummary ? (
            <Text style={styles.controlInput} numberOfLines={1}>{trajectorySummary}</Text>
          ) : null}
          {verifySummary ? (
            <Text style={styles.verifyInput} numberOfLines={1}>验证: {verifySummary}</Text>
          ) : null}
        </Pressable>
      ) : (
        <View style={styles.emptyBlock}>
          <Icon name="check-circle-2" size={20} color={C.green500} />
          <View style={styles.emptyCopy}>
            <Text style={styles.summary}>{state?.summary ?? '今天暂无需要突出的健康行动。'}</Text>
          </View>
        </View>
      )}

      {evidence.length > 0 ? (
        <View style={styles.evidenceList}>
          {evidence.map((item, index) => (
            <View
              key={`${item.kind}-${index}`}
              style={styles.evidenceRow}
              testID="daily-artifact-evidence"
            >
              <View style={styles.evidenceDot} />
              <View style={styles.evidenceCopy}>
                <Text style={styles.evidenceLabel}>{evidenceLabel(item.label)}</Text>
                <Text style={styles.evidenceSummary} numberOfLines={2}>{item.summary}</Text>
              </View>
            </View>
          ))}
        </View>
      ) : null}

      {artifact?.safety_boundary ? (
        <Text style={styles.safety} numberOfLines={2}>{artifact.safety_boundary}</Text>
      ) : null}

      {topAction ? (
        <>
          <View style={styles.actions}>
            <Pressable
              style={({ pressed }) => [
                styles.primaryButton,
                (!canComplete || busy) && styles.buttonDisabled,
                pressed && canComplete && !busy && { opacity: 0.86 },
              ]}
              disabled={!canComplete || busy}
              onPress={() => onComplete?.(topAction)}
              accessibilityRole="button"
              accessibilityLabel="完成今日最重要行动"
            >
              {completing ? (
                <ActivityIndicator size="small" color={C.greenOn} />
              ) : (
                <>
                  <Icon name="check" size={15} color={C.greenOn} />
                  <Text style={styles.primaryText}>完成</Text>
                </>
              )}
            </Pressable>
            <Pressable
              style={({ pressed }) => [styles.secondaryButton, pressed && !busy && { opacity: 0.86 }]}
              disabled={busy}
              onPress={() => setShowSkipReasons((value) => !value)}
              accessibilityRole="button"
              accessibilityLabel="跳过今日最重要行动"
            >
              <Text style={styles.secondaryText}>跳过</Text>
            </Pressable>
            <Pressable
              style={({ pressed }) => [styles.iconButton, pressed && !busy && { opacity: 0.86 }]}
              disabled={busy || !artifact}
              onPress={() => artifact && onAskReva?.(artifact)}
              accessibilityRole="button"
              accessibilityLabel="询问 Reva 今日行动"
            >
              <Icon name="messages-square" size={18} color={C.green600} />
            </Pressable>
          </View>

          {showSkipReasons ? (
            <View style={styles.skipBox}>
              <Text style={styles.skipTitle}>为什么跳过?</Text>
              <View style={styles.skipGrid}>
                {SKIP_REASONS.map((reason) => (
                  <Pressable
                    key={reason.value}
                    style={({ pressed }) => [styles.reasonChip, pressed && { opacity: 0.84 }]}
                    disabled={busy}
                    onPress={() => {
                      setShowSkipReasons(false);
                      onSkip?.(reason.value, topAction);
                    }}
                  >
                    <Text style={styles.reasonText}>{reason.label}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}
        </>
      ) : null}
    </View>
  );
}

function confidenceLabel(confidence?: string | null): string {
  switch (confidence) {
    case 'high': return '高可信';
    case 'medium': return '中可信';
    case 'low': return '待补数';
    default: return '今日';
  }
}

function freshnessLabel(artifact?: DailyArtifact | null): string {
  const freshness = artifact?.freshness?.status;
  const sourceCount = artifact?.freshness?.sources?.length ?? 0;
  if (freshness === 'fresh') return sourceCount ? `${sourceCount} 个来源 · 新鲜` : '数据新鲜';
  if (freshness === 'limited') return '数据有限';
  return freshness || '今日编排';
}

function evidenceLabel(label: string): string {
  switch (label) {
    case 'Why now': return '为什么现在';
    case 'Trajectory': return '近期趋势';
    case 'Verification': return '如何验证';
    default: return label;
  }
}

function toneStyle(tone?: string | null) {
  if (tone === 'urgent') return { backgroundColor: revaSemantic.risk.bg, borderColor: revaSemantic.risk.line };
  if (tone === 'focused') return { backgroundColor: revaSemantic.info.bg, borderColor: revaSemantic.info.line };
  return { backgroundColor: revaSemantic.normal.bg, borderColor: revaSemantic.normal.line };
}

function toneTextStyle(tone?: string | null) {
  if (tone === 'urgent') return { color: revaSemantic.risk.fg };
  if (tone === 'focused') return { color: revaSemantic.info.fg };
  return { color: revaSemantic.normal.fg };
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    borderRadius: revaRadii.lg,
    padding: 16,
    gap: 14,
    ...revaShadows.md,
  },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  loadingText: { fontSize: 14, color: C.ink2 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  headerText: { flex: 1, minWidth: 0 },
  overline: {
    fontFamily: 'IBMPlexMono',
    fontSize: 10,
    letterSpacing: 0.8,
    color: C.ink3,
  },
  stateLabel: {
    marginTop: 3,
    fontFamily: 'Manrope',
    fontSize: 17,
    lineHeight: 22,
    fontWeight: '800',
    color: C.ink1,
  },
  statusPill: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  statusPillText: { fontSize: 12, fontWeight: '700' },
  actionBlock: {
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    borderRadius: revaRadii.md,
    padding: 14,
    gap: 7,
  },
  actionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 },
  actionTag: { fontFamily: 'IBMPlexMono', fontSize: 11, fontWeight: '600', color: C.green600 },
  freshnessText: { flexShrink: 1, fontSize: 12, color: C.ink3 },
  title: { fontFamily: 'Manrope', fontSize: 18, lineHeight: 24, fontWeight: '800', color: C.ink1 },
  summary: { fontSize: 14, lineHeight: 20, color: C.ink2 },
  controlInput: { fontSize: 13, lineHeight: 18, color: C.green700, fontWeight: '700' },
  verifyInput: { fontSize: 12, lineHeight: 17, color: C.ink3 },
  emptyBlock: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  emptyCopy: { flex: 1, minWidth: 0, gap: 3 },
  evidenceList: { gap: 8 },
  evidenceRow: { flexDirection: 'row', gap: 9, alignItems: 'flex-start' },
  evidenceDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: C.green500,
    marginTop: 7,
  },
  evidenceCopy: { flex: 1, minWidth: 0 },
  evidenceLabel: { fontSize: 12, fontWeight: '700', color: C.ink1 },
  evidenceSummary: { marginTop: 2, fontSize: 12.5, lineHeight: 18, color: C.ink2 },
  safety: { fontSize: 11.5, lineHeight: 16, color: C.ink3 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 9 },
  primaryButton: {
    flex: 1,
    minHeight: 42,
    borderRadius: revaRadii.sm,
    backgroundColor: C.green500,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  buttonDisabled: { opacity: 0.45 },
  primaryText: { color: C.greenOn, fontSize: 14, fontWeight: '800' },
  secondaryButton: {
    minHeight: 42,
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.lineStrong,
    paddingHorizontal: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.surface,
  },
  secondaryText: { color: C.ink2, fontSize: 14, fontWeight: '700' },
  iconButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: C.green50,
  },
  skipBox: { gap: 9 },
  skipTitle: { fontSize: 12, fontWeight: '700', color: C.ink2 },
  skipGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  reasonChip: {
    borderRadius: revaRadii.pill,
    backgroundColor: C.paper2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 11,
    paddingVertical: 8,
  },
  reasonText: { fontSize: 12, fontWeight: '700', color: C.ink2 },
});
