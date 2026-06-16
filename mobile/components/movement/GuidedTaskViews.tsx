/**
 * GuidedTaskViews —— /guided-task 屏的展示层子组件 + 样式(从屏文件拆出以守 ≤500 行预算)。
 *
 * 纯展示,不持有业务状态;门控/动作/计划/引导分步/RPE+完成/跳过/完成反馈各一块。
 * 内容来自后端循证库(GuidedTask),前端不写死动作要领。
 */
import React from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TextStyle,
  TouchableOpacity,
  View,
  ViewStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { radii, spacing, typography } from '../../constants/theme';
import { ColorPalette, SemanticPalette } from '../../hooks/useTheme';
import EvidenceChip from '../shared/EvidenceChip';
import type { GuidedGateDecision, GuidedTask } from '../../services/guidedTask';

export const RPE_SCALE = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
export const SKIP_REASONS = ['没时间', '太累', '不在家', '身体不适'];

// 门控档 → 语义色 + 标签(裁决①:让用户感到系统在替他判断)。
const GATE_META: Record<GuidedGateDecision, { tone: keyof SemanticPalette; label: string; icon: string }> = {
  do: { tone: 'success', label: '照常做', icon: 'checkmark-circle' },
  modified: { tone: 'warning', label: '已降阶', icon: 'options' },
  rest_instead: { tone: 'danger', label: '今日换休息', icon: 'bed' },
};

export type Styles = ReturnType<typeof createStyles>;

// ── Header ───────────────────────────────────────────────
export function Header({
  title,
  onClose,
  styles,
  c,
}: {
  title: string;
  onClose: () => void;
  styles: Styles;
  c: ColorPalette;
}) {
  return (
    <View style={styles.header}>
      <TouchableOpacity onPress={onClose} hitSlop={12}>
        <Ionicons name="close" size={24} color={c.labelSecondary} />
      </TouchableOpacity>
      <Text style={styles.headerTitle} numberOfLines={1}>
        {title}
      </Text>
      <View style={{ width: 24 }} />
    </View>
  );
}

// ── 门控横幅(裁决①可见性:系统替你判断)───────────────────
export function GateBanner({ task, styles, s }: { task: GuidedTask; styles: Styles; s: SemanticPalette }) {
  const meta = GATE_META[task.gate.decision] ?? GATE_META.do;
  const tone = s[meta.tone];
  const note = task.gate.decision !== 'do' ? task.safety_note ?? task.gate.reason : task.gate.reason;
  return (
    <View style={[styles.gate, { backgroundColor: tone.bg }]}>
      <Ionicons name={meta.icon as any} size={22} color={tone.solid} />
      <View style={styles.gateBody}>
        <Text style={[styles.gateLabel, { color: tone.fg }]}>{meta.label}</Text>
        <Text style={[styles.gateReason, { color: tone.fg }]}>{note}</Text>
        <Text style={styles.gateZone}>恢复区:{zoneLabel(task.gate.readiness_zone)}</Text>
      </View>
    </View>
  );
}

function zoneLabel(zone: string): string {
  switch (zone) {
    case 'green':
      return '绿(可冲)';
    case 'yellow':
      return '黄(适度)';
    case 'red':
      return '红(需保守)';
    default:
      return '未知';
  }
}

// ── 动作卡 ───────────────────────────────────────────────
export function ExerciseCard({
  task,
  styles,
  c,
  s,
}: {
  task: GuidedTask;
  styles: Styles;
  c: ColorPalette;
  s: SemanticPalette;
}) {
  const ex = task.exercise;
  return (
    <View style={styles.card}>
      <View style={styles.exHeader}>
        <Text style={styles.exName}>{ex.name}</Text>
        <EvidenceChip level={ex.evidence_tier} />
      </View>

      {ex.media_ref ? (
        <View style={styles.mediaPlaceholder}>
          <Ionicons name="play-circle-outline" size={28} color={c.labelTertiary} />
          <Text style={styles.mediaHint}>示范视频(待加载)</Text>
        </View>
      ) : null}

      {ex.cues.length > 0 ? (
        <View style={styles.cueList}>
          {ex.cues.map((cue, i) => (
            <View key={i} style={styles.cueRow}>
              <Ionicons name="ellipse" size={6} color={c.brand} style={{ marginTop: 7 }} />
              <Text style={styles.cueText}>{cue}</Text>
            </View>
          ))}
        </View>
      ) : null}

      {ex.contraindications.length > 0 ? (
        <View style={[styles.contraBox, { backgroundColor: s.danger.bg }]}>
          <Ionicons name="warning-outline" size={16} color={s.danger.solid} />
          <View style={{ flex: 1 }}>
            {ex.contraindications.map((ct, i) => (
              <Text key={i} style={[styles.contraText, { color: s.danger.fg }]}>
                {ct}
              </Text>
            ))}
          </View>
        </View>
      ) : null}
    </View>
  );
}

// ── 计划卡 ───────────────────────────────────────────────
export function PlanCard({ task, styles, c }: { task: GuidedTask; styles: Styles; c: ColorPalette }) {
  const p = task.plan;
  const main =
    p.sets != null && p.reps != null
      ? `${p.sets} 组 × ${p.reps} 次`
      : p.duration_sec != null
        ? formatDuration(p.duration_sec)
        : '按引导执行';
  return (
    <View style={styles.card}>
      <View style={styles.planRow}>
        <Ionicons name="barbell-outline" size={18} color={c.brand} />
        <Text style={styles.planMain}>{main}</Text>
        {p.rest_sec != null ? <Text style={styles.planRest}>组间歇 {p.rest_sec}s</Text> : null}
      </View>
      {p.progression_note ? <Text style={styles.progression}>{p.progression_note}</Text> : null}
    </View>
  );
}

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec} 秒`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return s === 0 ? `${m} 分钟` : `${m} 分 ${s} 秒`;
}

// ── 引导执行分步器(expo-speech 念 cue + 震动节拍)─────────
export function GuideStepper({
  task,
  stepIdx,
  onStep,
  styles,
  c,
  s,
}: {
  task: GuidedTask;
  stepIdx: number;
  onStep: (idx: number, script: string[]) => void;
  styles: Styles;
  c: ColorPalette;
  s: SemanticPalette;
}) {
  const script = task.voice_script ?? [];
  if (script.length === 0) return null;
  const cur = script[Math.min(stepIdx, script.length - 1)];
  const atFirst = stepIdx <= 0;
  const atLast = stepIdx >= script.length - 1;
  return (
    <View style={styles.card}>
      <View style={styles.stepHeader}>
        <Ionicons name="megaphone-outline" size={16} color={c.brand} />
        <Text style={styles.stepLabel}>
          引导执行 · 第 {Math.min(stepIdx + 1, script.length)}/{script.length} 步
        </Text>
        <TouchableOpacity onPress={() => onStep(stepIdx, script)} hitSlop={10}>
          <Ionicons name="volume-high-outline" size={18} color={c.brand} />
        </TouchableOpacity>
      </View>

      <Text style={styles.stepText}>{cur}</Text>

      <View style={styles.stepNav}>
        <TouchableOpacity
          style={[styles.navBtn, atFirst && styles.navBtnDisabled]}
          disabled={atFirst}
          onPress={() => onStep(stepIdx - 1, script)}
        >
          <Ionicons name="chevron-back" size={18} color={atFirst ? c.labelTertiary : c.brand} />
          <Text style={[styles.navText, atFirst && { color: c.labelTertiary }]}>上一步</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.navBtn, styles.navBtnPrimary, { backgroundColor: s.success.solid }]}
          onPress={() => onStep(stepIdx + 1, script)}
          disabled={atLast}
        >
          <Text style={styles.navTextPrimary}>{atLast ? '已到最后一步' : '下一步'}</Text>
          {!atLast ? <Ionicons name="chevron-forward" size={18} color="#fff" /> : null}
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ── RPE 快选 + 完成 / 晚点 / 跳过 ────────────────────────
export function RpeAndComplete({
  task,
  rpe,
  setRpe,
  submitting,
  onComplete,
  onLater,
  onSkip,
  styles,
  c,
  s,
}: {
  task: GuidedTask;
  rpe: number | null;
  setRpe: (v: number) => void;
  submitting: boolean;
  onComplete: () => void;
  onLater: () => void;
  onSkip: () => void;
  styles: Styles;
  c: ColorPalette;
  s: SemanticPalette;
}) {
  const isRest = task.gate.decision === 'rest_instead';
  return (
    <View style={styles.card}>
      {!isRest ? (
        <>
          <Text style={styles.rpeLabel}>这次费力程度(可选)</Text>
          <View style={styles.rpeRow}>
            {RPE_SCALE.map((v) => (
              <TouchableOpacity
                key={v}
                style={[
                  styles.rpeChip,
                  rpe === v && { backgroundColor: s.success.solid, borderColor: s.success.solid },
                ]}
                onPress={() => setRpe(v)}
              >
                <Text style={[styles.rpeChipText, rpe === v && { color: '#fff' }]}>{v}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </>
      ) : null}

      <TouchableOpacity
        style={[styles.primaryBtn, { backgroundColor: s.success.solid }, submitting && styles.btnDisabled]}
        disabled={submitting}
        onPress={onComplete}
      >
        {submitting ? (
          <ActivityIndicator size="small" color="#fff" />
        ) : (
          <>
            <Ionicons name="checkmark" size={18} color="#fff" />
            <Text style={styles.primaryText}>{isRest ? '记下今天休息' : '完成'}</Text>
          </>
        )}
      </TouchableOpacity>

      <View style={styles.secondaryRow}>
        <TouchableOpacity style={styles.secondaryBtn} onPress={onLater}>
          <Text style={[styles.secondaryText, { color: c.labelSecondary }]}>晚点</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.secondaryBtn} onPress={onSkip}>
          <Text style={[styles.secondaryText, { color: c.labelSecondary }]}>今天跳过</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ── 跳过原因选择器 ───────────────────────────────────────
export function SkipPicker({
  onPick,
  onCancel,
  styles,
  c,
}: {
  onPick: (reason: string) => void;
  onCancel: () => void;
  styles: Styles;
  c: ColorPalette;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.skipTitle}>今天跳过的原因?</Text>
      <View style={styles.skipGrid}>
        {SKIP_REASONS.map((r) => (
          <TouchableOpacity key={r} style={styles.skipChip} onPress={() => onPick(r)}>
            <Text style={[styles.skipChipText, { color: c.labelPrimary }]}>{r}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <TouchableOpacity style={styles.skipCancel} onPress={onCancel}>
        <Text style={[styles.secondaryText, { color: c.labelTertiary }]}>取消</Text>
      </TouchableOpacity>
    </View>
  );
}

// ── 未同步终态(无 complete_ref:这次没有任何记录写回后端)─────
// 不能假装成功(Rule#1):不显示「已记录」,文案诚实告知未同步 + 指出可记录的入口。
export function NotSyncedView({
  styles,
  c,
  onClose,
}: {
  styles: Styles;
  c: ColorPalette;
  onClose: () => void;
}) {
  return (
    <View style={styles.center}>
      <Ionicons name="cloud-offline-outline" size={56} color={c.labelTertiary} />
      <Text style={styles.doneTitle}>这次没同步到健康数据</Text>
      <Text style={styles.doneSub}>
        从首页的运动项进入可记录到趋势。
      </Text>
      <TouchableOpacity style={[styles.primaryBtn, styles.doneBtn, { backgroundColor: c.brand }]} onPress={onClose}>
        <Text style={styles.primaryText}>回首页</Text>
      </TouchableOpacity>
    </View>
  );
}

// ── 医疗边界常驻兜底(N1:不弹窗,小字 footer)─────────────
export function SafetyFooter({ styles, c }: { styles: Styles; c: ColorPalette }) {
  return (
    <View style={styles.safetyFooter}>
      <Ionicons name="medkit-outline" size={12} color={c.labelTertiary} />
      <Text style={styles.safetyFooterText}>
        运动中出现胸闷/头晕/异常疼痛请立即停止,必要时就医。
      </Text>
    </View>
  );
}

// ── 完成肯定反馈 ─────────────────────────────────────────
export function DoneView({
  styles,
  s,
  onClose,
}: {
  styles: Styles;
  s: SemanticPalette;
  onClose: () => void;
}) {
  return (
    <View style={styles.center}>
      <Ionicons name="checkmark-circle" size={64} color={s.success.solid} />
      <Text style={styles.doneTitle}>记下了</Text>
      <Text style={styles.doneSub}>你的坚持在累积。</Text>
      <TouchableOpacity style={[styles.primaryBtn, styles.doneBtn, { backgroundColor: s.success.solid }]} onPress={onClose}>
        <Text style={styles.primaryText}>回首页</Text>
      </TouchableOpacity>
    </View>
  );
}

export function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: c.bgPrimary } as ViewStyle,
    center: {
      flex: 1,
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.md,
      padding: spacing.xl,
    } as ViewStyle,
    scroll: { padding: spacing.md, gap: spacing.md, paddingBottom: spacing.xxl } as ViewStyle,

    header: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: spacing.md,
      paddingVertical: spacing.sm,
    } as ViewStyle,
    headerTitle: {
      ...typography.titleSmall,
      color: c.labelPrimary,
      flex: 1,
      textAlign: 'center',
    } as TextStyle,

    errText: { ...typography.bodyMedium, color: c.labelSecondary } as TextStyle,
    retryBtn: {
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.lg,
      borderRadius: radii.full,
      backgroundColor: c.brandLight,
    } as ViewStyle,
    retryText: { ...typography.bodyMedium, color: c.brand, fontWeight: '600' } as TextStyle,

    gate: { flexDirection: 'row', gap: spacing.sm, padding: spacing.md, borderRadius: radii.md } as ViewStyle,
    gateBody: { flex: 1, gap: 2 },
    gateLabel: { ...typography.titleSmall, fontWeight: '700' } as TextStyle,
    gateReason: { ...typography.bodyMedium } as TextStyle,
    gateZone: { ...typography.bodySmall, color: c.labelSecondary, marginTop: 2 } as TextStyle,

    card: { backgroundColor: c.bgCard, borderRadius: radii.md, padding: spacing.md, gap: spacing.sm } as ViewStyle,

    exHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm } as ViewStyle,
    exName: { ...typography.titleSmall, color: c.labelPrimary, flex: 1 } as TextStyle,
    mediaPlaceholder: {
      height: 120,
      borderRadius: radii.sm,
      backgroundColor: c.fill,
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.xs,
    } as ViewStyle,
    mediaHint: { ...typography.bodySmall, color: c.labelTertiary } as TextStyle,
    cueList: { gap: spacing.xs },
    cueRow: { flexDirection: 'row', gap: spacing.sm, alignItems: 'flex-start' } as ViewStyle,
    cueText: { ...typography.bodyMedium, color: c.labelPrimary, flex: 1 } as TextStyle,
    contraBox: {
      flexDirection: 'row',
      gap: spacing.sm,
      padding: spacing.sm,
      borderRadius: radii.sm,
      alignItems: 'flex-start',
    } as ViewStyle,
    contraText: { ...typography.bodySmall, fontWeight: '600' } as TextStyle,

    planRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm } as ViewStyle,
    planMain: { ...typography.titleSmall, color: c.labelPrimary, flex: 1 } as TextStyle,
    planRest: { ...typography.bodySmall, color: c.labelSecondary } as TextStyle,
    progression: { ...typography.bodySmall, color: c.brand, fontWeight: '600' } as TextStyle,

    stepHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs } as ViewStyle,
    stepLabel: { ...typography.bodySmall, color: c.labelSecondary, flex: 1 } as TextStyle,
    stepText: { ...typography.bodyLarge, color: c.labelPrimary } as TextStyle,
    stepNav: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs } as ViewStyle,
    navBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: spacing.xs,
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
      borderRadius: radii.full,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
    } as ViewStyle,
    navBtnDisabled: { opacity: 0.5 },
    navBtnPrimary: { flex: 1, justifyContent: 'center', borderWidth: 0 } as ViewStyle,
    navText: { ...typography.bodyMedium, color: c.brand, fontWeight: '600' } as TextStyle,
    navTextPrimary: { ...typography.bodyMedium, color: '#fff', fontWeight: '700' } as TextStyle,

    rpeLabel: { ...typography.bodyMedium, color: c.labelPrimary } as TextStyle,
    rpeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs } as ViewStyle,
    rpeChip: {
      width: 36,
      height: 36,
      borderRadius: radii.full,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      alignItems: 'center',
      justifyContent: 'center',
    } as ViewStyle,
    rpeChipText: { ...typography.bodyMedium, color: c.labelPrimary, fontWeight: '600' } as TextStyle,

    primaryBtn: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'center',
      gap: spacing.xs,
      paddingVertical: spacing.md,
      borderRadius: radii.full,
      marginTop: spacing.sm,
    } as ViewStyle,
    btnDisabled: { opacity: 0.6 },
    primaryText: { ...typography.bodyLarge, color: '#fff', fontWeight: '700' } as TextStyle,
    secondaryRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs } as ViewStyle,
    secondaryBtn: { flex: 1, alignItems: 'center', paddingVertical: spacing.sm } as ViewStyle,
    secondaryText: { ...typography.bodyMedium, fontWeight: '600' } as TextStyle,

    skipTitle: { ...typography.titleSmall, color: c.labelPrimary } as TextStyle,
    skipGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm } as ViewStyle,
    skipChip: {
      paddingVertical: spacing.sm,
      paddingHorizontal: spacing.md,
      borderRadius: radii.full,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: c.separator,
      backgroundColor: c.fill,
    } as ViewStyle,
    skipChipText: { ...typography.bodyMedium, fontWeight: '600' } as TextStyle,
    skipCancel: { alignItems: 'center', paddingVertical: spacing.sm, marginTop: spacing.xs } as ViewStyle,

    doneTitle: { ...typography.titleMedium, color: c.labelPrimary, textAlign: 'center' } as TextStyle,
    doneSub: { ...typography.bodyMedium, color: c.labelSecondary, textAlign: 'center' } as TextStyle,
    doneBtn: { alignSelf: 'stretch', marginTop: spacing.lg } as ViewStyle,

    safetyFooter: {
      flexDirection: 'row',
      alignItems: 'flex-start',
      gap: spacing.xs,
      paddingHorizontal: spacing.xs,
      paddingTop: spacing.xs,
    } as ViewStyle,
    safetyFooterText: {
      ...typography.caption,
      color: c.labelTertiary,
      flex: 1,
      lineHeight: 16,
    } as TextStyle,
  });
}
