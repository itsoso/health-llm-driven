/**
 * 运动训练页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get } from '../../services/request';
import './index.scss';

interface WorkoutRecord {
  id: number;
  workout_date: string;
  workout_type: string;
  workout_name: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  calories: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  training_effect_aerobic: number | null;
  source: string;
}

interface WorkoutStats {
  total_workouts: number;
  total_duration_minutes?: number;
  total_duration_seconds?: number;
  total_calories: number;
  total_distance_km?: number;
  total_distance_meters?: number;
  workout_types?: Record<string, number>;
  workouts_by_type?: Record<string, { count: number; duration_minutes: number }>;
}

// 运动类型映射
const WORKOUT_TYPE_MAP: Record<string, { name: string; icon: string }> = {
  running: { name: '跑步', icon: '🏃' },
  cycling: { name: '骑行', icon: '🚴' },
  swimming: { name: '游泳', icon: '🏊' },
  walking: { name: '步行', icon: '🚶' },
  hiking: { name: '徒步', icon: '🥾' },
  strength: { name: '力量训练', icon: '💪' },
  yoga: { name: '瑜伽', icon: '🧘' },
  cardio: { name: '有氧运动', icon: '❤️' },
  hiit: { name: 'HIIT', icon: '🔥' },
  other: { name: '其他', icon: '🏋️' },
};

// 时间范围选项
const TIME_RANGES = [
  { value: 7, label: '最近7天' },
  { value: 30, label: '最近30天' },
];

export default function Workout() {
  const [loading, setLoading] = useState(true);
  const [workouts, setWorkouts] = useState<WorkoutRecord[]>([]);
  const [stats, setStats] = useState<WorkoutStats | null>(null);
  const [selectedDays, setSelectedDays] = useState(7); // 默认7天

  useEffect(() => {
    loadData(selectedDays);
  }, []);

  const loadData = async (days: number) => {
    setLoading(true);
    try {
      const [workoutList, workoutStats] = await Promise.all([
        get<WorkoutRecord[]>('/workout/me', { days }),
        get<WorkoutStats>('/workout/me/stats', { days }).catch(() => null),
      ]);

      setWorkouts(workoutList || []);

      if (workoutStats) {
        setStats(workoutStats);
      } else if (workoutList && workoutList.length > 0) {
        const totalDurationSeconds = workoutList.reduce((sum, w) => sum + (w.duration_seconds || 0), 0);
        const totalDistanceMeters = workoutList.reduce((sum, w) => sum + (w.distance_meters || 0), 0);
        const calculatedStats: WorkoutStats = {
          total_workouts: workoutList.length,
          total_duration_minutes: Math.round(totalDurationSeconds / 60),
          total_duration_seconds: totalDurationSeconds,
          total_calories: workoutList.reduce((sum, w) => sum + (w.calories || 0), 0),
          total_distance_km: Math.round((totalDistanceMeters / 1000) * 100) / 100,
          total_distance_meters: totalDistanceMeters,
        };
        setStats(calculatedStats);
      } else {
        setStats(null);
      }
    } catch (error) {
      console.error('加载运动数据失败:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleTimeRangeChange = (days: number) => {
    if (days !== selectedDays) {
      setSelectedDays(days);
      loadData(days);
    }
  };

  const handleRefresh = () => {
    Taro.showLoading({ title: '刷新中...' });
    loadData(selectedDays).finally(() => {
      Taro.hideLoading();
      Taro.showToast({ title: '刷新成功', icon: 'success', duration: 1000 });
    });
  };

  // 格式化时长
  const formatDuration = (secondsOrMinutes: number | null | undefined, isMinutes = false) => {
    if (secondsOrMinutes === null || secondsOrMinutes === undefined || secondsOrMinutes === 0) return '0分钟';
    const totalSeconds = isMinutes ? secondsOrMinutes * 60 : secondsOrMinutes;
    const hours = Math.floor(totalSeconds / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}小时${minutes}分`;
    }
    return `${minutes}分钟`;
  };

  // 格式化距离
  const formatDistance = (metersOrKm: number | null | undefined, isKm = false) => {
    if (metersOrKm === null || metersOrKm === undefined || metersOrKm === 0) return '0 km';
    const totalMeters = isKm ? metersOrKm * 1000 : metersOrKm;
    if (totalMeters >= 1000) {
      return `${(totalMeters / 1000).toFixed(2)} km`;
    }
    return `${Math.round(totalMeters)} m`;
  };

  // 获取运动类型信息
  const getWorkoutTypeInfo = (type: string) => {
    return WORKOUT_TYPE_MAP[type.toLowerCase()] || WORKOUT_TYPE_MAP.other;
  };

  // 格式化日期
  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (dateStr === today.toISOString().split('T')[0]) {
      return '今天';
    } else if (dateStr === yesterday.toISOString().split('T')[0]) {
      return '昨天';
    }
    return `${date.getMonth() + 1}月${date.getDate()}日`;
  };

  if (loading) {
    return (
      <View className="workout-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  return (
    <ScrollView className="workout-page" scrollY>
      {/* 头部 */}
      <View className="header">
        <View className="header-left">
          <Text className="title">运动训练</Text>
        </View>
        <View className="refresh-btn" onClick={handleRefresh}>
          <Text className="refresh-icon">🔄</Text>
        </View>
      </View>

      {/* 时间范围选择器 */}
      <View className="time-range-selector">
        {TIME_RANGES.map((range) => (
          <View
            key={range.value}
            className={`range-item ${selectedDays === range.value ? 'active' : ''}`}
            onClick={() => handleTimeRangeChange(range.value)}
          >
            <Text className="range-text">{range.label}</Text>
          </View>
        ))}
      </View>

      {/* 统计概览 */}
      <View className="stats-section">
        <View className="stats-row">
          <View className="stat-item">
            <Text className="stat-value">{stats?.total_workouts || workouts.length || 0}</Text>
            <Text className="stat-label">训练次数</Text>
          </View>
          <View className="stat-item">
            <Text className="stat-value">
              {(() => {
                if (stats) {
                  const totalSeconds = stats.total_duration_seconds ?? (stats.total_duration_minutes ? stats.total_duration_minutes * 60 : 0);
                  return formatDuration(totalSeconds, false);
                }
                const totalSeconds = workouts.reduce((sum, w) => sum + (w.duration_seconds || 0), 0);
                return formatDuration(totalSeconds, false);
              })()}
            </Text>
            <Text className="stat-label">总时长</Text>
          </View>
          <View className="stat-item">
            <Text className="stat-value">
              {(() => {
                if (stats) {
                  const totalMeters = stats.total_distance_meters ?? (stats.total_distance_km ? stats.total_distance_km * 1000 : 0);
                  return formatDistance(totalMeters, false);
                }
                const totalMeters = workouts.reduce((sum, w) => sum + (w.distance_meters || 0), 0);
                return formatDistance(totalMeters, false);
              })()}
            </Text>
            <Text className="stat-label">总距离</Text>
          </View>
          <View className="stat-item">
            <Text className="stat-value">
              {(() => {
                if (stats) {
                  return stats.total_calories?.toLocaleString() || '0';
                }
                const totalCalories = workouts.reduce((sum, w) => sum + (w.calories || 0), 0);
                return totalCalories.toLocaleString();
              })()}
            </Text>
            <Text className="stat-label">消耗卡路里</Text>
          </View>
        </View>
      </View>

      {/* 运动记录列表 */}
      {workouts.length === 0 ? (
        <View className="no-data">
          <View className="no-data-icon-wrap">
            <Text className="no-data-icon">🏃</Text>
          </View>
          <Text className="no-data-text">暂无运动记录</Text>
          <Text className="no-data-tip">同步 Garmin 数据后将在此显示</Text>
        </View>
      ) : (
        <View className="workout-list">
          <Text className="section-title">运动记录</Text>
          {workouts.map((workout) => {
            const typeInfo = getWorkoutTypeInfo(workout.workout_type);
            return (
              <View
                key={workout.id}
                className="workout-card"
                onClick={() => Taro.navigateTo({ url: `/pages/workout-detail/index?id=${workout.id}` })}
              >
                <View className="card-main">
                  <View className="workout-icon">
                    <Text>{typeInfo.icon}</Text>
                  </View>
                  <View className="workout-info">
                    <View className="workout-title-row">
                      <Text className="workout-name">
                        {workout.workout_name || typeInfo.name}
                      </Text>
                      <Text className="workout-date">{formatDate(workout.workout_date)}</Text>
                    </View>
                    <View className="workout-metrics">
                      {workout.duration_seconds && (
                        <Text className="metric">⏱ {formatDuration(workout.duration_seconds)}</Text>
                      )}
                      {workout.distance_meters && (
                        <Text className="metric">📍 {formatDistance(workout.distance_meters)}</Text>
                      )}
                      {workout.calories && (
                        <Text className="metric">🔥 {workout.calories} kcal</Text>
                      )}
                    </View>
                  </View>
                </View>
                <View className="card-arrow">
                  <Text>›</Text>
                </View>
              </View>
            );
          })}
        </View>
      )}

      {/* 提示 */}
      <View className="tip-section">
        <Text className="tip-text">💡 在 PC 端可查看更详细的运动分析和心率曲线</Text>
      </View>

      <View className="bottom-space" />
    </ScrollView>
  );
}
