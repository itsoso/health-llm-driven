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
        getTodayGarminData().catch((err) => {
          console.error('获取Garmin数据失败:', err);
          return null;
        }),
        getDailyRecommendation().catch((err) => {
          console.error('获取AI建议失败:', err);
          console.error('错误详情:', err);
          return null;
        }),
      ]);
      setGarminData(garmin);
      setRecommendation(rec);
      console.log('Dashboard数据加载完成:', {
        hasGarminData: !!garmin,
        hasRecommendation: !!rec,
        recommendation: rec,
      });
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
  const getBatteryProgress = (battery: number | null | undefined) => {
    if (battery === null || battery === undefined) return 0;
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
  // 优先使用 stress_level，如果没有则使用 stress_avg（兼容性）
  const stressValue = garminData?.stress_level ?? garminData?.stress_avg ?? null;
  const stressLevel = getStressLevel(stressValue);
  const stepsProgress = getStepsProgress(garminData?.steps ?? null);
  // 优先使用 body_battery_most_charged，如果没有则使用 body_battery_charged
  const batteryValue = garminData?.body_battery_most_charged ?? garminData?.body_battery_charged ?? null;
  const batteryProgress = getBatteryProgress(batteryValue);
  
  console.log('身体电量数据 - dashboard:', {
    most_charged: garminData?.body_battery_most_charged,
    charged: garminData?.body_battery_charged,
    batteryValue,
    batteryProgress,
  });

  // 获取建议列表
  const getRecommendations = () => {
    if (!recommendation) {
      console.log('recommendation为空');
      return [];
    }
    
    console.log('recommendation完整数据:', recommendation);
    console.log('recommendation.one_day:', recommendation.one_day);
    console.log('recommendation.one_day?.priority_recommendations:', recommendation.one_day?.priority_recommendations);
    
    // 不检查status，直接尝试获取建议
    const oneDay = recommendation.one_day;
    if (oneDay?.priority_recommendations && Array.isArray(oneDay.priority_recommendations)) {
      const recs = oneDay.priority_recommendations.slice(0, 5);
      console.log('从priority_recommendations获取到建议:', recs);
      return recs;
    }
    
    // 如果没有priority_recommendations，尝试从其他字段获取
    if (oneDay?.daily_goals && Array.isArray(oneDay.daily_goals)) {
      const recs = oneDay.daily_goals.slice(0, 5);
      console.log('从daily_goals获取到建议:', recs);
      return recs;
    }
    
    console.log('未找到建议数据，oneDay:', oneDay);
    return [];
  };

  const recommendations = getRecommendations();
  console.log('最终recommendations数组:', recommendations);
  console.log('recommendations.length:', recommendations.length);

  return (
    <ScrollView className="dashboard-scroll" scrollY>
      <View className="dashboard-page">
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
                  <Text className="metric-value">
                    {batteryValue !== null && batteryValue !== undefined ? batteryValue : '--'}
                  </Text>
                  <Text className="battery-range">最低 {garminData.body_battery_lowest ?? garminData.body_battery_drained ?? '--'}</Text>
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
                  {stressValue || '--'}
                </Text>
                <Text className="stress-badge" style={{ backgroundColor: stressLevel.color }}>
                  {stressLevel.level}
                </Text>
              </View>
              <Text className="stress-tip">
                {stressValue && stressValue <= 25 ? '状态放松，继续保持' : 
                 stressValue && stressValue <= 50 ? '压力适中，注意休息' :
                 stressValue ? '压力偏高，建议放松' : '暂无数据'}
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
          <View className="recommendation-section">
            <View className="section-header">
              <Text className="section-icon">💡</Text>
              <Text className="section-title">AI 健康建议</Text>
            </View>
            {(() => {
              console.log('渲染时检查 - recommendations:', recommendations);
              console.log('渲染时检查 - recommendations.length:', recommendations.length);
              console.log('渲染时检查 - recommendation:', recommendation);
              
              if (recommendations.length > 0) {
                console.log('准备渲染建议列表，数量:', recommendations.length);
                return (
                  <View className="recommendation-list">
                    {recommendations.map((rec, i) => {
                      console.log(`渲染建议 ${i}:`, rec, typeof rec);
                      if (!rec || typeof rec !== 'string') {
                        console.warn(`建议 ${i} 格式异常:`, rec);
                      }
                      return (
                        <View key={`rec-${i}`} className="recommendation-item">
                          <View className="rec-number">{i + 1}</View>
                          <Text className="rec-text">{String(rec || '')}</Text>
                        </View>
                      );
                    })}
                  </View>
                );
              } else {
                return (
                  <View className="no-recommendation">
                    <Text className="no-rec-text">暂无建议数据</Text>
                    <Text className="no-rec-tip">请先同步Garmin数据</Text>
                  </View>
                );
              }
            })()}
          </View>

          {/* 底部留白 */}
          <View className="bottom-space" />
        </>
      )}
      </View>
    </ScrollView>
  );
}
