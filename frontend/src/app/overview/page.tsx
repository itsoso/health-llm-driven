'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format, subDays } from 'date-fns';
import { zhCN } from 'date-fns/locale';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

// 运动记录类型
interface WorkoutSummary {
  id: number;
  workout_date: string;
  workout_type: string;
  workout_name: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  avg_heart_rate: number | null;
  calories: number | null;
  feeling: string | null;
  has_ai_analysis: boolean;
}

// 饮食记录类型
interface DietRecord {
  id: number;
  record_date: string;
  meal_type: string;
  food_items: string;
  calories: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
  fiber: number | null;
}

// 每日饮食汇总
interface DailyDietSummary {
  record_date: string;
  total_calories: number;
  total_protein: number;
  total_carbs: number;
  total_fat: number;
  total_fiber: number;
  meals_count: number;
  meals: DietRecord[];
}

interface GarminData {
  id: number;
  record_date: string;
  sleep_score: number | null;
  total_sleep_duration: number | null;
  sleep_start_time: string | null;  // 睡眠开始时间 HH:MM:SS
  sleep_end_time: string | null;    // 睡眠结束时间 HH:MM:SS
  resting_heart_rate: number | null;
  avg_heart_rate: number | null;
  hrv: number | null;
  hrv_status: string | null;
  hrv_7day_avg: number | null;
  steps: number | null;
  calories_burned: number | null;
  active_calories: number | null;
  bmr_calories: number | null;
  active_minutes: number | null;
  intensity_minutes_goal: number | null;
  moderate_intensity_minutes: number | null;
  vigorous_intensity_minutes: number | null;
  stress_level: number | null;
  body_battery_charged: number | null;
  body_battery_drained: number | null;
  body_battery_most_charged: number | null;
  body_battery_lowest: number | null;
  body_battery_current: number | null;  // 当前实时电量
  avg_respiration_awake: number | null;
  avg_respiration_sleep: number | null;
  lowest_respiration: number | null;
  highest_respiration: number | null;
  spo2_avg: number | null;
  spo2_min: number | null;
  spo2_max: number | null;
  vo2max_running: number | null;
  floors_climbed: number | null;
  distance_meters: number | null;
}

// 格式化时长
function formatDuration(minutes: number | null | undefined): string {
  if (!minutes) return '--';
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${hours}小时${mins}分钟`;
}

// HRV状态翻译
function getHrvStatusText(status: string | null | undefined): { text: string; color: string } {
  const statusMap: Record<string, { text: string; color: string }> = {
    'BALANCED': { text: '平衡', color: 'text-green-500' },
    'balanced': { text: '平衡', color: 'text-green-500' },
    'UNBALANCED': { text: '不平衡', color: 'text-orange-500' },
    'unbalanced': { text: '不平衡', color: 'text-orange-500' },
    'LOW': { text: '偏低', color: 'text-red-500' },
    'low': { text: '偏低', color: 'text-red-500' },
  };
  return statusMap[status || ''] || { text: status || '--', color: 'text-gray-500' };
}

// 格式化睡眠时间 (HH:MM:SS -> 12小时制)
function formatSleepTime(timeStr: string | null | undefined): string {
  if (!timeStr) return '--';
  try {
    const [hours, minutes] = timeStr.split(':').map(Number);
    const period = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 || 12;
    return `${displayHours}:${minutes.toString().padStart(2, '0')} ${period}`;
  } catch {
    return '--';
  }
}

// 睡眠分数颜色
function getSleepScoreColor(score: number | null | undefined): string {
  if (!score) return 'text-gray-400';
  if (score >= 80) return 'text-blue-400';
  if (score >= 60) return 'text-green-400';
  if (score >= 40) return 'text-yellow-400';
  return 'text-red-400';
}

// 卡片组件
function MetricCard({
  icon,
  title,
  children,
  className = '',
}: {
  icon: string;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`bg-white rounded-2xl shadow-md hover:shadow-lg transition-shadow duration-200 p-5 flex flex-col ${className}`}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xl">{icon}</span>
        <span className="text-gray-600 font-medium text-sm">{title}</span>
      </div>
      <div className="flex-1">
        {children}
      </div>
    </div>
  );
}

function OverviewContent() {
  const { token } = useAuth();
  const today = format(new Date(), 'yyyy-MM-dd');
  const weekAgo = format(subDays(new Date(), 7), 'yyyy-MM-dd');
  const monthAgo = format(subDays(new Date(), 30), 'yyyy-MM-dd');

  // 获取最近30天数据（取最新一天显示）
  const { data: recentData, isLoading, error } = useQuery<GarminData[]>({
    queryKey: ['garmin-recent', monthAgo, today],
    queryFn: async () => {
      console.log('[Overview] 请求 API:', `${API_BASE}/daily-health/garmin/me?start_date=${monthAgo}&end_date=${today}`);
      const res = await fetch(`${API_BASE}/daily-health/garmin/me?start_date=${monthAgo}&end_date=${today}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      console.log('[Overview] API 响应状态:', res.status);
      if (!res.ok) {
        const errorText = await res.text();
        console.error('[Overview] API 错误:', errorText);
        throw new Error('获取数据失败');
      }
      const data = await res.json();
      console.log('[Overview] API 返回数据:', data);
      console.log('[Overview] 数据条数:', Array.isArray(data) ? data.length : 0);
      return data; // 后端直接返回数组
    },
    enabled: !!token,
  });

  // 获取今日运动记录
  const { data: workoutsData } = useQuery<WorkoutSummary[]>({
    queryKey: ['workouts-today', today],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/workout/me?days=1`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取运动数据失败');
      return res.json();
    },
    enabled: !!token,
  });

  // 获取今日饮食汇总
  const { data: dietData } = useQuery<DailyDietSummary>({
    queryKey: ['diet-today', today],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/diet/records/me/date/${today}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('获取饮食数据失败');
      return res.json();
    },
    enabled: !!token,
  });
  
  // 调试日志
  console.log('[Overview] token:', !!token);
  console.log('[Overview] isLoading:', isLoading);
  console.log('[Overview] error:', error);
  console.log('[Overview] recentData:', recentData);

  // 后端直接返回数组，不是 { data: [...] }
  const allRecords = recentData || [];
  
  // 按日期降序排序，找到第一条有实际数据的记录
  const sortedRecords = [...allRecords].sort((a, b) => 
    new Date(b.record_date).getTime() - new Date(a.record_date).getTime()
  );
  
  // 找到有实际数据的记录（睡眠分数或步数不为空）
  const record = sortedRecords.find(r => 
    r.sleep_score !== null || r.steps !== null || r.resting_heart_rate !== null
  ) || sortedRecords[0];
  
  // 最近7天数据用于图表
  const weekRecords = sortedRecords.slice(0, 7).reverse();

  // 准备睡眠柱状图数据
  const sleepChartData = weekRecords.slice(-7).map((r) => ({
    date: format(new Date(r.record_date), 'E', { locale: zhCN }),
    deep: r.total_sleep_duration ? Math.round((r.total_sleep_duration * 0.2)) : 0, // 模拟深睡
    light: r.total_sleep_duration ? Math.round((r.total_sleep_duration * 0.5)) : 0, // 模拟浅睡
    rem: r.total_sleep_duration ? Math.round((r.total_sleep_duration * 0.2)) : 0, // 模拟REM
    awake: r.total_sleep_duration ? Math.round((r.total_sleep_duration * 0.1)) : 0, // 模拟清醒
  }));

  // 准备心率曲线数据
  const hrChartData = weekRecords.slice(-7).map((r) => ({
    date: format(new Date(r.record_date), 'E', { locale: zhCN }),
    resting: r.resting_heart_rate,
    avg: r.avg_heart_rate,
  }));

  // 准备HRV趋势数据
  const hrvChartData = weekRecords.slice(-28).map((r) => ({
    date: format(new Date(r.record_date), 'MM/dd'),
    hrv: r.hrv,
  }));

  // 计算本周强度活动时间
  const weeklyIntensityMinutes = weekRecords.reduce((sum, r) => {
    return sum + (r.moderate_intensity_minutes || 0) + (r.vigorous_intensity_minutes || 0) * 2;
  }, 0);
  const intensityGoal = record?.intensity_minutes_goal || 150;
  const intensityProgress = Math.min((weeklyIntensityMinutes / intensityGoal) * 100, 100);

  // 计算7天平均静息心率
  const avg7DayRestingHR = weekRecords.length > 0
    ? Math.round(weekRecords.reduce((sum, r) => sum + (r.resting_heart_rate || 0), 0) / weekRecords.filter(r => r.resting_heart_rate).length)
    : null;

  // 计算今日运动数据
  const todayWorkouts = workoutsData?.filter(w => w.workout_date === today) || [];
  const totalWorkoutCalories = todayWorkouts.reduce((sum, w) => sum + (w.calories || 0), 0);
  const totalWorkoutDuration = todayWorkouts.reduce((sum, w) => sum + (w.duration_seconds || 0), 0);
  const totalWorkoutDistance = todayWorkouts.reduce((sum, w) => sum + (w.distance_meters || 0), 0);

  // 获取运动类型名称
  const getWorkoutTypeName = (type: string): string => {
    const typeMap: Record<string, string> = {
      running: '跑步',
      walking: '步行',
      cycling: '骑行',
      swimming: '游泳',
      strength: '力量训练',
      yoga: '瑜伽',
      hiking: '徒步',
      other: '其他',
    };
    return typeMap[type] || type;
  };

  // 获取餐食类型名称
  const getMealTypeName = (type: string): string => {
    const typeMap: Record<string, string> = {
      breakfast: '早餐',
      lunch: '午餐',
      dinner: '晚餐',
      snack: '加餐',
      extra: '其他',
    };
    return typeMap[type] || type;
  };

  // 计算能量差
  const bmrCalories = record?.bmr_calories || 1800; // 基础代谢，默认1800
  const totalCaloriesOut = (record?.calories_burned || 0); // 总消耗（包含基础代谢+活动消耗）
  const totalCaloriesIn = dietData?.total_calories || 0; // 摄入热量
  const energyBalance = totalCaloriesIn - totalCaloriesOut; // 能量差（正数=盈余，负数=亏损）

  if (isLoading) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-gray-100">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </main>
    );
  }

  if (error) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-gray-100 pt-4">
        <div className="text-center">
          <div className="text-6xl mb-4">❌</div>
          <h2 className="text-xl font-bold text-red-700 mb-2">获取数据失败</h2>
          <p className="text-gray-500 mb-4">{String(error)}</p>
          <pre className="text-xs text-left bg-gray-200 p-2 rounded max-w-md overflow-auto">
            API: {API_BASE}/daily-health/garmin/me
          </pre>
        </div>
      </main>
    );
  }

  if (!record) {
    return (
      <main className="min-h-screen flex items-center justify-center bg-gray-100 pt-4">
        <div className="text-center">
          <div className="text-6xl mb-4">📊</div>
          <h2 className="text-xl font-bold text-gray-700 mb-2">暂无健康数据</h2>
          <p className="text-gray-500 mb-4">请先同步 Garmin 数据</p>
          <p className="text-xs text-gray-400 mb-2">
            API返回: {JSON.stringify(recentData)}
          </p>
          <a 
            href="/settings#garmin" 
            className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
          >
            前往设置同步
          </a>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen p-4 md:p-6 bg-gradient-to-br from-gray-50 to-gray-100 pt-4 md:pt-4">
      <div className="max-w-7xl mx-auto">
        {/* 页面标题 */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-1">概览</h1>
            {record && (
              <p className="text-sm text-gray-500">
                数据日期: {format(new Date(record.record_date), 'yyyy年MM月dd日', { locale: zhCN })}
                {record.record_date !== today && (
                  <span className="ml-2 text-orange-500">(非今日数据)</span>
                )}
              </p>
            )}
          </div>
          <span className="text-blue-500 text-sm font-medium cursor-pointer hover:text-blue-600 hover:underline transition-colors">查看全部</span>
        </div>

        {/* 健康指标网格 - Garmin风格 */}
        {/* 第一行：重要指标 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          
          {/* 睡眠分数 */}
          <MetricCard icon="😴" title="睡眠分数">
            <div className="flex items-baseline gap-4">
              <span className={`text-5xl font-bold ${getSleepScoreColor(record?.sleep_score)}`}>
                {record?.sleep_score || '--'}
              </span>
              <div>
                <div className="text-lg text-gray-700">
                  {formatDuration(record?.total_sleep_duration)}
                </div>
                <div className="text-sm text-gray-500">持续时间</div>
              </div>
            </div>
            {/* 睡眠阶段柱状图 */}
            <div className="mt-4 h-24">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={sleepChartData} barGap={0}>
                  <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 10 }} />
                  <Bar dataKey="deep" stackId="a" fill="#1e40af" radius={[0, 0, 0, 0]} />
                  <Bar dataKey="light" stackId="a" fill="#3b82f6" />
                  <Bar dataKey="rem" stackId="a" fill="#c026d3" />
                  <Bar dataKey="awake" stackId="a" fill="#f97316" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>{formatSleepTime(record?.sleep_start_time)}</span>
              <span>{formatSleepTime(record?.sleep_end_time)}</span>
            </div>
          </MetricCard>

          {/* HRV状态 */}
          <MetricCard icon="💓" title="HRV状态">
            <div className="flex items-center gap-2 mb-2">
              <span className={`w-3 h-3 rounded-sm ${
                record?.hrv_status === 'BALANCED' ? 'bg-green-500' : 
                record?.hrv_status === 'UNBALANCED' ? 'bg-orange-500' : 'bg-gray-400'
              }`}></span>
              <span className={`text-xl font-bold ${getHrvStatusText(record?.hrv_status).color}`}>
                {getHrvStatusText(record?.hrv_status).text}
              </span>
            </div>
            <div className="text-3xl font-bold text-gray-800">
              {record?.hrv ? Math.round(record.hrv) : '--'} <span className="text-lg font-normal text-gray-500">毫秒</span>
            </div>
            <div className="text-sm text-gray-500">7天平均</div>
            
            {/* HRV状态条 */}
            <div className="flex gap-0.5 mt-3">
              {['red', 'orange', 'yellow', 'green', 'green'].map((color, i) => (
                <div key={i} className={`h-2 flex-1 rounded-sm bg-${color}-${i < 2 ? '500' : '400'}`}
                  style={{ backgroundColor: ['#ef4444', '#f97316', '#eab308', '#22c55e', '#22c55e'][i] }}
                />
              ))}
            </div>
            
            {/* HRV趋势图 */}
            <div className="mt-3 h-16">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={hrvChartData}>
                  <defs>
                    <linearGradient id="hrvGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="hrv" stroke="#10b981" fill="url(#hrvGradient)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="text-xs text-gray-400 text-center mt-1">过去 4 周</div>
          </MetricCard>

          {/* 身体电量 */}
          <MetricCard icon="🔋" title="身体电量">
            {(() => {
              const currentBattery = record?.body_battery_current;
              const peakBattery = record?.body_battery_most_charged ?? record?.body_battery_charged;
              const displayBattery = currentBattery ?? peakBattery;
              const hasCurrent = currentBattery !== null && currentBattery !== undefined;
              const hasPeak = peakBattery !== null && peakBattery !== undefined;
              
              const getBatteryColor = (value: number | null | undefined) => {
                if (value === null || value === undefined) return 'text-gray-400';
                if (value >= 80) return 'text-green-500';
                if (value >= 50) return 'text-yellow-500';
                return 'text-red-500';
              };
              
              const getBatteryBgColor = (value: number | null | undefined) => {
                if (value === null || value === undefined) return 'bg-gray-400';
                if (value >= 80) return 'bg-green-500';
                if (value >= 50) return 'bg-yellow-500';
                return 'bg-red-500';
              };
              
              return (
                <>
                  {/* 主显示：当前值或峰值 */}
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-4xl font-bold ${getBatteryColor(displayBattery)}`}>
                      {displayBattery ?? '--'}
                    </span>
                    <span className="text-lg text-gray-500">/100</span>
                  </div>
                  <div className="text-sm text-gray-500 mb-2">
                    {hasCurrent ? '当前' : hasPeak ? '峰值' : '暂无数据'}
                    {hasCurrent && (
                      <span className={`ml-2 ${getBatteryColor(currentBattery)}`}>
                        {currentBattery! >= 80 ? '充足' : currentBattery! >= 50 ? '中等' : '偏低'}
                      </span>
                    )}
                  </div>
                  
                  {/* 身体电量进度条 */}
                  <div className="relative h-3 bg-gray-200 rounded-full overflow-hidden mb-3">
                    <div 
                      className={`h-full transition-all ${getBatteryBgColor(displayBattery)}`}
                      style={{ width: `${Math.min(displayBattery ?? 0, 100)}%` }}
                    />
                  </div>
                  
                  {/* 身体电量详情：峰值、最低、消耗 */}
                  <div className="space-y-1 text-sm">
                    {hasCurrent && hasPeak && currentBattery !== peakBattery && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">📈 峰值</span>
                        <span className={`font-medium ${getBatteryColor(peakBattery)}`}>{peakBattery}</span>
                      </div>
                    )}
                    {record?.body_battery_lowest !== null && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">📉 最低</span>
                        <span className="text-gray-800 font-medium">{record.body_battery_lowest}</span>
                      </div>
                    )}
                    {record?.body_battery_drained !== null && (
                      <div className="flex justify-between">
                        <span className="text-gray-500">⚡ 消耗</span>
                        <span className="text-orange-600 font-medium">-{record.body_battery_drained}</span>
                      </div>
                    )}
                  </div>
                </>
              );
            })()}
          </MetricCard>

          {/* 心率 */}
          <MetricCard icon="❤️" title="心率">
            <div className="text-3xl font-bold text-gray-800">
              {avg7DayRestingHR || '--'} <span className="text-lg font-normal text-gray-500">bpm</span>
            </div>
            <div className="text-sm text-gray-500">过去 7 天平均静息心率</div>
            
            <div className="mt-2 text-2xl font-bold text-gray-800">
              {record?.resting_heart_rate || '--'} <span className="text-lg font-normal text-gray-500">bpm</span>
            </div>
            <div className="text-sm text-gray-500">静止</div>
            
            {/* 心率曲线 */}
            <div className="mt-3 h-16">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={hrChartData}>
                  <Line type="monotone" dataKey="resting" stroke="#3b82f6" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="text-xs text-gray-400 text-center mt-1">过去 7 天</div>
          </MetricCard>
        </div>

        {/* 运动与饮食 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
          {/* 今日运动 */}
          <MetricCard icon="🏋️" title="今日运动">
            {todayWorkouts.length > 0 ? (
              <div>
                <div className="text-3xl font-bold text-orange-500 mb-1">
                  {totalWorkoutCalories.toLocaleString()}
                  <span className="text-lg font-normal text-gray-500 ml-1">大卡</span>
                </div>
                <div className="text-sm text-gray-500 mb-3">运动消耗热量</div>
                
                {/* 运动统计 */}
                <div className="flex gap-4 text-sm mb-3">
                  <div>
                    <span className="text-gray-800 font-medium">
                      {Math.floor(totalWorkoutDuration / 60)}分钟
                    </span>
                    <span className="text-gray-500 ml-1">时长</span>
                  </div>
                  {totalWorkoutDistance > 0 && (
                    <div>
                      <span className="text-gray-800 font-medium">
                        {(totalWorkoutDistance / 1000).toFixed(2)}km
                      </span>
                      <span className="text-gray-500 ml-1">距离</span>
                    </div>
                  )}
                </div>

                {/* 运动记录列表 */}
                <div className="space-y-2 max-h-32 overflow-y-auto">
                  {todayWorkouts.map((workout) => (
                    <div key={workout.id} className="flex justify-between items-center text-sm bg-gray-50 rounded-lg px-3 py-2">
                      <div>
                        <span className="font-medium text-gray-800">
                          {workout.workout_name || getWorkoutTypeName(workout.workout_type)}
                        </span>
                        <span className="text-gray-400 ml-2">
                          {Math.floor((workout.duration_seconds || 0) / 60)}分钟
                        </span>
                      </div>
                      <span className="text-orange-500 font-medium">{workout.calories || 0}卡</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center py-4">
                <div className="text-4xl mb-2">🏃‍♂️</div>
                <p className="text-gray-500 text-sm">今日暂无运动记录</p>
                <p className="text-gray-400 text-xs mt-1">记录运动以追踪消耗热量</p>
              </div>
            )}
          </MetricCard>

          {/* 今日饮食 */}
          <MetricCard icon="🍽️" title="今日饮食">
            {dietData && dietData.meals_count > 0 ? (
              <div>
                <div className="text-3xl font-bold text-green-500 mb-1">
                  {dietData.total_calories.toLocaleString()}
                  <span className="text-lg font-normal text-gray-500 ml-1">大卡</span>
                </div>
                <div className="text-sm text-gray-500 mb-3">摄入热量</div>
                
                {/* 营养素摘要 */}
                <div className="grid grid-cols-3 gap-2 text-sm mb-3">
                  <div className="bg-blue-50 rounded-lg p-2 text-center">
                    <div className="font-medium text-blue-600">{dietData.total_protein.toFixed(0)}g</div>
                    <div className="text-xs text-gray-500">蛋白质</div>
                  </div>
                  <div className="bg-yellow-50 rounded-lg p-2 text-center">
                    <div className="font-medium text-yellow-600">{dietData.total_carbs.toFixed(0)}g</div>
                    <div className="text-xs text-gray-500">碳水</div>
                  </div>
                  <div className="bg-red-50 rounded-lg p-2 text-center">
                    <div className="font-medium text-red-500">{dietData.total_fat.toFixed(0)}g</div>
                    <div className="text-xs text-gray-500">脂肪</div>
                  </div>
                </div>

                {/* 餐食列表 */}
                <div className="space-y-1 max-h-24 overflow-y-auto">
                  {dietData.meals.map((meal) => (
                    <div key={meal.id} className="flex justify-between items-center text-sm">
                      <span className="text-gray-600">
                        {getMealTypeName(meal.meal_type)}
                      </span>
                      <span className="text-green-500 font-medium">{meal.calories || 0}卡</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="text-center py-4">
                <div className="text-4xl mb-2">🥗</div>
                <p className="text-gray-500 text-sm">今日暂无饮食记录</p>
                <p className="text-gray-400 text-xs mt-1">记录饮食以追踪摄入热量</p>
              </div>
            )}
          </MetricCard>

          {/* 能量平衡 */}
          <MetricCard icon="⚖️" title="能量平衡">
            <div>
              {/* 能量差显示 */}
              <div className={`text-3xl font-bold mb-1 ${
                energyBalance > 0 ? 'text-green-500' : energyBalance < 0 ? 'text-red-500' : 'text-gray-500'
              }`}>
                {energyBalance > 0 ? '+' : ''}{energyBalance.toLocaleString()}
                <span className="text-lg font-normal text-gray-500 ml-1">大卡</span>
              </div>
              <div className="text-sm text-gray-500 mb-3">
                {energyBalance > 0 ? '热量盈余' : energyBalance < 0 ? '热量亏损' : '能量平衡'}
              </div>
              
              {/* 能量构成进度条 */}
              <div className="space-y-3">
                {/* 消耗 */}
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-500">总消耗</span>
                    <span className="text-red-500 font-medium">{totalCaloriesOut.toLocaleString()} 大卡</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-red-400 rounded-full"
                      style={{ width: `${Math.min((totalCaloriesOut / Math.max(totalCaloriesOut, totalCaloriesIn, 1)) * 100, 100)}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>基础代谢: {bmrCalories}</span>
                    <span>活动: {record?.active_calories || 0}</span>
                  </div>
                </div>
                
                {/* 摄入 */}
                <div>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-500">总摄入</span>
                    <span className="text-green-500 font-medium">{totalCaloriesIn.toLocaleString()} 大卡</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-green-400 rounded-full"
                      style={{ width: `${Math.min((totalCaloriesIn / Math.max(totalCaloriesOut, totalCaloriesIn, 1)) * 100, 100)}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-gray-400 mt-1">
                    <span>{dietData?.meals_count || 0} 餐</span>
                    <span>{dietData?.total_protein?.toFixed(0) || 0}g 蛋白质</span>
                  </div>
                </div>
              </div>
              
              {/* 小提示 */}
              <div className="mt-3 text-xs text-gray-400 bg-gray-50 rounded-lg p-2">
                💡 {energyBalance < -500 ? '今日热量亏损较大，注意适当补充' : 
                    energyBalance > 500 ? '今日热量摄入较多，建议增加运动' : 
                    '能量摄入适中，继续保持！'}
              </div>
            </div>
          </MetricCard>
        </div>

        {/* 第二行：活动指标 */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
          {/* 强度活动时间 */}
          <MetricCard icon="🏃" title="强度活动时间">
            <div className="flex justify-center">
              <div className="relative w-28 h-28">
                <svg className="w-full h-full transform -rotate-90">
                  <circle
                    cx="56"
                    cy="56"
                    r="48"
                    stroke="#e5e7eb"
                    strokeWidth="8"
                    fill="none"
                  />
                  <circle
                    cx="56"
                    cy="56"
                    r="48"
                    stroke="#3b82f6"
                    strokeWidth="8"
                    fill="none"
                    strokeDasharray={`${intensityProgress * 3.02} 302`}
                    strokeLinecap="round"
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-3xl font-bold text-gray-800">{weeklyIntensityMinutes}</span>
                </div>
              </div>
            </div>
            <div className="text-center text-sm text-gray-500 mt-2">
              目标: {intensityGoal} 分钟
            </div>
            {/* 周几指示器 */}
            <div className="flex justify-center gap-3 mt-3">
              {['一', '二', '三', '四', '五', '六', '日'].map((day, i) => (
                <span key={day} className={`text-xs ${i === new Date().getDay() - 1 ? 'text-blue-500 font-bold' : 'text-gray-400'}`}>
                  {day}
                </span>
              ))}
            </div>
          </MetricCard>

          {/* 热量消耗 */}
          <MetricCard icon="🔥" title="热量消耗">
            <div className="text-4xl font-bold text-gray-800">
              {record?.calories_burned?.toLocaleString() || '--'}
            </div>
            <div className="flex gap-0 mt-3 rounded-full overflow-hidden h-3">
              <div 
                className="bg-red-500" 
                style={{ width: `${record?.active_calories && record?.calories_burned ? (record.active_calories / record.calories_burned) * 100 : 30}%` }}
              />
              <div 
                className="bg-blue-500" 
                style={{ width: `${record?.bmr_calories && record?.calories_burned ? (record.bmr_calories / record.calories_burned) * 100 : 70}%` }}
              />
            </div>
            <div className="flex justify-between mt-2 text-sm">
              <div>
                <span className="text-gray-800 font-medium">{record?.active_calories || '--'}</span>
                <span className="text-gray-500 ml-1">运动</span>
              </div>
              <div>
                <span className="text-gray-800 font-medium">{record?.bmr_calories || '--'}</span>
                <span className="text-gray-500 ml-1">静息消耗</span>
              </div>
            </div>
          </MetricCard>

          {/* 呼吸 */}
          <MetricCard icon="🌬️" title="呼吸">
            <div className="space-y-2">
              <div>
                <div className="text-3xl font-bold text-gray-800">
                  {record?.avg_respiration_awake ? Math.round(record.avg_respiration_awake) : '--'} <span className="text-lg font-normal text-gray-500">brpm</span>
                </div>
                <div className="text-sm text-gray-500">清醒平均</div>
              </div>
              <div>
                <div className="text-2xl font-bold text-gray-800">
                  {record?.avg_respiration_sleep ? Math.round(record.avg_respiration_sleep) : '--'} <span className="text-base font-normal text-gray-500">brpm</span>
                </div>
                <div className="text-sm text-gray-500">睡眠平均</div>
              </div>
              <div>
                <div className="text-lg text-gray-700">
                  {record?.lowest_respiration ? Math.round(record.lowest_respiration) : '--'}/{record?.highest_respiration ? Math.round(record.highest_respiration) : '--'} <span className="text-sm text-gray-500">brpm</span>
                </div>
                <div className="text-sm text-gray-500">低/高</div>
              </div>
            </div>
          </MetricCard>

          {/* VO2 Max */}
          <MetricCard icon="🏃‍♂️" title="跑步最大摄氧量">
            {record?.vo2max_running ? (
              <div>
                <div className="text-4xl font-bold text-blue-500">
                  {record.vo2max_running.toFixed(1)}
                </div>
                <div className="text-sm text-gray-500 mt-1">mL/kg/min</div>
              </div>
            ) : (
              <div className="text-center py-4">
                <div className="text-4xl mb-2">🏃</div>
                <p className="text-gray-500 text-sm">跟踪户外跑步情况，了解您当前的最大摄氧量。</p>
              </div>
            )}
          </MetricCard>
        </div>

        {/* 第三行：次要指标，紧凑排列 */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-4 gap-4">
          {/* 血氧饱和度 */}
          <MetricCard icon="🩸" title="脉搏血氧饱和度适应">
            {record?.spo2_avg !== null && record?.spo2_avg !== undefined ? (
              <div>
                <div className="text-4xl font-bold text-green-500">
                  {record.spo2_avg.toFixed(0)}%
                </div>
                <div className="text-sm text-gray-500 mt-1">
                  范围: {record.spo2_min !== null && record.spo2_min !== undefined ? record.spo2_min.toFixed(0) : '--'}% - {record.spo2_max !== null && record.spo2_max !== undefined ? record.spo2_max.toFixed(0) : '--'}%
                </div>
              </div>
            ) : (
              <div className="text-center py-4">
                <div className="text-4xl mb-2 opacity-50">🔴</div>
                <p className="text-gray-500 text-sm">今日无读数</p>
              </div>
            )}
          </MetricCard>

          {/* 步数 */}
          <MetricCard icon="👣" title="步数">
            <div className="text-3xl font-bold text-gray-800">
              {record?.steps?.toLocaleString() || '--'}
            </div>
          </MetricCard>

          {/* 距离 */}
          <MetricCard icon="📏" title="距离">
            <div className="text-3xl font-bold text-gray-800">
              {record?.distance_meters ? (record.distance_meters / 1000).toFixed(2) : '--'} <span className="text-lg font-normal text-gray-500">km</span>
            </div>
          </MetricCard>

          {/* 楼层 */}
          <MetricCard icon="🏢" title="楼层">
            <div className="text-3xl font-bold text-gray-800">
              {record?.floors_climbed || '--'} <span className="text-lg font-normal text-gray-500">层</span>
            </div>
          </MetricCard>

          {/* 压力 */}
          <MetricCard icon="😰" title="压力">
            <div className="text-3xl font-bold text-gray-800">
              {record?.stress_level || '--'}
            </div>
          </MetricCard>
        </div>
      </div>
    </main>
  );
}

export default function OverviewPage() {
  return (
    <ProtectedRoute>
      <OverviewContent />
    </ProtectedRoute>
  );
}

