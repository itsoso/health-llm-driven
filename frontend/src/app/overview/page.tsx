'use client';

import { useState, useEffect, useRef } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { api } from '@/services/api/client';
import { format, subDays, startOfWeek } from 'date-fns';
import { utcToZonedTime } from 'date-fns-tz';
import { zhCN } from 'date-fns/locale';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

import { GarminData, WorkoutSummary, DailyDietSummary } from './components/types';
import HealthMetricsCards from './components/HealthMetricsCards';
import WorkoutDietCards from './components/WorkoutDietCards';
import ActivityMetricsCards from './components/ActivityMetricsCards';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || '/api';

function OverviewContent() {
  const { token } = useAuth();

  useEffect(() => { document.title = '健康总览 | 健康管理'; }, []);

  // 快速记录
  const [quickInput, setQuickInput] = useState('');
  const [quickToast, setQuickToast] = useState('');
  const quickToastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const quickMutation = useMutation({
    mutationFn: (text: string) => api.post('/quick-record', { text }),
    onSuccess: (res: any) => {
      if (quickToastTimer.current) clearTimeout(quickToastTimer.current);
      setQuickToast(res.data?.message || '记录成功');
      setQuickInput('');
      quickToastTimer.current = setTimeout(() => setQuickToast(''), 3000);
    },
    onError: (err: any) => {
      if (quickToastTimer.current) clearTimeout(quickToastTimer.current);
      setQuickToast(err?.response?.data?.detail || '格式不对，试试「喝水500」「体重71.5」');
      quickToastTimer.current = setTimeout(() => setQuickToast(''), 4000);
    },
  });
  // 使用北京时间 (UTC+8) 计算日期
  const TIMEZONE = 'Asia/Shanghai';
  const nowInTimezone = utcToZonedTime(new Date(), TIMEZONE);
  const today = format(nowInTimezone, 'yyyy-MM-dd');
  const monthAgo = format(subDays(nowInTimezone, 30), 'yyyy-MM-dd');

  // 计算本周周一（用于强度活动时间计算）
  const mondayOfThisWeek = startOfWeek(nowInTimezone, { weekStartsOn: 1 });
  const mondayDateStr = format(mondayOfThisWeek, 'yyyy-MM-dd');

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
      return data;
    },
    enabled: !!token,
  });

  // 获取本周运动记录
  const { data: workoutsData } = useQuery<WorkoutSummary[]>({
    queryKey: ['workouts-week', mondayDateStr],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/workout/me?days=7`, {
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

  // 后端直接返回数组
  const allRecords = recentData || [];

  // 按日期降序排序，找到第一条有实际数据的记录
  const sortedRecords = [...allRecords].sort((a, b) =>
    new Date(b.record_date).getTime() - new Date(a.record_date).getTime()
  );

  // 找到有实际数据的记录（睡眠分数或步数不为空）
  const record = sortedRecords.find(r =>
    r.sleep_score !== null || r.steps !== null || r.resting_heart_rate !== null
  ) || sortedRecords[0];

  // 获取最新的 VO2max 数据（可能不在今天）
  const latestVO2maxRecord = sortedRecords.find(r => r.vo2max_running !== null);
  const vo2maxValue = latestVO2maxRecord?.vo2max_running || record?.vo2max_running;

  // 最近7天数据用于图表
  const weekRecords = sortedRecords.slice(0, 7).reverse();

  // 准备睡眠柱状图数据
  const sleepChartData = weekRecords.slice(-7).map((r) => ({
    date: format(new Date(r.record_date), 'E', { locale: zhCN }),
    deep: r.total_sleep_duration ? Math.round((r.total_sleep_duration * 0.2)) : 0,
    light: r.total_sleep_duration ? Math.round((r.total_sleep_duration * 0.5)) : 0,
    rem: r.total_sleep_duration ? Math.round((r.total_sleep_duration * 0.2)) : 0,
    awake: r.total_sleep_duration ? Math.round((r.total_sleep_duration * 0.1)) : 0,
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
  const thisWeekRecords = sortedRecords.filter(r => r.record_date >= mondayDateStr);
  const weeklyIntensityMinutes = thisWeekRecords.reduce((sum, r) => {
    const moderate = r.moderate_intensity_minutes || 0;
    const vigorous = r.vigorous_intensity_minutes || 0;
    return sum + moderate + vigorous * 2;
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

  // 计算能量差
  const bmrCalories = record?.bmr_calories || 1800;
  const totalCaloriesOut = (record?.calories_burned || 0);
  const totalCaloriesIn = dietData?.total_calories || 0;
  const energyBalance = totalCaloriesIn - totalCaloriesOut;

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
          <div className="text-6xl mb-4">📈</div>
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
        </div>

        {/* 第一行：睡眠/HRV/身体电量/心率 */}
        <HealthMetricsCards
          record={record}
          sleepChartData={sleepChartData}
          hrChartData={hrChartData}
          hrvChartData={hrvChartData}
          avg7DayRestingHR={avg7DayRestingHR}
        />

        {/* 第二行：运动/饮食/能量平衡 */}
        <WorkoutDietCards
          record={record}
          todayWorkouts={todayWorkouts}
          totalWorkoutCalories={totalWorkoutCalories}
          totalWorkoutDuration={totalWorkoutDuration}
          totalWorkoutDistance={totalWorkoutDistance}
          dietData={dietData}
          totalCaloriesOut={totalCaloriesOut}
          totalCaloriesIn={totalCaloriesIn}
          energyBalance={energyBalance}
          bmrCalories={bmrCalories}
        />

        {/* 第三行+第四行：活动指标 */}
        <ActivityMetricsCards
          record={record}
          weeklyIntensityMinutes={weeklyIntensityMinutes}
          intensityGoal={intensityGoal}
          intensityProgress={intensityProgress}
          vo2maxValue={vo2maxValue}
          latestVO2maxRecord={latestVO2maxRecord}
        />
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
