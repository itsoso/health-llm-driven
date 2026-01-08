/**
 * 数据面板页
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getTodayGarminData, getDailyRecommendation } from '../../services/api';
import { formatSleepDuration, getSleepScoreLevel, getStressLevel } from '@health-app/shared';
import type { GarminData, DailyRecommendation } from '@health-app/shared';
import './index.scss';

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [garminData, setGarminData] = useState<GarminData | null>(null);
  const [recommendation, setRecommendation] = useState<DailyRecommendation | null>(null);

  useEffect(() => {
    loadData();
  }, []);

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
    });
  };

  if (loading) {
    return (
      <View className="dashboard-page loading">
        <Text>加载中...</Text>
      </View>
    );
  }

  const sleepLevel = getSleepScoreLevel(garminData?.sleep_score);
  const stressLevel = getStressLevel(garminData?.stress_level);

  return (
    <ScrollView className="dashboard-page" scrollY>
      {/* 头部 */}
      <View className="header">
        <Text className="title">今日健康数据</Text>
        <Text className="refresh" onClick={handleRefresh}>🔄 刷新</Text>
      </View>

      {!garminData ? (
        <View className="no-data">
          <Text className="no-data-icon">📊</Text>
          <Text className="no-data-text">暂无今日数据</Text>
          <Text className="no-data-tip">请在 PC 端同步 Garmin 数据</Text>
        </View>
      ) : (
        <>
          {/* 核心指标卡片 */}
          <View className="stats-grid">
            {/* 睡眠 */}
            <View className="stat-card sleep">
              <Text className="stat-icon">😴</Text>
              <Text className="stat-label">睡眠分数</Text>
              <View className="stat-value-row">
                <Text className="stat-value" style={{ color: sleepLevel.color }}>
                  {garminData.sleep_score || '--'}
                </Text>
                <Text className="stat-badge" style={{ backgroundColor: sleepLevel.color }}>
                  {sleepLevel.label}
                </Text>
              </View>
              <Text className="stat-sub">
                时长: {formatSleepDuration(garminData.total_sleep_duration)}
              </Text>
            </View>

            {/* 步数 */}
            <View className="stat-card steps">
              <Text className="stat-icon">👟</Text>
              <Text className="stat-label">今日步数</Text>
              <Text className="stat-value">{garminData.steps?.toLocaleString() || '--'}</Text>
              <Text className="stat-sub">
                目标: 8,000 步
              </Text>
            </View>

            {/* 心率 */}
            <View className="stat-card heart">
              <Text className="stat-icon">❤️</Text>
              <Text className="stat-label">静息心率</Text>
              <Text className="stat-value">{garminData.resting_heart_rate || '--'}</Text>
              <Text className="stat-unit">bpm</Text>
            </View>

            {/* 压力 */}
            <View className="stat-card stress">
              <Text className="stat-icon">🧠</Text>
              <Text className="stat-label">压力水平</Text>
              <Text className="stat-value" style={{ color: stressLevel.color }}>
                {garminData.stress_level || '--'}
              </Text>
              <Text className="stat-badge" style={{ backgroundColor: stressLevel.color }}>
                {stressLevel.label}
              </Text>
            </View>

            {/* 身体电量 */}
            <View className="stat-card battery">
              <Text className="stat-icon">🔋</Text>
              <Text className="stat-label">身体电量</Text>
              <Text className="stat-value">{garminData.body_battery_most_charged || '--'}</Text>
              <Text className="stat-sub">
                最低: {garminData.body_battery_lowest || '--'}
              </Text>
            </View>

            {/* HRV */}
            <View className="stat-card hrv">
              <Text className="stat-icon">💓</Text>
              <Text className="stat-label">HRV</Text>
              <Text className="stat-value">{garminData.hrv || '--'}</Text>
              <Text className="stat-unit">ms</Text>
            </View>
          </View>

          {/* AI 建议 */}
          {recommendation && (
            <View className="recommendation-section">
              <Text className="section-title">💡 今日建议</Text>
              <View className="recommendation-card">
                <Text className="recommendation-summary">
                  {recommendation.overall_summary || '暂无建议'}
                </Text>
                {recommendation.priority_recommendations?.slice(0, 3).map((rec, i) => (
                  <View key={i} className="recommendation-item">
                    <Text className="recommendation-bullet">•</Text>
                    <Text className="recommendation-text">{rec}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}
        </>
      )}
    </ScrollView>
  );
}

