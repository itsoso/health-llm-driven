/**
 * SleepSummaryCard — 「睡眠概览」结构化卡(汇总卡族第二张,复元 Reva 设计语言)。
 *
 * 后端经 ```reva-ui fence 内联下发(与 diet/metric_table 同通道):
 *   {"type":"sleep_summary","v":1,"data":{...}}
 * → ChatBubble extractRevaUiBlocks(utils/revaUiBlocks.ts 有 sleep 分支)→ renderCard → 本卡。
 * **v 是整数 1**,parser 校验 v===1(diet 上线即坏的教训)。
 *
 * 结构:壳/头、关键观察、睡眠时长进度条走 **StatusSummary scaffold**(statusSummary.tsx);
 * 本卡只保留领域主体 —— 逐夜(日期×评分/时长/深睡)表 + 近期均值行。视觉与 diet 卡同语言。
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import type { TextStyle } from 'react-native';
import { revaColors as C, revaFonts } from '../../../constants/revaTheme';
import type { CardSpec } from './types';
import {
  StatusSummaryShell,
  StatusObservationList,
  StatusProgressBar,
  parseObservations,
  fmtNum,
  pickText,
  pickNum,
} from './statusSummary';

// 表列顺序 = 契约字段 → 表头。评分为设备分, 时长为 h, 深睡为分钟(见 unitLegend)。
const NIGHT_COLS = ['score', 'duration_h', 'deep_min'] as const;
const NIGHT_HEADERS = ['评分', '时长', '深睡'] as const;

interface Night {
  date: string;
  values: (string | null)[]; // 3 列: 评分 / 时长(h) / 深睡(min), null → '—'
}

/** ISO/YYYY-MM-DD → 「MM-DD」;其它原样;空 → '—'。 */
function fmtNightDate(raw: unknown): string {
  const s = pickText(raw);
  if (!s) return '—';
  const m = /^\d{4}-(\d{2})-(\d{2})/.exec(s);
  return m ? `${m[1]}-${m[2]}` : s;
}

function nightCells(source: Record<string, unknown>): (string | null)[] {
  return [
    fmtNum(source.score),
    fmtNum(source.duration_h),
    fmtNum(source.deep_min),
  ];
}

function parseNights(raw: unknown): Night[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item): Night | null => {
      if (!item || typeof item !== 'object') return null;
      const r = item as Record<string, unknown>;
      return { date: fmtNightDate(r.date), values: nightCells(r) };
    })
    .filter((n): n is Night => n != null);
}

export function SleepSummaryCardView({ data }: { data?: unknown }) {
  const d = (data && typeof data === 'object') ? (data as Record<string, any>) : {};
  const rangeLabel = pickText(d.range_label);
  const nights = parseNights(d.nights);
  const avg = (d.averages && typeof d.averages === 'object') ? (d.averages as Record<string, unknown>) : {};
  const avgCells = nightCells(avg);
  const hasAvg = avgCells.some((v) => v != null);
  const observations = parseObservations(d.observations);

  const durCurrent = pickNum(d.duration?.current_h);
  const durTarget = pickNum(d.duration?.target_h);
  const showDuration = durCurrent != null && durTarget != null && durTarget > 0;
  const durPct = showDuration ? (durCurrent! / durTarget!) * 100 : 0;
  const durRemaining = showDuration ? Math.round((durTarget! - durCurrent!) * 10) / 10 : 0;

  return (
    <StatusSummaryShell
      icon="moon"
      title="睡眠概览"
      subtitle={rangeLabel ? `北京时间 · ${rangeLabel}` : undefined}
    >
      {nights.length > 0 || hasAvg ? (
        <View style={styles.table}>
          <View style={[styles.row, styles.headRow]}>
            <View style={styles.dateCol} />
            {NIGHT_HEADERS.map((h) => (
              <Text key={h} maxFontSizeMultiplier={1.1} style={[styles.headCell, styles.numCol]}>{h}</Text>
            ))}
          </View>

          {nights.map((n, i) => (
            <View key={i} style={[styles.row, styles.nightRow, i < nights.length - 1 ? styles.rowDivider : null]}>
              <Text maxFontSizeMultiplier={1.2} style={[styles.dateCell, styles.dateCol]}>{n.date}</Text>
              {n.values.map((v, ci) => (
                <Text key={ci} maxFontSizeMultiplier={1.2} style={[styles.valueCell, styles.numCol]}>{v ?? '—'}</Text>
              ))}
            </View>
          ))}

          {hasAvg ? (
            <View style={[styles.row, styles.totalRow]}>
              <Text maxFontSizeMultiplier={1.2} style={[styles.totalLabel, styles.dateCol]}>近期平均</Text>
              {avgCells.map((v, ci) => (
                <Text key={ci} maxFontSizeMultiplier={1.2} style={[styles.totalCell, styles.numCol]}>{v ?? '—'}</Text>
              ))}
            </View>
          ) : null}

          <Text maxFontSizeMultiplier={1.1} style={styles.unitLegend}>评分 设备分 · 时长 h · 深睡 分钟</Text>
        </View>
      ) : null}

      <StatusObservationList items={observations} />

      {showDuration ? (
        <StatusProgressBar
          label="平均睡眠时长"
          valueText={`${durCurrent}/${durTarget}h`}
          pct={durPct}
          hint={durRemaining > 0 ? `距 ${durTarget}h 目标还差约 ${durRemaining}h` : undefined}
          tone="info"
        />
      ) : null}
    </StatusSummaryShell>
  );
}

export const SleepSummaryCardSpec: CardSpec = {
  type: 'sleep_summary',
  label: '睡眠概览',
  match() {
    return null; // 仅接受后端下发 (reva-ui fence), 不本地关键词触发
  },
  build() {
    return null;
  },
  render: (data) => <SleepSummaryCardView data={data} />,
};

// 领域专属样式:逐夜表(壳/头/观察/进度条样式在 statusSummary.tsx)。
const styles = StyleSheet.create({
  table: {
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.line,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  headRow: { paddingTop: 8, paddingBottom: 5 },
  nightRow: { paddingVertical: 8 },
  rowDivider: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: C.line },
  dateCol: { flex: 1.4 },
  numCol: { flex: 1, textAlign: 'right' },
  dateCell: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    color: C.ink1,
    fontVariant: ['tabular-nums'],
  } as TextStyle,
  headCell: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '600',
    letterSpacing: 0.3,
    color: C.ink3,
  } as TextStyle,
  valueCell: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '500',
    color: C.ink1,
    lineHeight: 17,
    fontVariant: ['tabular-nums'],
  } as TextStyle,
  totalRow: {
    paddingTop: 9,
    paddingBottom: 2,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: C.lineStrong,
  },
  totalLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  totalCell: {
    fontFamily: revaFonts.mono,
    fontSize: 13,
    fontWeight: '700',
    color: C.ink1,
    fontVariant: ['tabular-nums'],
  } as TextStyle,
  unitLegend: {
    marginTop: 7,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
    lineHeight: 14,
  } as TextStyle,
});
