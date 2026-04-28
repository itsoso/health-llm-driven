import React, { useMemo, useState } from 'react';
import { View, Text, StyleSheet, Dimensions, TouchableOpacity, LayoutChangeEvent } from 'react-native';
import Svg, { Line, Circle, Polyline, Rect, G, Text as SvgText } from 'react-native-svg';
import { colors, spacing, typography } from '../../constants/theme';
import type { TrendSeries } from '../../services/trends';
import DataPointTooltip from './DataPointTooltip';

interface Props {
  series: TrendSeries[];
  height?: number;
}

const PADDING = { top: 20, right: 16, bottom: 32, left: 44 };
const Y_TICK_COUNT = 5;

interface TooltipInfo {
  date: string;
  value: number;
  unit: string;
  label: string;
  color: string;
  isAbnormal?: boolean;
  x: number;
  y: number;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function niceStep(range: number, count: number): number {
  const rough = range / count;
  const mag = Math.pow(10, Math.floor(Math.log10(rough)));
  const norm = rough / mag;
  let step: number;
  if (norm <= 1) step = 1;
  else if (norm <= 2) step = 2;
  else if (norm <= 5) step = 5;
  else step = 10;
  return step * mag;
}

export default function TrendChart({ series, height = 220 }: Props) {
  const [chartWidth, setChartWidth] = useState(Dimensions.get('window').width - 32);
  const [tooltip, setTooltip] = useState<TooltipInfo | null>(null);

  const onLayout = (e: LayoutChangeEvent) => {
    setChartWidth(e.nativeEvent.layout.width);
  };

  const plotW = chartWidth - PADDING.left - PADDING.right;
  const plotH = height - PADDING.top - PADDING.bottom;

  const allPoints = useMemo(
    () => series.flatMap((s) => s.data.map((d) => d.value)),
    [series],
  );

  const hasData = allPoints.length > 0;

  const { yMin, yMax, yTicks } = useMemo(() => {
    if (!hasData) return { yMin: 0, yMax: 100, yTicks: [0, 25, 50, 75, 100] };

    let lo = Math.min(...allPoints);
    let hi = Math.max(...allPoints);

    series.forEach((s) => {
      if (s.referenceRange) {
        lo = Math.min(lo, s.referenceRange.low);
        hi = Math.max(hi, s.referenceRange.high);
      }
    });

    const range = hi - lo || 1;
    const margin = range * 0.1;
    lo = Math.max(0, lo - margin);
    hi = hi + margin;

    const step = niceStep(hi - lo, Y_TICK_COUNT);
    const niceLo = Math.floor(lo / step) * step;
    const niceHi = Math.ceil(hi / step) * step;

    const ticks: number[] = [];
    for (let v = niceLo; v <= niceHi; v += step) {
      ticks.push(Math.round(v * 100) / 100);
    }

    return { yMin: niceLo, yMax: niceHi, yTicks: ticks };
  }, [allPoints, series, hasData]);

  const allDates = useMemo(() => {
    const set = new Set<string>();
    series.forEach((s) => s.data.forEach((d) => set.add(d.date)));
    return [...set].sort();
  }, [series]);

  const scaleX = (date: string) => {
    if (allDates.length <= 1) return PADDING.left + plotW / 2;
    const i = allDates.indexOf(date);
    return PADDING.left + (i / (allDates.length - 1)) * plotW;
  };

  const scaleY = (val: number) => {
    const range = yMax - yMin || 1;
    return PADDING.top + plotH - ((val - yMin) / range) * plotH;
  };

  const xLabels = useMemo(() => {
    if (allDates.length <= 6) return allDates;
    const step = Math.ceil(allDates.length / 6);
    return allDates.filter((_, i) => i % step === 0 || i === allDates.length - 1);
  }, [allDates]);

  const handlePointPress = (
    s: TrendSeries,
    d: { date: string; value: number; unit: string; isAbnormal?: boolean },
  ) => {
    setTooltip({
      date: d.date,
      value: d.value,
      unit: d.unit,
      label: s.label,
      color: s.color,
      isAbnormal: d.isAbnormal,
      x: scaleX(d.date),
      y: scaleY(d.value),
    });
  };

  if (!hasData) {
    return (
      <View style={[styles.container, { height }]} onLayout={onLayout}>
        <Text style={styles.emptyText}>暂无数据</Text>
      </View>
    );
  }

  return (
    <View style={styles.container} onLayout={onLayout}>
      <Svg width={chartWidth} height={height}>
        {/* grid lines */}
        {yTicks.map((tick) => (
          <Line
            key={tick}
            x1={PADDING.left}
            y1={scaleY(tick)}
            x2={chartWidth - PADDING.right}
            y2={scaleY(tick)}
            stroke={colors.separator}
            strokeWidth={1}
          />
        ))}

        {/* Y axis labels */}
        {yTicks.map((tick) => (
          <SvgText
            key={`yl-${tick}`}
            x={PADDING.left - 6}
            y={scaleY(tick) + 4}
            textAnchor="end"
            fontSize={10}
            fill={colors.labelTertiary}
          >
            {Number.isInteger(tick) ? tick : tick.toFixed(1)}
          </SvgText>
        ))}

        {/* X axis labels */}
        {xLabels.map((date) => (
          <SvgText
            key={`xl-${date}`}
            x={scaleX(date)}
            y={height - 6}
            textAnchor="middle"
            fontSize={10}
            fill={colors.labelTertiary}
          >
            {formatDate(date)}
          </SvgText>
        ))}

        {/* reference range bands */}
        {series.map(
          (s) =>
            s.referenceRange && (
              <Rect
                key={`ref-${s.label}`}
                x={PADDING.left}
                y={scaleY(s.referenceRange.high)}
                width={plotW}
                height={scaleY(s.referenceRange.low) - scaleY(s.referenceRange.high)}
                fill={s.color}
                opacity={0.08}
              />
            ),
        )}

        {/* line series */}
        {series.map((s) => {
          if (s.data.length === 0) return null;
          const points = s.data.map((d) => `${scaleX(d.date)},${scaleY(d.value)}`).join(' ');
          return (
            <G key={s.label}>
              <Polyline
                points={points}
                fill="none"
                stroke={s.color}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {s.data.map((d, i) => (
                <Circle
                  key={i}
                  cx={scaleX(d.date)}
                  cy={scaleY(d.value)}
                  r={4}
                  fill={d.isAbnormal ? colors.red : s.color}
                  stroke={colors.bgCard}
                  strokeWidth={2}
                />
              ))}
            </G>
          );
        })}
      </Svg>

      {/* touchable overlay for data points */}
      {series.map((s) =>
        s.data.map((d, i) => (
          <TouchableOpacity
            key={`${s.label}-${i}`}
            testID={`point-${s.label}-${i}`}
            style={{
              position: 'absolute',
              left: scaleX(d.date) - 12,
              top: scaleY(d.value) - 12,
              width: 24,
              height: 24,
            }}
            onPress={() => handlePointPress(s, d)}
            activeOpacity={0.7}
          />
        )),
      )}

      {/* tooltip */}
      {tooltip && (
        <DataPointTooltip {...tooltip} chartWidth={chartWidth} />
      )}

      {/* legend */}
      {series.length > 1 && (
        <View style={styles.legend}>
          {series.map((s) => (
            <View key={s.label} style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: s.color }]} />
              <Text style={styles.legendText}>{s.label}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'relative',
  },
  emptyText: {
    ...typography.bodyMedium,
    color: colors.labelTertiary,
    textAlign: 'center',
    marginTop: 80,
  },
  legend: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: spacing.lg,
    marginTop: spacing.sm,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  legendDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  legendText: {
    ...typography.caption,
    color: colors.labelSecondary,
  },
});
