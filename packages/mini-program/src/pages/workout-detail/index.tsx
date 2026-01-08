/**
 * 运动详情页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Button } from '@tarojs/components';
import Taro, { useRouter } from '@tarojs/taro';
import { get, post } from '../../services/request';
import './index.scss';

interface WorkoutDetail {
  id: number;
  workout_date: string;
  workout_start_time: string;
  workout_end_time: string | null;
  workout_type: string;
  workout_name: string | null;
  duration_seconds: number | null;
  distance_meters: number | null;
  calories: number | null;
  avg_heart_rate: number | null;
  max_heart_rate: number | null;
  avg_pace_seconds_per_km: number | null;
  max_pace_seconds_per_km: number | null;
  avg_speed_kmh: number | null;
  max_speed_kmh: number | null;
  elevation_gain_meters: number | null;
  elevation_loss_meters: number | null;
  training_effect_aerobic: number | null;
  training_effect_anaerobic: number | null;
  vo2max: number | null;
  training_load: number | null;
  hr_zone_1_seconds: number | null;
  hr_zone_2_seconds: number | null;
  hr_zone_3_seconds: number | null;
  hr_zone_4_seconds: number | null;
  hr_zone_5_seconds: number | null;
  heart_rate_data: string | null;
  ai_analysis: string | null;
  notes: string | null;
  source: string;
}

// 运动类型映射
const WORKOUT_TYPE_MAP: Record<string, { name: string; icon: string; color: string }> = {
  running: { name: '跑步', icon: '🏃', color: '#10B981' },
  cycling: { name: '骑行', icon: '🚴', color: '#3B82F6' },
  swimming: { name: '游泳', icon: '🏊', color: '#06B6D4' },
  walking: { name: '步行', icon: '🚶', color: '#8B5CF6' },
  hiking: { name: '徒步', icon: '🥾', color: '#F59E0B' },
  strength: { name: '力量训练', icon: '💪', color: '#EF4444' },
  yoga: { name: '瑜伽', icon: '🧘', color: '#EC4899' },
  cardio: { name: '有氧运动', icon: '❤️', color: '#F43F5E' },
  hiit: { name: 'HIIT', icon: '🔥', color: '#F97316' },
  other: { name: '其他', icon: '🏋️', color: '#6B7280' },
};

// 心率区间颜色
const HR_ZONE_COLORS = ['#9CA3AF', '#3B82F6', '#10B981', '#F59E0B', '#EF4444'];
const HR_ZONE_NAMES = ['热身', '燃脂', '有氧', '无氧', '极限'];

export default function WorkoutDetail() {
  const router = useRouter();
  const workoutId = router.params.id;
  
  const [loading, setLoading] = useState(true);
  const [detail, setDetail] = useState<WorkoutDetail | null>(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    if (workoutId) {
      loadDetail();
    }
  }, [workoutId]);

  const loadDetail = async () => {
    setLoading(true);
    try {
      const data = await get<WorkoutDetail>(`/workout/me/${workoutId}`);
      setDetail(data);
    } catch (error) {
      console.error('加载运动详情失败:', error);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  // 触发AI分析
  const handleAnalyze = async () => {
    if (!workoutId || analyzing) return;
    
    setAnalyzing(true);
    Taro.showLoading({ title: '正在分析...' });
    
    try {
      await post(`/workout/me/${workoutId}/analyze`);
      Taro.hideLoading();
      Taro.showToast({ title: 'AI分析完成', icon: 'success' });
      // 重新加载详情以获取分析结果
      await loadDetail();
    } catch (error: any) {
      Taro.hideLoading();
      Taro.showToast({ 
        title: error.message || 'AI分析失败', 
        icon: 'none',
        duration: 3000
      });
    } finally {
      setAnalyzing(false);
    }
  };

  // 格式化时长
  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '--';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hours > 0) {
      return `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
    }
    return `${minutes}:${String(secs).padStart(2, '0')}`;
  };

  // 格式化距离
  const formatDistance = (meters: number | null) => {
    if (!meters) return '--';
    if (meters >= 1000) {
      return `${(meters / 1000).toFixed(2)} km`;
    }
    return `${Math.round(meters)} m`;
  };

  // 格式化配速
  const formatPace = (secondsPerKm: number | null) => {
    if (!secondsPerKm) return '--';
    const minutes = Math.floor(secondsPerKm / 60);
    const seconds = Math.round(secondsPerKm % 60);
    return `${minutes}'${String(seconds).padStart(2, '0')}"`;
  };

  // 格式化时间
  const formatTime = (timeStr: string | null) => {
    if (!timeStr) return '--';
    const date = new Date(timeStr);
    return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
  };

  // 获取运动类型信息
  const getWorkoutTypeInfo = (type: string) => {
    return WORKOUT_TYPE_MAP[type?.toLowerCase()] || WORKOUT_TYPE_MAP.other;
  };

  // 计算心率区间总时长
  const getTotalHrZoneSeconds = () => {
    if (!detail) return 0;
    return (detail.hr_zone_1_seconds || 0) + 
           (detail.hr_zone_2_seconds || 0) + 
           (detail.hr_zone_3_seconds || 0) + 
           (detail.hr_zone_4_seconds || 0) + 
           (detail.hr_zone_5_seconds || 0);
  };

  // 渲染心率区间
  const renderHrZones = () => {
    if (!detail) return null;
    const zones = [
      detail.hr_zone_1_seconds,
      detail.hr_zone_2_seconds,
      detail.hr_zone_3_seconds,
      detail.hr_zone_4_seconds,
      detail.hr_zone_5_seconds,
    ];
    const total = getTotalHrZoneSeconds();
    if (total === 0) return null;

    return (
      <View className="hr-zones">
        {zones.map((seconds, index) => {
          const percentage = seconds ? (seconds / total) * 100 : 0;
          if (percentage < 1) return null;
          return (
            <View key={index} className="zone-item">
              <View className="zone-bar-container">
                <View 
                  className="zone-bar" 
                  style={{ 
                    width: `${percentage}%`, 
                    backgroundColor: HR_ZONE_COLORS[index] 
                  }} 
                />
              </View>
              <View className="zone-info">
                <View 
                  className="zone-dot" 
                  style={{ backgroundColor: HR_ZONE_COLORS[index] }} 
                />
                <Text className="zone-name">{HR_ZONE_NAMES[index]}</Text>
                <Text className="zone-percent">{percentage.toFixed(0)}%</Text>
                <Text className="zone-time">{formatDuration(seconds)}</Text>
              </View>
            </View>
          );
        })}
      </View>
    );
  };

  // 渲染AI分析（美化JSON）
  const renderAiAnalysis = (analysisStr: string) => {
    try {
      const analysis = JSON.parse(analysisStr);
      
      // 如果是对象，格式化显示
      if (typeof analysis === 'object' && analysis !== null) {
        const sections: { title: string; content: string; icon: string }[] = [];
        
        // 常见字段映射
        const fieldMap: Record<string, { title: string; icon: string }> = {
          summary: { title: '总结', icon: '📋' },
          overall_summary: { title: '总结', icon: '📋' },
          intensity: { title: '运动强度', icon: '💪' },
          intensity_analysis: { title: '强度分析', icon: '💪' },
          heart_rate_analysis: { title: '心率分析', icon: '❤️' },
          performance: { title: '表现评价', icon: '🏆' },
          suggestion: { title: '建议', icon: '💡' },
          suggestions: { title: '建议', icon: '💡' },
          improvement: { title: '改进建议', icon: '📈' },
          recovery: { title: '恢复建议', icon: '🛌' },
          next_workout: { title: '下次训练建议', icon: '🎯' },
          calories_analysis: { title: '热量消耗', icon: '🔥' },
          pace_analysis: { title: '配速分析', icon: '⚡' },
          training_effect: { title: '训练效果', icon: '📊' },
        };

        for (const [key, value] of Object.entries(analysis)) {
          if (value && typeof value === 'string' && value.trim()) {
            const fieldInfo = fieldMap[key] || { title: key.replace(/_/g, ' '), icon: '•' };
            sections.push({
              title: fieldInfo.title,
              content: value as string,
              icon: fieldInfo.icon,
            });
          } else if (Array.isArray(value) && value.length > 0) {
            const fieldInfo = fieldMap[key] || { title: key.replace(/_/g, ' '), icon: '•' };
            sections.push({
              title: fieldInfo.title,
              content: value.join('\n• '),
              icon: fieldInfo.icon,
            });
          }
        }

        if (sections.length > 0) {
          return (
            <>
              {sections.map((section, index) => (
                <View key={index} className="ai-section">
                  <Text className="ai-section-title">{section.icon} {section.title}</Text>
                  <Text className="ai-section-content">{section.content}</Text>
                </View>
              ))}
            </>
          );
        }
      }
      
      // 如果是字符串，直接显示
      if (typeof analysis === 'string') {
        return <Text className="ai-content">{analysis}</Text>;
      }
    } catch (e) {
      // 解析失败，直接显示原文
    }
    
    // 默认直接显示
    return <Text className="ai-content">{analysisStr}</Text>;
  };

  // 渲染心率曲线
  const renderHeartRateChart = () => {
    if (!detail?.heart_rate_data) return null;
    
    try {
      const hrData = JSON.parse(detail.heart_rate_data);
      if (!Array.isArray(hrData) || hrData.length === 0) return null;

      const values = hrData.map((p: any) => p.hr || p.value || 0);
      const maxVal = Math.max(...values);
      const minVal = Math.min(...values);
      const range = maxVal - minVal || 1;

      // 采样
      const sampledData = hrData.length > 30 
        ? hrData.filter((_: any, i: number) => i % Math.ceil(hrData.length / 30) === 0)
        : hrData;

      return (
        <View className="hr-chart">
          <View className="chart-header">
            <Text className="chart-title">心率曲线</Text>
            <View className="chart-legend">
              <Text className="legend-min">{minVal}</Text>
              <Text className="legend-sep">-</Text>
              <Text className="legend-max">{maxVal}</Text>
              <Text className="legend-unit">bpm</Text>
            </View>
          </View>
          <View className="chart-bars">
            {sampledData.map((point: any, index: number) => {
              const value = point.hr || point.value || 0;
              const height = ((value - minVal) / range) * 100;
              return (
                <View key={index} className="bar-wrapper">
                  <View 
                    className="bar" 
                    style={{ 
                      height: `${Math.max(height, 5)}%`,
                      backgroundColor: value > 150 ? '#EF4444' : 
                                      value > 120 ? '#F59E0B' : 
                                      value > 100 ? '#10B981' : '#3B82F6'
                    }} 
                  />
                </View>
              );
            })}
          </View>
        </View>
      );
    } catch (e) {
      return null;
    }
  };

  if (loading) {
    return (
      <View className="workout-detail-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  if (!detail) {
    return (
      <View className="workout-detail-page error">
        <Text className="error-icon">😔</Text>
        <Text className="error-text">运动记录不存在</Text>
      </View>
    );
  }

  const typeInfo = getWorkoutTypeInfo(detail.workout_type);

  return (
    <ScrollView className="workout-detail-page" scrollY>
      {/* 头部 */}
      <View className="header" style={{ backgroundColor: typeInfo.color }}>
        <View className="header-icon">
          <Text>{typeInfo.icon}</Text>
        </View>
        <Text className="header-name">{detail.workout_name || typeInfo.name}</Text>
        <Text className="header-date">{detail.workout_date}</Text>
        <Text className="header-time">
          {formatTime(detail.workout_start_time)} - {formatTime(detail.workout_end_time)}
        </Text>
      </View>

      {/* 核心数据 */}
      <View className="core-stats">
        <View className="core-item">
          <Text className="core-value">{formatDuration(detail.duration_seconds)}</Text>
          <Text className="core-label">时长</Text>
        </View>
        <View className="core-divider" />
        <View className="core-item">
          <Text className="core-value">{formatDistance(detail.distance_meters)}</Text>
          <Text className="core-label">距离</Text>
        </View>
        <View className="core-divider" />
        <View className="core-item">
          <Text className="core-value">{detail.calories || '--'}</Text>
          <Text className="core-label">卡路里</Text>
        </View>
      </View>

      {/* 心率数据 */}
      <View className="section">
        <Text className="section-title">❤️ 心率</Text>
        <View className="stats-grid">
          <View className="stat-card">
            <Text className="stat-value">{detail.avg_heart_rate || '--'}</Text>
            <Text className="stat-label">平均心率</Text>
            <Text className="stat-unit">bpm</Text>
          </View>
          <View className="stat-card">
            <Text className="stat-value max">{detail.max_heart_rate || '--'}</Text>
            <Text className="stat-label">最大心率</Text>
            <Text className="stat-unit">bpm</Text>
          </View>
        </View>
        {renderHeartRateChart()}
        {renderHrZones()}
      </View>

      {/* 配速/速度 */}
      {(detail.avg_pace_seconds_per_km || detail.avg_speed_kmh) && (
        <View className="section">
          <Text className="section-title">⚡ 速度</Text>
          <View className="stats-grid">
            {detail.avg_pace_seconds_per_km && (
              <View className="stat-card">
                <Text className="stat-value">{formatPace(detail.avg_pace_seconds_per_km)}</Text>
                <Text className="stat-label">平均配速</Text>
                <Text className="stat-unit">/km</Text>
              </View>
            )}
            {detail.max_pace_seconds_per_km && (
              <View className="stat-card">
                <Text className="stat-value">{formatPace(detail.max_pace_seconds_per_km)}</Text>
                <Text className="stat-label">最快配速</Text>
                <Text className="stat-unit">/km</Text>
              </View>
            )}
            {detail.avg_speed_kmh && (
              <View className="stat-card">
                <Text className="stat-value">{detail.avg_speed_kmh.toFixed(1)}</Text>
                <Text className="stat-label">平均速度</Text>
                <Text className="stat-unit">km/h</Text>
              </View>
            )}
          </View>
        </View>
      )}

      {/* 海拔 */}
      {(detail.elevation_gain_meters || detail.elevation_loss_meters) && (
        <View className="section">
          <Text className="section-title">⛰️ 海拔</Text>
          <View className="stats-grid">
            <View className="stat-card">
              <Text className="stat-value up">+{Math.round(detail.elevation_gain_meters || 0)}</Text>
              <Text className="stat-label">累计爬升</Text>
              <Text className="stat-unit">米</Text>
            </View>
            <View className="stat-card">
              <Text className="stat-value down">-{Math.round(detail.elevation_loss_meters || 0)}</Text>
              <Text className="stat-label">累计下降</Text>
              <Text className="stat-unit">米</Text>
            </View>
          </View>
        </View>
      )}

      {/* 训练效果 */}
      {(detail.training_effect_aerobic || detail.training_effect_anaerobic) && (
        <View className="section">
          <Text className="section-title">💪 训练效果</Text>
          <View className="stats-grid">
            {detail.training_effect_aerobic && (
              <View className="stat-card">
                <Text className="stat-value effect">{detail.training_effect_aerobic.toFixed(1)}</Text>
                <Text className="stat-label">有氧效果</Text>
              </View>
            )}
            {detail.training_effect_anaerobic && (
              <View className="stat-card">
                <Text className="stat-value effect">{detail.training_effect_anaerobic.toFixed(1)}</Text>
                <Text className="stat-label">无氧效果</Text>
              </View>
            )}
            {detail.vo2max && (
              <View className="stat-card">
                <Text className="stat-value">{detail.vo2max.toFixed(0)}</Text>
                <Text className="stat-label">VO2 Max</Text>
              </View>
            )}
            {detail.training_load && (
              <View className="stat-card">
                <Text className="stat-value">{detail.training_load}</Text>
                <Text className="stat-label">训练负荷</Text>
              </View>
            )}
          </View>
        </View>
      )}

      {/* AI分析 */}
      <View className="section">
        <View className="section-header">
          <Text className="section-title">🤖 AI 分析</Text>
          <Button 
            className={`analyze-btn ${analyzing ? 'loading' : ''}`}
            onClick={handleAnalyze}
            disabled={analyzing}
          >
            {analyzing ? '分析中...' : (detail.ai_analysis ? '重新分析' : '开始分析')}
          </Button>
        </View>
        {detail.ai_analysis ? (
          <View className="ai-card">
            {renderAiAnalysis(detail.ai_analysis)}
          </View>
        ) : (
          <View className="ai-card empty">
            <Text className="empty-icon">💡</Text>
            <Text className="empty-text">点击"开始分析"获取AI专业建议</Text>
          </View>
        )}
      </View>

      {/* 备注 */}
      {detail.notes && (
        <View className="section">
          <Text className="section-title">📝 备注</Text>
          <View className="notes-card">
            <Text className="notes-content">{detail.notes}</Text>
          </View>
        </View>
      )}

      {/* 来源 */}
      <View className="source-info">
        <Text>数据来源: {detail.source === 'garmin' ? 'Garmin Connect' : '手动记录'}</Text>
      </View>

      <View className="bottom-space" />
    </ScrollView>
  );
}
