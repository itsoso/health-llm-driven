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
  total_duration_seconds: number;
  total_calories: number;
  total_distance_meters: number;
  workout_types: Record<string, number>;
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

export default function Workout() {
  const [loading, setLoading] = useState(true);
  const [workouts, setWorkouts] = useState<WorkoutRecord[]>([]);
  const [stats, setStats] = useState<WorkoutStats | null>(null);
  const [selectedWorkout, setSelectedWorkout] = useState<WorkoutRecord | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    try {
      // 获取最近30天的运动记录
      const endDate = new Date().toISOString().split('T')[0];
      const startDate = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];
      
      const [workoutList, workoutStats] = await Promise.all([
        get<WorkoutRecord[]>('/workout/me', { start_date: startDate, end_date: endDate, limit: 20 }),
        get<WorkoutStats>('/workout/me/stats', { days: 30 }).catch(() => null),
      ]);
      
      setWorkouts(workoutList || []);
      setStats(workoutStats);
    } catch (error) {
      console.error('加载运动数据失败:', error);
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

  // 格式化时长
  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '--';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}小时${minutes}分`;
    }
    return `${minutes}分钟`;
  };

  // 格式化距离
  const formatDistance = (meters: number | null) => {
    if (!meters) return '--';
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(2)} km`;
    }
    return `${meters} m`;
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
          <Text className="subtitle">最近30天</Text>
        </View>
        <View className="refresh-btn" onClick={handleRefresh}>
          <Text className="refresh-icon">🔄</Text>
        </View>
      </View>

      {/* 统计概览 */}
      {stats && (
        <View className="stats-section">
          <View className="stats-row">
            <View className="stat-item">
              <Text className="stat-value">{stats.total_workouts}</Text>
              <Text className="stat-label">训练次数</Text>
            </View>
            <View className="stat-item">
              <Text className="stat-value">{formatDuration(stats.total_duration_seconds)}</Text>
              <Text className="stat-label">总时长</Text>
            </View>
            <View className="stat-item">
              <Text className="stat-value">{formatDistance(stats.total_distance_meters)}</Text>
              <Text className="stat-label">总距离</Text>
            </View>
            <View className="stat-item">
              <Text className="stat-value">{stats.total_calories?.toLocaleString() || 0}</Text>
              <Text className="stat-label">消耗卡路里</Text>
            </View>
          </View>
        </View>
      )}

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
                onClick={() => setSelectedWorkout(selectedWorkout?.id === workout.id ? null : workout)}
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
                
                {/* 展开详情 */}
                {selectedWorkout?.id === workout.id && (
                  <View className="card-detail">
                    <View className="detail-row">
                      <View className="detail-item">
                        <Text className="detail-label">平均心率</Text>
                        <Text className="detail-value">
                          {workout.avg_heart_rate ? `${workout.avg_heart_rate} bpm` : '--'}
                        </Text>
                      </View>
                      <View className="detail-item">
                        <Text className="detail-label">最大心率</Text>
                        <Text className="detail-value">
                          {workout.max_heart_rate ? `${workout.max_heart_rate} bpm` : '--'}
                        </Text>
                      </View>
                    </View>
                    {workout.training_effect_aerobic && (
                      <View className="detail-row">
                        <View className="detail-item full">
                          <Text className="detail-label">有氧训练效果</Text>
                          <Text className="detail-value effect">{workout.training_effect_aerobic.toFixed(1)}</Text>
                        </View>
                      </View>
                    )}
                    <View className="detail-source">
                      来源: {workout.source === 'garmin' ? 'Garmin' : '手动记录'}
                    </View>
                  </View>
                )}
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
