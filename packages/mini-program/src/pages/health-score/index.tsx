/**
 * 健康评分页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getDailyHealthScore, getHealthScoreTrend } from '../../services/api';
import type { HealthScoreResult, HealthScoreTrend, HealthScoreDimension } from '../../types';
import './index.scss';

function getScoreColor(score: number): string {
  if (score >= 80) return '#22c55e';
  if (score >= 60) return '#eab308';
  if (score >= 40) return '#f97316';
  return '#ef4444';
}

export default function HealthScorePage() {
  const [loading, setLoading] = useState(true);
  const [scoreData, setScoreData] = useState<HealthScoreResult | null>(null);
  const [trendData, setTrendData] = useState<HealthScoreTrend | null>(null);
  const [trendDays, setTrendDays] = useState(7);

  useEffect(() => {
    loadData();
  }, [trendDays]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [scoreRes, trendRes] = await Promise.allSettled([
        getDailyHealthScore(),
        getHealthScoreTrend(trendDays),
      ]);

      if (scoreRes.status === 'fulfilled') {
        setScoreData(scoreRes.value);
      }
      if (trendRes.status === 'fulfilled') {
        setTrendData(trendRes.value);
      }
    } catch (e) {
      console.error('加载健康评分失败:', e);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <View className="hs-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">计算评分中...</Text>
      </View>
    );
  }

  return (
    <View className="hs-page">
      <ScrollView className="hs-scroll" scrollY>
        {scoreData?.status === 'no_data' ? (
          <View className="empty-state">
            <Text className="empty-icon">📊</Text>
            <Text className="empty-text">暂无健康数据</Text>
            <Text className="empty-hint">记录运动、睡眠、饮食等数据后查看评分</Text>
          </View>
        ) : (
          <>
            {/* 总分 */}
            <View className="score-card">
              <View className="score-ring">
                <Text className="score-value" style={{ color: getScoreColor(scoreData?.total_score || 0) }}>
                  {scoreData?.total_score || 0}
                </Text>
                <Text className="score-grade">{scoreData?.grade}</Text>
              </View>
              <Text className="score-date">{scoreData?.date}</Text>
            </View>

            {/* 维度列表 */}
            <View className="dimensions-card">
              <Text className="card-title">各维度评分</Text>
              {scoreData?.dimensions?.map((dim: HealthScoreDimension, i: number) => (
                <View key={i} className="dimension-item">
                  <View className="dim-header">
                    <Text className="dim-name">{dim.name}</Text>
                    <Text className="dim-score" style={{ color: getScoreColor(dim.score) }}>
                      {dim.score}
                    </Text>
                  </View>
                  <View className="dim-bar-bg">
                    <View
                      className="dim-bar-fill"
                      style={{
                        width: `${dim.score}%`,
                        backgroundColor: getScoreColor(dim.score),
                      }}
                    />
                  </View>
                  <Text className="dim-desc">{dim.description}</Text>
                </View>
              ))}
            </View>

            {/* 建议 */}
            {scoreData?.suggestions && scoreData.suggestions.length > 0 && (
              <View className="suggestions-card">
                <Text className="card-title">改善建议</Text>
                {scoreData.suggestions.map((s: string, i: number) => (
                  <View key={i} className="suggestion-item">
                    <Text className="suggestion-dot">&#x2022;</Text>
                    <Text className="suggestion-text">{s}</Text>
                  </View>
                ))}
              </View>
            )}

            {/* 趋势 */}
            <View className="trend-card">
              <View className="trend-header">
                <Text className="card-title">评分趋势</Text>
                <View className="days-selector">
                  {[7, 14, 30].map((d) => (
                    <View
                      key={d}
                      className={`days-btn ${trendDays === d ? 'active' : ''}`}
                      onClick={() => setTrendDays(d)}
                    >
                      <Text>{d}天</Text>
                    </View>
                  ))}
                </View>
              </View>

              {trendData?.avg_score && (
                <View className="trend-stats">
                  <Text className="trend-avg">
                    平均: <Text style={{ color: getScoreColor(trendData.avg_score), fontWeight: '600' }}>{trendData.avg_score}</Text>
                  </Text>
                  {trendData.trend && (
                    <Text className="trend-direction">
                      趋势: <Text style={{ color: trendData.trend === 'up' ? '#22c55e' : trendData.trend === 'down' ? '#ef4444' : '#6b7280' }}>
                        {trendData.trend === 'up' ? '上升' : trendData.trend === 'down' ? '下降' : '稳定'}
                      </Text>
                    </Text>
                  )}
                </View>
              )}

              {trendData?.scores && trendData.scores.length > 0 ? (
                <View className="trend-list">
                  {trendData.scores.slice().reverse().map((s, i) => (
                    <View key={i} className="trend-item">
                      <Text className="trend-date">{s.date.slice(5)}</Text>
                      <View className="trend-bar-bg">
                        <View
                          className="trend-bar-fill"
                          style={{
                            width: `${s.score}%`,
                            backgroundColor: getScoreColor(s.score),
                          }}
                        />
                      </View>
                      <Text className="trend-score" style={{ color: getScoreColor(s.score) }}>
                        {s.score}
                      </Text>
                    </View>
                  ))}
                </View>
              ) : (
                <Text className="no-trend">暂无趋势数据</Text>
              )}
            </View>
          </>
        )}

        <View className="bottom-spacer" />
      </ScrollView>
    </View>
  );
}
