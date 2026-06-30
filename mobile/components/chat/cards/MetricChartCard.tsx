import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import Svg, { Circle, Line, Polyline } from 'react-native-svg';
import { CardShell } from './CardShell';
import type { CardSpec } from './types';
import {
  revaColors as C,
  revaFonts,
  revaRadii,
  revaSemantic,
} from '../../../constants/revaTheme';

interface MetricChartPoint {
  date?: unknown;
  value?: unknown;
  rolling_7d?: unknown;
  source?: unknown;
}

interface MetricChartData {
  metric?: unknown;
  title?: unknown;
  unit?: unknown;
  start_date?: unknown;
  end_date?: unknown;
  coverage?: {
    days_with_data?: unknown;
    days_in_window?: unknown;
  };
  latest?: {
    date?: unknown;
    value?: unknown;
    source?: unknown;
  };
  summary?: {
    avg?: unknown;
    last_7d_avg?: unknown;
    last_30d_avg?: unknown;
    prev_30d_avg?: unknown;
    last_30_vs_prev_30_delta?: unknown;
  };
  series?: MetricChartPoint[];
  boundary?: unknown;
}

interface RevaUiLineChartSeries {
  name?: unknown;
  role?: unknown;
  points?: unknown;
}

interface RevaUiLineChartAnnotation {
  label?: unknown;
  kind?: unknown;
}

interface RevaUiLineChartData {
  component?: unknown;
  schema?: unknown;
  metric?: unknown;
  range?: unknown;
  title?: unknown;
  unit?: unknown;
  x?: unknown;
  series?: unknown;
  annotations?: unknown;
  source?: unknown;
  data_note?: unknown;
}

interface MetricEmptyStateData {
  component?: unknown;
  schema?: unknown;
  metric?: unknown;
  range?: unknown;
  title?: unknown;
  message?: unknown;
  suggestions?: unknown;
  boundary?: unknown;
}

const CHART_W = 300;
const CHART_H = 118;
const PAD_X = 12;
const PAD_Y = 14;
const LINE_COLORS = [C.green500, C.blue500, '#6D4AAE', '#C98A1E', C.ink2];

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

function points(value: unknown): MetricChartPoint[] {
  if (!Array.isArray(value)) return [];
  return value.filter((point) => point && num((point as MetricChartPoint).value) != null);
}

function lineSeries(value: unknown): RevaUiLineChartSeries[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is RevaUiLineChartSeries => {
    if (!item || typeof item !== 'object') return false;
    const rawPoints = (item as RevaUiLineChartSeries).points;
    return Array.isArray(rawPoints) && rawPoints.some((point) => num(point) != null);
  });
}

function annotations(value: unknown): RevaUiLineChartAnnotation[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is RevaUiLineChartAnnotation => (
    !!item && typeof item === 'object' && !!text((item as RevaUiLineChartAnnotation).label)
  ));
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => text(item))
    .filter((item): item is string => !!item);
}

function formatValue(value: unknown, unit: string): string {
  const n = num(value);
  if (n == null) return '--';
  return `${n.toFixed(1)}${unit}`;
}

function formatDelta(value: unknown, unit: string): string | null {
  const n = num(value);
  if (n == null) return null;
  return `近30天 ${n > 0 ? '+' : ''}${n.toFixed(1)}${unit}`;
}

function formatCoverage(data: MetricChartData): string {
  const withData = text(data.coverage?.days_with_data) || '0';
  const total = text(data.coverage?.days_in_window) || '0';
  return `${withData}/${total} 天`;
}

function formatRange(data: MetricChartData): string {
  const start = text(data.start_date) || '--';
  const end = text(data.end_date) || '--';
  return `${start} 至 ${end}`;
}

function sourceLabel(value: unknown): string {
  const source = text(value);
  if (source === 'apple-watch') return 'Apple Watch';
  if (source === 'ringconn') return 'RingConn';
  if (source === 'garmin') return 'Garmin';
  return source || '数据源';
}

function polylineFor(values: { value: number | null }[], min: number, max: number): string {
  const range = max - min || 1;
  const innerW = CHART_W - PAD_X * 2;
  const innerH = CHART_H - PAD_Y * 2;
  const denom = Math.max(values.length - 1, 1);
  return values
    .map((point, index) => {
      if (point.value == null) return null;
      const x = PAD_X + (index / denom) * innerW;
      const y = PAD_Y + innerH - ((point.value - min) / range) * innerH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(' ');
}

function polylineForValues(values: (number | null)[], min: number, max: number): string {
  const range = max - min || 1;
  const innerW = CHART_W - PAD_X * 2;
  const innerH = CHART_H - PAD_Y * 2;
  const denom = Math.max(values.length - 1, 1);
  return values
    .map((value, index) => {
      if (value == null) return null;
      const x = PAD_X + (index / denom) * innerW;
      const y = PAD_Y + innerH - ((value - min) / range) * innerH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter(Boolean)
    .join(' ');
}

function MetricLineChart({ data }: { data: MetricChartPoint[] }) {
  const cleaned = data
    .map((point) => ({
      value: num(point.value),
      rolling: num(point.rolling_7d),
    }))
    .filter((point) => point.value != null);
  if (cleaned.length < 2) return null;
  const valueNumbers = cleaned
    .flatMap((point) => [point.value, point.rolling])
    .filter((value): value is number => value != null);
  const min = Math.min(...valueNumbers);
  const max = Math.max(...valueNumbers);
  const valueLine = polylineFor(cleaned.map((point) => ({ value: point.value })), min, max);
  const rollingLine = polylineFor(cleaned.map((point) => ({ value: point.rolling })), min, max);
  const last = cleaned[cleaned.length - 1].value;
  const lastX = PAD_X + (CHART_W - PAD_X * 2);
  const lastY = last == null
    ? null
    : PAD_Y + (CHART_H - PAD_Y * 2) - ((last - min) / (max - min || 1)) * (CHART_H - PAD_Y * 2);

  return (
    <View style={styles.chartFrame}>
      <Svg width="100%" height={CHART_H} viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
        <Line x1={PAD_X} y1={PAD_Y} x2={CHART_W - PAD_X} y2={PAD_Y} stroke={C.line} strokeWidth={1} />
        <Line x1={PAD_X} y1={CHART_H / 2} x2={CHART_W - PAD_X} y2={CHART_H / 2} stroke={C.line} strokeWidth={1} />
        <Line x1={PAD_X} y1={CHART_H - PAD_Y} x2={CHART_W - PAD_X} y2={CHART_H - PAD_Y} stroke={C.line} strokeWidth={1} />
        {valueLine ? (
          <Polyline points={valueLine} fill="none" stroke={C.green500} strokeWidth={2.1} strokeLinecap="round" strokeLinejoin="round" />
        ) : null}
        {rollingLine ? (
          <Polyline points={rollingLine} fill="none" stroke={C.focusBg} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
        ) : null}
        {lastY != null ? <Circle cx={lastX} cy={lastY} r={4} fill={C.focusBg} /> : null}
      </Svg>
      <View style={styles.legend}>
        <LegendDot color={C.green500} label="每日" />
        <LegendDot color={C.focusBg} label="7日均线" />
      </View>
    </View>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <View style={styles.legendItem}>
      <View style={[styles.legendDot, { backgroundColor: color }]} />
      <Text maxFontSizeMultiplier={1.2} style={styles.legendText}>{label}</Text>
    </View>
  );
}

function RevaUiLineChart({ data }: { data: RevaUiLineChartData }) {
  const series = lineSeries(data.series);
  const normalized = series.map((item, index) => ({
    name: text(item.name) || `序列 ${index + 1}`,
    values: Array.isArray(item.points)
      ? item.points.map((point) => num(point))
      : [],
    color: LINE_COLORS[index % LINE_COLORS.length],
  })).filter((item) => item.values.some((value) => value != null));
  const values = normalized.flatMap((item) => item.values).filter((value): value is number => value != null);
  if (normalized.length === 0 || values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);

  return (
    <View style={styles.chartFrame}>
      <Svg width="100%" height={CHART_H} viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
        <Line x1={PAD_X} y1={PAD_Y} x2={CHART_W - PAD_X} y2={PAD_Y} stroke={C.line} strokeWidth={1} />
        <Line x1={PAD_X} y1={CHART_H / 2} x2={CHART_W - PAD_X} y2={CHART_H / 2} stroke={C.line} strokeWidth={1} />
        <Line x1={PAD_X} y1={CHART_H - PAD_Y} x2={CHART_W - PAD_X} y2={CHART_H - PAD_Y} stroke={C.line} strokeWidth={1} />
        {normalized.map((item) => {
          const line = polylineForValues(item.values, min, max);
          return line ? (
            <Polyline
              key={item.name}
              points={line}
              fill="none"
              stroke={item.color}
              strokeWidth={item.name.includes('均值') ? 2.6 : 2}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ) : null;
        })}
      </Svg>
      <View style={styles.axisRow}>
        <Text maxFontSizeMultiplier={1.1} style={styles.axisText} numberOfLines={1}>
          {Array.isArray(data.x) && data.x.length > 0 ? text(data.x[0]) || '--' : '--'}
        </Text>
        <Text maxFontSizeMultiplier={1.1} style={styles.axisText} numberOfLines={1}>
          {Array.isArray(data.x) && data.x.length > 0 ? text(data.x[data.x.length - 1]) || '--' : '--'}
        </Text>
      </View>
      <View style={styles.legend}>
        {normalized.slice(0, 4).map((item) => (
          <LegendDot key={item.name} color={item.color} label={item.name} />
        ))}
      </View>
    </View>
  );
}

export function RevaUiLineChartCardView(data: RevaUiLineChartData) {
  const notes = text(data.data_note);
  const anns = annotations(data.annotations);
  return (
    <CardShell
      icon="stats-chart"
      iconColor={C.green500}
      title={text(data.title) || '指标趋势'}
      badge="真实数据"
      badgeColor={C.green500}
      bg={C.surface}
    >
      <RevaUiLineChart data={data} />
      {anns.length > 0 ? (
        <View style={styles.annotationStack}>
          {anns.slice(0, 3).map((item, index) => (
            <Text key={`${text(item.label)}-${index}`} maxFontSizeMultiplier={1.2} style={styles.annotationText}>
              {text(item.label)}
            </Text>
          ))}
        </View>
      ) : null}
      {notes ? (
        <Text maxFontSizeMultiplier={1.2} style={styles.boundary}>
          {notes}
        </Text>
      ) : null}
      <Text maxFontSizeMultiplier={1.2} style={styles.boundary}>
        趋势仅用于健康管理参考,不替代诊断或治疗。
      </Text>
    </CardShell>
  );
}

export function MetricEmptyStateCardView(data: MetricEmptyStateData) {
  const suggestions = stringList(data.suggestions).slice(0, 4);
  const boundary = text(data.boundary) || '仅用于健康管理参考,不替代诊断或治疗。';
  return (
    <CardShell
      icon="alert-circle"
      iconColor={revaSemantic.caution.fg}
      title={text(data.title) || '数据不足'}
      badge="待补齐"
      badgeColor={revaSemantic.caution.fg}
      bg={C.surface}
    >
      <Text maxFontSizeMultiplier={1.2} style={styles.emptyMessage}>
        {text(data.message) || '暂无足够数据生成趋势图。'}
      </Text>
      {suggestions.length > 0 ? (
        <View style={styles.suggestionStack}>
          {suggestions.map((item, index) => (
            <View key={`${item}-${index}`} style={styles.suggestionItem}>
              <Text maxFontSizeMultiplier={1.1} style={styles.suggestionIndex}>
                {index + 1}
              </Text>
              <Text maxFontSizeMultiplier={1.2} style={styles.suggestionText}>
                {item}
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

export function MetricChartCardView(data: MetricChartData) {
  const unit = text(data.unit) || '';
  const series = points(data.series);
  const latestValue = formatValue(data.latest?.value, unit);
  const delta = formatDelta(data.summary?.last_30_vs_prev_30_delta, unit);
  const latestSource = sourceLabel(data.latest?.source);
  const boundary = text(data.boundary) || '趋势仅用于健康管理参考,不替代诊断或治疗。';

  return (
    <CardShell
      icon="stats-chart"
      iconColor={C.green500}
      title={text(data.title) || '指标趋势'}
      badge="趋势"
      badgeColor={C.green500}
      bg={C.surface}
    >
      <View style={styles.hero}>
        <View style={styles.latestBlock}>
          <Text maxFontSizeMultiplier={1.2} style={styles.latestLabel}>最新</Text>
          <Text maxFontSizeMultiplier={1.2} style={styles.latestValue}>{latestValue}</Text>
          <Text maxFontSizeMultiplier={1.1} style={styles.latestSource} numberOfLines={1}>
            {text(data.latest?.date) || '--'} · {latestSource}
          </Text>
        </View>
        <View style={styles.summaryBlock}>
          <MetricPill label="覆盖" value={formatCoverage(data)} />
          {delta ? (
            <MetricPill
              label="趋势"
              value={delta}
              tone={(num(data.summary?.last_30_vs_prev_30_delta) ?? 0) < 0 ? 'caution' : 'normal'}
            />
          ) : null}
        </View>
      </View>

      <MetricLineChart data={series} />

      <View style={styles.metaRow}>
        <Text maxFontSizeMultiplier={1.1} style={styles.metaText} numberOfLines={1}>
          {formatRange(data)}
        </Text>
        {data.summary?.last_7d_avg != null ? (
          <Text maxFontSizeMultiplier={1.1} style={styles.metaText} numberOfLines={1}>
            7日均 {formatValue(data.summary.last_7d_avg, unit)}
          </Text>
        ) : null}
      </View>

      <Text maxFontSizeMultiplier={1.2} style={styles.boundary}>
        {boundary}
      </Text>
    </CardShell>
  );
}

function MetricPill({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  tone?: 'neutral' | 'normal' | 'caution';
}) {
  const palette = tone === 'normal'
    ? revaSemantic.normal
    : tone === 'caution'
      ? revaSemantic.caution
      : { fg: C.ink2, bg: C.paper2, line: C.line };
  return (
    <View style={[styles.metricPill, { backgroundColor: palette.bg, borderColor: palette.line }]}>
      <Text maxFontSizeMultiplier={1.1} style={styles.metricLabel}>{label}</Text>
      <Text maxFontSizeMultiplier={1.2} style={[styles.metricValue, { color: palette.fg }]} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

export const MetricChartCardSpec: CardSpec<MetricChartData> = {
  type: 'metric_chart',
  label: '指标图表',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <MetricChartCardView {...data} />,
};

export const RevaUiLineChartCardSpec: CardSpec<RevaUiLineChartData> = {
  type: 'line_chart',
  label: '趋势图表',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <RevaUiLineChartCardView {...data} />,
};

export const MetricLineChartCardSpec: CardSpec<RevaUiLineChartData> = {
  type: 'metric_line_chart',
  label: '指标趋势图表',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <RevaUiLineChartCardView {...data} />,
};

export const MetricEmptyStateCardSpec: CardSpec<MetricEmptyStateData> = {
  type: 'metric_empty_state',
  label: '指标数据不足',
  match() {
    return null;
  },
  build() {
    return null;
  },
  render: (data) => <MetricEmptyStateCardView {...data} />,
};

const styles = StyleSheet.create({
  hero: {
    flexDirection: 'row',
    gap: 10,
    alignItems: 'stretch',
  },
  latestBlock: {
    flex: 1,
    minWidth: 0,
    borderRadius: revaRadii.md,
    backgroundColor: C.green50,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.green100,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  latestLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 11,
    fontWeight: '700',
    color: C.ink3,
  } as TextStyle,
  latestValue: {
    marginTop: 2,
    fontFamily: revaFonts.mono,
    fontSize: 24,
    fontWeight: '800',
    color: C.ink1,
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  latestSource: {
    marginTop: 2,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink2,
  } as TextStyle,
  summaryBlock: {
    width: 112,
    gap: 6,
  },
  metricPill: {
    minHeight: 42,
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: 8,
    paddingVertical: 5,
    justifyContent: 'center',
  },
  metricLabel: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    fontWeight: '700',
    color: C.ink3,
  } as TextStyle,
  metricValue: {
    marginTop: 1,
    fontFamily: revaFonts.mono,
    fontSize: 12,
    fontWeight: '800',
    fontVariant: ['tabular-nums'] as const,
  } as TextStyle,
  chartFrame: {
    marginTop: 10,
    borderRadius: revaRadii.md,
    backgroundColor: C.surface2,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: C.line,
    overflow: 'hidden',
  },
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    paddingHorizontal: 10,
    paddingBottom: 8,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  legendDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  legendText: {
    fontFamily: revaFonts.sans,
    fontSize: 10,
    color: C.ink3,
  } as TextStyle,
  metaRow: {
    marginTop: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  metaText: {
    flexShrink: 1,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    color: C.ink3,
  } as TextStyle,
  boundary: {
    marginTop: 8,
    fontFamily: revaFonts.sans,
    fontSize: 11,
    lineHeight: 15,
    color: C.ink3,
  } as TextStyle,
  emptyMessage: {
    fontFamily: revaFonts.sans,
    fontSize: 13,
    lineHeight: 19,
    color: C.ink2,
  } as TextStyle,
  suggestionStack: {
    marginTop: 10,
    gap: 7,
  },
  suggestionItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: revaRadii.sm,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: revaSemantic.caution.line,
    backgroundColor: revaSemantic.caution.bg,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  suggestionIndex: {
    width: 18,
    height: 18,
    borderRadius: 9,
    overflow: 'hidden',
    backgroundColor: C.surface,
    textAlign: 'center',
    fontFamily: revaFonts.mono,
    fontSize: 11,
    lineHeight: 18,
    fontWeight: '800',
    color: revaSemantic.caution.fg,
  } as TextStyle,
  suggestionText: {
    flex: 1,
    minWidth: 0,
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: C.ink2,
  } as TextStyle,
  axisRow: {
    marginTop: -2,
    paddingHorizontal: 10,
    paddingBottom: 5,
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  axisText: {
    fontFamily: revaFonts.mono,
    fontSize: 10,
    color: C.ink3,
  } as TextStyle,
  annotationStack: {
    marginTop: 8,
    gap: 4,
  },
  annotationText: {
    fontFamily: revaFonts.sans,
    fontSize: 12,
    lineHeight: 17,
    color: C.ink2,
  } as TextStyle,
});
