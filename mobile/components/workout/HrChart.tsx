import React, { useMemo } from 'react';
import { View } from 'react-native';
import Svg, { Polyline, Rect, Text as SvgText } from 'react-native-svg';
import { revaColors as C } from '../../constants/revaTheme';
import type { HeartRatePoint } from '../../services/workouts';

interface Props {
  samples: HeartRatePoint[];
  height?: number;
  hrMax?: number | null;   // 用户 HRmax, 无则按 220-age 或 sample max 粗估
  hrRest?: number | null;  // 静息 HR
}

/**
 * 纯 SVG 心率曲线. 横轴=时间 (sec 从运动起), 纵轴=HR bpm.
 * 背景按 HR zone 染色 (Z1/Z2 绿, Z3 黄, Z4 橙, Z5 红), 曲线走 brand 深色.
 *
 * 没用 victory-native 是因为它要 native dep + bundle 大; 这里是时间序列点,
 * 自己画 Polyline + 横线 zone 已经够用.
 */
export default function HrChart({ samples, height = 120, hrMax = null, hrRest = null }: Props) {
  const prepared = useMemo(() => {
    if (!samples || samples.length < 2) return null;
    const xs = samples.map(s => s.time);
    const ys = samples.map(s => s.hr);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.max(40, Math.min(...ys) - 5);
    const maxY = Math.max(...ys) + 5;
    // fallback HRmax/HRrest if not given
    const hrmax = hrMax ?? Math.max(maxY, 180);
    const hrrest = hrRest ?? 60;
    // Karvonen zones
    const range = hrmax - hrrest;
    const zoneBounds = {
      z1: hrrest + range * 0.5,
      z2: hrrest + range * 0.6,
      z3: hrrest + range * 0.7,
      z4: hrrest + range * 0.8,
      z5: hrrest + range * 0.9,
    };
    return { samples, minX, maxX, minY, maxY, zoneBounds, hrmax };
  }, [samples, hrMax, hrRest]);

  if (!prepared) return null;

  const W = 320;
  const H = height;
  const padX = 8;
  const padT = 8;
  const padB = 20;
  const plotW = W - padX * 2;
  const plotH = H - padT - padB;

  const { minX, maxX, minY, maxY, zoneBounds } = prepared;
  const toX = (t: number) => padX + ((t - minX) / Math.max(1, maxX - minX)) * plotW;
  const toY = (hr: number) => padT + (1 - (hr - minY) / Math.max(1, maxY - minY)) * plotH;

  // zone band colors (light tints)
  const bands = [
    { from: minY, to: zoneBounds.z2, color: '#D4F4DD' }, // Z1-Z2 light green
    { from: zoneBounds.z2, to: zoneBounds.z3, color: '#C8E8FF' }, // Z2-Z3 light blue
    { from: zoneBounds.z3, to: zoneBounds.z4, color: '#FFE9B3' }, // Z3-Z4 yellow
    { from: zoneBounds.z4, to: zoneBounds.z5, color: '#FFCFA6' }, // Z4-Z5 orange
    { from: zoneBounds.z5, to: maxY, color: '#FFB5B5' }, // Z5+ red
  ];

  const pts = prepared.samples.map(s => `${toX(s.time)},${toY(s.hr)}`).join(' ');

  const fmtTime = (t: number) => {
    const m = Math.floor(t / 60);
    return `${m}′`;
  };

  return (
    <View>
      <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none">
        {bands.map((b, i) => {
          const yTop = toY(Math.min(maxY, Math.max(minY, b.to)));
          const yBot = toY(Math.min(maxY, Math.max(minY, b.from)));
          const bandH = Math.max(0, yBot - yTop);
          if (bandH <= 0) return null;
          return (
            <Rect key={i} x={padX} y={yTop} width={plotW} height={bandH} fill={b.color} opacity={0.55} />
          );
        })}
        <Polyline
          points={pts}
          fill="none"
          stroke={C.green500}
          strokeWidth={1.8}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* X-axis ticks: 0, 1/4, 2/4, 3/4, end */}
        {[0, 0.25, 0.5, 0.75, 1].map((p, i) => {
          const t = minX + (maxX - minX) * p;
          const x = toX(t);
          return (
            <SvgText key={i} x={x} y={H - 4} fontSize="9" fill={C.ink3} textAnchor="middle">
              {fmtTime(t - minX)}
            </SvgText>
          );
        })}
        {/* Y-axis max/min label */}
        <SvgText x={W - padX - 2} y={padT + 10} fontSize="9" fill={C.ink3} textAnchor="end">{Math.round(maxY)}</SvgText>
        <SvgText x={W - padX - 2} y={H - padB - 2} fontSize="9" fill={C.ink3} textAnchor="end">{Math.round(minY)}</SvgText>
      </Svg>
    </View>
  );
}
