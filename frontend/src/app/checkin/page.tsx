'use client';

import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api';

interface CheckinTemplate {
  id: number;
  user_id: number;
  name: string;
  description: string | null;
  icon: string;
  color: string;
  category: string;
  unit: string;
  default_target: number;
  total_checkins: number;
  current_streak: number;
  best_streak: number;
  last_checkin_date: string | null;
  is_active: boolean;
  today_completed: boolean;
}

interface CheckinRecord {
  id: number;
  template_id: number;
  checkin_date: string;
  value: number;
  target: number;
  completion_rate: number;
  template_name: string;
  template_icon: string;
  template_category: string;
  checkin_time: string;
}

interface DailySummary {
  date: string;
  total_templates: number;
  completed_templates: number;
  completion_rate: number;
  records: CheckinRecord[];
}

interface CheckinStats {
  total_checkins: number;
  total_templates: number;
  active_templates: number;
  current_streak: number;
  best_streak: number;
  checkins_today: number;
  checkins_this_week: number;
  checkins_this_month: number;
  completion_rate_today: number;
  by_category: Record<string, { count: number; total_checkins: number }>;
  daily_trend: { date: string; count: number; rate: number }[];
}

interface CalendarDayData {
  completed: boolean;
  rate: number;
  records: number;
}

interface CalendarData {
  year: number;
  month: number;
  days: Record<string, CalendarDayData>;
  total_days: number;
  completed_days: number;
  completion_rate: number;
}

const categoryLabels: Record<string, string> = {
  exercise: '运动',
  health: '健康',
  habit: '习惯',
  medicine: '用药',
  custom: '自定义',
};

const categoryColors: Record<string, string> = {
  exercise: 'from-blue-600 to-cyan-500',
  health: 'from-red-600 to-pink-500',
  habit: 'from-green-600 to-emerald-500',
  medicine: 'from-purple-600 to-violet-500',
  custom: 'from-orange-600 to-amber-500',
};

export default function CheckinPage() {
  const router = useRouter();
  const { user, isLoading: authLoading } = useAuth();
  const queryClient = useQueryClient();
  
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [showQuickCheckin, setShowQuickCheckin] = useState<CheckinTemplate | null>(null);
  const [quickValue, setQuickValue] = useState<number | ''>('');
  const [activeTab, setActiveTab] = useState<'checkin' | 'calendar' | 'stats'>('checkin');
  
  // 日历月份状态
  const today = new Date();
  const [calendarYear, setCalendarYear] = useState(today.getFullYear());
  const [calendarMonth, setCalendarMonth] = useState(today.getMonth() + 1);

  // 获取今日打卡汇总
  const { data: todaySummary, isLoading: summaryLoading } = useQuery<DailySummary>({
    queryKey: ['checkinToday'],
    queryFn: async () => {
      const response = await api.get('/checkin/records/today');
      return response.data;
    },
    enabled: !!user,
  });

  // 获取打卡模板
  const { data: templatesData, isLoading: templatesLoading } = useQuery<{
    templates: CheckinTemplate[];
    total: number;
    categories: Record<string, number>;
  }>({
    queryKey: ['checkinTemplates', selectedCategory],
    queryFn: async () => {
      const params = selectedCategory ? { category: selectedCategory } : {};
      const response = await api.get('/checkin/templates', { params });
      return response.data;
    },
    enabled: !!user,
  });

  // 获取统计数据
  const { data: stats } = useQuery<CheckinStats>({
    queryKey: ['checkinStats'],
    queryFn: async () => {
      const response = await api.get('/checkin/stats');
      return response.data;
    },
    enabled: !!user,
  });

  // 获取日历数据
  const { data: calendarData } = useQuery<CalendarData>({
    queryKey: ['checkinCalendar', calendarYear, calendarMonth],
    queryFn: async () => {
      const response = await api.get(`/checkin/calendar/${calendarYear}/${calendarMonth}`);
      return response.data;
    },
    enabled: !!user && activeTab === 'calendar',
  });

  // 生成日历网格
  const calendarGrid = useMemo(() => {
    const firstDay = new Date(calendarYear, calendarMonth - 1, 1);
    const lastDay = new Date(calendarYear, calendarMonth, 0);
    const daysInMonth = lastDay.getDate();
    const startDayOfWeek = firstDay.getDay(); // 0 = Sunday
    
    const grid: (number | null)[] = [];
    // 填充月初空白
    for (let i = 0; i < startDayOfWeek; i++) {
      grid.push(null);
    }
    // 填充日期
    for (let day = 1; day <= daysInMonth; day++) {
      grid.push(day);
    }
    return grid;
  }, [calendarYear, calendarMonth]);

  // 初始化默认模板
  const initMutation = useMutation({
    mutationFn: async () => {
      const response = await api.post('/checkin/templates/init-defaults');
      return response.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['checkinTemplates'] });
      queryClient.invalidateQueries({ queryKey: ['checkinStats'] });
      alert(data.message);
    },
  });

  // 快速打卡
  const quickCheckinMutation = useMutation({
    mutationFn: async ({ template_id, value }: { template_id: number; value?: number }) => {
      const response = await api.post('/checkin/records/quick', {
        template_id,
        value,
      });
      return response.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['checkinToday'] });
      queryClient.invalidateQueries({ queryKey: ['checkinTemplates'] });
      queryClient.invalidateQueries({ queryKey: ['checkinStats'] });
      setShowQuickCheckin(null);
      setQuickValue('');
    },
    onError: (error: any) => {
      alert(error.response?.data?.detail || '打卡失败');
    },
  });

  const handleQuickCheckin = (template: CheckinTemplate) => {
    if (template.today_completed) {
      alert('今日已完成此项打卡');
      return;
    }
    setShowQuickCheckin(template);
    setQuickValue(template.default_target);
  };

  const confirmQuickCheckin = () => {
    if (showQuickCheckin) {
      quickCheckinMutation.mutate({
        template_id: showQuickCheckin.id,
        value: quickValue || undefined,
      });
    }
  };

  if (authLoading || summaryLoading || templatesLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-purple-400"></div>
      </div>
    );
  }

  if (!user) {
    router.push('/login');
    return null;
  }

  const templates = templatesData?.templates || [];
  const categories = templatesData?.categories || {};

  // 没有模板时显示初始化提示
  if (templates.length === 0 && !selectedCategory) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
        <header className="bg-black/20 backdrop-blur-sm border-b border-white/10">
          <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-3">
            <button onClick={() => router.back()} className="text-white/70 hover:text-white">
              ← 返回
            </button>
            <h1 className="text-xl font-bold text-white">每日打卡</h1>
          </div>
        </header>
        
        <main className="max-w-4xl mx-auto px-4 py-12">
          <div className="text-center">
            <div className="text-6xl mb-6">🎯</div>
            <h2 className="text-2xl font-bold text-white mb-4">开始你的打卡之旅</h2>
            <p className="text-white/70 mb-8 max-w-md mx-auto">
              通过每日打卡，记录你的健康习惯，微小的进步将汇聚成巨大的改变
            </p>
            <button
              onClick={() => initMutation.mutate()}
              disabled={initMutation.isPending}
              className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-xl font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
            >
              {initMutation.isPending ? '初始化中...' : '✨ 初始化默认打卡项目'}
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      {/* 头部 */}
      <header className="bg-black/20 backdrop-blur-sm border-b border-white/10">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button onClick={() => router.back()} className="text-white/70 hover:text-white">
              ← 返回
            </button>
            <h1 className="text-xl font-bold text-white">每日打卡</h1>
          </div>
          <button
            onClick={() => router.push('/profile')}
            className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white/80 rounded-lg text-sm transition-colors"
          >
            👤 个人画像
          </button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-6 space-y-6">
        {/* Tab 切换 */}
        <div className="flex gap-2 bg-white/5 rounded-xl p-1">
          <button
            onClick={() => setActiveTab('checkin')}
            className={`flex-1 py-2.5 rounded-lg font-medium transition-all ${
              activeTab === 'checkin'
                ? 'bg-purple-600 text-white'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            📝 打卡
          </button>
          <button
            onClick={() => setActiveTab('calendar')}
            className={`flex-1 py-2.5 rounded-lg font-medium transition-all ${
              activeTab === 'calendar'
                ? 'bg-purple-600 text-white'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            📅 日历
          </button>
          <button
            onClick={() => setActiveTab('stats')}
            className={`flex-1 py-2.5 rounded-lg font-medium transition-all ${
              activeTab === 'stats'
                ? 'bg-purple-600 text-white'
                : 'text-white/70 hover:text-white hover:bg-white/10'
            }`}
          >
            📊 统计
          </button>
        </div>

        {/* ========== 打卡 Tab ========== */}
        {activeTab === 'checkin' && (
          <>
            {/* 今日进度 */}
            {todaySummary && (
              <div className="bg-gradient-to-r from-purple-600/30 to-pink-600/30 rounded-2xl p-6 border border-purple-500/30">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h2 className="text-white/70 text-sm mb-1">今日打卡进度</h2>
                    <div className="flex items-baseline gap-2">
                      <span className="text-4xl font-bold text-white">{todaySummary.completed_templates}</span>
                      <span className="text-white/50">/ {todaySummary.total_templates}</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={`text-3xl font-bold ${
                      todaySummary.completion_rate >= 80 ? 'text-green-400' :
                      todaySummary.completion_rate >= 50 ? 'text-yellow-400' : 'text-white'
                    }`}>
                      {todaySummary.completion_rate}%
                    </div>
                    <span className="text-white/50 text-sm">完成率</span>
                  </div>
                </div>
                {/* 进度条 */}
                <div className="h-2 bg-white/20 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      todaySummary.completion_rate >= 80 ? 'bg-green-500' :
                      todaySummary.completion_rate >= 50 ? 'bg-yellow-500' : 'bg-purple-500'
                    }`}
                    style={{ width: `${todaySummary.completion_rate}%` }}
                  />
                </div>
              </div>
            )}

            {/* 分类筛选 */}
            <div className="flex gap-2 overflow-x-auto pb-2">
              <button
                onClick={() => setSelectedCategory(null)}
                className={`px-4 py-2 rounded-lg font-medium whitespace-nowrap transition-all ${
                  !selectedCategory
                    ? 'bg-purple-600 text-white'
                    : 'bg-white/10 text-white/70 hover:bg-white/20'
                }`}
              >
                全部 ({templates.length})
              </button>
              {Object.entries(categories).map(([cat, count]) => (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(selectedCategory === cat ? null : cat)}
                  className={`px-4 py-2 rounded-lg font-medium whitespace-nowrap transition-all ${
                    selectedCategory === cat
                      ? 'bg-purple-600 text-white'
                      : 'bg-white/10 text-white/70 hover:bg-white/20'
                  }`}
                >
                  {categoryLabels[cat] || cat} ({count})
                </button>
              ))}
            </div>

            {/* 打卡项目列表 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {templates.map(template => (
                <div
                  key={template.id}
                  className={`relative overflow-hidden rounded-xl border transition-all ${
                    template.today_completed
                      ? 'bg-green-500/10 border-green-500/30'
                      : 'bg-white/5 border-white/10 hover:bg-white/10'
                  }`}
                >
                  {/* 背景装饰 */}
                  <div className={`absolute inset-0 bg-gradient-to-br ${categoryColors[template.category] || 'from-gray-600 to-gray-500'} opacity-5`} />
                  
                  <div className="relative p-4">
                    <div className="flex items-start justify-between mb-3">
                      <div className="flex items-center gap-3">
                        <span className="text-3xl">{template.icon}</span>
                        <div>
                          <h3 className="text-white font-medium">{template.name}</h3>
                          <span className="text-white/50 text-sm">
                            {categoryLabels[template.category]} · {template.default_target} {template.unit}
                          </span>
                        </div>
                      </div>
                      {template.today_completed && (
                        <span className="px-2 py-1 bg-green-500/20 text-green-400 text-xs rounded-full">
                          ✓ 已完成
                        </span>
                      )}
                    </div>
                    
                    {/* 统计信息 */}
                    <div className="flex items-center gap-4 text-sm text-white/50 mb-3">
                      <span>🔥 连续 {template.current_streak} 天</span>
                      <span>⭐ 最佳 {template.best_streak} 天</span>
                      <span>📊 共 {template.total_checkins} 次</span>
                    </div>
                    
                    {/* 打卡按钮 */}
                    <button
                      onClick={() => handleQuickCheckin(template)}
                      disabled={template.today_completed || quickCheckinMutation.isPending}
                      className={`w-full py-2.5 rounded-lg font-medium transition-all ${
                        template.today_completed
                          ? 'bg-white/5 text-white/30 cursor-not-allowed'
                          : 'bg-gradient-to-r from-purple-600 to-pink-600 text-white hover:opacity-90'
                      }`}
                    >
                      {template.today_completed ? '今日已打卡' : '立即打卡'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        {/* ========== 日历 Tab ========== */}
        {activeTab === 'calendar' && (
          <>
            {/* 月份切换 */}
            <div className="bg-white/5 rounded-xl p-4 border border-white/10">
              <div className="flex items-center justify-between mb-4">
                <button
                  onClick={() => {
                    if (calendarMonth === 1) {
                      setCalendarYear(calendarYear - 1);
                      setCalendarMonth(12);
                    } else {
                      setCalendarMonth(calendarMonth - 1);
                    }
                  }}
                  className="p-2 hover:bg-white/10 rounded-lg text-white/70 hover:text-white transition-colors"
                >
                  ← 上月
                </button>
                <h3 className="text-xl font-bold text-white">
                  {calendarYear}年{calendarMonth}月
                </h3>
                <button
                  onClick={() => {
                    if (calendarMonth === 12) {
                      setCalendarYear(calendarYear + 1);
                      setCalendarMonth(1);
                    } else {
                      setCalendarMonth(calendarMonth + 1);
                    }
                  }}
                  className="p-2 hover:bg-white/10 rounded-lg text-white/70 hover:text-white transition-colors"
                >
                  下月 →
                </button>
              </div>

              {/* 本月统计 */}
              {calendarData && (
                <div className="flex items-center justify-center gap-6 mb-4 py-3 bg-white/5 rounded-lg">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-green-400">{calendarData.completed_days}</div>
                    <div className="text-white/50 text-xs">打卡天数</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-white">{calendarData.total_days}</div>
                    <div className="text-white/50 text-xs">本月天数</div>
                  </div>
                  <div className="text-center">
                    <div className={`text-2xl font-bold ${
                      calendarData.completion_rate >= 80 ? 'text-green-400' :
                      calendarData.completion_rate >= 50 ? 'text-yellow-400' : 'text-white'
                    }`}>
                      {calendarData.completion_rate}%
                    </div>
                    <div className="text-white/50 text-xs">完成率</div>
                  </div>
                </div>
              )}

              {/* 星期标题 */}
              <div className="grid grid-cols-7 gap-1 mb-2">
                {['日', '一', '二', '三', '四', '五', '六'].map(day => (
                  <div key={day} className="text-center text-white/50 text-sm py-2">
                    {day}
                  </div>
                ))}
              </div>

              {/* 日历网格 */}
              <div className="grid grid-cols-7 gap-1">
                {calendarGrid.map((day, index) => {
                  if (day === null) {
                    return <div key={`empty-${index}`} className="aspect-square" />;
                  }
                  
                  const dayData = calendarData?.days[String(day)];
                  const isToday = 
                    calendarYear === today.getFullYear() && 
                    calendarMonth === today.getMonth() + 1 && 
                    day === today.getDate();
                  const isFuture = new Date(calendarYear, calendarMonth - 1, day) > today;
                  
                  return (
                    <div
                      key={day}
                      className={`aspect-square flex flex-col items-center justify-center rounded-lg transition-all ${
                        isToday ? 'ring-2 ring-purple-500' : ''
                      } ${
                        isFuture ? 'opacity-30' :
                        dayData?.completed ? 'bg-green-500/30' :
                        dayData?.records ? 'bg-yellow-500/30' :
                        'bg-white/5'
                      }`}
                    >
                      <span className={`text-sm font-medium ${
                        isToday ? 'text-purple-400' :
                        dayData?.completed ? 'text-green-400' :
                        'text-white/70'
                      }`}>
                        {day}
                      </span>
                      {dayData && dayData.records > 0 && (
                        <span className="text-xs text-white/50 mt-0.5">
                          {dayData.records}项
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 图例说明 */}
            <div className="flex items-center justify-center gap-6 text-sm text-white/70">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded bg-green-500/30"></div>
                <span>全部完成</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded bg-yellow-500/30"></div>
                <span>部分完成</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 rounded bg-white/5"></div>
                <span>未打卡</span>
              </div>
            </div>
          </>
        )}

        {/* ========== 统计 Tab ========== */}
        {activeTab === 'stats' && stats && (
          <>
            {/* 统计卡片 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-gradient-to-br from-purple-600/30 to-purple-800/30 rounded-xl p-4 border border-purple-500/30">
                <div className="text-3xl font-bold text-white">{stats.current_streak}</div>
                <div className="text-purple-300 text-sm">🔥 当前连续</div>
              </div>
              <div className="bg-gradient-to-br from-amber-600/30 to-amber-800/30 rounded-xl p-4 border border-amber-500/30">
                <div className="text-3xl font-bold text-white">{stats.best_streak}</div>
                <div className="text-amber-300 text-sm">⭐ 最佳连续</div>
              </div>
              <div className="bg-gradient-to-br from-blue-600/30 to-blue-800/30 rounded-xl p-4 border border-blue-500/30">
                <div className="text-3xl font-bold text-white">{stats.checkins_this_week}</div>
                <div className="text-blue-300 text-sm">📅 本周打卡</div>
              </div>
              <div className="bg-gradient-to-br from-green-600/30 to-green-800/30 rounded-xl p-4 border border-green-500/30">
                <div className="text-3xl font-bold text-white">{stats.total_checkins}</div>
                <div className="text-green-300 text-sm">📊 总打卡次数</div>
              </div>
            </div>

            {/* 分类统计 */}
            <div className="bg-white/5 rounded-xl p-6 border border-white/10">
              <h3 className="text-white font-medium mb-4">分类统计</h3>
              <div className="space-y-4">
                {Object.entries(stats.by_category).map(([category, data]) => (
                  <div key={category} className="flex items-center gap-4">
                    <div className="w-24 text-white/70 text-sm">
                      {categoryLabels[category] || category}
                    </div>
                    <div className="flex-1">
                      <div className="h-4 bg-white/10 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full bg-gradient-to-r ${categoryColors[category] || 'from-gray-500 to-gray-600'}`}
                          style={{ width: `${Math.min((data.total_checkins / (stats.total_checkins || 1)) * 100, 100)}%` }}
                        />
                      </div>
                    </div>
                    <div className="text-white font-medium w-16 text-right">
                      {data.total_checkins}次
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 7天趋势图 */}
            {stats.daily_trend.length > 0 && (
              <div className="bg-white/5 rounded-xl p-6 border border-white/10">
                <h3 className="text-white font-medium mb-4">最近7天趋势</h3>
                <div className="flex items-end justify-between h-40 gap-2">
                  {stats.daily_trend.map((day) => (
                    <div key={day.date} className="flex-1 flex flex-col items-center gap-2">
                      <div className="text-white/50 text-xs mb-1">{Math.round(day.rate)}%</div>
                      <div
                        className={`w-full rounded-t transition-all ${
                          day.rate >= 80 ? 'bg-gradient-to-t from-green-600 to-green-400' :
                          day.rate >= 50 ? 'bg-gradient-to-t from-yellow-600 to-yellow-400' :
                          day.rate > 0 ? 'bg-gradient-to-t from-purple-600 to-purple-400' : 'bg-white/10'
                        }`}
                        style={{ height: `${Math.max(day.rate, 5)}%` }}
                      />
                      <span className="text-white/50 text-xs">
                        {new Date(day.date).getDate()}日
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* 快速打卡弹窗 */}
      {showQuickCheckin && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-slate-800 rounded-2xl p-6 w-full max-w-sm border border-white/20">
            <div className="flex items-center gap-3 mb-6">
              <span className="text-4xl">{showQuickCheckin.icon}</span>
              <div>
                <h3 className="text-xl font-bold text-white">{showQuickCheckin.name}</h3>
                <span className="text-white/50 text-sm">
                  目标: {showQuickCheckin.default_target} {showQuickCheckin.unit}
                </span>
              </div>
            </div>
            
            <div className="mb-6">
              <label className="block text-white/70 text-sm mb-2">完成数量</label>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => setQuickValue(prev => Math.max(0, (Number(prev) || 0) - 1))}
                  className="w-12 h-12 bg-white/10 hover:bg-white/20 text-white text-xl rounded-lg transition-colors"
                >
                  -
                </button>
                <input
                  type="number"
                  value={quickValue}
                  onChange={e => setQuickValue(e.target.value ? Number(e.target.value) : '')}
                  className="flex-1 bg-white/10 border border-white/20 rounded-lg px-4 py-3 text-white text-center text-xl focus:outline-none focus:border-purple-500"
                />
                <button
                  onClick={() => setQuickValue(prev => (Number(prev) || 0) + 1)}
                  className="w-12 h-12 bg-white/10 hover:bg-white/20 text-white text-xl rounded-lg transition-colors"
                >
                  +
                </button>
              </div>
              <span className="text-white/40 text-xs mt-1 block text-center">
                单位: {showQuickCheckin.unit}
              </span>
            </div>
            
            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowQuickCheckin(null);
                  setQuickValue('');
                }}
                className="flex-1 py-3 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={confirmQuickCheckin}
                disabled={quickCheckinMutation.isPending}
                className="flex-1 py-3 bg-gradient-to-r from-purple-600 to-pink-600 text-white rounded-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {quickCheckinMutation.isPending ? '打卡中...' : '确认打卡'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
