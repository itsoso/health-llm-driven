/**
 * 身体成分分析页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getBodyCompositionTrend, getBodyAnalysis } from '../../services/api';
import type { BodyCompositionTrend, BodyAnalysisResult, BodyAnalysisItem } from '../../types';
import './index.scss';

type Tab = 'trend' | 'analysis';

function getStatusColor(status: string): string {
  const map: Record<string, string> = {
    '正常': '#10b981',
    '充足': '#10b981',
    '偏低': '#f59e0b',
    '偏高': '#f97316',
    '过高': '#ef4444',
    '肥胖': '#ef4444',
  };
  return map[status] || '#6b7280';
}

export default function BodyCompositionPage() {
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>('trend');
  const [days, setDays] = useState(30);
  const [trend, setTrend] = useState<BodyCompositionTrend | null>(null);
  const [analysis, setAnalysis] = useState<BodyAnalysisResult | null>(null);

  useEffect(() => {
    loadData();
  }, [days]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [trendRes, analysisRes] = await Promise.allSettled([
        getBodyCompositionTrend(days),
        getBodyAnalysis(),
      ]);

      if (trendRes.status === 'fulfilled') {
        setTrend(trendRes.value);
      }
      if (analysisRes.status === 'fulfilled') {
        setAnalysis(analysisRes.value);
      }
    } catch (e) {
      console.error('加载身体成分数据失败:', e);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <View className="bc-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  const summary = trend?.summary;
  const dataPoints = trend?.data_points || [];

  return (
    <View className="bc-page">
      <ScrollView className="bc-scroll" scrollY>
        {/* Tab 切换 */}
        <View className="tab-bar">
          <View
            className={`tab-item ${tab === 'trend' ? 'active' : ''}`}
            onClick={() => setTab('trend')}
          >
            <Text>趋势</Text>
          </View>
          <View
            className={`tab-item ${tab === 'analysis' ? 'active' : ''}`}
            onClick={() => setTab('analysis')}
          >
            <Text>分析</Text>
          </View>
        </View>

        {/* 摘要卡片 */}
        {summary && summary.current_weight && (
          <View className="summary-card">
            <View className="summary-row">
              <View className="summary-item">
                <Text className="summary-value">{summary.current_weight}</Text>
                <Text className="summary-unit">kg</Text>
                <Text className="summary-label">体重</Text>
                {summary.weight_change !== null && (
                  <Text className={`summary-change ${summary.weight_change > 0 ? 'up' : 'down'}`}>
                    {summary.weight_change > 0 ? '+' : ''}{summary.weight_change}
                  </Text>
                )}
              </View>
              <View className="summary-item">
                <Text className="summary-value">{summary.current_body_fat ?? '--'}</Text>
                <Text className="summary-unit">%</Text>
                <Text className="summary-label">体脂率</Text>
                {summary.body_fat_change !== undefined && (
                  <Text className={`summary-change ${summary.body_fat_change > 0 ? 'up' : 'down'}`}>
                    {summary.body_fat_change > 0 ? '+' : ''}{summary.body_fat_change}%
                  </Text>
                )}
              </View>
              <View className="summary-item">
                <Text className="summary-value">{summary.current_muscle_mass ?? '--'}</Text>
                <Text className="summary-unit">kg</Text>
                <Text className="summary-label">肌肉量</Text>
                {summary.muscle_mass_change !== undefined && (
                  <Text className={`summary-change ${summary.muscle_mass_change > 0 ? 'down' : 'up'}`}>
                    {summary.muscle_mass_change > 0 ? '+' : ''}{summary.muscle_mass_change}
                  </Text>
                )}
              </View>
            </View>
            <View className="summary-row">
              <View className="summary-item">
                <Text className="summary-value">{summary.current_bmi ?? '--'}</Text>
                <Text className="summary-label">BMI</Text>
              </View>
              <View className="summary-item">
                <Text className="summary-value">{summary.record_count}</Text>
                <Text className="summary-label">记录数</Text>
              </View>
            </View>
          </View>
        )}

        {tab === 'trend' && (
          <>
            {/* 天数选择 */}
            <View className="days-selector">
              {[7, 30, 90].map((d) => (
                <View
                  key={d}
                  className={`days-btn ${days === d ? 'active' : ''}`}
                  onClick={() => setDays(d)}
                >
                  <Text>{d}天</Text>
                </View>
              ))}
            </View>

            {dataPoints.length === 0 ? (
              <View className="empty-state">
                <Text className="empty-icon">📊</Text>
                <Text className="empty-text">暂无身体成分数据</Text>
                <Text className="empty-hint">在体重记录页面添加数据后查看趋势</Text>
              </View>
            ) : (
              <View className="trend-list">
                <Text className="section-title">数据记录</Text>
                {dataPoints.slice().reverse().map((point, idx) => (
                  <View key={idx} className="trend-item">
                    <View className="trend-date">
                      <Text>{point.date}</Text>
                    </View>
                    <View className="trend-metrics">
                      <View className="metric">
                        <Text className="metric-value">{point.weight}</Text>
                        <Text className="metric-label">kg</Text>
                      </View>
                      {point.body_fat_percentage && (
                        <View className="metric">
                          <Text className="metric-value">{point.body_fat_percentage}</Text>
                          <Text className="metric-label">%体脂</Text>
                        </View>
                      )}
                      {point.muscle_mass_kg && (
                        <View className="metric">
                          <Text className="metric-value">{point.muscle_mass_kg}</Text>
                          <Text className="metric-label">肌肉</Text>
                        </View>
                      )}
                      {point.bmi && (
                        <View className="metric">
                          <Text className="metric-value">{point.bmi}</Text>
                          <Text className="metric-label">BMI</Text>
                        </View>
                      )}
                      {point.water_percentage && (
                        <View className="metric">
                          <Text className="metric-value">{point.water_percentage}</Text>
                          <Text className="metric-label">%水分</Text>
                        </View>
                      )}
                    </View>
                  </View>
                ))}
              </View>
            )}
          </>
        )}

        {tab === 'analysis' && (
          <>
            {analysis?.status === 'no_data' ? (
              <View className="empty-state">
                <Text className="empty-icon">🔬</Text>
                <Text className="empty-text">暂无分析数据</Text>
                <Text className="empty-hint">记录体重和身体成分后查看健康分析</Text>
              </View>
            ) : (
              <View className="analysis-section">
                {analysis?.record_date && (
                  <Text className="analysis-date">数据日期: {analysis.record_date}</Text>
                )}
                {analysis?.analysis?.map((item: BodyAnalysisItem, i: number) => (
                  <View key={i} className="analysis-card">
                    <View className="analysis-header">
                      <Text className="analysis-metric">{item.metric}</Text>
                      <View
                        className="analysis-badge"
                        style={{ backgroundColor: getStatusColor(item.status) + '20', color: getStatusColor(item.status) }}
                      >
                        <Text style={{ color: getStatusColor(item.status) }}>{item.status}</Text>
                      </View>
                    </View>
                    <Text className="analysis-value">当前值: {item.value}</Text>
                    <Text className="analysis-advice">{item.advice}</Text>
                  </View>
                ))}
              </View>
            )}
          </>
        )}

        <View className="bottom-spacer" />
      </ScrollView>
    </View>
  );
}
