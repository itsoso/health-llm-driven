/**
 * 运动指导页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Button } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getPreWorkoutGuidance } from '../../services/api';
import { PreWorkoutGuidance } from '../../types';
import { getWorkoutTypeDisplay, getWorkoutTypeName } from '../../utils/workout';
import './index.scss';

export default function WorkoutGuidance() {
  const [guidance, setGuidance] = useState<PreWorkoutGuidance | null>(null);
  const [loading, setLoading] = useState(true);
  const [workoutType, setWorkoutType] = useState('running');

  useEffect(() => {
    loadGuidance();
  }, []);

  const loadGuidance = async () => {
    try {
      setLoading(true);
      const data = await getPreWorkoutGuidance(workoutType);
      setGuidance(data);
    } catch (e) {
      console.error('获取运动指导失败:', e);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const handleWorkoutTypeChange = (type: string) => {
    setWorkoutType(type);
    loadGuidance();
  };

  if (loading) {
    return (
      <View className="workout-guidance-page">
        <View className="loading-container">
          <Text className="loading-text">正在生成运动指导...</Text>
        </View>
      </View>
    );
  }

  if (!guidance) {
    return (
      <View className="workout-guidance-page">
        <View className="error-container">
          <Text className="error-icon">😕</Text>
          <Text className="error-text">暂无运动指导数据</Text>
          <Button className="retry-btn" onClick={loadGuidance}>重新加载</Button>
        </View>
      </View>
    );
  }

  return (
    <ScrollView className="workout-guidance-page" scrollY>
      {/* 页面标题 */}
      <View className="page-header">
        <Text className="page-title">
          {guidance.workout_type ? getWorkoutTypeDisplay(guidance.workout_type) : '🎯'} 智能运动指导
        </Text>
        <Text className="page-subtitle">
          {guidance.workout_type 
            ? `${getWorkoutTypeName(guidance.workout_type)}训练 · 基于科学训练理论` 
            : '基于张展晖课程的科学训练建议'}
        </Text>
      </View>

      {/* 当前状态 */}
      {guidance.user_status && (
        <View className="section">
          <View className="section-header">
            <Text className="section-icon">📊</Text>
            <Text className="section-title">当前状态</Text>
          </View>
          <View className="status-card">
            <View className="status-grid">
              <View className="status-item">
                <Text className="status-label">身体电量</Text>
                <Text className="status-value">
                  {guidance.user_status.body_battery ?? '--'}
                </Text>
              </View>
              <View className="status-item">
                <Text className="status-label">HRV</Text>
                <Text className="status-value">
                  {guidance.user_status.hrv ?? '--'} ms
                </Text>
              </View>
              <View className="status-item">
                <Text className="status-label">睡眠分数</Text>
                <Text className="status-value">
                  {guidance.user_status.sleep_score ?? '--'}
                </Text>
              </View>
              <View className="status-item">
                <Text className="status-label">压力水平</Text>
                <Text className="status-value">
                  {guidance.user_status.stress_level ?? '--'}
                </Text>
              </View>
            </View>
            <View className="readiness-badge">
              <Text className="readiness-text">{guidance.user_status.readiness ?? '--'}</Text>
            </View>
          </View>
        </View>
      )}

      {/* 训练目标 */}
      {guidance.training_objective && (
        <View className="section">
          <View className="section-header">
            <Text className="section-icon">🎯</Text>
            <Text className="section-title">训练目标</Text>
          </View>
          <View className="objective-card">
            <Text className="objective-text">{guidance.training_objective}</Text>
          </View>
        </View>
      )}

      {/* 心率区间 */}
      {guidance.heart_rate_zones && (
        <View className="section">
          <View className="section-header">
            <Text className="section-icon">❤️</Text>
            <Text className="section-title">心率区间</Text>
          </View>
          <View className="zones-card">
            <View className="zone-item max-hr">
              <Text className="zone-label">最大心率</Text>
              <Text className="zone-value">{guidance.heart_rate_zones.max_heart_rate ?? '--'} bpm</Text>
            </View>
            {guidance.heart_rate_zones.zone2_fat_burn && (
              <View className="zone-item zone2">
                <Text className="zone-label">燃脂区 (60-70%)</Text>
                <Text className="zone-value">
                  {guidance.heart_rate_zones.zone2_fat_burn[0]}-{guidance.heart_rate_zones.zone2_fat_burn[1]} bpm
                </Text>
              </View>
            )}
            {guidance.heart_rate_zones.zone3_aerobic && (
              <View className="zone-item zone3">
                <Text className="zone-label">有氧区 (70-80%)</Text>
                <Text className="zone-value">
                  {guidance.heart_rate_zones.zone3_aerobic[0]}-{guidance.heart_rate_zones.zone3_aerobic[1]} bpm
                </Text>
              </View>
            )}
            {guidance.heart_rate_zones.zone4_threshold && (
              <View className="zone-item zone4">
                <Text className="zone-label">乳酸阈值区 (80-90%)</Text>
                <Text className="zone-value">
                  {guidance.heart_rate_zones.zone4_threshold[0]}-{guidance.heart_rate_zones.zone4_threshold[1]} bpm
                </Text>
              </View>
            )}
          </View>
        </View>
      )}

      {/* 热身建议 */}
      {guidance.warm_up && guidance.warm_up.length > 0 && (
        <View className="section">
          <View className="section-header">
            <Text className="section-icon">🔥</Text>
            <Text className="section-title">热身建议</Text>
          </View>
          <View className="tips-card">
            {guidance.warm_up.map((tip, idx) => (
              <View key={idx} className="tip-item">
                <Text className="tip-bullet">•</Text>
                <Text className="tip-text">{tip}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 关键提醒 */}
      {guidance.key_reminders && guidance.key_reminders.length > 0 && (
        <View className="section">
          <View className="section-header">
            <Text className="section-icon">⚠️</Text>
            <Text className="section-title">关键提醒</Text>
          </View>
          <View className="tips-card">
            {guidance.key_reminders.map((reminder, idx) => (
              <View key={idx} className="tip-item warning">
                <Text className="tip-bullet">⚠️</Text>
                <Text className="tip-text">{reminder}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 课程要点 - 已隐藏 */}
      {false && guidance.course_insights && guidance.course_insights.length > 0 && (
        <View className="section">
          <View className="section-header">
            <Text className="section-icon">📚</Text>
            <Text className="section-title">课程要点</Text>
          </View>
          <View className="tips-card insights">
            {guidance.course_insights.map((insight, idx) => (
              <View key={idx} className="tip-item">
                <Text className="tip-bullet">💡</Text>
                <Text className="tip-text">{insight}</Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* 开始训练按钮 */}
      <View className="action-section">
        <Button 
          className="start-btn"
          onClick={() => {
            Taro.showToast({ title: '开始训练！', icon: 'success' });
            Taro.navigateBack();
          }}
        >
          开始训练 🏃
        </Button>
      </View>
    </ScrollView>
  );
}
