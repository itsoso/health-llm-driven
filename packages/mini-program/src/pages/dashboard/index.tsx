/**
 * 数据面板页
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getTodayGarminData, getDailyRecommendation } from '../../services/api';
import { formatSleepDuration, getSleepScoreLevel, getStressLevel } from '../../types';
import type { GarminData, DailyRecommendation } from '../../types';
import './index.scss';

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [garminData, setGarminData] = useState<GarminData | null>(null);
  const [recommendation, setRecommendation] = useState<DailyRecommendation | null>(null);

  useEffect(() => {
    loadData();
  }, []);

  // 页面显示时刷新
  Taro.useDidShow(() => {
    loadData();
  });

  const loadData = async () => {
    setLoading(true);
    try {
      const [garmin, rec] = await Promise.all([
        getTodayGarminData(),
        getDailyRecommendation().catch(() => null),
      ]);
      setGarminData(garmin);
      setRecommendation(rec);
    } catch (error) {
      console.error('加载数据失败:', error);
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

  // 计算步数进度
  const getStepsProgress = (steps: number | null) => {
    if (!steps) return 0;
    const goal = 8000;
    return Math.min((steps / goal) * 100, 100);
  };

  // 计算身体电量进度
  const getBatteryProgress = (battery: number | null) => {
    if (!battery) return 0;
    return battery;
  };

  if (loading) {
    return (
      <View className="dashboard-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  const sleepLevel = getSleepScoreLevel(garminData?.sleep_score ?? null);
  const stressLevel = getStressLevel(garminData?.stress_avg ?? null);
  const stepsProgress = getStepsProgress(garminData?.steps ?? null);
  const batteryProgress = getBatteryProgress(garminData?.body_battery_most_charged ?? null);

  // 获取建议列表
  const getRecommendations = () => {
    if (!recommendation || recommendation.status !== 'success') return [];
    const oneDay = recommendation.one_day;
    if (oneDay?.priority_recommendations) {
      return oneDay.priority_recommendations.slice(0, 3);
    }
    return [];
  };

  const recommendations = getRecommendations();

  return (
    <ScrollView className="dashboard-page" scrollY>
      {/* 头部 */}
      <View className="header">
        <View className="header-left">
          <Text className="title">健康数据</Text>
          <Text className="subtitle">
            {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })}
          </Text>
        </View>
        <View className="refresh-btn" onClick={handleRefresh}>
          <Text className="refresh-icon">🔄</Text>
        </View>
      </View>

      {!garminData ? (
        <View className="no-data">
          <View className="no-data-icon-wrap">
            <Text className="no-data-icon">📊</Text>
          </View>
          <Text className="no-data-text">暂无今日数据</Text>
          <Text className="no-data-tip">请在 PC 端同步 Garmin 数据</Text>
        </View>
      ) : (
        <>
          {/* 睡眠卡片 - 大卡片 */}
          <View className="sleep-card">
            <View className="sleep-header">
              <Text className="sleep-icon">🌙</Text>
              <Text className="sleep-title">睡眠质量</Text>
            </View>
            <View className="sleep-content">
              <View className="sleep-score">
                <Text className="score-value" style={{ color: sleepLevel.color }}>
                  {garminData.sleep_score || '--'}
                </Text>
                <Text className="score-badge" style={{ backgroundColor: sleepLevel.color }}>
                  {sleepLevel.level}
                </Text>
              </View>
              <View className="sleep-details">
                <View className="sleep-item">
                  <Text className="item-label">总时长</Text>
                  <Text className="item-value">{formatSleepDuration(garminData.total_sleep_duration)}</Text>
                </View>
                <View className="sleep-item">
                  <Text className="item-label">深睡</Text>
                  <Text className="item-value">{formatSleepDuration(garminData.deep_sleep_duration)}</Text>
                </View>
                <View className="sleep-item">
                  <Text className="item-label">REM</Text>
                  <Text className="item-value">{formatSleepDuration(garminData.rem_sleep_duration)}</Text>
                </View>
              </View>
            </View>
          </View>

          {/* 步数和心率 - 两列 */}
          <View className="dual-cards">
            {/* 步数 */}
            <View className="metric-card steps-card">
              <View className="metric-header">
                <Text className="metric-icon">👟</Text>
                <Text className="metric-label">今日步数</Text>
              </View>
              <Text className="metric-value">{garminData.steps?.toLocaleString() || '--'}</Text>
              <View className="progress-bar">
                <View className="progress-fill" style={{ width: `${stepsProgress}%` }} />
              </View>
              <Text className="metric-goal">目标 8,000 步 · {stepsProgress.toFixed(0)}%</Text>
            </View>

            {/* 心率 */}
            <View className="metric-card heart-card">
              <View className="metric-header">
                <Text className="metric-icon">❤️</Text>
                <Text className="metric-label">静息心率</Text>
              </View>
              <View className="metric-value-row">
                <Text className="metric-value">{garminData.resting_heart_rate || '--'}</Text>
                <Text className="metric-unit">bpm</Text>
              </View>
              <View className="heart-range">
                <Text className="range-label">平均</Text>
                <Text className="range-value">{garminData.avg_heart_rate || '--'} bpm</Text>
              </View>
            </View>
          </View>

          {/* 身体电量和压力 - 两列 */}
          <View className="dual-cards">
            {/* 身体电量 */}
            <View className="metric-card battery-card">
              <View className="metric-header">
                <Text className="metric-icon">🔋</Text>
                <Text className="metric-label">身体电量</Text>
              </View>
              <View className="battery-display">
                <View className="battery-visual">
                  <View className="battery-level" style={{ height: `${batteryProgress}%` }} />
                </View>
                <View className="battery-info">
                  <Text className="metric-value">{garminData.body_battery_most_charged || '--'}</Text>
                  <Text className="battery-range">最低 {garminData.body_battery_lowest || '--'}</Text>
                </View>
              </View>
            </View>

            {/* 压力 */}
            <View className="metric-card stress-card">
              <View className="metric-header">
                <Text className="metric-icon">🧘</Text>
                <Text className="metric-label">压力水平</Text>
              </View>
              <View className="metric-value-row">
                <Text className="metric-value" style={{ color: stressLevel.color }}>
                  {garminData.stress_avg || '--'}
                </Text>
                <Text className="stress-badge" style={{ backgroundColor: stressLevel.color }}>
                  {stressLevel.level}
                </Text>
              </View>
              <Text className="stress-tip">
                {garminData.stress_avg && garminData.stress_avg <= 25 ? '状态放松，继续保持' : 
                 garminData.stress_avg && garminData.stress_avg <= 50 ? '压力适中，注意休息' :
                 garminData.stress_avg ? '压力偏高，建议放松' : '暂无数据'}
              </Text>
            </View>
          </View>

          {/* HRV 和 SpO2 - 两列 */}
          <View className="dual-cards">
            {/* HRV */}
            <View className="metric-card hrv-card">
              <View className="metric-header">
                <Text className="metric-icon">💓</Text>
                <Text className="metric-label">HRV</Text>
              </View>
              <View className="metric-value-row">
                <Text className="metric-value">{garminData.hrv || '--'}</Text>
                <Text className="metric-unit">ms</Text>
              </View>
              <Text className="hrv-status">
                {garminData.hrv_status === 'BALANCED' ? '平衡' : 
                 garminData.hrv_status === 'UNBALANCED' ? '不平衡' : 
                 garminData.hrv_status || '未知'}
              </Text>
            </View>

            {/* SpO2 */}
            <View className="metric-card spo2-card">
              <View className="metric-header">
                <Text className="metric-icon">🫁</Text>
                <Text className="metric-label">血氧饱和度</Text>
              </View>
              <View className="metric-value-row">
                <Text className="metric-value">{garminData.spo2_avg || '--'}</Text>
                <Text className="metric-unit">%</Text>
              </View>
              <Text className="spo2-range">
                {garminData.spo2_min && garminData.spo2_max 
                  ? `${garminData.spo2_min}% - ${garminData.spo2_max}%`
                  : '暂无数据'}
              </Text>
            </View>
          </View>

          {/* AI 建议 */}
          {recommendations.length > 0 && (
            <View className="recommendation-section">
              <View className="section-header">
                <Text className="section-icon">💡</Text>
                <Text className="section-title">AI 健康建议</Text>
              </View>
              <View className="recommendation-list">
                {recommendations.map((rec, i) => (
                  <View key={i} className="recommendation-item">
                    <View className="rec-number">{i + 1}</View>
                    <Text className="rec-text">{rec}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* 底部留白 */}
          <View className="bottom-space" />
        </>
      )}
    </ScrollView>
  );
}
