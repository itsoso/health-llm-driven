'use client';
import { useState, useEffect } from 'react';

export default function AnimatedRing({ score, size = 130, strokeWidth = 10 }: { score: number; size?: number; strokeWidth?: number }) {
  const [offset, setOffset] = useState(0);
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const target = c - (score / 100) * c;
  useEffect(() => { setOffset(c); const t = setTimeout(() => setOffset(target), 80); return () => clearTimeout(t); }, [score, c, target]);
  const color = score >= 80 ? '#22c55e' : score >= 60 ? '#f59e0b' : '#ef4444';
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#dcfce7" strokeWidth={strokeWidth} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
        strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
        style={{ transition: 'stroke-dashoffset 1.5s cubic-bezier(0.4,0,0.2,1)' }} />
    </svg>
  );
}
