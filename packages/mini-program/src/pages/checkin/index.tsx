import { useState, useEffect, useCallback, useMemo } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { request } from '../../services/request';
import './index.scss';

interface CheckinTemplate {
  id: number;
  name: string;
  icon: string;
  category: string;
  unit: string;
  default_target: number;
  total_checkins: number;
  current_streak: number;
  best_streak: number;
  today_completed: boolean;
}

interface DailySummary {
  date: string;
  total_templates: number;
  completed_templates: number;
  completion_rate: number;
}

interface CheckinStats {
  total_checkins: number;
  current_streak: number;
  best_streak: number;
  checkins_today: number;
  checkins_this_week: number;
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

export default function CheckinPage() {
  const [loading, setLoading] = useState(true);
  const [templates, setTemplates] = useState<CheckinTemplate[]>([]);
  const [summary, setSummary] = useState<DailySummary | null>(null);
  const [stats, setStats] = useState<CheckinStats | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [showModal, setShowModal] = useState(false);
  const [currentTemplate, setCurrentTemplate] = useState<CheckinTemplate | null>(null);
  const [checkinValue, setCheckinValue] = useState<number>(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  
  // Tab 和日历状态
  const [activeTab, setActiveTab] = useState<'checkin' | 'calendar'>('checkin');
  const today = new Date();
  const [calendarYear, setCalendarYear] = useState(today.getFullYear());
  const [calendarMonth, setCalendarMonth] = useState(today.getMonth() + 1);
  const [calendarData, setCalendarData] = useState<CalendarData | null>(null);
  
  // 生成日历网格
  const calendarGrid = useMemo(() => {
    const firstDay = new Date(calendarYear, calendarMonth - 1, 1);
    const lastDay = new Date(calendarYear, calendarMonth, 0);
    const daysInMonth = lastDay.getDate();
    const startDayOfWeek = firstDay.getDay();
    
    const grid: (number | null)[] = [];
    for (let i = 0; i < startDayOfWeek; i++) {
      grid.push(null);
    }
    for (let day = 1; day <= daysInMonth; day++) {
      grid.push(day);
    }
    return grid;
  }, [calendarYear, calendarMonth]);

  // 加载数据
  const loadData = useCallback(async () => {
    const token = Taro.getStorageSync('access_token');
    if (!token) {
      Taro.redirectTo({ url: '/pages/index/index' });
      return;
    }

    try {
      setLoading(true);

      // 并行请求
      const [templatesRes, summaryRes, statsRes] = await Promise.all([
        request<{ templates: CheckinTemplate[] }>({
          url: '/checkin/templates',
          method: 'GET',
          params: selectedCategory ? { category: selectedCategory } : {},
        }),
        request<DailySummary>({
          url: '/checkin/records/today',
          method: 'GET',
        }),
        request<CheckinStats>({
          url: '/checkin/stats',
          method: 'GET',
        }),
      ]);

      // request 函数直接返回响应数据
      setTemplates(templatesRes?.templates || []);
      setSummary(summaryRes);
      setStats(statsRes);
    } catch (error) {
      console.error('加载数据失败:', error);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  }, [selectedCategory]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 加载日历数据
  useEffect(() => {
    if (activeTab === 'calendar') {
      loadCalendarData();
    }
  }, [activeTab, calendarYear, calendarMonth]);

  const loadCalendarData = async () => {
    try {
      const res = await request<CalendarData>({
        url: `/checkin/calendar/${calendarYear}/${calendarMonth}`,
        method: 'GET',
      });
      // request 函数直接返回响应数据
      setCalendarData(res);
    } catch (error) {
      console.error('加载日历数据失败:', error);
    }
  };

  // 初始化默认模板
  const initTemplates = async () => {
    try {
      Taro.showLoading({ title: '初始化中...' });
      await request({
        url: '/checkin/templates/init-defaults',
        method: 'POST',
      });
      Taro.showToast({ title: '初始化成功', icon: 'success' });
      loadData();
    } catch (error) {
      console.error('初始化失败:', error);
      Taro.showToast({ title: '初始化失败', icon: 'none' });
    } finally {
      Taro.hideLoading();
    }
  };

  // 打开打卡弹窗
  const openCheckin = (template: CheckinTemplate) => {
    if (template.today_completed) {
      Taro.showToast({ title: '今日已完成', icon: 'none' });
      return;
    }
    setCurrentTemplate(template);
    setCheckinValue(template.default_target);
    setShowModal(true);
  };

  // 确认打卡
  const confirmCheckin = async () => {
    if (!currentTemplate || isSubmitting) return;

    try {
      setIsSubmitting(true);
      await request({
        url: '/checkin/records/quick',
        method: 'POST',
        data: {
          template_id: currentTemplate.id,
          value: checkinValue,
        },
      });

      Taro.showToast({ title: '打卡成功！', icon: 'success' });
      setShowModal(false);
      setCurrentTemplate(null);
      loadData();
    } catch (error: any) {
      Taro.showToast({
        title: error.message || '打卡失败',
        icon: 'none',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  // 获取分类列表
  const categories = stats?.by_category
    ? Object.keys(stats.by_category)
    : [];

  if (loading) {
    return (
      <View className="checkin-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  // 没有模板时显示初始化
  if (templates.length === 0) {
    return (
      <View className="checkin-page empty">
        <Text className="empty-icon">🎯</Text>
        <Text className="empty-title">开始你的打卡之旅</Text>
        <Text className="empty-desc">
          通过每日打卡，记录健康习惯
        </Text>
        <View className="init-btn" onClick={initTemplates}>
          ✨ 初始化默认项目
        </View>
      </View>
    );
  }

  return (
    <View className="checkin-page">
      {/* Tab 切换 */}
      <View className="tab-bar">
        <View
          className={`tab-item ${activeTab === 'checkin' ? 'active' : ''}`}
          onClick={() => setActiveTab('checkin')}
        >
          <Text>📝 打卡</Text>
        </View>
        <View
          className={`tab-item ${activeTab === 'calendar' ? 'active' : ''}`}
          onClick={() => setActiveTab('calendar')}
        >
          <Text>📅 日历</Text>
        </View>
      </View>

      {/* 打卡 Tab */}
      {activeTab === 'checkin' && (
        <>
          {/* 今日进度 */}
      {summary && (
        <View className="progress-card">
          <View className="progress-header">
            <View className="progress-left">
              <Text className="progress-label">今日打卡进度</Text>
              <View className="progress-value">
                <Text className="progress-completed">{summary.completed_templates}</Text>
                <Text className="progress-total">/ {summary.total_templates}</Text>
              </View>
            </View>
            <View className="progress-right">
              <Text className={`progress-rate ${summary.completion_rate >= 80 ? 'high' : summary.completion_rate >= 50 ? 'medium' : ''}`}>
                {summary.completion_rate}%
              </Text>
              <Text className="progress-rate-label">完成率</Text>
            </View>
          </View>
          <View className="progress-bar">
            <View
              className={`progress-fill ${summary.completion_rate >= 80 ? 'high' : summary.completion_rate >= 50 ? 'medium' : ''}`}
              style={{ width: `${summary.completion_rate}%` }}
            />
          </View>
        </View>
      )}

      {/* 统计卡片 */}
      {stats && (
        <View className="stats-row">
          <View className="stat-card">
            <Text className="stat-value">{stats.current_streak}</Text>
            <Text className="stat-label">当前连续</Text>
          </View>
          <View className="stat-card">
            <Text className="stat-value">{stats.best_streak}</Text>
            <Text className="stat-label">最佳连续</Text>
          </View>
          <View className="stat-card">
            <Text className="stat-value">{stats.checkins_this_week}</Text>
            <Text className="stat-label">本周打卡</Text>
          </View>
          <View className="stat-card">
            <Text className="stat-value">{stats.total_checkins}</Text>
            <Text className="stat-label">总次数</Text>
          </View>
        </View>
      )}

      {/* 分类筛选 */}
      <ScrollView scrollX className="category-scroll">
        <View className="category-list">
          <View
            className={`category-item ${!selectedCategory ? 'active' : ''}`}
            onClick={() => setSelectedCategory(null)}
          >
            全部
          </View>
          {categories.map(cat => (
            <View
              key={cat}
              className={`category-item ${selectedCategory === cat ? 'active' : ''}`}
              onClick={() => setSelectedCategory(selectedCategory === cat ? null : cat)}
            >
              {categoryLabels[cat] || cat}
            </View>
          ))}
        </View>
      </ScrollView>

      {/* 打卡项目列表 */}
      <ScrollView scrollY className="template-scroll" enhanced showScrollbar={false}>
        <View className="template-list">
          {templates.map(template => (
            <View
              key={template.id}
              className={`template-card ${template.today_completed ? 'completed' : ''}`}
              hoverClass="template-card-hover"
              onClick={() => openCheckin(template)}
            >
              <View className="template-header">
                <View className="template-info">
                  <Text className="template-icon">{template.icon}</Text>
                  <View className="template-text">
                    <Text className="template-name">{template.name}</Text>
                    <Text className="template-meta">
                      {categoryLabels[template.category]} · {template.default_target} {template.unit}
                    </Text>
                  </View>
                </View>
                {template.today_completed && (
                  <View className="completed-badge">✓</View>
                )}
              </View>

              <View className="template-stats">
                <Text className="stat-item">🔥 {template.current_streak}天</Text>
                <Text className="stat-item">⭐ {template.best_streak}天</Text>
                <Text className="stat-item">📊 {template.total_checkins}次</Text>
              </View>

              <View className={`checkin-btn ${template.today_completed ? 'disabled' : ''}`}>
                {template.today_completed ? '今日已打卡' : '立即打卡'}
              </View>
            </View>
          ))}
        </View>
      </ScrollView>
        </>
      )}

      {/* 日历 Tab */}
      {activeTab === 'calendar' && (
        <View className="calendar-container">
          {/* 月份切换 */}
          <View className="calendar-header">
            <View
              className="month-btn"
              onClick={() => {
                if (calendarMonth === 1) {
                  setCalendarYear(calendarYear - 1);
                  setCalendarMonth(12);
                } else {
                  setCalendarMonth(calendarMonth - 1);
                }
              }}
            >
              <Text>← 上月</Text>
            </View>
            <Text className="month-title">{calendarYear}年{calendarMonth}月</Text>
            <View
              className="month-btn"
              onClick={() => {
                if (calendarMonth === 12) {
                  setCalendarYear(calendarYear + 1);
                  setCalendarMonth(1);
                } else {
                  setCalendarMonth(calendarMonth + 1);
                }
              }}
            >
              <Text>下月 →</Text>
            </View>
          </View>

          {/* 月份统计 */}
          {calendarData && (
            <View className="month-stats">
              <View className="month-stat-item">
                <Text className="month-stat-value green">{calendarData.completed_days}</Text>
                <Text className="month-stat-label">打卡天数</Text>
              </View>
              <View className="month-stat-item">
                <Text className="month-stat-value">{calendarData.total_days}</Text>
                <Text className="month-stat-label">本月天数</Text>
              </View>
              <View className="month-stat-item">
                <Text className={`month-stat-value ${calendarData.completion_rate >= 80 ? 'green' : calendarData.completion_rate >= 50 ? 'yellow' : ''}`}>
                  {calendarData.completion_rate}%
                </Text>
                <Text className="month-stat-label">完成率</Text>
              </View>
            </View>
          )}

          {/* 星期标题 */}
          <View className="weekday-row">
            {['日', '一', '二', '三', '四', '五', '六'].map(day => (
              <Text key={day} className="weekday-item">{day}</Text>
            ))}
          </View>

          {/* 日历网格 */}
          <View className="calendar-grid">
            {calendarGrid.map((day, index) => {
              if (day === null) {
                return <View key={`empty-${index}`} className="calendar-day empty" />;
              }
              
              const dayData = calendarData?.days[String(day)];
              const isToday = 
                calendarYear === today.getFullYear() && 
                calendarMonth === today.getMonth() + 1 && 
                day === today.getDate();
              const isFuture = new Date(calendarYear, calendarMonth - 1, day) > today;
              
              return (
                <View
                  key={day}
                  className={`calendar-day ${isToday ? 'today' : ''} ${isFuture ? 'future' : ''} ${dayData?.completed ? 'completed' : dayData?.records ? 'partial' : ''}`}
                >
                  <Text className="day-number">{day}</Text>
                  {dayData && dayData.records > 0 && (
                    <Text className="day-count">{dayData.records}项</Text>
                  )}
                </View>
              );
            })}
          </View>

          {/* 图例 */}
          <View className="calendar-legend">
            <View className="legend-item">
              <View className="legend-dot completed" />
              <Text className="legend-text">全部完成</Text>
            </View>
            <View className="legend-item">
              <View className="legend-dot partial" />
              <Text className="legend-text">部分完成</Text>
            </View>
            <View className="legend-item">
              <View className="legend-dot" />
              <Text className="legend-text">未打卡</Text>
            </View>
          </View>
        </View>
      )}

      {/* 打卡弹窗 */}
      {showModal && currentTemplate && (
        <View className="modal-mask" onClick={() => setShowModal(false)}>
          <View className="modal-content" onClick={e => e.stopPropagation()}>
            <View className="modal-header">
              <Text className="modal-icon">{currentTemplate.icon}</Text>
              <View className="modal-title-group">
                <Text className="modal-title">{currentTemplate.name}</Text>
                <Text className="modal-target">
                  目标: {currentTemplate.default_target} {currentTemplate.unit}
                </Text>
              </View>
            </View>

            <View className="modal-input-group">
              <Text className="input-label">完成数量</Text>
              <View className="input-row">
                <View
                  className="input-btn"
                  onClick={() => setCheckinValue(Math.max(0, checkinValue - 1))}
                >
                  -
                </View>
                <View className="input-value">{checkinValue}</View>
                <View
                  className="input-btn"
                  onClick={() => setCheckinValue(checkinValue + 1)}
                >
                  +
                </View>
              </View>
              <Text className="input-unit">{currentTemplate.unit}</Text>
            </View>

            <View className="modal-actions">
              <View className="modal-btn cancel" onClick={() => setShowModal(false)}>
                取消
              </View>
              <View
                className={`modal-btn confirm ${isSubmitting ? 'disabled' : ''}`}
                onClick={confirmCheckin}
              >
                {isSubmitting ? '提交中...' : '确认打卡'}
              </View>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}
