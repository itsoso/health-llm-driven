/**
 * 健康报告页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { generateHealthReport, getHealthReports, getHealthReportDetail } from '../../services/api';
import type { HealthReportItem } from '../../services/api';
import './index.scss';

function formatMinutes(mins: number | null | undefined): string {
  if (!mins) return '--';
  const h = Math.floor(mins / 60);
  const m = Math.round(mins % 60);
  return `${h}h${m}m`;
}

function getScoreColor(score: number | null): string {
  if (!score) return '#9ca3af';
  if (score >= 80) return '#22c55e';
  if (score >= 60) return '#eab308';
  if (score >= 40) return '#f97316';
  return '#ef4444';
}

export default function HealthReportPage() {
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [reports, setReports] = useState<HealthReportItem[]>([]);
  const [selectedReport, setSelectedReport] = useState<HealthReportItem | null>(null);

  useEffect(() => {
    loadReports();
  }, []);

  const loadReports = async () => {
    try {
      setLoading(true);
      const data = await getHealthReports(20);
      setReports(data);
    } catch (e) {
      console.error('[Report] 加载失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async (type: string) => {
    if (generating) return;
    try {
      setGenerating(true);
      Taro.showLoading({ title: '生成中...' });
      const report = await generateHealthReport(type);
      Taro.hideLoading();
      Taro.showToast({ title: '报告已生成', icon: 'success' });
      setSelectedReport(report);
      loadReports();
    } catch (e) {
      Taro.hideLoading();
      console.error('[Report] 生成失败:', e);
      Taro.showToast({ title: '生成失败', icon: 'none' });
    } finally {
      setGenerating(false);
    }
  };

  if (loading) {
    return (
      <View className='report-page loading'>
        <View className='loading-spinner' />
        <Text className='loading-text'>加载中...</Text>
      </View>
    );
  }

  // 报告详情
  if (selectedReport) {
    const r = selectedReport;
    return (
      <ScrollView className='report-page' scrollY>
        <View className='back-btn' onClick={() => setSelectedReport(null)}>
          <Text className='back-text'>&lt; 返回列表</Text>
        </View>

        {/* 头部 */}
        <View className='detail-header'>
          <View className='header-info'>
            <Text className='report-title'>{r.title}</Text>
            <Text className='report-date'>{r.start_date} ~ {r.end_date}</Text>
          </View>
          <View className='score-circle' style={{ borderColor: getScoreColor(r.health_score) }}>
            <Text className='score-num' style={{ color: getScoreColor(r.health_score) }}>
              {r.health_score ?? '--'}
            </Text>
            <Text className='score-label'>健康分</Text>
          </View>
        </View>

        {/* 数据摘要 */}
        <View className='summary-grid'>
          <View className='summary-card'>
            <Text className='card-title'>运动</Text>
            <View className='metric'><Text className='metric-label'>日均步数</Text><Text className='metric-value'>{r.exercise_summary?.avg_daily_steps?.toLocaleString() || '--'}</Text></View>
            <View className='metric'><Text className='metric-label'>总消耗</Text><Text className='metric-value'>{r.exercise_summary?.total_calories_burned || '--'} kcal</Text></View>
          </View>

          <View className='summary-card'>
            <Text className='card-title'>睡眠</Text>
            <View className='metric'><Text className='metric-label'>平均时长</Text><Text className='metric-value'>{formatMinutes(r.sleep_summary?.avg_sleep_duration)}</Text></View>
            <View className='metric'><Text className='metric-label'>平均评分</Text><Text className='metric-value'>{r.sleep_summary?.avg_sleep_score || '--'}</Text></View>
          </View>

          <View className='summary-card'>
            <Text className='card-title'>饮食</Text>
            <View className='metric'><Text className='metric-label'>日均热量</Text><Text className='metric-value'>{r.diet_summary?.avg_daily_calories || '--'} kcal</Text></View>
            <View className='metric'><Text className='metric-label'>记录天数</Text><Text className='metric-value'>{r.diet_summary?.record_days || 0} 天</Text></View>
          </View>

          <View className='summary-card'>
            <Text className='card-title'>情绪</Text>
            <View className='metric'><Text className='metric-label'>平均情绪</Text><Text className='metric-value'>{r.mood_summary?.avg_mood_score || '--'}/5</Text></View>
            <View className='metric'><Text className='metric-label'>记录天数</Text><Text className='metric-value'>{r.mood_summary?.record_days || 0} 天</Text></View>
          </View>
        </View>

        {/* 建议 */}
        {r.ai_recommendations?.length > 0 && (
          <View className='recommendations'>
            <Text className='section-title'>健康建议</Text>
            {r.ai_recommendations.map((rec, i) => (
              <View key={i} className='rec-item'>
                <Text className='rec-icon'>💡</Text>
                <Text className='rec-text'>{rec}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    );
  }

  // 报告列表
  return (
    <ScrollView className='report-page' scrollY>
      {/* 生成按钮 */}
      <View className='generate-buttons'>
        <View className='gen-btn weekly' onClick={() => handleGenerate('weekly')}>
          <Text className='gen-text'>{generating ? '生成中...' : '生成周报'}</Text>
        </View>
        <View className='gen-btn monthly' onClick={() => handleGenerate('monthly')}>
          <Text className='gen-text'>{generating ? '生成中...' : '生成月报'}</Text>
        </View>
      </View>

      {/* 列表 */}
      {reports.length === 0 ? (
        <View className='empty-state'>
          <Text className='empty-text'>还没有健康报告</Text>
          <Text className='empty-hint'>点击上方按钮生成第一份报告</Text>
        </View>
      ) : (
        <View className='report-list'>
          {reports.map(report => (
            <View key={report.id} className='report-card' onClick={() => setSelectedReport(report)}>
              <View className='card-score' style={{ borderColor: getScoreColor(report.health_score) }}>
                <Text className='card-score-num' style={{ color: getScoreColor(report.health_score) }}>
                  {report.health_score ?? '--'}
                </Text>
              </View>
              <View className='card-info'>
                <Text className='card-title-text'>{report.title}</Text>
                <Text className='card-date'>{report.start_date.slice(5)} ~ {report.end_date.slice(5)}</Text>
              </View>
              <View className='card-badge'>
                <Text className='badge-text'>{report.report_type === 'weekly' ? '周报' : '月报'}</Text>
              </View>
            </View>
          ))}
        </View>
      )}
    </ScrollView>
  );
}
