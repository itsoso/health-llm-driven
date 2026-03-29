'use client';

import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  BarChart, Bar, Legend,
} from 'recharts';

interface TypeDistributionItem {
  name: string;
  count: number;
  duration: number;
  color: string;
}

interface WorkoutTypeDistributionProps {
  typeDistribution: TypeDistributionItem[];
}

export default function WorkoutTypeDistribution({ typeDistribution }: WorkoutTypeDistributionProps) {
  if (typeDistribution.length === 0) return null;

  return (
    <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
      <h3 className="text-lg font-bold text-white mb-4">🏃 运动类型分布</h3>
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={typeDistribution} layout="vertical" margin={{ left: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
            <XAxis type="number" stroke="#9ca3af" />
            <YAxis type="category" dataKey="name" stroke="#9ca3af" width={90} tick={{ fontSize: 12 }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff' }}
              formatter={(v: number, name: string) => [
                name === '次数' ? `${v} 次` : `${Math.floor(v / 60)}小时${v % 60}分钟`,
                name === '次数' ? '训练次数' : '总时长'
              ]}
            />
            <Legend wrapperStyle={{ color: '#9ca3af' }} />
            <Bar dataKey="count" fill="#3b82f6" name="次数" radius={[0, 4, 4, 0]} />
            <Bar dataKey="duration" fill="#10b981" name="时长(分)" radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* Detail Table */}
      <div className="mt-4 grid grid-cols-2 md:grid-cols-3 gap-3">
        {typeDistribution.map((item) => (
          <div key={item.name} className="bg-slate-700/50 rounded-lg p-3 flex items-center gap-3">
            <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
            <div className="flex-1 min-w-0">
              <div className="text-white text-sm font-medium truncate">{item.name}</div>
              <div className="text-gray-400 text-xs">
                {item.count}次 · {Math.floor(item.duration / 60)}h{item.duration % 60}m
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
