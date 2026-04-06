'use client';

export default function Sparkline({ data, color = '#22c55e', w = 130, h = 36 }: { data: number[]; color?: string; w?: number; h?: number }) {
  if (!data.length) return null;
  const max = Math.max(...data), min = Math.min(...data), range = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 4) - 2}`).join(' ');
  const gid = 'g' + color.replace('#', '');
  return (
    <svg width={w} height={h} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.15" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon fill={`url(#${gid})`} points={`0,${h} ${pts} ${w},${h}`} />
      <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={pts} />
    </svg>
  );
}
