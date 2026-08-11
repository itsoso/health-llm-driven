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
  isDailyArtifactFollowUpAction,
  resolveDailyArtifactCompletionTarget,
} from '../../services/dailyArtifact';
import {
  buildTrajectorySummary,
  buildVerifySummary,
  stateVariableLabel,
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
  // 「如何验证」先保留指标 key 做特殊语义判断，再统一映射成中文显示名。
  const verifyMetricKeys = topAction ? verificationMetricKeys(topAction) : [];
  const verifyMetricNames = verifyMetricKeys
    .map((key) => stateVariableLabel(key))
    .filter((label): label is string => Boolean(label));
  const visibleEvidence = topAction
    ? rewriteVerificationEvidence(
        buildVisibleEvidence(artifact?.evidence ?? [], topAction, trajectorySummary, verifySummary),
        verifyMetricNames,
        verifyMetricKeys,
      )
    : [];
  const doNow = topAction ? conciseActionCopy(topAction.do_now, topAction.title) : null;
  const canComplete = Boolean(
    topAction?.actions?.complete?.enabled && resolveDailyArtifactCompletionTarget(topAction),
  );
  const isFollowUp = isDailyArtifactFollowUpAction(topAction);
  const primaryActionLabel = canComplete ? '完成' : isFollowUp ? '处理复查' : '去执行';
  const primaryAccessibilityLabel = canComplete
    ? '完成今日最重要行动'
    : isFollowUp
      ? '处理今日复查'
      : '执行今日最重要行动';

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
          <Text style={styles.overline}>今日行动</Text>
          {topAction && state?.summary ? (
            <Text style={styles.headerHint} numberOfLines={1}>{state.summary}</Text>
          ) : null}
        </View>
        <View style={[styles.statusPill, confidenceToneStyle(artifact?.confidence)]}>
          <Text style={[styles.statusPillText, confidenceToneTextStyle(artifact?.confidence)]}>
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
          <View style={styles.actionMetaRow}>
            <Text style={styles.freshnessText} numberOfLines={1}>
              {[priorityLabel(topAction.priority_tier), freshnessLabel(artifact)].filter(Boolean).join(' · ')}
            </Text>
            <Icon name="chevron-right" size={16} color={C.ink3} />
          </View>
          <Text style={styles.title} numberOfLines={2}>{displayTitle || topAction.title}</Text>
          {doNow ? (
            <View style={styles.doNowRow}>
              <Icon name={canComplete ? 'check-circle-2' : isFollowUp ? 'calendar-check' : 'play-circle'} size={17} color={C.green600} />
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
            <Text style={styles.emptyTitle}>{state?.label ?? '暂无今日重点'}</Text>
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
              accessibilityLabel={primaryAccessibilityLabel}
            >
              {completing ? (
                <ActivityIndicator size="small" color={C.greenOn} />
              ) : (
                <>
                  <Icon name={canComplete ? 'check' : isFollowUp ? 'calendar-check' : 'play'} size={15} color={C.greenOn} />
                  <Text style={styles.primaryText}>{primaryActionLabel}</Text>
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
              accessibilityLabel="询问小巴今日行动"
            >
              <Icon name="messages-square" size={16} color={C.green600} />
              <Text style={styles.askText}>问小巴</Text>
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
    case 'high': return '重点行动';
    case 'medium': return '建议行动';
    case 'low': return '待补数据';
    default: return '今日建议';
  }
}

function priorityLabel(priority?: string | null): string | null {
  switch (priority) {
    case 'P0': return '优先处理';
    case 'P1': return '今日重点';
    case 'P2': return '可安排';
    default: return priority ? '今日重点' : null;
  }
}

function freshnessLabel(artifact?: DailyArtifact | null): string {
  const freshness = artifact?.freshness?.status;
  if (freshness === 'fresh') return '数据已更新';
  if (freshness === 'limited') return '数据有限';
  if (freshness === 'stale') return '等待更新';
  return freshness ? '数据已同步' : '今日编排';
}

function evidenceLabel(label: string): string {
  switch (label) {
    case 'Why now': return '为什么现在';
    case 'Trajectory': return '近期趋势';
    case 'Verification': return '如何验证';
    default: return label;
  }
}

// do_now「执行」子行的 affordance 前缀:后端有时把整条标题原样塞进 do_now,再前缀
// 「查看并确认:」/「今日训练:」——渲染出来就是标题在大字下面又抄了一遍(用户实拍的重复)。
const AFFORDANCE_PREFIX_RE = /^\s*查看并确认\s*[:：]?\s*(?:今日训练\s*[:：]\s*)?/u;
const AFFORDANCE_LABEL = '查看并确认';

// do_now 与标题去重:剥掉 affordance 前缀后,若剩余与标题(原始/清洗后任一)高度相似(>60% 归一化
// 包含),说明这行只是标题的复读 —— 有 affordance 前缀就只留「查看并确认」这一 chip 文案,
// 没有前缀(纯复读)就整行丢掉。压制处理会保持点击行为不变(调用方 onPress 不受文案影响)。
function conciseActionCopy(copy?: string | null, title?: string | null): string | null {
  if (!copy) return null;
  const trimmed = copy.trim();
  if (!trimmed) return null;

  const hadAffordancePrefix = AFFORDANCE_PREFIX_RE.test(trimmed);
  const stripped = trimmed.replace(AFFORDANCE_PREFIX_RE, '').trim();
  const bodyForCompare = stripped || trimmed;

  if (isTitleEcho(bodyForCompare, title)) {
    return hadAffordancePrefix ? AFFORDANCE_LABEL : null;
  }
  return trimmed;
}

// 归一化包含判定:copy 与标题(原始 + formatHealthActionTitle 清洗后)任一方向包含,
// 且被包含串占较长串 >60% → 视为「同一句话」。避免只按精确相等漏掉标题被复读的情况。
function isTitleEcho(copy: string, title?: string | null): boolean {
  const a = normalizeCopy(copy);
  if (!a) return false;
  for (const t of [title, formatHealthActionTitle(title)]) {
    const b = normalizeCopy(t);
    if (!b) continue;
    if (a === b) return true;
    const [shorter, longer] = a.length <= b.length ? [a, b] : [b, a];
    if (longer.includes(shorter) && shorter.length / longer.length > 0.6) return true;
  }
  return false;
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

// 「如何验证」行去 filler:后端有时给「后续用这些信号验证是否有效。」这类什么都没说的泛化句。
// 有具体验证指标(体重 / 腰围 / 收缩压…)→ 换成实名句「后续观察 X / Y 的变化。」;
// 一个具体指标都没有 → 整行丢掉(不留 filler)。非 verification 行原样透传。
function rewriteVerificationEvidence(
  evidence: DailyArtifactEvidence[],
  metricNames: string[],
  metricKeys: string[],
): DailyArtifactEvidence[] {
  return evidence.flatMap((item) => {
    if (!isVerificationEvidence(item)) return [item];
    if (metricNames.length === 0) return []; // 无指标 → 丢掉泛化 filler 行
    if (metricKeys.includes('follow_up_completed')) {
      return [{ ...item, summary: '后续确认复查是否完成。' }];
    }
    return [{ ...item, summary: `后续观察 ${metricNames.join(' / ')} 的变化。` }];
  });
}

function isVerificationEvidence(item: DailyArtifactEvidence): boolean {
  return `${item.kind} ${item.label}`.toLowerCase().includes('verification');
}

// 从 action 抽出验证指标 key(verify_by.metrics + target/verification 信号),去重、去空；
// 显示名在调用处统一走 stateVariableLabel 单一真相源。
function verificationMetricKeys(action: DailyArtifactTopAction): string[] {
  const raw: (string | null | undefined)[] = [];
  const verifyBy = (action as { verify_by?: { metrics?: unknown } }).verify_by;
  if (Array.isArray(verifyBy?.metrics)) {
    for (const m of verifyBy.metrics) if (typeof m === 'string') raw.push(m);
  }
  raw.push(action.verification_signal ?? null);
  raw.push(action.target_state_variable ?? null);
  const seen = new Set<string>();
  const keys: string[] = [];
  for (const key of raw) {
    const normalized = key?.trim();
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized);
      keys.push(normalized);
    }
  }
  return keys;
}

function normalizeCopy(value?: string | null): string {
  return String(value ?? '')
    .replace(/[：:]\s*/gu, ':')
    .replace(/[，,。.;；\s]+/gu, '')
    .trim()
    .toLowerCase();
}

// 可信度 pill 配色跟「可信度」这个正向信号走,不跟 state.tone(紧急态)走:
// 重点行动 = 正向 → success 绿;建议行动 = 中性;待补数据 = 提示补数 → caution 琥珀。
// 之前误用 tone 上色,tone=urgent 时会把「高可信」染成红色,读成告警(语义色误用)。
function confidenceToneStyle(confidence?: string | null) {
  const s = confidenceSemantic(confidence);
  return { backgroundColor: s.bg, borderColor: s.line };
}

function confidenceToneTextStyle(confidence?: string | null) {
  return { color: confidenceSemantic(confidence).fg };
}

// 中性(中可信 / 缺省):走 Reva 中性 token(纸底 + 灰线 + 次级墨),不占任何临床语义色。
const CONFIDENCE_NEUTRAL = { fg: C.ink2, bg: C.paper2, line: C.lineStrong };

function confidenceSemantic(confidence?: string | null) {
  if (confidence === 'high') return revaSemantic.normal; // 正向:绿
  if (confidence === 'low') return revaSemantic.caution; // 待补数:琥珀
  return CONFIDENCE_NEUTRAL; // 中可信 / 缺省:中性(绝不用 risk 红)
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    borderRadius: revaRadii.lg,
    padding: 17,
    gap: 14,
    ...revaShadows.sm,
  },
  loadingRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  loadingText: { fontSize: 14, color: C.ink2 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  headerText: { flex: 1, minWidth: 0 },
  overline: {
    fontFamily: 'Manrope',
    fontSize: 13,
    lineHeight: 17,
    fontWeight: '800',
    color: C.green700,
  },
  headerHint: {
    marginTop: 3,
    fontSize: 12,
    lineHeight: 17,
    color: C.ink3,
  },
  statusPill: {
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: revaRadii.pill,
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  statusPillText: { fontSize: 12, fontWeight: '700' },
  actionBlock: {
    backgroundColor: C.surface,
    borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    padding: 14,
    gap: 9,
  },
  actionMetaRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 10 },
  freshnessText: { flexShrink: 1, fontSize: 12, color: C.ink3 },
  title: { fontFamily: 'Manrope', fontSize: 19, lineHeight: 26, fontWeight: '800', color: C.ink1 },
  summary: { fontSize: 14, lineHeight: 20, color: C.ink2 },
  doNowRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    paddingTop: 1,
  },
  executeText: { flex: 1, minWidth: 0, fontSize: 14, lineHeight: 20, color: C.ink2, fontWeight: '600' },
  summaryChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  summaryChip: {
    flexGrow: 1,
    flexBasis: 130,
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.surface2,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  summaryChipLabel: { fontSize: 11, color: C.ink3, fontWeight: '700' },
  summaryChipText: { marginTop: 2, fontSize: 12.5, color: C.green700, fontWeight: '800' },
  emptyBlock: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  emptyCopy: { flex: 1, minWidth: 0, gap: 3 },
  emptyTitle: { fontSize: 15, lineHeight: 20, fontWeight: '800', color: C.ink1 },
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
  actions: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  primaryButton: {
    flex: 1,
    minHeight: 44,
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
    minHeight: 44,
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
    height: 44,
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
