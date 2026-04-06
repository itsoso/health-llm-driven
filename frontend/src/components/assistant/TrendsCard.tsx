'use client';
import Sparkline from '@/components/charts/Sparkline';

interface TrendsCardProps {
  garminHistory: any[];
}

export default function TrendsCard({ garminHistory }: TrendsCardProps) {
  const last7 = garminHistory.slice(-7);
  const prev7 = garminHistory.slice(-14, -7);

  if (last7.length < 4) return null;

  const avg = (arr: number[]) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
  const pctChange = (cur: number, prev: number) => prev > 0 ? ((cur - prev) / prev * 100).toFixed(1) : '0';

  const hrValues = last7.map((r: any) => r.resting_heart_rate || r.avg_heart_rate).filter(Boolean);
  const hrvValues = last7.map((r: any) => r.hrv).filter(Boolean);
  const stressValues = last7.map((r: any) => r.stress_level).filter(Boolean);

  const hrAvg = Math.round(avg(hrValues));
  const hrvAvg = Math.round(avg(hrvValues));
  const stressAvg = Math.round(avg(stressValues));
  const stepsAvg = Math.round(avg(last7.map((r: any) => r.steps || 0)));

  const prevHrAvg = Math.round(avg(prev7.map((r: any) => r.resting_heart_rate || r.avg_heart_rate).filter(Boolean)));
  const prevHrvAvg = Math.round(avg(prev7.map((r: any) => r.hrv).filter(Boolean)));
  const prevStressAvg = Math.round(avg(prev7.map((r: any) => r.stress_level).filter(Boolean)));
  const prevStepsAvg = Math.round(avg(prev7.map((r: any) => r.steps || 0)));

  const trends = [
    { label: '心率', data: hrValues, avg: hrAvg, prevAvg: prevHrAvg, color: '#ef4444', goodDown: true },
    { label: 'HRV', data: hrvValues, avg: hrvAvg, prevAvg: prevHrvAvg, color: '#8b5cf6', goodDown: false },
    { label: '压力', data: stressValues, avg: stressAvg, prevAvg: prevStressAvg, color: '#f59e0b', goodDown: true },
    { label: '步数', data: last7.map((r: any) => r.steps || 0), avg: stepsAvg, prevAvg: prevStepsAvg, color: '#6366f1', goodDown: false },
  ];

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-3">
      <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">7日趋势</span>
      <div className="grid grid-cols-4 gap-2 mt-2">
        {trends.map(t => {
          const change = Number(pctChange(t.avg, t.prevAvg));
          const isGood = t.goodDown ? change <= 0 : change >= 0;
          return (
            <div key={t.label} className="text-center">
              <div className="flex items-center justify-center gap-1 mb-0.5">
                <span className="text-[10px] text-gray-500">{t.label}</span>
                <span className={`text-[9px] font-semibold ${isGood ? 'text-green-500' : 'text-red-400'}`}>{change >= 0 ? '+' : ''}{change}%</span>
              </div>
              <div className="text-base font-bold text-gray-800">{t.avg || '--'}</div>
              <Sparkline data={t.data} color={t.color} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
