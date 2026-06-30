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
  DailyArtifactEvidence,
  DailyArtifactTopAction,
} from '../../services/dailyArtifact';
import {
  buildTrajectorySummary,
  buildVerifySummary,
} from '../../services/trajectoryDisplay';
import { formatHealthActionTitle } from '../../utils/actionCopy';
import { Icon } from '../reva/RevaKit';

export default function DailyArtifactCard({
  artifact,
  loading = false,
  completing = false,
  skipping = false,
  onComplete,
  onSkip,
  onAskReva,
  onExplainBasis,
  onPressAction,
}: {
  artifact?: DailyArtifact | null;
  loading?: boolean;
  completing?: boolean;
  skipping?: boolean;
  onComplete?: (action: DailyArtifactTopAction) => void;
  onSkip?: (reason: AgendaSkipReason, action: DailyArtifactTopAction | null) => void;
  onAskReva?: (artifact: DailyArtifact) => void;
  onExplainBasis?: (artifact: DailyArtifact) => void;
  onPressAction?: (action: DailyArtifactTopAction) => void;
}) {
  const [showSkipReasons, setShowSkipReasons] = useState(false);
  const state = artifact?.state;
  const topAction = artifact?.top_action ?? null;
  const displayTitle = topAction ? formatHealthActionTitle(topAction.title) : null;
  const busy = completing || skipping;
  const trajectorySummary = topAction ? buildTrajectorySummary(topAction) : null;
  const verifySummary = topAction ? buildVerifySummary(topAction) : null;
  const visibleEvidence = topAction
    ? buildVisibleEvidence(artifact?.evidence ?? [], topAction, trajectorySummary, verifySummary)
    : [];
  const doNow = topAction ? conciseActionCopy(topAction.do_now, topAction.title) : null;
  const canComplete = Boolean(
    topAction?.actions?.complete?.enabled && hasCompletionSource(topAction),
  );

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
          <Text style={styles.overline}>今日焦点</Text>
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
          accessibilityLabel={`今日最重要行动:${displayTitle || topAction.title}`}
        >
          <View style={styles.actionHead}>
            <Text style={styles.actionTag}>现在只做</Text>
            <Text style={styles.freshnessText} numberOfLines={1}>
              {[topAction.priority_tier, freshnessLabel(artifact)].filter(Boolean).join(' · ')}
            </Text>
          </View>
          <Text style={styles.title} numberOfLines={2}>{displayTitle || topAction.title}</Text>
          {doNow ? (
            <View style={styles.executeRow}>
              <View style={styles.executeIcon}>
                <Icon name={canComplete ? 'check' : 'play'} size={14} color={C.green600} />
              </View>
              <Text style={styles.executeText} numberOfLines={2}>{doNow}</Text>
            </View>
          ) : null}
          {(trajectorySummary || verifySummary) ? (
            <View style={styles.summaryChips}>
              {trajectorySummary ? (
                <View style={styles.summaryChip}>
                  <Text style={styles.summaryChipLabel}>目标</Text>
                  <Text style={styles.summaryChipText} numberOfLines={1}>
                    {stripSummaryPrefix(trajectorySummary)}
                  </Text>
                </View>
              ) : null}
              {verifySummary ? (
                <View style={styles.summaryChip}>
                  <Text style={styles.summaryChipLabel}>验证</Text>
                  <Text style={styles.summaryChipText} numberOfLines={1}>{verifySummary}</Text>
                </View>
              ) : null}
            </View>
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

      {(topAction?.why_now || visibleEvidence.length > 0) ? (
        <View style={styles.evidenceList}>
          <View style={styles.evidenceHeader}>
            <Icon name="sparkles" size={14} color={C.green600} />
            <Text style={styles.evidenceHeaderText}>决策依据</Text>
          </View>
          {topAction?.why_now ? (
            <View style={styles.basisReasonRow} testID="daily-artifact-basis-reason">
              <View style={styles.evidenceDot} />
              <View style={styles.evidenceCopy}>
                <Text style={styles.evidenceLabel}>为什么现在</Text>
                <Text style={styles.evidenceSummary} numberOfLines={2}>{topAction.why_now}</Text>
              </View>
            </View>
          ) : null}
          {visibleEvidence.map((item, index) => (
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
          {artifact ? (
            <Pressable
              style={({ pressed }) => [styles.basisLink, pressed && { opacity: 0.82 }]}
              disabled={busy}
              onPress={() => onExplainBasis?.(artifact)}
              accessibilityRole="button"
              accessibilityLabel="查看今日行动决策依据"
            >
              <Text style={styles.basisLinkText}>查看决策依据</Text>
              <Icon name="messages-square" size={14} color={C.green600} />
            </Pressable>
          ) : null}
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
                !canComplete && styles.executeButton,
                busy && styles.buttonDisabled,
                pressed && !busy && { opacity: 0.86 },
              ]}
              disabled={busy}
              onPress={() => {
                if (canComplete) onComplete?.(topAction);
                else onPressAction?.(topAction);
              }}
              accessibilityRole="button"
              accessibilityLabel={canComplete ? '完成今日最重要行动' : '执行今日最重要行动'}
            >
              {completing ? (
                <ActivityIndicator size="small" color={C.greenOn} />
              ) : (
                <>
                  <Icon name={canComplete ? 'check' : 'play'} size={15} color={C.greenOn} />
                  <Text style={styles.primaryText}>{canComplete ? '完成' : '去执行'}</Text>
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
              style={({ pressed }) => [styles.askButton, pressed && !busy && { opacity: 0.86 }]}
              disabled={busy || !artifact}
              onPress={() => artifact && onAskReva?.(artifact)}
              accessibilityRole="button"
              accessibilityLabel="询问阿衡今日行动"
            >
              <Icon name="messages-square" size={16} color={C.green600} />
              <Text style={styles.askText}>问阿衡</Text>
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

function hasCompletionSource(action: DailyArtifactTopAction): boolean {
  const source = action.actions?.complete?.source ?? action.source;
  return Boolean(source?.object_type && source.object_id != null);
}

function conciseActionCopy(copy?: string | null, title?: string | null): string | null {
  if (!copy) return null;
  const normalizedCopy = normalizeCopy(copy);
  if (!normalizedCopy) return null;
  if (normalizedCopy === normalizeCopy(title)) return null;
  return copy.trim();
}

function stripSummaryPrefix(summary: string): string {
  return summary
    .replace(/^目标:\s*/u, '')
    .replace(/\s*·\s*周期:\s*/u, ' · ');
}

function buildVisibleEvidence(
  evidence: DailyArtifactEvidence[],
  action: DailyArtifactTopAction,
  trajectorySummary: string | null,
  verifySummary: string | null,
): DailyArtifactEvidence[] {
  const used = new Set<string>();
  [
    action.title,
    action.do_now,
    action.why_now,
    trajectorySummary,
    verifySummary,
  ].forEach((value) => {
    const key = normalizeCopy(value);
    if (key) used.add(key);
  });

  return evidence
    .filter((item) => {
      const key = normalizeCopy(item.summary);
      if (!key || used.has(key)) return false;
      used.add(key);
      return true;
    })
    .sort((a, b) => evidencePriority(a) - evidencePriority(b))
    .slice(0, 2);
}

function evidencePriority(item: DailyArtifactEvidence): number {
  const key = `${item.kind} ${item.label}`.toLowerCase();
  if (key.includes('why')) return 0;
  if (key.includes('verification')) return 1;
  if (key.includes('trajectory')) return 2;
  return 3;
}

function normalizeCopy(value?: string | null): string {
  return String(value ?? '')
    .replace(/[：:]\s*/gu, ':')
    .replace(/[，,。.;；\s]+/gu, '')
    .trim()
    .toLowerCase();
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
    padding: 18,
    gap: 15,
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
    borderRadius: revaRadii.md,
    padding: 15,
    gap: 10,
  },
  actionHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 },
  actionTag: { fontSize: 12, fontWeight: '800', color: C.green600 },
  freshnessText: { flexShrink: 1, fontSize: 12, color: C.ink3 },
  title: { fontFamily: 'Manrope', fontSize: 20, lineHeight: 27, fontWeight: '800', color: C.ink1 },
  summary: { fontSize: 14, lineHeight: 20, color: C.ink2 },
  executeRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 9,
    backgroundColor: C.surface,
    borderRadius: revaRadii.sm,
    padding: 10,
  },
  executeIcon: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: C.green50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  executeText: { flex: 1, minWidth: 0, fontSize: 14, lineHeight: 20, color: C.ink2, fontWeight: '600' },
  summaryChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  summaryChip: {
    flexGrow: 1,
    flexBasis: 130,
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.surface,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  summaryChipLabel: { fontSize: 11, color: C.ink3, fontWeight: '700' },
  summaryChipText: { marginTop: 2, fontSize: 12.5, color: C.green700, fontWeight: '800' },
  emptyBlock: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  emptyCopy: { flex: 1, minWidth: 0, gap: 3 },
  evidenceList: {
    gap: 8,
    paddingTop: 2,
  },
  evidenceHeader: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  evidenceHeaderText: { fontSize: 12, fontWeight: '800', color: C.green700 },
  evidenceRow: { flexDirection: 'row', gap: 9, alignItems: 'flex-start' },
  basisReasonRow: { flexDirection: 'row', gap: 9, alignItems: 'flex-start' },
  evidenceDot: {
    width: 7,
    height: 7,
    borderRadius: 3.5,
    backgroundColor: C.green500,
    marginTop: 7,
  },
  evidenceCopy: { flex: 1, minWidth: 0 },
  evidenceLabel: { fontSize: 12, fontWeight: '800', color: C.ink1 },
  evidenceSummary: { marginTop: 2, fontSize: 12.5, lineHeight: 18, color: C.ink2 },
  basisLink: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    borderRadius: revaRadii.pill,
    backgroundColor: C.green50,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  basisLinkText: { fontSize: 12.5, fontWeight: '800', color: C.green600 },
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
  executeButton: { backgroundColor: C.focusBg },
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
  askButton: {
    minWidth: 72,
    height: 42,
    borderRadius: revaRadii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    flexDirection: 'row',
    gap: 4,
    paddingHorizontal: 10,
    backgroundColor: C.green50,
  },
  askText: { fontSize: 13, fontWeight: '800', color: C.green600 },
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
