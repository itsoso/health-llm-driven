'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, subDays, addDays } from 'date-fns';
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
  ReferenceArea,
} from 'recharts';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

const API_BASE = '/api';

// 时间范围类型
type TimeRange = '1day' | '7days' | '4weeks' | '1year';

function HeartRateContent() {
  const { token } = useAuth();
  const [selectedDate, setSelectedDate] = useState(new Date());
  const [timeRange, setTimeRange] = useState<TimeRange>('1day');

  // 根据时间范围计算天数
  const getDaysFromRange = (range: TimeRange): number => {
    switch (range) {
      case '1day': return 1;
      case '7days': return 7;
      case '4weeks': return 28;
      case '1year': return 365;
      default: return 1;
    }
  };

  const days = getDaysFromRange(timeRange);

  // 获取每日详细心率数据
  const { data: dailyData, isLoading: loadingDaily, error: dailyError } = useQuery({
    queryKey: ['heart-rate-daily', format(selectedDate, 'yyyy-MM-dd')],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/heart-rate/me/daily/${format(selectedDate, 'yyyy-MM-dd')}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || '获取心率数据失败');
      }
      return res.json();
    },
    enabled: !!token && timeRange === '1day',
    retry: 1,
    staleTime: 1000 * 60 * 5, // 5分钟缓存
  });

  // 获取心率趋势数据（7天/4周/1年）
  const { data: trendData, isLoading: loadingTrend, error: trendError } = useQuery({
    queryKey: ['heart-rate-trend', days],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/heart-rate/me/trend?days=${days}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || '获取心率趋势失败');
      }
      return res.json();
    },
    enabled: !!token && timeRange !== '1day',
    retry: 1,
    staleTime: 1000 * 60 * 5, // 5分钟缓存
  });

  // 日期导航
  const goToPreviousDay = () => setSelectedDate(prev => subDays(prev, 1));
  const goToNextDay = () => {
    const tomorrow = addDays(selectedDate, 1);
    if (tomorrow <= new Date()) {
      setSelectedDate(tomorrow);
    }
  };
  const isToday = format(selectedDate, 'yyyy-MM-dd') === format(new Date(), 'yyyy-MM-dd');

  // 处理每日心率时间线数据 - 24小时格式
  const timelineChartData = useMemo(() => {
    if (!dailyData?.heart_rate_timeline?.length) return [];
    
    // 创建24小时的时间点
    const hourlyData: { [key: string]: number[] } = {};
    
    dailyData.heart_rate_timeline.forEach((point: any) => {
      const hour = point.time.split(':')[0];
      if (!hourlyData[hour]) {
        hourlyData[hour] = [];
      }
      hourlyData[hour].push(point.value);
    });

    // 生成24小时数据
    const result = [];
    for (let i = 0; i < 24; i++) {
      const hour = i.toString().padStart(2, '0');
      const values = hourlyData[hour] || [];
      const avg = values.length > 0 ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : null;
      const max = values.length > 0 ? Math.max(...values) : null;
      const min = values.length > 0 ? Math.min(...values) : null;
      
      // 转换为12小时制显示
      let label = '';
      if (i === 0) label = '12a';
      else if (i === 6) label = '6a';
      else if (i === 12) label = '12p';
      else if (i === 18) label = '6p';
      else label = '';

      result.push({
        hour: i,
        label,
        心率: avg,
        最高: max,
        最低: min,
        fullLabel: `${hour}:00`,
      });
    }
    return result;
  }, [dailyData]);

  // 趋势数据
  const trendChartData = useMemo(() => {
    if (!trendData?.daily_data?.length) return [];
    return trendData.daily_data.map((day: any) => ({
      date: format(new Date(day.record_date), timeRange === '1year' ? 'MM/dd' : 'MM/dd'),
      静息心率: day.resting_heart_rate,
      平均心率: day.avg_heart_rate,
      最高心率: day.max_heart_rate,
    }));
  }, [trendData, timeRange]);

  // 统计数据
  const stats = useMemo(() => {
    if (timeRange === '1day') {
      return {
        avgResting: dailyData?.summary?.resting_heart_rate,
        resting: dailyData?.summary?.resting_heart_rate,
        max: dailyData?.summary?.max_heart_rate,
        min: dailyData?.summary?.min_heart_rate,
        hrv: dailyData?.hrv,
      };
    } else {
      return {
        avgResting: trendData?.avg_resting_heart_rate ? Math.round(trendData.avg_resting_heart_rate) : null,
        resting: trendData?.avg_resting_heart_rate ? Math.round(trendData.avg_resting_heart_rate) : null,
        max: trendData?.max_heart_rate,
        min: trendData?.min_heart_rate,
        hrv: trendData?.avg_hrv ? Math.round(trendData.avg_hrv) : null,
      };
    }
  }, [timeRange, dailyData, trendData]);

  const isLoading = timeRange === '1day' ? loadingDaily : loadingTrend;
  const error = timeRange === '1day' ? dailyError : trendError;

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* 标题 */}
        <h1 className="text-3xl font-light text-gray-800 mb-6">心率</h1>

        {/* 日期导航 + 时间范围选择 */}
        <div className="flex items-center justify-between mb-6">
          {/* 左侧：日期导航 */}
          <div className="flex items-center gap-2">
            <button
              onClick={goToPreviousDay}
              className="w-8 h-8 rounded-full bg-gray-100 hover:bg-gray-200 flex items-center justify-center text-gray-600 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button
              onClick={goToNextDay}
              disabled={isToday}
              className={`w-8 h-8 rounded-full flex items-center justify-center transition-colors ${
                isToday 
                  ? 'bg-gray-50 text-gray-300 cursor-not-allowed' 
                  : 'bg-gray-100 hover:bg-gray-200 text-gray-600'
              }`}
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <div className="flex items-center gap-2 px-3 py-1.5 bg-gray-100 rounded-full text-sm text-gray-700">
              <span>📅</span>
              <span>{format(selectedDate, 'M月d日', { locale: zhCN })}</span>
            </div>
          </div>

          {/* 右侧：时间范围选择 */}
          <div className="flex bg-gray-100 rounded-lg p-1">
            {[
              { key: '1day', label: '1 天' },
              { key: '7days', label: '7 天' },
              { key: '4weeks', label: '4 周' },
              { key: '1year', label: '1 年' },
            ].map((item) => (
              <button
                key={item.key}
                onClick={() => setTimeRange(item.key as TimeRange)}
                className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
                  timeRange === item.key
                    ? 'bg-white text-gray-900 shadow-sm'
                    : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {/* 分割线 */}
        <div className="border-t border-gray-200 mb-6" />

        {/* 每日时间轴标题 */}
        <h2 className="text-lg text-gray-700 mb-4">
          {timeRange === '1day' ? '每日时间轴' : `${getDaysFromRange(timeRange)}天趋势`}
        </h2>

        {/* 心率图表 */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-6">
          {isLoading ? (
            <div className="h-64 flex items-center justify-center text-gray-400">
              <div className="animate-pulse">加载中...</div>
            </div>
          ) : error ? (
            <div className="h-64 flex flex-col items-center justify-center text-red-400">
              <div className="text-5xl mb-3">⚠️</div>
              <p className="text-red-500 font-medium">加载失败</p>
              <p className="text-sm text-red-400 mt-1">{(error as Error).message}</p>
              <p className="text-xs text-gray-400 mt-2">请检查 Garmin 凭证设置</p>
            </div>
          ) : timeRange === '1day' ? (
            // 24小时心率图
            timelineChartData.some(d => d.心率 !== null) ? (
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={timelineChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="heartRateGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#60a5fa" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                  <XAxis 
                    dataKey="hour"
                    stroke="#9ca3af"
                    tick={{ fill: '#9ca3af', fontSize: 12 }}
                    tickFormatter={(hour) => {
                      if (hour === 0) return '12a';
                      if (hour === 6) return '6a';
                      if (hour === 12) return '12p';
                      if (hour === 18) return '6p';
                      return '';
                    }}
                    interval={0}
                    axisLine={{ stroke: '#e5e7eb' }}
                    tickLine={false}
                  />
                  <YAxis 
                    stroke="#9ca3af"
                    tick={{ fill: '#9ca3af', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    domain={[40, 'auto']}
                    width={40}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#fff', 
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                    }}
                    formatter={(value: number) => value ? [`${value} bpm`, '心率'] : ['-', '心率']}
                    labelFormatter={(hour: number) => `${hour.toString().padStart(2, '0')}:00`}
                  />
                  <Area
                    type="monotone"
                    dataKey="心率"
                    stroke="#60a5fa"
                    strokeWidth={2}
                    fill="url(#heartRateGradient)"
                    connectNulls
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-64 flex flex-col items-center justify-center text-gray-400">
                <div className="text-5xl mb-3">❤️</div>
                <p className="text-gray-500">暂无心率数据</p>
                <p className="text-sm text-gray-400 mt-1">请确保已同步 Garmin 数据</p>
              </div>
            )
          ) : (
            // 趋势图
            trendChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={trendChartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
                  <XAxis 
                    dataKey="date"
                    stroke="#9ca3af"
                    tick={{ fill: '#9ca3af', fontSize: 11 }}
                    axisLine={{ stroke: '#e5e7eb' }}
                    tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis 
                    stroke="#9ca3af"
                    tick={{ fill: '#9ca3af', fontSize: 11 }}
                    axisLine={false}
                    tickLine={false}
                    domain={[40, 'auto']}
                    width={40}
                  />
                  <Tooltip 
                    contentStyle={{ 
                      backgroundColor: '#fff', 
                      border: '1px solid #e5e7eb',
                      borderRadius: '8px',
                      boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
                    }}
                  />
                  <Legend 
                    iconType="circle"
                    iconSize={8}
                    wrapperStyle={{ paddingTop: '10px' }}
                  />
                  <Line 
                    type="monotone" 
                    dataKey="静息心率" 
                    stroke="#10b981" 
                    strokeWidth={2}
                    dot={{ fill: '#10b981', strokeWidth: 0, r: 3 }}
                    connectNulls
                  />
                  <Line 
                    type="monotone" 
                    dataKey="平均心率" 
                    stroke="#60a5fa" 
                    strokeWidth={2}
                    dot={{ fill: '#60a5fa', strokeWidth: 0, r: 3 }}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-64 flex flex-col items-center justify-center text-gray-400">
                <div className="text-5xl mb-3">📈</div>
                <p className="text-gray-500">暂无趋势数据</p>
              </div>
            )
          )}

          {/* 图例 */}
          {timeRange === '1day' && timelineChartData.some(d => d.心率 !== null) && (
            <div className="flex items-center justify-center gap-6 mt-4 pt-4 border-t border-gray-100">
              <div className="flex items-center gap-2">
                <div className="w-3 h-0.5 bg-blue-400" />
                <span className="text-sm text-gray-500">心率</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full bg-indigo-600" />
                <span className="text-sm text-gray-500">睡眠</span>
              </div>
            </div>
          )}
        </div>

        {/* 统计卡片 */}
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-3xl font-light text-gray-800">
              {stats.avgResting || '--'}
              <span className="text-lg text-gray-500 ml-1">bpm</span>
            </div>
            <div className="text-sm text-gray-500 mt-1">
              {timeRange === '1day' ? '静息心率' : `${getDaysFromRange(timeRange)}天平均静息心率`}
            </div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-light text-gray-800">
              {stats.resting || '--'}
              <span className="text-lg text-gray-500 ml-1">bpm</span>
            </div>
            <div className="text-sm text-gray-500 mt-1">静止</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-light text-gray-800">
              {stats.max || '--'}
              <span className="text-lg text-gray-500 ml-1">bpm</span>
            </div>
            <div className="text-sm text-gray-500 mt-1">最高</div>
          </div>
        </div>

        {/* HRV 卡片 */}
        {stats.hrv && (
          <div className="mt-6 bg-white rounded-xl shadow-sm p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm text-gray-500 mb-1">心率变异性 (HRV)</div>
                <div className="text-2xl font-light text-gray-800">
                  {stats.hrv}
                  <span className="text-lg text-gray-500 ml-1">ms</span>
                </div>
              </div>
              <div className={`px-3 py-1 rounded-full text-sm ${
                stats.hrv >= 50 ? 'bg-green-100 text-green-700' :
                stats.hrv >= 35 ? 'bg-blue-100 text-blue-700' :
                stats.hrv >= 25 ? 'bg-yellow-100 text-yellow-700' :
                'bg-red-100 text-red-700'
              }`}>
                {stats.hrv >= 50 ? '优秀' :
                 stats.hrv >= 35 ? '良好' :
                 stats.hrv >= 25 ? '一般' : '需改善'}
              </div>
            </div>
          </div>
        )}

        {/* 心率知识卡片 */}
        <div className="mt-6 bg-white rounded-xl shadow-sm p-4">
          <h3 className="text-gray-700 font-medium mb-3">💡 关于静息心率</h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-gray-600">&lt; 60 bpm - 运动员级/优秀</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-blue-500" />
                <span className="text-gray-600">60-70 bpm - 良好</span>
              </div>
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-yellow-500" />
                <span className="text-gray-600">70-80 bpm - 一般</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-red-500" />
                <span className="text-gray-600">&gt; 80 bpm - 需关注</span>
              </div>
            </div>
          </div>
        </div>
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
