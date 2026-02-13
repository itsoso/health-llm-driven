/**
 * 健康洞察页面
 */
import { useState } from 'react';
import { View, Text, Button, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { request } from '../../services/request';
import './index.scss';

export default function AIInsights() {
  const [loading, setLoading] = useState(false);
  const [dailyInsights, setDailyInsights] = useState<any[]>([]);
  const [currentRecommendation, setCurrentRecommendation] = useState<any>(null);

  // 生成今日洞察
  const handleGenerateDailyInsight = async () => {
    setLoading(true);
    try {
      Taro.showLoading({ title: '生成中...' });
      await request<any>({
        url: '/ai-insights/insights/daily/generate',
        method: 'POST',
      });

      Taro.hideLoading();
      Taro.showToast({ title: '生成成功', icon: 'success' });

      // 刷新洞察列表
      await loadDailyInsights();
    } catch (error: any) {
      Taro.hideLoading();
      Taro.showToast({
        title: error.message || '生成失败',
        icon: 'none',
        duration: 3000,
      });
    } finally {
      setLoading(false);
    }
  };

  // 加载每日洞察列表
  const loadDailyInsights = async () => {
    try {
      const result = await request<any>({
        url: '/ai-insights/insights/daily?days=7',
        method: 'GET',
      });
      setDailyInsights(result.items || []);
    } catch (error: any) {
      console.error('加载洞察列表失败:', error);
    }
  };

  // 生成实时建议
  const handleGenerateRealtimeRecommendation = async () => {
    setLoading(true);
    try {
      Taro.showLoading({ title: '分析中...' });

      // 尝试获取当前位置（非必须，后端会从用户画像获取城市）
      let latitude: number | undefined;
      let longitude: number | undefined;
      try {
        const location = await Taro.getLocation({ type: 'gcj02' });
        latitude = location.latitude;
        longitude = location.longitude;
      } catch {
        console.log('获取位置失败，将使用用户画像中的城市设置');
      }

      const result = await request<any>({
        url: '/ai-insights/recommendations/realtime',
        method: 'POST',
        data: {
          latitude,
          longitude,
          // city 不传，后端自动从用户画像获取
        },
      });

      Taro.hideLoading();
      Taro.showToast({ title: '生成成功', icon: 'success' });
      setCurrentRecommendation(result);
    } catch (error: any) {
      Taro.hideLoading();
      Taro.showToast({
        title: error.message || '生成失败',
        icon: 'none',
        duration: 3000,
      });
    } finally {
      setLoading(false);
    }
  };

  // 获取最新实时建议
  const handleGetLatestRecommendation = async () => {
    try {
      const result = await request<any>({
        url: '/ai-insights/recommendations/latest',
        method: 'GET',
      });

      if (result) {
        setCurrentRecommendation(result);
        Taro.showToast({ title: '已加载最新建议', icon: 'success' });
      } else {
        Taro.showToast({
          title: '暂无有效建议',
          icon: 'none',
        });
      }
    } catch (error: any) {
      Taro.showToast({
        title: error.message || '加载失败',
        icon: 'none',
      });
    }
  };

  // 查看洞察详情
  const handleViewInsight = (insight: any) => {
    Taro.showModal({
      title: insight.review_date,
      content: insight.content,
      showCancel: false,
      confirmText: '关闭',
    });
  };

  // 页面加载时获取数据
  Taro.useDidShow(() => {
    loadDailyInsights();
    handleGetLatestRecommendation();
  });

  return (
    <ScrollView className="ai-insights-page" scrollY>
      {/* 页面标题 */}
      <View className="page-header">
        <Text className="page-title">🧠 健康洞察</Text>
        <Text className="page-subtitle">每日复盘和实时健康建议</Text>
      </View>

      {/* 每日洞察区域 */}
      <View className="section">
        <View className="section-header">
          <Text className="section-icon">📊</Text>
          <Text className="section-title">每日健康洞察</Text>
        </View>

        <View className="action-card">
          <View className="action-info">
            <Text className="action-title">生成今日洞察</Text>
            <Text className="action-desc">基于今日健康数据生成分析报告</Text>
          </View>
          <Button
            className="action-btn primary"
            onClick={handleGenerateDailyInsight}
            disabled={loading}
          >
            {loading ? '生成中...' : '生成洞察'}
          </Button>
        </View>

        {/* 洞察列表 */}
        {dailyInsights.length > 0 && (
          <View className="insights-list">
            <Text className="list-title">最近洞察（{dailyInsights.length}条）</Text>
            {dailyInsights.map((insight, idx) => (
              <View
                key={insight.id || idx}
                className="insight-item"
                onClick={() => handleViewInsight(insight)}
              >
                <View className="insight-header">
                  <Text className="insight-date">📅 {insight.review_date}</Text>
                  <Text className="insight-time">
                    {new Date(insight.generated_at).toLocaleTimeString('zh-CN', {
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </Text>
                </View>
                {insight.summary && (
                  <Text className="insight-summary">{insight.summary}</Text>
                )}
                <View className="insight-footer">
                  <Text className="insight-action">点击查看详情 →</Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* 实时建议区域 */}
      <View className="section">
        <View className="section-header">
          <Text className="section-icon">⚡</Text>
          <Text className="section-title">实时健康建议</Text>
        </View>

        <View className="action-card">
          <View className="action-info">
            <Text className="action-title">生成实时建议</Text>
            <Text className="action-desc">结合当前时间、位置、天气、身体状态等生成建议</Text>
          </View>
          <Button
            className="action-btn secondary"
            onClick={handleGenerateRealtimeRecommendation}
            disabled={loading}
          >
            {loading ? '分析中...' : '生成建议'}
          </Button>
        </View>

        {/* 当前建议展示 */}
        {currentRecommendation && (
          <View className="recommendation-card">
            <View className="rec-header">
              <View className="rec-badge">
                {currentRecommendation.recommendation_type === 'urgent' && (
                  <Text className="badge urgent">🔴 紧急</Text>
                )}
                {currentRecommendation.recommendation_type === 'important' && (
                  <Text className="badge important">🟡 重要</Text>
                )}
                {currentRecommendation.recommendation_type === 'normal' && (
                  <Text className="badge normal">🟢 常规</Text>
                )}
              </View>
              <Text className="rec-time">
                {new Date(currentRecommendation.generated_at).toLocaleString('zh-CN', {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </Text>
            </View>

            <View className="rec-content">
              <Text className="rec-text">{currentRecommendation.content}</Text>
            </View>

            {/* 上下文信息 */}
            {currentRecommendation.context_data && (
              <View className="rec-context">
                <Text className="context-title">📍 上下文信息</Text>
                {currentRecommendation.weather_data && (
                  <View className="context-row">
                    <Text className="context-label">天气:</Text>
                    <Text className="context-value">
                      {currentRecommendation.weather_data.weather_condition}{' '}
                      {currentRecommendation.weather_data.temperature}°C
                    </Text>
                  </View>
                )}
                {currentRecommendation.air_quality_data && (
                  <View className="context-row">
                    <Text className="context-label">空气:</Text>
                    <Text className="context-value">
                      AQI {currentRecommendation.air_quality_data.aqi}{' '}
                      {currentRecommendation.air_quality_data.quality_level}
                    </Text>
                  </View>
                )}
                {currentRecommendation.location && (
                  <View className="context-row">
                    <Text className="context-label">位置:</Text>
                    <Text className="context-value">
                      {currentRecommendation.location.city || '当前位置'}
                    </Text>
                  </View>
                )}
              </View>
            )}

            {/* 过期时间 */}
            {currentRecommendation.expires_at && (
              <View className="rec-footer">
                <Text className="rec-expires">
                  有效期至: {new Date(currentRecommendation.expires_at).toLocaleString('zh-CN')}
                </Text>
              </View>
            )}
          </View>
        )}
      </View>

      <View style={{ height: '40px' }} />
    </ScrollView>
  );
}
