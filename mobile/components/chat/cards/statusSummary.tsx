/**
 * StatusSummary scaffold — 汇总类卡族(饮食 / 恢复 / 睡眠 / 身体状态…)的**共享结构与原语**。
 *
 * 北极星 = DietSummaryCard 的设计语言。每张汇总卡只写自己的领域主体(如饮食的餐次×宏量表),
 * 其余「壳 + 2 行头」「关键观察(三步临床语义色)」「进度/目标条」都从这里取,视觉一字不差、
 * 不再各卡复制。防御性解析原语(pickText/pickNum/fmtNum/parseObservations/formatBeijingDate)
 * 同样共享 —— 字段缺失降级不崩、数字 ≤1 位小数(founder ≤2 位规范内)。
 *
 * 用法:
 *   <StatusSummaryShell icon="clipboard-outline" title="今日饮食汇总" subtitle="北京时间 · 7月16日">
 *     {领域主体}
 *     <StatusObservationList items={parseObservations(d.observations)} />
 *     <StatusProgressBar label="饮水进度" valueText="500/2000ml" pct={25} hint="还差约 1500ml" />
 *   </StatusSummaryShell>
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { TextStyle } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaShadows,
  revaSemantic,
  revaSpacing,
  type RevaStatus,
} from '../../../constants/revaTheme';

// ── 类型 ────────────────────────────────────────────────────────────────────
export interface StatusObservation {
  status: RevaStatus;
  label: string;
  detail?: string;
}

const OBS_STATUS: Record<string, RevaStatus> = {
  normal: 'normal', caution: 'caution', risk: 'risk', info: 'info',
};
const OBS_ICON: Record<RevaStatus, keyof typeof Ionicons.glyphMap> = {
  normal: 'checkmark-circle', caution: 'warning', risk: 'alert-circle', info: 'information-circle',
};

// ── 防御性解析原语(每张汇总卡都要,统一在此,禁止各卡复制) ──────────────────
export function pickText(v: unknown): string | undefined {
  if (typeof v === 'string') { const t = v.trim(); return t || undefined; }
  if (typeof v === 'number' && Number.isFinite(v)) return String(v);
  return undefined;
}
export function pickNum(v: unknown): number | undefined {
  if (typeof v === 'number' && Number.isFinite(v)) return v;
  if (typeof v === 'string' && v.trim()) { const n = Number(v.trim()); return Number.isFinite(n) ? n : undefined; }
  return undefined;
}
/** 展示数字:整数原样, 否则最多 1 位小数(founder ≤2 位规范内)。缺值 → null。 */
export function fmtNum(v: unknown): string | null {
  const n = pickNum(v);
  if (n == null) return null;
  return Number.isInteger(n) ? String(n) : String(Math.round(n * 10) / 10);
}
/** ISO record_date → 「M月D日」;非 ISO 原样;空 → undefined。 */
export function formatBeijingDate(raw: unknown): string | undefined {
  const s = pickText(raw);
  if (!s) return undefined;
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? `${Number(m[2])}月${Number(m[3])}日` : s;
}
/** [{severity,label,detail}] → 已归一化观察;label 缺失丢弃;未知 severity → normal。 */
export function parseObservations(raw: unknown): StatusObservation[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item): StatusObservation | null => {
      if (!item || typeof item !== 'object') return null;
      const r = item as Record<string, unknown>;
      const label = pickText(r.label);
      if (!label) return null;
      const status = OBS_STATUS[pickText(r.severity) || ''] || 'normal';
      return { status, label, detail: pickText(r.detail) };
    })
    .filter((o): o is StatusObservation => o != null);
}

// ── 组件原语 ────────────────────────────────────────────────────────────────
/** 卡壳 + 2 行头(图标 + 标题 + 可选副行)。领域主体作为 children 传入。 */
export function StatusSummaryShell({
  icon, iconColor = C.green500, title, subtitle, children,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  iconColor?: string;
  title: string;
  subtitle?: string;
  children?: React.ReactNode;
}) {
  return (
    <View style={ss.card}>
      <View style={ss.header}>
        <Ionicons name={icon} size={16} color={iconColor} />
        <View style={ss.headerText}>
          <Text maxFontSizeMultiplier={1.3} style={ss.title}>{title}</Text>
          {subtitle ? (
            <Text maxFontSizeMultiplier={1.2} style={ss.subtitle}>{subtitle}</Text>
          ) : null}
        </View>
      </View>
      {children}
    </View>
  );
}

/** 「关键观察」段:每条一行,三步临床语义色(normal/caution/risk/info)。空 → 不渲染。 */
export function StatusObservationList({
  items, label = '关键观察',
}: {
  items: StatusObservation[];
  label?: string;
}) {
  if (!items.length) return null;
  return (
    <View style={ss.obsSection}>
      <Text maxFontSizeMultiplier={1.1} style={ss.sectionLabel}>{label}</Text>
      {items.map((obs, i) => (
        <View key={i} style={ss.obsRow}>
          <Ionicons
            name={OBS_ICON[obs.status]}
            size={14}
            color={revaSemantic[obs.status].fg}
            style={ss.obsIcon}
          />
          <Text maxFontSizeMultiplier={1.2} style={ss.obsBody}>
            <Text style={[ss.obsLabel, { color: revaSemantic[obs.status].fg }]}>{obs.label}</Text>
            {obs.detail ? <Text style={ss.obsDetail}>{`  ${obs.detail}`}</Text> : null}
          </Text>
        </View>
      ))}
    </View>
  );
}

/** 进度/目标条(饮水 / 睡眠时长 / 步数…):标题 + 右侧数值 + 轨道 + 可选提示。tone 决定语义色。 */
export function StatusProgressBar({
  label, valueText, pct, hint, tone = 'info',
}: {
  label: string;
  valueText: string;
  pct: number; // 0..100
  hint?: string;
  tone?: RevaStatus;
}) {
  const sem = revaSemantic[tone];
  const clamped = Math.max(0, Math.min(100, pct));
  return (
    <View style={[ss.progressSection, { backgroundColor: sem.bg, borderColor: sem.line }]}>
      <View style={ss.progressHead}>
        <Text maxFontSizeMultiplier={1.1} style={ss.sectionLabel}>{label}</Text>
        <Text maxFontSizeMultiplier={1.1} style={[ss.progressValue, { color: sem.fg }]}>{valueText}</Text>
      </View>
      <View style={[ss.progressTrack, { backgroundColor: sem.line }]}>
        <View style={[ss.progressFill, { width: `${clamped}%`, backgroundColor: sem.fg }]} />
      </View>
      {hint ? <Text maxFontSizeMultiplier={1.1} style={ss.progressHint}>{hint}</Text> : null}
    </View>
  );
}

// ── 共享样式(= DietSummaryCard 原样抽出,视觉零变化) ─────────────────────────
export const ss = StyleSheet.create({
  card: {
    borderRadius: revaRadii.lg,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    backgroundColor: C.surface,
    paddingHorizontal: revaSpacing.s4,
    paddingVertical: revaSpacing.s3 + 2,
    marginVertical: revaSpacing.s2,
    minWidth: 240,
    ...revaShadows.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: revaSpacing.s2,
    marginBottom: revaSpacing.s3,
  },
  headerText: { flexShrink: 1, gap: 2 },
  title: {
    fontFamily: revaFonts.sans,
    fontSize: 14,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 19,
  } as TextStyle,
  subtitle: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink3,
    lineHeight: 15,
  } as TextStyle,

  obsSection: { marginTop: revaSpacing.s3, gap: 6 },
  sectionLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.3,
    color: C.ink3,
  } as TextStyle,
  obsRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 6 },
  obsIcon: { marginTop: 1 },
  obsBody: { flex: 1, lineHeight: 17 } as TextStyle,
  obsLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    fontWeight: '700',
  } as TextStyle,
  obsDetail: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink2,
  } as TextStyle,

  progressSection: {
    marginTop: revaSpacing.s3,
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 9,
    borderRadius: revaRadii.md,
    borderWidth: StyleSheet.hairlineWidth,
  },
  progressHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  progressValue: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 16,
    fontVariant: ['tabular-nums'],
  } as TextStyle,
  progressTrack: {
    height: 6,
    borderRadius: 3,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    borderRadius: 3,
  },
  progressHint: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 14,
  } as TextStyle,
});
