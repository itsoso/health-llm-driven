'use client';

export default function SleepStageBar({ deep, rem, light }: { deep: number; rem: number; light: number }) {
  const t = deep + rem + light;
  if (t <= 0) return null;
  return (
    <div style={{ display: 'flex', height: 10, borderRadius: 8, overflow: 'hidden', background: '#f3f4f6' }}>
      <div style={{ width: `${(deep / t) * 100}%`, background: '#065f46', transition: 'width 1s' }} />
      <div style={{ width: `${(rem / t) * 100}%`, background: '#22c55e', transition: 'width 1s' }} />
      <div style={{ width: `${(light / t) * 100}%`, background: '#bbf7d0', transition: 'width 1s' }} />
    </div>
  );
}
