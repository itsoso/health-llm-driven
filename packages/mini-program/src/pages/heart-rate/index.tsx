/**
 * 心率追踪页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Canvas } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get } from '../../services/request';
import './index.scss';

/**
 * 获取北京时间的日期字符串 (YYYY-MM-DD)
 */
function getBeijingDateString(date: Date = new Date()): string {
  // 北京时间 = UTC+8
  const beijingOffset = 8 * 60; // 8小时，转换为分钟
  const localOffset = date.getTimezoneOffset(); // 本地时区偏移（分钟，UTC为0，北京为-480）
  const beijingTime = new Date(date.getTime() + (beijingOffset + localOffset) * 60 * 1000);
  
  const year = beijingTime.getFullYear();
  const month = String(beijingTime.getMonth() + 1).padStart(2, '0');
  const day = String(beijingTime.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

interface HeartRatePoint {
  timestamp: number;
  time: string;
  value: number;
}

interface HeartRateSummary {
  record_date: string;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  min_heart_rate: number | null;
  resting_heart_rate: number | null;
}

interface DailyHeartRate {
  record_date: string;
  summary: HeartRateSummary;
  heart_rate_timeline: HeartRatePoint[];
  hrv: number | null;
}

interface HeartRateTrend {
  days: number;
  daily_data: HeartRateSummary[];
  hrv_data: { date: string; hrv: number }[];
  avg_heart_rate: number | null;
  avg_resting_heart_rate: number | null;
  avg_hrv: number | null;
  max_heart_rate: number | null;
  min_heart_rate: number | null;
}

export default function HeartRate() {
  const [loading, setLoading] = useState(true);
  const [dailyData, setDailyData] = useState<DailyHeartRate | null>(null);
  const [trendData, setTrendData] = useState<HeartRateTrend | null>(null);
  // 使用北京时间获取当前日期
  const [selectedDate, setSelectedDate] = useState(getBeijingDateString());
  const [viewMode, setViewMode] = useState<'day' | 'week'>('day');

  useEffect(() => {
    loadData();
  }, [selectedDate]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [daily, trend] = await Promise.all([
        get<DailyHeartRate>(`/heart-rate/me/daily/${selectedDate}`).catch(() => null),
        get<HeartRateTrend>('/heart-rate/me/trend', { days: 7 }).catch(() => null),
      ]);
      setDailyData(daily);
      setTrendData(trend);
    } catch (error) {
      console.error('加载心率数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = () => {
    Taro.showLoading({ title: '刷新中...' });
    loadData().finally(() => {
      Taro.hideLoading();
      Taro.showToast({ title: '刷新成功', icon: 'success', duration: 1000 });
    });
  };

  // 切换日期（基于北京时间）
  const changeDate = (offset: number) => {
    const current = new Date(selectedDate + 'T00:00:00+08:00'); // 解析为北京时间
    current.setDate(current.getDate() + offset);
    const todayStr = getBeijingDateString();
    const newDateStr = getBeijingDateString(current);
    
    // 不能超过今天
    if (newDateStr <= todayStr) {
      setSelectedDate(newDateStr);
    }
  };

  // 格式化日期显示（基于北京时间）
  const formatDateDisplay = (dateStr: string) => {
    const date = new Date(dateStr + 'T00:00:00+08:00');
    const todayStr = getBeijingDateString();
    const yesterdayDate = new Date();
    yesterdayDate.setDate(yesterdayDate.getDate() - 1);
    const yesterdayStr = getBeijingDateString(yesterdayDate);
    
    if (dateStr === todayStr) return '今天';
    if (dateStr === yesterdayStr) return '昨天';
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  };

  // 获取心率状态
  const getHeartRateStatus = (hr: number | null) => {
    if (!hr) return { text: '未知', color: '#9CA3AF', bg: 'rgba(156, 163, 175, 0.2)' };
    if (hr < 50) return { text: '偏低', color: '#3B82F6', bg: 'rgba(59, 130, 246, 0.2)' };
    if (hr <= 60) return { text: '优秀', color: '#10B981', bg: 'rgba(16, 185, 129, 0.2)' };
    if (hr <= 80) return { text: '正常', color: '#10B981', bg: 'rgba(16, 185, 129, 0.2)' };
    return { text: '偏高', color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.2)' };
  };

  // 获取HRV状态
  const getHrvStatus = (hrv: number | null) => {
    if (!hrv) return { text: '未知', color: '#9CA3AF' };
    if (hrv >= 50) return { text: '优秀', color: '#10B981' };
    if (hrv >= 30) return { text: '良好', color: '#3B82F6' };
    if (hrv >= 20) return { text: '一般', color: '#F59E0B' };
    return { text: '较低', color: '#EF4444' };
  };

  // 渲染简易心率曲线（使用纯View模拟）
  const renderHeartRateChart = () => {
    const timeline = dailyData?.heart_rate_timeline || [];
    if (timeline.length === 0) {
      return (
        <View className="chart-empty">
          <Text>暂无心率曲线数据</Text>
        </View>
      );
    }

    // 找出最大最小值
    const values = timeline.map(p => p.value);
    const maxVal = Math.max(...values);
    const minVal = Math.min(...values);
    const range = maxVal - minVal || 1;

    // 采样：最多显示48个点（每30分钟一个）
    const sampledData = timeline.length > 48 
      ? timeline.filter((_, i) => i % Math.ceil(timeline.length / 48) === 0)
      : timeline;

    return (
      <View className="chart-container">
        <View className="chart-y-axis">
          <Text className="y-label">{maxVal}</Text>
          <Text className="y-label">{Math.round((maxVal + minVal) / 2)}</Text>
          <Text className="y-label">{minVal}</Text>
        </View>
        <View className="chart-area">
          <View className="chart-bars">
            {sampledData.map((point, index) => {
              const height = ((point.value - minVal) / range) * 100;
              return (
                <View key={index} className="bar-wrapper">
                  <View 
                    className="bar" 
                    style={{ 
                      height: `${Math.max(height, 5)}%`,
                      backgroundColor: point.value > 100 ? '#EF4444' : 
                                      point.value > 80 ? '#F59E0B' : '#10B981'
                    }} 
                  />
                </View>
              );
            })}
          </View>
          <View className="chart-x-axis">
            <Text className="x-label">00:00</Text>
            <Text className="x-label">06:00</Text>
            <Text className="x-label">12:00</Text>
            <Text className="x-label">18:00</Text>
            <Text className="x-label">24:00</Text>
          </View>
        </View>
      </View>
    );
  };

  // 渲染7天趋势
  const renderTrendChart = () => {
    const data = trendData?.daily_data || [];
    if (data.length === 0) {
      return (
        <View className="chart-empty">
          <Text>暂无趋势数据</Text>
        </View>
      );
    }

    return (
      <View className="trend-list">
        {data.slice(-7).map((day, index) => {
          const status = getHeartRateStatus(day.resting_heart_rate);
          const date = new Date(day.record_date);
          const dayName = ['日', '一', '二', '三', '四', '五', '六'][date.getDay()];
          
          return (
            <View key={index} className="trend-item">
              <View className="trend-date">
                <Text className="trend-day">周{dayName}</Text>
                <Text className="trend-date-num">{date.getDate()}</Text>
              </View>
              <View className="trend-bar-container">
                <View 
                  className="trend-bar"
                  style={{ 
                    width: `${day.resting_heart_rate ? Math.min((day.resting_heart_rate / 100) * 100, 100) : 0}%`,
                    backgroundColor: status.color
                  }}
                />
              </View>
              <Text className="trend-value" style={{ color: status.color }}>
                {day.resting_heart_rate || '--'}
              </Text>
            </View>
          );
        })}
      </View>
    );
  };

  const summary = dailyData?.summary;
  const restingStatus = getHeartRateStatus(summary?.resting_heart_rate ?? null);
  const hrvStatus = getHrvStatus(dailyData?.hrv ?? null);

  if (loading) {
    return (
      <View className="heart-rate-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <ScrollView className="heart-rate-page" scrollY>
      {/* 头部日期选择 */}
      <View className="header">
        <View className="date-nav">
          <View className="nav-btn" onClick={() => changeDate(-1)}>
            <Text>‹</Text>
          </View>
          <Text className="current-date">{formatDateDisplay(selectedDate)}</Text>
          <View 
            className={`nav-btn ${selectedDate === getBeijingDateString() ? 'disabled' : ''}`}
            onClick={() => changeDate(1)}
          >
            <Text>›</Text>
          </View>
        </View>
        <View className="refresh-btn" onClick={handleRefresh}>
          <Text>🔄</Text>
        </View>
      </View>

      {/* 核心指标卡片 */}
      <View className="main-card">
        <View className="main-icon">❤️</View>
        <View className="main-content">
          <Text className="main-label">静息心率</Text>
          <View className="main-value-row">
            <Text className="main-value">{summary?.resting_heart_rate || '--'}</Text>
            <Text className="main-unit">bpm</Text>
          </View>
          <View className="status-badge" style={{ backgroundColor: restingStatus.bg }}>
            <Text style={{ color: restingStatus.color }}>{restingStatus.text}</Text>
          </View>
        </View>
      </View>

      {/* 心率概览 */}
      <View className="stats-grid">
        <View className="stat-card">
          <Text className="stat-icon">📊</Text>
          <Text className="stat-label">平均心率</Text>
          <Text className="stat-value">{summary?.avg_heart_rate || '--'}</Text>
          <Text className="stat-unit">bpm</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-icon">📈</Text>
          <Text className="stat-label">最高心率</Text>
          <Text className="stat-value max">{summary?.max_heart_rate || '--'}</Text>
          <Text className="stat-unit">bpm</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-icon">📉</Text>
          <Text className="stat-label">最低心率</Text>
          <Text className="stat-value min">{summary?.min_heart_rate || '--'}</Text>
          <Text className="stat-unit">bpm</Text>
        </View>
        <View className="stat-card">
          <Text className="stat-icon">💓</Text>
          <Text className="stat-label">HRV</Text>
          <View className="stat-value-row">
            <Text className="stat-value" style={{ color: hrvStatus.color }}>
              {dailyData?.hrv || '--'}
            </Text>
            <Text className="stat-unit">ms</Text>
          </View>
          <Text className="stat-status" style={{ color: hrvStatus.color }}>{hrvStatus.text}</Text>
        </View>
      </View>

      {/* 心率曲线 */}
      <View className="section">
        <Text className="section-title">📈 今日心率曲线</Text>
        <View className="chart-card">
          {renderHeartRateChart()}
        </View>
      </View>

      {/* 7天趋势 */}
      <View className="section">
        <Text className="section-title">📊 最近7天趋势</Text>
        <View className="trend-card">
          {trendData && (
            <View className="trend-summary">
              <View className="trend-stat">
                <Text className="trend-stat-value">{trendData.avg_resting_heart_rate || '--'}</Text>
                <Text className="trend-stat-label">平均静息</Text>
              </View>
              <View className="trend-stat">
                <Text className="trend-stat-value">{trendData.avg_hrv || '--'}</Text>
                <Text className="trend-stat-label">平均HRV</Text>
              </View>
              <View className="trend-stat">
                <Text className="trend-stat-value">{trendData.max_heart_rate || '--'}</Text>
                <Text className="trend-stat-label">最高心率</Text>
              </View>
            </View>
          )}
          {renderTrendChart()}
        </View>
      </View>

      {/* 健康提示 */}
      <View className="tip-card">
        <Text className="tip-title">💡 健康提示</Text>
        <Text className="tip-content">
          {summary?.resting_heart_rate && summary.resting_heart_rate > 80 
            ? '您的静息心率偏高，建议增加有氧运动，保持良好作息。'
            : summary?.resting_heart_rate && summary.resting_heart_rate < 50
            ? '您的静息心率较低，如有不适请咨询医生。'
            : '保持规律运动和充足睡眠，有助于维持健康的心率水平。'}
        </Text>
      </View>

      <View className="bottom-space" />
    </ScrollView>
  );
}
