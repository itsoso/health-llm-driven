/**
 * 数据面板页
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getTodayGarminData, getDailyRecommendation, syncMyGarminData, getTodayExternalRecommendations } from '../../services/api';
import { formatSleepDuration, getSleepScoreLevel, getStressLevel } from '../../types';
import type { GarminData, DailyRecommendation, TodayExternalRecommendations, ExternalRecommendation } from '../../types';
import './index.scss';

// Markdown 渲染组件 - 使用原生 View/Text 组件
interface MarkdownNode {
  type: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'p' | 'ul' | 'ol' | 'hr' | 'table' | 'blockquote' | 'code';
  content?: string;
  items?: string[];
  rows?: string[][];
}

function parseMarkdown(markdown: string): MarkdownNode[] {
  if (!markdown) return [];
  const nodes: MarkdownNode[] = [];

  // 按行处理，更精确地解析
  const lines = markdown.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) { i++; continue; }

    // 标题 (支持 1-6 级)
    if (line.startsWith('###### ')) {
      nodes.push({ type: 'h6', content: line.replace(/^###### /, '') });
      i++; continue;
    }
    if (line.startsWith('##### ')) {
      nodes.push({ type: 'h5', content: line.replace(/^##### /, '') });
      i++; continue;
    }
    if (line.startsWith('#### ')) {
      nodes.push({ type: 'h4', content: line.replace(/^#### /, '') });
      i++; continue;
    }
    if (line.startsWith('### ')) {
      nodes.push({ type: 'h3', content: line.replace(/^### /, '') });
      i++; continue;
    }
    if (line.startsWith('## ')) {
      nodes.push({ type: 'h2', content: line.replace(/^## /, '') });
      i++; continue;
    }
    if (line.startsWith('# ')) {
      nodes.push({ type: 'h1', content: line.replace(/^# /, '') });
      i++; continue;
    }

    // 引用块
    if (line.startsWith('> ')) {
      const quoteLines: string[] = [line.replace(/^> ?/, '')];
      let j = i + 1;
      while (j < lines.length && lines[j].trim().startsWith('>')) {
        quoteLines.push(lines[j].trim().replace(/^> ?/, ''));
        j++;
      }
      nodes.push({ type: 'blockquote', content: quoteLines.join('\n') });
      i = j; continue;
    }

    // 代码块
    if (line.startsWith('```')) {
      const codeLines: string[] = [];
      let j = i + 1;
      while (j < lines.length && !lines[j].trim().startsWith('```')) {
        codeLines.push(lines[j]);
        j++;
      }
      nodes.push({ type: 'code', content: codeLines.join('\n') });
      i = j + 1; continue;
    }

    // 分隔线
    if (/^[-*_]{3,}$/.test(line)) {
      nodes.push({ type: 'hr' });
      i++; continue;
    }

    // 表格 - 检测连续的表格行
    if (line.includes('|')) {
      const tableLines: string[] = [line];
      let j = i + 1;
      while (j < lines.length && lines[j].includes('|')) {
        tableLines.push(lines[j]);
        j++;
      }
      if (tableLines.length > 1) {
        const rows = tableLines
          .filter(l => l.trim() && !l.match(/^\|?[\s-|]+\|?$/))
          .map(l => l.split('|').filter(cell => cell.trim()).map(cell => cell.trim()));
        if (rows.length > 0) {
          nodes.push({ type: 'table', rows });
          i = j; continue;
        }
      }
    }

    // 无序列表 - 收集连续的列表项
    if (/^[-*+•]\s/.test(line)) {
      const items: string[] = [line.replace(/^[-*+•]\s+/, '')];
      let j = i + 1;
      while (j < lines.length && /^[-*+•]\s/.test(lines[j].trim())) {
        items.push(lines[j].trim().replace(/^[-*+•]\s+/, ''));
        j++;
      }
      nodes.push({ type: 'ul', items });
      i = j; continue;
    }

    // 有序列表
    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [line.replace(/^\d+\.\s+/, '')];
      let j = i + 1;
      while (j < lines.length && /^\d+\.\s/.test(lines[j].trim())) {
        items.push(lines[j].trim().replace(/^\d+\.\s+/, ''));
        j++;
      }
      nodes.push({ type: 'ol', items });
      i = j; continue;
    }

    // 普通段落
    nodes.push({ type: 'p', content: line });
    i++;
  }

  return nodes;
}

// 处理行内格式（粗体）
function formatText(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1');
}

// Markdown 渲染组件
function MarkdownRenderer({ content }: { content: string }) {
  const nodes = parseMarkdown(content);

  return (
    <View className="md-content">
      {nodes.map((node, index) => {
        switch (node.type) {
          case 'h1':
            return <Text key={index} className="md-h1">{formatText(node.content || '')}</Text>;
          case 'h2':
            return <Text key={index} className="md-h2">{formatText(node.content || '')}</Text>;
          case 'h3':
            return <Text key={index} className="md-h3">{formatText(node.content || '')}</Text>;
          case 'h4':
            return <Text key={index} className="md-h4">{formatText(node.content || '')}</Text>;
          case 'h5':
            return <Text key={index} className="md-h5">{formatText(node.content || '')}</Text>;
          case 'h6':
            return <Text key={index} className="md-h6">{formatText(node.content || '')}</Text>;
          case 'blockquote':
            return (
              <View key={index} className="md-blockquote">
                <Text className="md-blockquote-text">{formatText(node.content || '')}</Text>
              </View>
            );
          case 'code':
            return (
              <View key={index} className="md-code">
                <Text className="md-code-text">{node.content || ''}</Text>
              </View>
            );
          case 'hr':
            return <View key={index} className="md-hr" />;
          case 'ul':
            return (
              <View key={index} className="md-ul">
                {node.items?.map((item, i) => (
                  <View key={i} className="md-li">
                    <Text className="md-li-marker">•</Text>
                    <Text className="md-li-text">{formatText(item)}</Text>
                  </View>
                ))}
              </View>
            );
          case 'ol':
            return (
              <View key={index} className="md-ol">
                {node.items?.map((item, i) => (
                  <View key={i} className="md-li">
                    <Text className="md-li-marker">{i + 1}.</Text>
                    <Text className="md-li-text">{formatText(item)}</Text>
                  </View>
                ))}
              </View>
            );
          case 'table':
            return (
              <View key={index} className="md-table">
                {node.rows?.map((row, rowIndex) => (
                  <View key={rowIndex} className={`md-tr ${rowIndex === 0 ? 'md-thead' : ''}`}>
                    {row.map((cell, cellIndex) => (
                      <Text key={cellIndex} className="md-td">{formatText(cell)}</Text>
                    ))}
                  </View>
                ))}
              </View>
            );
          case 'p':
          default:
            return <Text key={index} className="md-p">{formatText(node.content || '')}</Text>;
        }
      })}
    </View>
  );
}

// 类别配置
const CATEGORY_CONFIG: Record<string, { icon: string; label: string }> = {
  exercise: { icon: '🏃', label: '运动' },
  diet: { icon: '🥗', label: '饮食' },
  sleep: { icon: '😴', label: '睡眠' },
  supplement: { icon: '💊', label: '补剂' },
  general: { icon: '✨', label: '综合' },
};
const CATEGORY_ORDER = ['exercise', 'diet', 'sleep', 'supplement', 'general'];

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [garminData, setGarminData] = useState<GarminData | null>(null);
  const [recommendation, setRecommendation] = useState<DailyRecommendation | null>(null);
  // 新增：Tab 切换和外部建议
  const [activeTab, setActiveTab] = useState<'ai' | 'external'>('ai');
  const [externalData, setExternalData] = useState<TodayExternalRecommendations | null>(null);
  const [externalLoading, setExternalLoading] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    // 检查是否已登录
    const token = Taro.getStorageSync('access_token');
    if (!token) {
      Taro.switchTab({ url: '/pages/index/index' });
      return;
    }
    loadData();
  }, []);

  // 切换到外部建议时加载数据
  useEffect(() => {
    if (activeTab === 'external' && !externalData) {
      loadExternalData();
    }
  }, [activeTab]);

  const loadExternalData = async () => {
    setExternalLoading(true);
    try {
      const data = await getTodayExternalRecommendations();
      setExternalData(data);
    } catch (e) {
      console.error('加载外部建议失败:', e);
    } finally {
      setExternalLoading(false);
    }
  };

  const toggleExpand = (id: number) => {
    setExpandedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) newSet.delete(id);
      else newSet.add(id);
      return newSet;
    });
  };

  const cleanTitle = (title: string) => {
    if (!title) return '';
    return title.replace(/^#{1,6}\s*/, '').replace(/\*\*([^*]+)\*\*/g, '$1').trim();
  };

  const getContentPreview = (content: string) => {
    if (!content) return '';
    const plainText = content
      .replace(/#{1,6}\s/g, '')
      .replace(/\*\*([^*]+)\*\*/g, '$1')
      .replace(/\*([^*]+)\*/g, '$1')
      .replace(/\n+/g, ' ')
      .trim();
    return plainText.length > 80 ? plainText.slice(0, 80) + '...' : plainText;
  };

  const formatTime = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch { return ''; }
  };

  // 页面显示时刷新
  Taro.useDidShow(() => {
    const token = Taro.getStorageSync('access_token');
    if (token) {
      loadData();
    }
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
          console.error('获取建议失败:', err);
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

  const [syncing, setSyncing] = useState(false);

  const handleRefresh = async () => {
    Taro.showLoading({ title: '同步中...' });
    setSyncing(true);
    
    try {
      // 先尝试同步 Garmin 数据
      console.log('[Dashboard] 开始同步 Garmin 数据...');
      const syncResult = await syncMyGarminData(1).catch((err) => {
        console.log('[Dashboard] Garmin同步失败或未绑定:', err?.message || err);
        return null;
      });
      
      console.log('[Dashboard] 同步结果:', syncResult);
      
      if (syncResult?.status === 'success') {
        Taro.showToast({ title: '同步成功', icon: 'success', duration: 1500 });
        // 同步成功后等待更长时间让数据入库
        await new Promise(resolve => setTimeout(resolve, 1000));
      } else if (syncResult?.status === 'no_data') {
        Taro.showToast({ title: '暂无新数据', icon: 'none', duration: 1500 });
      } else if (syncResult?.status === 'skipped') {
        Taro.showToast({ title: syncResult.message || '同步跳过', icon: 'none', duration: 1500 });
      }
      
      // 重新加载数据
      console.log('[Dashboard] 开始重新加载数据...');
      await loadData();
      console.log('[Dashboard] 数据加载完成');
      
    } catch (error: any) {
      console.error('[Dashboard] 刷新失败:', error);
      // 如果是未绑定，仍然刷新数据
      await loadData();
      Taro.showToast({ title: '数据已刷新', icon: 'success', duration: 1000 });
    } finally {
      setSyncing(false);
      Taro.hideLoading();
    }
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
  // 优先使用当前电量，其次使用最高电量
  const currentBattery = garminData?.body_battery_current ?? null;
  const maxBattery = garminData?.body_battery_most_charged ?? garminData?.body_battery_charged ?? null;
  const displayBattery = currentBattery ?? maxBattery;
  const batteryProgress = getBatteryProgress(displayBattery);
  
  console.log('身体电量数据 - dashboard:', {
    current: garminData?.body_battery_current,
    most_charged: garminData?.body_battery_most_charged,
    charged: garminData?.body_battery_charged,
    displayBattery,
    batteryProgress,
  });
  
  console.log('血氧数据 - dashboard:', {
    spo2_avg: garminData?.spo2_avg,
    spo2_min: garminData?.spo2_min,
    spo2_max: garminData?.spo2_max,
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

  // 渲染外部建议内容
  const renderExternalAdvice = () => {
    if (externalLoading) {
      return (
        <View className="external-loading">
          <View className="loading-spinner" />
          <Text className="loading-text">加载中...</Text>
        </View>
      );
    }

    if (!externalData?.has_recommendations) {
      return (
        <View className="external-empty">
          <Text className="empty-icon">📭</Text>
          <Text className="empty-title">暂无外部建议</Text>
          <Text className="empty-text">外部健康助手分析您的数据后，会在这里展示个性化建议</Text>
        </View>
      );
    }

    return (
      <View className="external-content">
        {CATEGORY_ORDER.map((category) => {
          const recs = externalData.categories[category];
          if (!recs || recs.length === 0) return null;
          const config = CATEGORY_CONFIG[category] || { icon: '📋', label: category };

          return (
            <View key={category} className={`ext-category category-${category}`}>
              <View className="ext-category-header">
                <Text className="ext-category-icon">{config.icon}</Text>
                <Text className="ext-category-title">{config.label}</Text>
                <Text className="ext-category-count">({recs.length})</Text>
              </View>

              {recs.map((rec: ExternalRecommendation) => (
                <View key={rec.id} className="ext-advice-card expanded">
                  <View className="ext-advice-header">
                    <Text className="ext-advice-title">{cleanTitle(rec.title)}</Text>
                  </View>
                  <View className="ext-advice-meta">
                    <Text className="ext-source-name">{rec.source_name}</Text>
                    <Text className="ext-advice-time">{formatTime(rec.created_at)}</Text>
                  </View>
                  {/* 直接显示完整内容 */}
                  <View className="ext-advice-content">
                    <MarkdownRenderer content={rec.content} />
                  </View>
                </View>
              ))}
            </View>
          );
        })}
      </View>
    );
  };

  return (
    <ScrollView className="dashboard-scroll" scrollY>
      <View className="dashboard-page">
        {/* 头部 */}
        <View className="header">
          <View className="header-left">
            <Text className="title">健康建议</Text>
            <Text className="subtitle">
              {new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'short' })}
            </Text>
          </View>
          <View className={`refresh-btn ${syncing ? 'syncing' : ''}`} onClick={syncing ? undefined : (activeTab === 'ai' ? handleRefresh : loadExternalData)}>
            <Text className="refresh-icon">{syncing || externalLoading ? '⏳' : '🔄'}</Text>
          </View>
        </View>

        {/* Tab 切换 */}
        <View className="tab-bar">
          <View className={`tab-item ${activeTab === 'ai' ? 'active' : ''}`} onClick={() => setActiveTab('ai')}>
            <Text className="tab-text">💡 智能建议</Text>
          </View>
          <View className={`tab-item ${activeTab === 'external' ? 'active' : ''}`} onClick={() => setActiveTab('external')}>
            <Text className="tab-text">📡 多源建议</Text>
          </View>
        </View>

        {/* 外部建议 Tab */}
        {activeTab === 'external' && renderExternalAdvice()}

        {/* 智能建议 Tab */}
        {activeTab === 'ai' && (
          <>
            {!garminData ? (
              <View className="no-data">
          <View className="no-data-icon-wrap">
            <Text className="no-data-icon">📈</Text>
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
                    {displayBattery !== null && displayBattery !== undefined ? displayBattery : '--'}
                  </Text>
                  <Text className="battery-range">
                    {currentBattery !== null ? '当前' : '峰值'} · 
                    {maxBattery !== null && currentBattery !== null && currentBattery !== maxBattery 
                      ? ` 峰值${maxBattery}`
                      : ` 最低${garminData.body_battery_lowest ?? garminData.body_battery_drained ?? '--'}`}
                  </Text>
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
                <Text className="metric-value">
                  {garminData.spo2_avg !== null && garminData.spo2_avg !== undefined 
                    ? Math.round(garminData.spo2_avg) 
                    : '--'}
                </Text>
                <Text className="metric-unit">%</Text>
              </View>
              <Text className="spo2-range">
                {garminData.spo2_min !== null && garminData.spo2_min !== undefined &&
                 garminData.spo2_max !== null && garminData.spo2_max !== undefined
                  ? `${garminData.spo2_min}% - ${garminData.spo2_max}%`
                  : '暂无数据'}
              </Text>
            </View>
          </View>

          {/* 健康建议 */}
          <View className="recommendation-section">
            <View className="section-header">
              <Text className="section-icon">💡</Text>
              <Text className="section-title">健康建议</Text>
            </View>
            {recommendations.length > 0 ? (
              <View className="recommendation-list">
                {recommendations.map((rec, i) => {
                  if (!rec || typeof rec !== 'string') {
                    console.warn(`建议 ${i} 格式异常:`, rec);
                    return null;
                  }
                  return (
                    <View key={`rec-${i}`} className="recommendation-item">
                      <View className="rec-number">{i + 1}</View>
                      <Text className="rec-text">{String(rec)}</Text>
                    </View>
                  );
                })}
              </View>
            ) : (
              <View className="no-recommendation">
                <Text className="no-rec-text">暂无建议数据</Text>
                <Text className="no-rec-tip">请先同步Garmin数据</Text>
              </View>
            )}
          </View>

          {/* 底部留白 */}
          <View className="bottom-space" />
        </>
      )}
          </>
        )}
      </View>
    </ScrollView>
  );
}
