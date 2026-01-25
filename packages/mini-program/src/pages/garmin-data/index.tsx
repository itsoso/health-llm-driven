/**
 * Garmin 数据列表页面 - 显示最近14天的健康数据
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get } from '../../services/request';
import './index.scss';

interface GarminData {
  id: number;
  record_date: string;
  sleep_score: number | null;
  total_sleep_duration: number | null;
  deep_sleep_duration: number | null;
  rem_sleep_duration: number | null;
  light_sleep_duration: number | null;
  resting_heart_rate: number | null;
  avg_heart_rate: number | null;
  hrv: number | null;
  hrv_status: string | null;
  steps: number | null;
  calories_burned: number | null;
  active_calories: number | null;
  stress_level: number | null;
  body_battery_most_charged: number | null;
  body_battery_lowest: number | null;
  spo2_avg: number | null;
  distance_meters: number | null;
  floors_climbed: number | null;
}

// HRV状态映射
const HRV_STATUS_MAP: Record<string, { text: string; color: string }> = {
  BALANCED: { text: '平衡', color: '#10B981' },
  balanced: { text: '平衡', color: '#10B981' },
  UNBALANCED: { text: '不平衡', color: '#F59E0B' },
  unbalanced: { text: '不平衡', color: '#F59E0B' },
  LOW: { text: '偏低', color: '#EF4444' },
  low: { text: '偏低', color: '#EF4444' },
};

// 睡眠评分颜色
const getSleepScoreColor = (score: number | null): string => {
  if (!score) return '#6B7280';
  if (score >= 80) return '#10B981';
  if (score >= 60) return '#F59E0B';
  return '#EF4444';
};

// 获取北京日期
const getBeijingDateString = (date: Date = new Date()): string => {
  const beijingOffset = 8 * 60;
  const localOffset = date.getTimezoneOffset();
  const beijingTime = new Date(date.getTime() + (beijingOffset + localOffset) * 60 * 1000);
  return beijingTime.toISOString().split('T')[0];
};

export default function GarminDataPage() {
  const [loading, setLoading] = useState(true);
  const [dataList, setDataList] = useState<GarminData[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      const today = new Date();
      const endDate = getBeijingDateString(today);
      const startDate = getBeijingDateString(new Date(today.getTime() - 13 * 24 * 60 * 60 * 1000));
      
      const data = await get<GarminData[]>('/daily-health/garmin/me', {
        start_date: startDate,
        end_date: endDate,
      });
      
      // 按日期降序排序
      const sorted = data.sort((a, b) => 
        new Date(b.record_date).getTime() - new Date(a.record_date).getTime()
      );
      setDataList(sorted);
    } catch (error) {
      console.error('加载Garmin数据失败:', error);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  // 格式化日期显示
  const formatDate = (dateStr: string): { day: string; weekday: string; isToday: boolean } => {
    const date = new Date(dateStr);
    const today = getBeijingDateString();
    const yesterday = getBeijingDateString(new Date(Date.now() - 24 * 60 * 60 * 1000));
    
    const weekdays = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
    const day = `${date.getMonth() + 1}/${date.getDate()}`;
    
    if (dateStr === today) {
      return { day, weekday: '今天', isToday: true };
    } else if (dateStr === yesterday) {
      return { day, weekday: '昨天', isToday: false };
    }
    return { day, weekday: weekdays[date.getDay()], isToday: false };
  };

  // 格式化睡眠时长
  const formatSleepDuration = (minutes: number | null): string => {
    if (!minutes) return '--';
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h${mins}m`;
  };

  // 格式化距离
  const formatDistance = (meters: number | null): string => {
    if (!meters) return '--';
    return `${(meters / 1000).toFixed(1)}km`;
  };

  // 渲染单日数据卡片
  const renderDayCard = (data: GarminData) => {
    const dateInfo = formatDate(data.record_date);
    const hrvStatus = HRV_STATUS_MAP[data.hrv_status || ''] || { text: '--', color: '#6B7280' };
    const isExpanded = selectedDate === data.record_date;

    return (
      <View 
        key={data.id} 
        className={`day-card ${isExpanded ? 'expanded' : ''} ${dateInfo.isToday ? 'today' : ''}`}
        onClick={() => setSelectedDate(isExpanded ? null : data.record_date)}
      >
        {/* 日期头部 */}
        <View className="card-header">
          <View className="date-info">
            <Text className="date-day">{dateInfo.day}</Text>
            <Text className="date-weekday">{dateInfo.weekday}</Text>
          </View>
          <View className="quick-stats">
            {data.sleep_score && (
              <View className="quick-stat">
                <Text className="stat-icon">😴</Text>
                <Text className="stat-value" style={{ color: getSleepScoreColor(data.sleep_score) }}>
                  {data.sleep_score}
                </Text>
              </View>
            )}
            {data.steps && (
              <View className="quick-stat">
                <Text className="stat-icon">👟</Text>
                <Text className="stat-value">{data.steps.toLocaleString()}</Text>
              </View>
            )}
            {data.resting_heart_rate && (
              <View className="quick-stat">
                <Text className="stat-icon">❤️</Text>
                <Text className="stat-value">{data.resting_heart_rate}</Text>
              </View>
            )}
          </View>
          <Text className="expand-icon">{isExpanded ? '▲' : '▼'}</Text>
        </View>

        {/* 展开详情 */}
        {isExpanded && (
          <View className="card-detail">
            {/* 睡眠 */}
            <View className="detail-section">
              <Text className="section-title">🌙 睡眠</Text>
              <View className="detail-grid">
                <View className="detail-item">
                  <Text className="item-value" style={{ color: getSleepScoreColor(data.sleep_score) }}>
                    {data.sleep_score || '--'}
                  </Text>
                  <Text className="item-label">评分</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{formatSleepDuration(data.total_sleep_duration)}</Text>
                  <Text className="item-label">总时长</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{formatSleepDuration(data.deep_sleep_duration)}</Text>
                  <Text className="item-label">深睡</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{formatSleepDuration(data.rem_sleep_duration)}</Text>
                  <Text className="item-label">REM</Text>
                </View>
              </View>
            </View>

            {/* 心率 & HRV */}
            <View className="detail-section">
              <Text className="section-title">❤️ 心率</Text>
              <View className="detail-grid">
                <View className="detail-item">
                  <Text className="item-value">{data.resting_heart_rate || '--'}</Text>
                  <Text className="item-label">静息心率</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{data.avg_heart_rate || '--'}</Text>
                  <Text className="item-label">平均心率</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{data.hrv || '--'}</Text>
                  <Text className="item-label">HRV</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value" style={{ color: hrvStatus.color }}>{hrvStatus.text}</Text>
                  <Text className="item-label">HRV状态</Text>
                </View>
              </View>
            </View>

            {/* 活动 */}
            <View className="detail-section">
              <Text className="section-title">🏃 活动</Text>
              <View className="detail-grid">
                <View className="detail-item">
                  <Text className="item-value">{data.steps?.toLocaleString() || '--'}</Text>
                  <Text className="item-label">步数</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{formatDistance(data.distance_meters)}</Text>
                  <Text className="item-label">距离</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{data.calories_burned || '--'}</Text>
                  <Text className="item-label">总卡路里</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{data.floors_climbed || '--'}</Text>
                  <Text className="item-label">楼层</Text>
                </View>
              </View>
            </View>

            {/* 身体状态 */}
            <View className="detail-section">
              <Text className="section-title">💪 身体状态</Text>
              <View className="detail-grid">
                <View className="detail-item">
                  <Text className="item-value">{data.body_battery_most_charged || '--'}</Text>
                  <Text className="item-label">身体电量(高)</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{data.body_battery_lowest || '--'}</Text>
                  <Text className="item-label">身体电量(低)</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">{data.stress_level || '--'}</Text>
                  <Text className="item-label">压力</Text>
                </View>
                <View className="detail-item">
                  <Text className="item-value">
                    {data.spo2_avg !== null && data.spo2_avg !== undefined 
                      ? `${Math.round(data.spo2_avg)}%` 
                      : '--%'}
                  </Text>
                  <Text className="item-label">血氧</Text>
                </View>
              </View>
            </View>
          </View>
        )}
      </View>
    );
  };

  if (loading) {
    return (
      <View className="garmin-data-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <ScrollView className="garmin-data-page" scrollY>
      {/* 页面标题 */}
      <View className="page-header">
        <Text className="page-title">📈 Garmin 健康数据</Text>
        <Text className="page-subtitle">最近14天</Text>
      </View>

      {/* 数据列表 */}
      {dataList.length === 0 ? (
        <View className="empty-state">
          <Text className="empty-icon">📭</Text>
          <Text className="empty-title">暂无数据</Text>
          <Text className="empty-desc">请先同步Garmin数据</Text>
        </View>
      ) : (
        <View className="data-list">
          {dataList.map(data => renderDayCard(data))}
        </View>
      )}

      <View className="bottom-space" />
    </ScrollView>
  );
}
