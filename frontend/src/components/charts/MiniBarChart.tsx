'use client';

export default function MiniBarChart({ data, color = '#22c55e', w = 150, h = 40 }: { data: { label: string; value: number }[]; color?: string; w?: number; h?: number }) {
  const max = Math.max(...data.map(d => d.value)) || 1;
  const bw = w / data.length - 4;
  return (
    <svg width={w} height={h + 14}>
      {data.map((d, i) => {
        const bh = d.value > 0 ? Math.max((d.value / max) * h, 3) : 3;
        return (
          <g key={i}>
            <rect x={i * (bw + 4)} y={h - bh} width={bw} height={bh} rx={3}
              fill={d.value > 0 ? color : '#e5e7eb'} opacity={d.value > 0 ? 1 : 0.4} />
            <text x={i * (bw + 4) + bw / 2} y={h + 11} textAnchor="middle" fontSize="9" fill="#9ca3af">{d.label}</text>
          </g>
        );
      })}
    </svg>
  );
}
