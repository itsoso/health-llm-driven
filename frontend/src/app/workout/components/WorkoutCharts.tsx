'use client';

import { UseMutationResult } from '@tanstack/react-query';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  AreaChart, Area, BarChart, Bar,
} from 'recharts';
import dynamic from 'next/dynamic';
import { formatPace, formatDistance } from './workoutUtils';
import { WorkoutDetail } from './workoutTypes';

const WorkoutMap = dynamic(() => import('@/components/WorkoutMap'), {
  ssr: false,
  loading: () => (
    <div className="h-[400px] w-full flex items-center justify-center bg-slate-700/50 rounded-lg">
      <div className="text-gray-400">加载地图中...</div>
    </div>
  ),
});

interface WorkoutChartsProps {
  workoutDetail: WorkoutDetail;
  heartRateChartData: any[];
  elevationChartData: any[];
  paceChartData: any[];
  routeData: any[];
  refreshHRMutation: UseMutationResult<any, Error, number>;
}

export default function WorkoutCharts({
  workoutDetail,
  heartRateChartData,
  elevationChartData,
  paceChartData,
  routeData,
  refreshHRMutation,
}: WorkoutChartsProps) {
  return (
    <>
      {/* Map */}
      {routeData.length > 0 && (
        <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
          <h3 className="text-lg font-bold text-white mb-4">🗺️ 运动路线</h3>
          <div className="h-[400px] w-full">
            <WorkoutMap routeData={routeData} />
          </div>
        </div>
      )}

      {/* Heart Rate Chart */}
      <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-white">❤️ 心率曲线</h3>
          {workoutDetail && workoutDetail.source === 'garmin' && (
            <button
              onClick={() => refreshHRMutation.mutate(workoutDetail.id)}
              disabled={refreshHRMutation.isPending}
              className="px-3 py-1 bg-blue-600/80 text-white text-xs rounded hover:bg-blue-600 disabled:opacity-50 transition-colors"
            >
              {refreshHRMutation.isPending ? '加载中...' : '🔄 刷新数据'}
            </button>
          )}
        </div>
        {heartRateChartData.length > 0 ? (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={heartRateChartData}>
                <defs>
                  <linearGradient id="hrGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="time" stroke="#9ca3af" tickFormatter={(v) => `${v}分`} />
                <YAxis stroke="#9ca3af" domain={['dataMin - 10', 'dataMax + 10']} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151' }}
                  labelFormatter={(v) => `${v}分钟`}
                  formatter={(v: number) => [`${v} bpm`, '心率']}
                />
                <Area type="monotone" dataKey="hr" stroke="#ef4444" fill="url(#hrGradient)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-64 flex flex-col items-center justify-center text-gray-400">
            <div className="text-4xl mb-3">📉</div>
            <p className="text-lg">暂无心率曲线数据</p>
            {workoutDetail?.source === 'garmin' && (
              <p className="text-sm mt-1">点击"刷新数据"尝试获取</p>
            )}
          </div>
        )}
      </div>

      {/* Elevation Chart */}
      {elevationChartData.length > 0 && (
        <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
          <h3 className="text-lg font-bold text-white mb-4">⛰️ 海拔高度</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={elevationChartData}>
                <defs>
                  <linearGradient id="elevationGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="time"
                  stroke="#9ca3af"
                  tickFormatter={(v) => {
                    const hours = Math.floor(v / 60);
                    const minutes = v % 60;
                    return hours > 0 ? `${hours}:${minutes.toString().padStart(2, '0')}` : `${minutes}分`;
                  }}
                  label={{ value: '时间', position: 'insideBottom', offset: -5, style: { fill: '#9ca3af' } }}
                />
                <YAxis
                  stroke="#9ca3af"
                  label={{ value: '海拔(m)', angle: -90, position: 'insideLeft', style: { fill: '#9ca3af' } }}
                  domain={['dataMin - 10', 'dataMax + 10']}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff' }}
                  labelFormatter={(v) => {
                    const hours = Math.floor(v / 60);
                    const minutes = v % 60;
                    return hours > 0 ? `${hours}:${minutes.toString().padStart(2, '0')}` : `${minutes}分`;
                  }}
                  formatter={(v: number) => [`${v.toFixed(0)}米`, '海拔']}
                />
                <Area type="monotone" dataKey="elevation" stroke="#10b981" fill="url(#elevationGradient)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          {workoutDetail.elevation_gain_meters && workoutDetail.elevation_loss_meters && (
            <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-green-900/30 rounded-lg p-3 border border-green-800/50">
                <div className="text-green-400 text-xs">累计爬升</div>
                <div className="text-lg font-bold text-green-400">
                  {workoutDetail.elevation_gain_meters.toFixed(0)} <span className="text-sm">m</span>
                </div>
              </div>
              <div className="bg-blue-900/30 rounded-lg p-3 border border-blue-800/50">
                <div className="text-blue-400 text-xs">累计下降</div>
                <div className="text-lg font-bold text-blue-400">
                  {workoutDetail.elevation_loss_meters.toFixed(0)} <span className="text-sm">m</span>
                </div>
              </div>
              {workoutDetail.min_elevation_meters && (
                <div className="bg-slate-700/50 rounded-lg p-3">
                  <div className="text-gray-400 text-xs">最低海拔</div>
                  <div className="text-lg font-bold text-white">
                    {workoutDetail.min_elevation_meters.toFixed(0)} <span className="text-sm">m</span>
                  </div>
                </div>
              )}
              {workoutDetail.max_elevation_meters && (
                <div className="bg-slate-700/50 rounded-lg p-3">
                  <div className="text-gray-400 text-xs">最高海拔</div>
                  <div className="text-lg font-bold text-white">
                    {workoutDetail.max_elevation_meters.toFixed(0)} <span className="text-sm">m</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Speed Chart */}
      {paceChartData.length > 0 && (
        <div className="bg-slate-800/60 rounded-xl p-6 border border-slate-700">
          <h3 className="text-lg font-bold text-white mb-4">⚡ 速度</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={paceChartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis
                  dataKey="time"
                  stroke="#9ca3af"
                  tickFormatter={(v) => {
                    const hours = Math.floor(v / 60);
                    const minutes = v % 60;
                    return hours > 0 ? `${hours}:${minutes.toString().padStart(2, '0')}` : `${minutes}分`;
                  }}
                  label={{ value: '时间', position: 'insideBottom', offset: -5, style: { fill: '#9ca3af' } }}
                />
                <YAxis
                  stroke="#9ca3af"
                  label={{ value: '速度(km/h)', angle: -90, position: 'insideLeft', style: { fill: '#9ca3af' } }}
                  domain={[0, 'dataMax + 1']}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1f2937', border: '1px solid #374151', color: '#fff' }}
                  labelFormatter={(v) => {
                    const hours = Math.floor(v / 60);
                    const minutes = v % 60;
                    return hours > 0 ? `${hours}:${minutes.toString().padStart(2, '0')}` : `${minutes}分`;
                  }}
                  formatter={(v: number) => [`${v.toFixed(1)} 公里/小时`, '速度']}
                />
                <Bar dataKey="speed" fill="#3b82f6" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {(workoutDetail.avg_speed_kmh || workoutDetail.max_speed_kmh) && (
            <div className="mt-4 grid grid-cols-2 gap-4">
              {workoutDetail.avg_speed_kmh && (
                <div className="bg-blue-900/30 rounded-lg p-3 border border-blue-800/50">
                  <div className="text-blue-400 text-xs">平均速度</div>
                  <div className="text-lg font-bold text-blue-400">
                    {workoutDetail.avg_speed_kmh.toFixed(1)} <span className="text-sm">km/h</span>
                  </div>
                </div>
              )}
              {workoutDetail.max_speed_kmh && (
                <div className="bg-purple-900/30 rounded-lg p-3 border border-purple-800/50">
                  <div className="text-purple-400 text-xs">最大速度</div>
                  <div className="text-lg font-bold text-purple-400">
                    {workoutDetail.max_speed_kmh.toFixed(1)} <span className="text-sm">km/h</span>
                  </div>
                </div>
              )}
              {workoutDetail.avg_pace_seconds_per_km && (
                <div className="bg-slate-700/50 rounded-lg p-3">
                  <div className="text-gray-400 text-xs">平均配速</div>
                  <div className="text-lg font-bold text-white font-mono">
                    {formatPace(workoutDetail.avg_pace_seconds_per_km)}
                  </div>
                </div>
              )}
              {workoutDetail.best_pace_seconds_per_km && (
                <div className="bg-slate-700/50 rounded-lg p-3">
                  <div className="text-gray-400 text-xs">最佳配速</div>
                  <div className="text-lg font-bold text-white font-mono">
                    {formatPace(workoutDetail.best_pace_seconds_per_km)}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </>
  );
}
