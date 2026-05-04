import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TextStyle } from 'react-native';
import Svg, { Rect, Text as SvgText } from 'react-native-svg';
import { ColorPalette, useTheme } from '../../hooks/useTheme';
import type { PacePoint } from '../../services/workouts';

interface Props {
  paceTimeline: PacePoint[];        // time (sec), pace (sec/km)
  totalDistanceKm: number | null;
  durationSec: number | null;
  height?: number;
}

/**
 * 按公里分段的配速柱状图. 横轴=公里编号, 纵轴=配速 (越快柱越短...不对, 越快 = pace 值越小).
 *
 * 读 pace_timeline (按 Garmin 时序给的 每点即时配速 sec/km),
 * 根据点间距估算每公里时间: 若有 elevation/distance 就按距离切, 否则按总距离均匀切.
 *
 * 简化版: 按时间均匀把 pace 切 N 段, N = round(totalDistance).
 */
export default function PaceBars({ paceTimeline, totalDistanceKm, durationSec, height = 100 }: Props) {
  const { c } = useTheme();
  const styles = useMemo(() => createStyles(c), [c]);

  const bars = useMemo(() => {
    if (!paceTimeline || paceTimeline.length < 2 || !totalDistanceKm || !durationSec) return null;
    const nBars = Math.max(1, Math.min(30, Math.round(totalDistanceKm)));
    if (nBars < 1) return null;

    // 简化: 按时间均等切, 每段平均 pace
    const segDurSec = durationSec / nBars;
    const segments: { km: number; pace: number }[] = [];
    for (let i = 0; i < nBars; i++) {
      const segStart = i * segDurSec;
      const segEnd = (i + 1) * segDurSec;
      const inRange = paceTimeline.filter(p => p.time >= segStart && p.time < segEnd);
      if (inRange.length === 0) continue;
      const avg = inRange.reduce((s, p) => s + p.pace, 0) / inRange.length;
      segments.push({ km: i + 1, pace: avg });
    }
    if (segments.length === 0) return null;

    const minPace = Math.min(...segments.map(s => s.pace));
    const maxPace = Math.max(...segments.map(s => s.pace));
    return { segments, minPace, maxPace };
  }, [paceTimeline, totalDistanceKm, durationSec]);

  if (!bars) return null;

  const W = 320;
  const H = height;
  const padX = 8;
  const padT = 8;
  const padB = 18;
  const plotW = W - padX * 2;
  const plotH = H - padT - padB;

  const { segments, minPace, maxPace } = bars;
  const gap = 3;
  const barW = Math.max(2, (plotW - gap * (segments.length - 1)) / segments.length);
  const range = Math.max(10, maxPace - minPace); // at least 10s span

  // 快 (小 pace 值) 用绿, 慢 (大 pace 值) 用橙
  const barColor = (pace: number) => {
    const ratio = (pace - minPace) / range;
    if (ratio < 0.33) return '#4CAF50';
    if (ratio < 0.66) return '#FFB84D';
    return '#FF7043';
  };

  const fmtPace = (p: number) => {
    const m = Math.floor(p / 60);
    const s = Math.round(p % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  return (
    <View>
      <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {segments.map((seg, i) => {
          const x = padX + i * (barW + gap);
          const h = ((seg.pace - minPace) / range) * plotH * 0.85 + plotH * 0.15;
          const y = padT + plotH - h;
          return (
            <Rect
              key={i}
              x={x}
              y={y}
              width={barW}
              height={h}
              rx={2}
              fill={barColor(seg.pace)}
            />
          );
        })}
        {/* Y labels */}
        <SvgText x={W - padX} y={padT + 8} fontSize="9" fill={c.labelTertiary} textAnchor="end">{fmtPace(maxPace)}</SvgText>
        <SvgText x={W - padX} y={padT + plotH - 2} fontSize="9" fill={c.labelTertiary} textAnchor="end">{fmtPace(minPace)}</SvgText>
      </Svg>
      <View style={styles.caption}>
        <Text style={styles.captionText}>{segments.length} km · 最快 {fmtPace(minPace)} · 最慢 {fmtPace(maxPace)}</Text>
      </View>
    </View>
  );
}

function createStyles(c: ColorPalette) {
  return StyleSheet.create({
    caption: { marginTop: 4, alignItems: 'center' },
    captionText: {
      fontSize: 11,
      color: c.labelTertiary,
      fontVariant: ['tabular-nums'] as const,
    } as TextStyle,
  });
}
