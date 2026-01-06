'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, subDays } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api/v1';

function HeartRateContent() {
  const { user, token } = useAuth();
  const [selectedDate, setSelectedDate] = useState(format(new Date(), 'yyyy-MM-dd'));
  const [trendDays, setTrendDays] = useState(7);
  const [activeTab, setActiveTab] = useState<'daily' | 'trend'>('daily');

  // 获取每日详细心率数据
  const { data: dailyData, isLoading: loadingDaily, error: dailyError } = useQuery({
    queryKey: ['heart-rate-daily', selectedDate],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/heart-rate/me/daily/${selectedDate}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取心率数据失败');
      return res.json();
    },
    enabled: !!token && activeTab === 'daily',
  });

  // 获取心率趋势数据
  const { data: trendData, isLoading: loadingTrend, error: trendError } = useQuery({
    queryKey: ['heart-rate-trend', trendDays],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/heart-rate/me/trend?days=${trendDays}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取心率趋势失败');
      return res.json();
    },
    enabled: !!token && activeTab === 'trend',
  });

  // 处理每日心率时间线数据
  const timelineChartData = useMemo(() => {
    if (!dailyData?.heart_rate_timeline?.length) return [];
    return dailyData.heart_rate_timeline.map((point: any) => ({
      time: point.time,
      心率: point.value,
    }));
  }, [dailyData]);

  // 处理趋势数据
  const trendChartData = useMemo(() => {
    if (!trendData?.daily_data?.length) return [];
    return trendData.daily_data.map((day: any) => ({
      date: format(new Date(day.record_date), 'MM/dd'),
      平均心率: day.avg_heart_rate,
      静息心率: day.resting_heart_rate,
      最高心率: day.max_heart_rate,
      最低心率: day.min_heart_rate,
    }));
  }, [trendData]);

  // HRV趋势数据
  const hrvChartData = useMemo(() => {
    if (!trendData?.hrv_data?.length) return [];
    return trendData.hrv_data.map((item: any) => ({
      date: format(new Date(item.date), 'MM/dd'),
      HRV: item.hrv,
    }));
  }, [trendData]);

  // 心率区间评估
  const getHeartRateStatus = (resting: number | null) => {
    if (!resting) return { label: '无数据', color: 'text-gray-400', bg: 'bg-gray-100' };
    if (resting < 50) return { label: '运动员级', color: 'text-emerald-600', bg: 'bg-emerald-50' };
    if (resting < 60) return { label: '优秀', color: 'text-green-600', bg: 'bg-green-50' };
    if (resting < 70) return { label: '良好', color: 'text-blue-600', bg: 'bg-blue-50' };
    if (resting < 80) return { label: '一般', color: 'text-yellow-600', bg: 'bg-yellow-50' };
    if (resting < 90) return { label: '偏高', color: 'text-orange-600', bg: 'bg-orange-50' };
    return { label: '需关注', color: 'text-red-600', bg: 'bg-red-50' };
  };

  // HRV评估
  const getHRVStatus = (hrv: number | null) => {
    if (!hrv) return { label: '无数据', color: 'text-gray-400', bg: 'bg-gray-100' };
    if (hrv >= 50) return { label: '优秀', color: 'text-emerald-600', bg: 'bg-emerald-50' };
    if (hrv >= 35) return { label: '良好', color: 'text-green-600', bg: 'bg-green-50' };
    if (hrv >= 25) return { label: '一般', color: 'text-yellow-600', bg: 'bg-yellow-50' };
    return { label: '需改善', color: 'text-red-600', bg: 'bg-red-50' };
  };

  const hrStatus = getHeartRateStatus(
    activeTab === 'daily' 
      ? dailyData?.summary?.resting_heart_rate 
      : trendData?.avg_resting_heart_rate
  );
  
  const hrvStatus = getHRVStatus(
    activeTab === 'daily' 
      ? dailyData?.hrv 
      : trendData?.avg_hrv
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* 顶部装饰 */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-40 -right-40 w-80 h-80 bg-rose-500/20 rounded-full blur-3xl" />
        <div className="absolute top-1/2 -left-40 w-80 h-80 bg-purple-500/20 rounded-full blur-3xl" />
      </div>

      <div className="relative max-w-7xl mx-auto px-4 py-8">
        {/* 标题区域 */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-rose-400 via-pink-400 to-purple-400 bg-clip-text text-transparent mb-2">
            ❤️ 心率监测
          </h1>
          <p className="text-gray-400">实时心率数据与趋势分析</p>
        </div>

        {/* 标签切换 */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setActiveTab('daily')}
            className={`px-6 py-3 rounded-xl font-medium transition-all ${
              activeTab === 'daily'
                ? 'bg-gradient-to-r from-rose-500 to-pink-500 text-white shadow-lg shadow-rose-500/25'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            📊 每日详情
          </button>
          <button
            onClick={() => setActiveTab('trend')}
            className={`px-6 py-3 rounded-xl font-medium transition-all ${
              activeTab === 'trend'
                ? 'bg-gradient-to-r from-rose-500 to-pink-500 text-white shadow-lg shadow-rose-500/25'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            📈 趋势分析
          </button>
        </div>

        {/* 日期/天数选择器 */}
        <div className="mb-6">
          {activeTab === 'daily' ? (
            <div className="flex items-center gap-4">
              <label className="text-gray-300">选择日期:</label>
              <input
                type="date"
                value={selectedDate}
                max={format(new Date(), 'yyyy-MM-dd')}
                onChange={(e) => setSelectedDate(e.target.value)}
                className="px-4 py-2 bg-white/10 border border-white/20 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-rose-500"
              />
              <div className="flex gap-2">
                {[0, 1, 2, 3].map((offset) => {
                  const date = subDays(new Date(), offset);
                  const dateStr = format(date, 'yyyy-MM-dd');
                  const label = offset === 0 ? '今天' : offset === 1 ? '昨天' : format(date, 'MM/dd');
                  return (
                    <button
                      key={offset}
                      onClick={() => setSelectedDate(dateStr)}
                      className={`px-3 py-1 rounded-lg text-sm transition-all ${
                        selectedDate === dateStr
                          ? 'bg-rose-500 text-white'
                          : 'bg-white/10 text-gray-300 hover:bg-white/20'
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-4">
              <label className="text-gray-300">统计周期:</label>
              <div className="flex gap-2">
                {[7, 14, 30, 60, 90].map((d) => (
                  <button
                    key={d}
                    onClick={() => setTrendDays(d)}
                    className={`px-4 py-2 rounded-lg transition-all ${
                      trendDays === d
                        ? 'bg-gradient-to-r from-rose-500 to-pink-500 text-white'
                        : 'bg-white/10 text-gray-300 hover:bg-white/20'
                    }`}
                  >
                    {d}天
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* 数据卡片 */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          {activeTab === 'daily' ? (
            <>
              <div className="bg-white/10 backdrop-blur-xl rounded-2xl p-6 border border-white/10">
                <div className="text-gray-400 text-sm mb-1">平均心率</div>
                <div className="text-3xl font-bold text-white">
                  {dailyData?.summary?.avg_heart_rate || '--'}
                  <span className="text-lg text-gray-400 ml-1">bpm</span>
                </div>
              </div>
              <div className={`${hrStatus.bg} backdrop-blur-xl rounded-2xl p-6 border border-white/10`}>
                <div className="text-gray-600 text-sm mb-1">静息心率</div>
                <div className={`text-3xl font-bold ${hrStatus.color}`}>
                  {dailyData?.summary?.resting_heart_rate || '--'}
                  <span className="text-lg text-gray-400 ml-1">bpm</span>
                </div>
                <div className={`text-sm ${hrStatus.color} mt-1`}>{hrStatus.label}</div>
              </div>
              <div className="bg-white/10 backdrop-blur-xl rounded-2xl p-6 border border-white/10">
                <div className="text-gray-400 text-sm mb-1">心率范围</div>
                <div className="text-2xl font-bold text-white">
                  {dailyData?.summary?.min_heart_rate || '--'} - {dailyData?.summary?.max_heart_rate || '--'}
                  <span className="text-sm text-gray-400 ml-1">bpm</span>
                </div>
              </div>
              <div className={`${hrvStatus.bg} backdrop-blur-xl rounded-2xl p-6 border border-white/10`}>
                <div className="text-gray-600 text-sm mb-1">HRV (心率变异性)</div>
                <div className={`text-3xl font-bold ${hrvStatus.color}`}>
                  {dailyData?.hrv ? Math.round(dailyData.hrv) : '--'}
                  <span className="text-lg text-gray-400 ml-1">ms</span>
                </div>
                <div className={`text-sm ${hrvStatus.color} mt-1`}>{hrvStatus.label}</div>
              </div>
            </>
          ) : (
            <>
              <div className="bg-white/10 backdrop-blur-xl rounded-2xl p-6 border border-white/10">
                <div className="text-gray-400 text-sm mb-1">平均心率</div>
                <div className="text-3xl font-bold text-white">
                  {trendData?.avg_heart_rate ? Math.round(trendData.avg_heart_rate) : '--'}
                  <span className="text-lg text-gray-400 ml-1">bpm</span>
                </div>
              </div>
              <div className={`${hrStatus.bg} backdrop-blur-xl rounded-2xl p-6 border border-white/10`}>
                <div className="text-gray-600 text-sm mb-1">平均静息心率</div>
                <div className={`text-3xl font-bold ${hrStatus.color}`}>
                  {trendData?.avg_resting_heart_rate ? Math.round(trendData.avg_resting_heart_rate) : '--'}
                  <span className="text-lg text-gray-400 ml-1">bpm</span>
                </div>
                <div className={`text-sm ${hrStatus.color} mt-1`}>{hrStatus.label}</div>
              </div>
              <div className="bg-white/10 backdrop-blur-xl rounded-2xl p-6 border border-white/10">
                <div className="text-gray-400 text-sm mb-1">最高/最低心率</div>
                <div className="text-2xl font-bold text-white">
                  {trendData?.min_heart_rate || '--'} - {trendData?.max_heart_rate || '--'}
                  <span className="text-sm text-gray-400 ml-1">bpm</span>
                </div>
              </div>
              <div className={`${hrvStatus.bg} backdrop-blur-xl rounded-2xl p-6 border border-white/10`}>
                <div className="text-gray-600 text-sm mb-1">平均HRV</div>
                <div className={`text-3xl font-bold ${hrvStatus.color}`}>
                  {trendData?.avg_hrv ? Math.round(trendData.avg_hrv) : '--'}
                  <span className="text-lg text-gray-400 ml-1">ms</span>
                </div>
                <div className={`text-sm ${hrvStatus.color} mt-1`}>{hrvStatus.label}</div>
              </div>
            </>
          )}
        </div>

        {/* 图表区域 */}
        {activeTab === 'daily' ? (
          <div className="space-y-6">
            {/* 心率时间线 */}
            <div className="bg-white/5 backdrop-blur-xl rounded-2xl p-6 border border-white/10">
              <h3 className="text-xl font-semibold text-white mb-4">
                📈 {format(new Date(selectedDate), 'M月d日', { locale: zhCN })} 心率曲线
              </h3>
              {loadingDaily ? (
                <div className="h-80 flex items-center justify-center text-gray-400">
                  <div className="animate-pulse">加载中...</div>
                </div>
              ) : timelineChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <AreaChart data={timelineChartData}>
                    <defs>
                      <linearGradient id="heartRateGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#f43f5e" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#f43f5e" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis 
                      dataKey="time" 
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af', fontSize: 12 }}
                      interval="preserveStartEnd"
                    />
                    <YAxis 
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af' }}
                      domain={['dataMin - 10', 'dataMax + 10']}
                      label={{ value: 'bpm', angle: -90, position: 'insideLeft', fill: '#9ca3af' }}
                    />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: '#1f2937', 
                        border: '1px solid #374151',
                        borderRadius: '8px',
                        color: '#fff'
                      }}
                      formatter={(value: number) => [`${value} bpm`, '心率']}
                    />
                    {dailyData?.summary?.resting_heart_rate && (
                      <ReferenceLine 
                        y={dailyData.summary.resting_heart_rate} 
                        stroke="#10b981" 
                        strokeDasharray="5 5"
                        label={{ value: '静息心率', fill: '#10b981', fontSize: 12 }}
                      />
                    )}
                    <Area
                      type="monotone"
                      dataKey="心率"
                      stroke="#f43f5e"
                      strokeWidth={2}
                      fill="url(#heartRateGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-80 flex flex-col items-center justify-center text-gray-400">
                  <div className="text-6xl mb-4">💔</div>
                  <p>暂无详细心率数据</p>
                  <p className="text-sm mt-2">请确保已配置Garmin账号并完成数据同步</p>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* 心率趋势图 */}
            <div className="bg-white/5 backdrop-blur-xl rounded-2xl p-6 border border-white/10">
              <h3 className="text-xl font-semibold text-white mb-4">📊 心率趋势 (过去{trendDays}天)</h3>
              {loadingTrend ? (
                <div className="h-80 flex items-center justify-center text-gray-400">
                  <div className="animate-pulse">加载中...</div>
                </div>
              ) : trendChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={350}>
                  <LineChart data={trendChartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis 
                      dataKey="date" 
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af', fontSize: 12 }}
                    />
                    <YAxis 
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af' }}
                      domain={['dataMin - 10', 'dataMax + 10']}
                      label={{ value: 'bpm', angle: -90, position: 'insideLeft', fill: '#9ca3af' }}
                    />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: '#1f2937', 
                        border: '1px solid #374151',
                        borderRadius: '8px',
                        color: '#fff'
                      }}
                    />
                    <Legend />
                    <Line 
                      type="monotone" 
                      dataKey="平均心率" 
                      stroke="#f43f5e" 
                      strokeWidth={2}
                      dot={{ fill: '#f43f5e', strokeWidth: 0, r: 3 }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="静息心率" 
                      stroke="#10b981" 
                      strokeWidth={2}
                      dot={{ fill: '#10b981', strokeWidth: 0, r: 3 }}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="最高心率" 
                      stroke="#f59e0b" 
                      strokeWidth={1}
                      strokeDasharray="3 3"
                      dot={false}
                    />
                    <Line 
                      type="monotone" 
                      dataKey="最低心率" 
                      stroke="#6366f1" 
                      strokeWidth={1}
                      strokeDasharray="3 3"
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-80 flex flex-col items-center justify-center text-gray-400">
                  <div className="text-6xl mb-4">📉</div>
                  <p>暂无心率趋势数据</p>
                </div>
              )}
            </div>

            {/* HRV趋势图 */}
            <div className="bg-white/5 backdrop-blur-xl rounded-2xl p-6 border border-white/10">
              <h3 className="text-xl font-semibold text-white mb-4">💚 HRV 趋势 (心率变异性)</h3>
              {loadingTrend ? (
                <div className="h-64 flex items-center justify-center text-gray-400">
                  <div className="animate-pulse">加载中...</div>
                </div>
              ) : hrvChartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={280}>
                  <AreaChart data={hrvChartData}>
                    <defs>
                      <linearGradient id="hrvGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#10b981" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                    <XAxis 
                      dataKey="date" 
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af', fontSize: 12 }}
                    />
                    <YAxis 
                      stroke="#9ca3af"
                      tick={{ fill: '#9ca3af' }}
                      label={{ value: 'ms', angle: -90, position: 'insideLeft', fill: '#9ca3af' }}
                    />
                    <Tooltip 
                      contentStyle={{ 
                        backgroundColor: '#1f2937', 
                        border: '1px solid #374151',
                        borderRadius: '8px',
                        color: '#fff'
                      }}
                      formatter={(value: number) => [`${Math.round(value)} ms`, 'HRV']}
                    />
                    <Area
                      type="monotone"
                      dataKey="HRV"
                      stroke="#10b981"
                      strokeWidth={2}
                      fill="url(#hrvGradient)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-64 flex flex-col items-center justify-center text-gray-400">
                  <div className="text-4xl mb-2">💚</div>
                  <p>暂无HRV数据</p>
                </div>
              )}
            </div>

            {/* HRV说明 */}
            <div className="bg-white/5 backdrop-blur-xl rounded-2xl p-6 border border-white/10">
              <h3 className="text-lg font-semibold text-white mb-4">💡 HRV 知识</h3>
              <div className="grid md:grid-cols-2 gap-4 text-sm text-gray-300">
                <div className="space-y-2">
                  <p><span className="text-emerald-400 font-medium">什么是HRV?</span></p>
                  <p>心率变异性(HRV)是指相邻心跳之间时间间隔的变化。它反映了自主神经系统的平衡状态，是评估身体恢复能力和压力水平的重要指标。</p>
                </div>
                <div className="space-y-2">
                  <p><span className="text-emerald-400 font-medium">如何提高HRV?</span></p>
                  <ul className="list-disc list-inside space-y-1">
                    <li>保持规律作息，充足睡眠</li>
                    <li>适度有氧运动</li>
                    <li>减少压力，练习冥想</li>
                    <li>避免过度饮酒</li>
                  </ul>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function HeartRatePage() {
  return (
    <ProtectedRoute>
      <HeartRateContent />
    </ProtectedRoute>
  );
}

