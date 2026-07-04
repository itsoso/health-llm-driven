import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
} from '../../../constants/revaTheme';

interface OperatingReviewMetric {
  metric?: unknown;
  current?: unknown;
  delta?: unknown;
  current_date?: unknown;
}

interface OperatingReviewResult {
  prediction_id?: unknown;
  action_title?: unknown;
  metric?: unknown;
  horizon_days?: unknown;
  observed_delta?: unknown;
  verdict?: unknown;
  confidence_after?: unknown;
}

interface OperatingReviewData {
  window_days?: unknown;
  start_date?: unknown;
  end_date?: unknown;
  execution?: {
    total_events?: unknown;
    completed_events?: unknown;
    completion_rate?: unknown;
  };
  metrics?: OperatingReviewMetric[];
  prediction_backtest?: {
    status?: unknown;
    ready_candidate_count?: unknown;
    candidate_count?: unknown;
    summary?: { met?: unknown; not_met?: unknown; inconclusive?: unknown };
    results?: OperatingReviewResult[];
    boundary?: unknown;
  };
  causal_memory?: {
    notes?: { text?: unknown }[];
    claim_boundary?: unknown;
  };
}

const METRIC_LABELS: Record<string, string> = {
  weight: '体重',
  waist_cm: '腰围',
  systolic_bp: '收缩压',
  diastolic_bp: '舒张压',
  sleep_score: '睡眠评分',
  hrv: 'HRV',
};

function text(value: unknown): string | undefined {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed || undefined;
  }
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
}

function num(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value);
  return null;
}

function pct(value: unknown): string {
  const n = num(value);
  if (n == null) return '0%';
  return `${Math.round(n * 100)}%`;
}

function metricLabel(metric: unknown): string {
  const key = text(metric) || '';
  return METRIC_LABELS[key] || key || '指标';
}

function signed(value: unknown): string | null {
  const n = num(value);
  if (n == null) return null;
  return `${n > 0 ? '+' : ''}${n}`;
}

function verdictLabel(value: unknown): string {
  const v = text(value);
  if (v === 'met') return '支持';
  if (v === 'not_met') return '未支持';
  return '数据不足';
}

function predictionSummary(data: OperatingReviewData): string {
  const backtest = data.prediction_backtest;
  const ready = num(backtest?.ready_candidate_count) ?? 0;
  const met = num(backtest?.summary?.met) ?? 0;
  if (text(backtest?.status) === 'ready' && ready > 0) {
    return `预测回测: ${met}/${ready} 支持`;
  }
  return '预测回测: 数据积累中';
}

export function OperatingReviewCardView(data: OperatingReviewData) {
  const windowDays = text(data.window_days) || '7';
  const completionRate = pct(data.execution?.completion_rate);
  const completed = text(data.execution?.completed_events) || '0';
  const total = text(data.execution?.total_events) || '0';
  const totalActions = num(data.execution?.total_events) ?? 0;
  const hasActions = totalActions > 0;
  const metrics = Array.isArray(data.metrics) ? data.metrics.slice(0, 3) : [];
  const results = Array.isArray(data.prediction_backtest?.results)
    ? data.prediction_backtest.results.slice(0, 2)
    : [];
  const boundary = text(data.prediction_backtest?.boundary)
    || text(data.causal_memory?.claim_boundary)
    || '观察性复盘,不证明单个行动造成指标变化。';

  return (
    <CardShell
      icon="analytics-outline"
      iconColor={C.green700}
      title={`${windowDays}天复盘`}
      badge="复盘"
      badgeColor={C.green500}
      bg={C.green50}
    >
      {hasActions ? (
        <View style={styles.hero}>
          <View style={styles.rate}>
            <Text maxFontSizeMultiplier={1.2} style={styles.rateText}>{completionRate}</Text>
            <Text maxFontSizeMultiplier={1.2} style={styles.rateLabel}>完成率</Text>
          </View>
          <View style={styles.heroText}>
            <Text maxFontSizeMultiplier={1.3} style={styles.summary} numberOfLines={2}>
              完成率 {completionRate}
            </Text>
            <Text maxFontSizeMultiplier={1.2} style={styles.meta} numberOfLines={1}>
              {completed}/{total} 个行动 · {text(data.start_date) || '--'} 至 {text(data.end_date) || '--'}
            </Text>
          </View>
        </View>
      ) : (
        <View style={styles.accumulating}>
          <Text maxFontSizeMultiplier={1.3} style={styles.accumulatingTitle} numberOfLines={2}>
            行动数据积累中
          </Text>
          <Text maxFontSizeMultiplier={1.2} style={styles.accumulatingBody} numberOfLines={2}>
            首个 {windowDays} 天复盘将在有行动记录后生成
          </Text>
        </View>
      )}

      <Text maxFontSizeMultiplier={1.2} style={styles.predictionTitle}>
        {predictionSummary(data)}
      </Text>

      {results.length > 0 ? (
        <View style={styles.results}>
          {results.map((result, index) => (
            <View key={text(result.prediction_id) || String(index)} style={styles.resultRow}>
              <Ionicons name="git-compare-outline" size={12} color={C.green700} />
              <Text maxFontSizeMultiplier={1.2} style={styles.resultText} numberOfLines={2}>
                {text(result.action_title) || '预测记录'} · {metricLabel(result.metric)} · {verdictLabel(result.verdict)}
                {signed(result.observed_delta) ? ` · ${signed(result.observed_delta)}` : ''}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      {metrics.length > 0 ? (
        <View style={styles.metrics}>
          {metrics.map((metric, index) => (
            <View key={`${text(metric.metric) || 'metric'}-${index}`} style={styles.metricChip}>
              <Text maxFontSizeMultiplier={1.2} style={styles.metricText} numberOfLines={1}>
                {metricLabel(metric.metric)}
                {signed(metric.delta) ? ` ${signed(metric.delta)}` : ''}
              </Text>
            </View>
          ))}
        </View>
      ) : null}

      <Text maxFontSizeMultiplier={1.2} style={styles.boundary}>
        {boundary}
      </Text>
    </CardShell>
  );
}

export const OperatingReviewCardSpec: CardSpec<OperatingReviewData> = {
  type: 'operating_review',
  label: '健康复盘',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <OperatingReviewCardView {...data} />,
};

const styles = StyleSheet.create({
  hero: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  rate: {
    width: 56,
    height: 56,
    borderRadius: revaRadii.lg,
    backgroundColor: C.surface,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
  },
  rateText: {
    fontFamily: revaFonts.mono,
    fontSize: 16,
    fontWeight: '800',
    color: C.green700,
  } as TextStyle,
  rateLabel: {
    marginTop: 2,
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
  } as TextStyle,
  heroText: { flex: 1, minWidth: 0 },
  summary: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 20,
  } as TextStyle,
  meta: {
    marginTop: 3,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink3,
  } as TextStyle,
  accumulating: {
    paddingVertical: 2,
  },
  accumulatingTitle: {
    fontFamily: revaFonts.sans,
    fontSize: 15,
    fontWeight: '800',
    color: C.ink1,
    lineHeight: 20,
  } as TextStyle,
  accumulatingBody: {
    marginTop: 4,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    color: C.ink3,
    lineHeight: 17,
  } as TextStyle,
  predictionTitle: {
    marginTop: 10,
    fontFamily: revaFonts.sans,
    fontSize: 13,
    fontWeight: '800',
    color: C.ink1,
  } as TextStyle,
  results: { marginTop: 7, gap: 5 },
  resultRow: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'flex-start',
  },
  resultText: {
    flex: 1,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: C.ink2,
  } as TextStyle,
  metrics: {
    marginTop: 8,
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  metricChip: {
    borderRadius: revaRadii.pill,
    backgroundColor: C.surface,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  metricText: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '700',
    color: C.ink2,
  } as TextStyle,
  boundary: {
    marginTop: 9,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 15,
    color: C.ink3,
  } as TextStyle,
});
