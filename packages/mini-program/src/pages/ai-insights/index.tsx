/**
 * 健康洞察页面
 */
import { useState } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { request } from '../../services/request';
import './index.scss';

// ========== Markdown 解析与渲染 ==========

interface MarkdownNode {
  type: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'p' | 'ul' | 'ol' | 'hr' | 'table' | 'blockquote' | 'code';
  content?: string;
  items?: string[];
  rows?: string[][];
}

function parseMarkdown(markdown: string): MarkdownNode[] {
  if (!markdown) return [];
  const nodes: MarkdownNode[] = [];
  const lines = markdown.split('\n');
  let i = 0;

  while (i < lines.length) {
    const line = lines[i].trim();
    if (!line) { i++; continue; }

    if (line.startsWith('###### ')) { nodes.push({ type: 'h6', content: line.replace(/^###### /, '') }); i++; continue; }
    if (line.startsWith('##### ')) { nodes.push({ type: 'h5', content: line.replace(/^##### /, '') }); i++; continue; }
    if (line.startsWith('#### ')) { nodes.push({ type: 'h4', content: line.replace(/^#### /, '') }); i++; continue; }
    if (line.startsWith('### ')) { nodes.push({ type: 'h3', content: line.replace(/^### /, '') }); i++; continue; }
    if (line.startsWith('## ')) { nodes.push({ type: 'h2', content: line.replace(/^## /, '') }); i++; continue; }
    if (line.startsWith('# ')) { nodes.push({ type: 'h1', content: line.replace(/^# /, '') }); i++; continue; }

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

    if (/^[-*_]{3,}$/.test(line)) { nodes.push({ type: 'hr' }); i++; continue; }

    if (line.includes('|')) {
      const tableLines: string[] = [line];
      let j = i + 1;
      while (j < lines.length && lines[j].includes('|')) { tableLines.push(lines[j]); j++; }
      if (tableLines.length > 1) {
        const rows = tableLines
          .filter(l => l.trim() && !l.match(/^\|?[\s-|]+\|?$/))
          .map(l => l.split('|').filter(cell => cell.trim()).map(cell => cell.trim()));
        if (rows.length > 0) { nodes.push({ type: 'table', rows }); i = j; continue; }
      }
    }

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

    nodes.push({ type: 'p', content: line });
    i++;
  }

  return nodes;
}

function formatText(text: string): string {
  return text.replace(/\*\*(.+?)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1');
}

function MarkdownRenderer({ content }: { content: string }) {
  const nodes = parseMarkdown(content);

  return (
    <View className="md-content">
      {nodes.map((node, index) => {
        switch (node.type) {
          case 'h1': return <Text key={index} className="md-h1">{formatText(node.content || '')}</Text>;
          case 'h2': return <Text key={index} className="md-h2">{formatText(node.content || '')}</Text>;
          case 'h3': return <Text key={index} className="md-h3">{formatText(node.content || '')}</Text>;
          case 'h4': return <Text key={index} className="md-h4">{formatText(node.content || '')}</Text>;
          case 'h5': return <Text key={index} className="md-h5">{formatText(node.content || '')}</Text>;
          case 'h6': return <Text key={index} className="md-h6">{formatText(node.content || '')}</Text>;
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
          case 'hr': return <View key={index} className="md-hr" />;
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

// 从 markdown 内容中提取纯文本摘要
function extractSummary(content: string, maxLen = 60): string {
  if (!content) return '';
  const lines = content.split('\n').filter(l => l.trim());
  // 跳过标题行，找第一行有意义的内容
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('#')) continue;
    if (/^[-*_]{3,}$/.test(trimmed)) continue;
    if (!trimmed) continue;
    // 去掉 markdown 标记
    const clean = trimmed
      .replace(/^[-*+•]\s+/, '')
      .replace(/^\d+\.\s+/, '')
      .replace(/^>\s+/, '')
      .replace(/\*\*(.+?)\*\*/g, '$1')
      .replace(/\*([^*]+)\*/g, '$1');
    if (clean.length > 0) {
      return clean.length > maxLen ? clean.substring(0, maxLen) + '...' : clean;
    }
  }
  return content.substring(0, maxLen).replace(/[#*_\-]/g, '') + '...';
}

// ========== 页面组件 ==========

export default function AIInsights() {
  const [loading, setLoading] = useState(false);
  const [dailyInsights, setDailyInsights] = useState<any[]>([]);
  const [currentRecommendation, setCurrentRecommendation] = useState<any>(null);
  const [expandedInsightId, setExpandedInsightId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<'insights' | 'realtime'>('insights');

  // 生成今日洞察
  const handleGenerateDailyInsight = async () => {
    setLoading(true);
    try {
      Taro.showLoading({ title: '正在分析健康数据...' });
      await request<any>({
        url: '/ai-insights/insights/daily/generate',
        method: 'POST',
      });

      Taro.hideLoading();
      Taro.showToast({ title: '生成成功', icon: 'success' });
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
      Taro.showLoading({ title: '正在分析环境数据...' });

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
        data: { latitude, longitude },
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
        silent: true,
      });
      if (result) {
        setCurrentRecommendation(result);
      }
    } catch {
      // 静默失败
    }
  };

  // 切换洞察展开/收起
  const toggleInsight = (id: number) => {
    setExpandedInsightId(expandedInsightId === id ? null : id);
  };

  // 页面加载时获取数据
  Taro.useDidShow(() => {
    loadDailyInsights();
    handleGetLatestRecommendation();
  });

  // 获取建议类型的样式信息
  const getRecTypeInfo = (type: string) => {
    switch (type) {
      case 'urgent': return { label: '紧急', emoji: '🔴', cls: 'urgent' };
      case 'important': return { label: '重要', emoji: '🟡', cls: 'important' };
      default: return { label: '常规', emoji: '🟢', cls: 'normal' };
    }
  };

  return (
    <ScrollView className="insights-page" scrollY>
      {/* Tab 切换 */}
      <View className="tab-bar">
        <View
          className={`tab-item ${activeTab === 'insights' ? 'active' : ''}`}
          onClick={() => setActiveTab('insights')}
        >
          <Text className="tab-icon">📊</Text>
          <Text className="tab-label">每日复盘</Text>
        </View>
        <View
          className={`tab-item ${activeTab === 'realtime' ? 'active' : ''}`}
          onClick={() => setActiveTab('realtime')}
        >
          <Text className="tab-icon">⚡</Text>
          <Text className="tab-label">实时建议</Text>
        </View>
      </View>

      {/* ========== 每日洞察 Tab ========== */}
      {activeTab === 'insights' && (
        <View className="tab-content">
          {/* 生成按钮 */}
          <View className="generate-card" onClick={!loading ? handleGenerateDailyInsight : undefined}>
            <View className="generate-icon">
              <Text className="generate-emoji">{loading ? '⏳' : '✨'}</Text>
            </View>
            <View className="generate-info">
              <Text className="generate-title">{loading ? '正在生成...' : '生成今日复盘'}</Text>
              <Text className="generate-desc">基于今日运动、饮食、睡眠等数据</Text>
            </View>
            <View className="generate-arrow">
              <Text className="arrow-text">›</Text>
            </View>
          </View>

          {/* 洞察列表 */}
          {dailyInsights.length === 0 ? (
            <View className="empty-state">
              <Text className="empty-emoji">📋</Text>
              <Text className="empty-text">暂无洞察记录</Text>
              <Text className="empty-hint">点击上方按钮生成今日健康复盘</Text>
            </View>
          ) : (
            <View className="insight-list">
              <Text className="list-header">最近 {dailyInsights.length} 条复盘</Text>
              {dailyInsights.map((insight, idx) => {
                const isExpanded = expandedInsightId === (insight.id || idx);
                return (
                  <View
                    key={insight.id || idx}
                    className={`insight-card ${isExpanded ? 'expanded' : ''}`}
                  >
                    {/* 卡片头部 - 始终显示 */}
                    <View className="insight-card-header" onClick={() => toggleInsight(insight.id || idx)}>
                      <View className="insight-date-badge">
                        <Text className="date-day">
                          {insight.review_date ? insight.review_date.split('-')[2] : ''}
                        </Text>
                        <Text className="date-month">
                          {insight.review_date ? `${parseInt(insight.review_date.split('-')[1])}月` : ''}
                        </Text>
                      </View>
                      <View className="insight-meta">
                        <Text className="insight-title">
                          {insight.review_date} 健康复盘
                        </Text>
                        <Text className="insight-preview">
                          {insight.summary || extractSummary(insight.content || '')}
                        </Text>
                      </View>
                      <View className="insight-toggle">
                        <Text className={`toggle-icon ${isExpanded ? 'open' : ''}`}>
                          {isExpanded ? '收起' : '展开'}
                        </Text>
                      </View>
                    </View>

                    {/* 卡片内容 - 展开时显示 */}
                    {isExpanded && (
                      <View className="insight-card-body">
                        <View className="insight-divider" />
                        <MarkdownRenderer content={insight.content || ''} />
                        <View className="insight-card-footer">
                          <Text className="footer-time">
                            生成于 {new Date(insight.generated_at).toLocaleString('zh-CN', {
                              month: 'numeric',
                              day: 'numeric',
                              hour: '2-digit',
                              minute: '2-digit',
                            })}
                          </Text>
                        </View>
                      </View>
                    )}
                  </View>
                );
              })}
            </View>
          )}
        </View>
      )}

      {/* ========== 实时建议 Tab ========== */}
      {activeTab === 'realtime' && (
        <View className="tab-content">
          {/* 生成按钮 */}
          <View className="generate-card secondary" onClick={!loading ? handleGenerateRealtimeRecommendation : undefined}>
            <View className="generate-icon">
              <Text className="generate-emoji">{loading ? '⏳' : '🌤️'}</Text>
            </View>
            <View className="generate-info">
              <Text className="generate-title">{loading ? '正在分析...' : '生成实时建议'}</Text>
              <Text className="generate-desc">结合天气、空气质量、身体状态</Text>
            </View>
            <View className="generate-arrow">
              <Text className="arrow-text">›</Text>
            </View>
          </View>

          {/* 当前建议展示 */}
          {currentRecommendation ? (
            <View className="rec-card">
              {/* 建议头部 */}
              <View className="rec-card-header">
                <View className={`rec-type-badge ${getRecTypeInfo(currentRecommendation.recommendation_type).cls}`}>
                  <Text className="rec-type-text">
                    {getRecTypeInfo(currentRecommendation.recommendation_type).emoji}{' '}
                    {getRecTypeInfo(currentRecommendation.recommendation_type).label}
                  </Text>
                </View>
                <Text className="rec-time">
                  {new Date(currentRecommendation.generated_at).toLocaleString('zh-CN', {
                    month: 'numeric',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </Text>
              </View>

              {/* 环境信息卡片 */}
              {(currentRecommendation.weather_data || currentRecommendation.air_quality_data) && (
                <View className="env-info-bar">
                  {currentRecommendation.weather_data && (
                    <View className="env-tag">
                      <Text className="env-tag-text">
                        🌡️ {currentRecommendation.weather_data.temperature}°C {currentRecommendation.weather_data.weather_condition}
                      </Text>
                    </View>
                  )}
                  {currentRecommendation.air_quality_data && (
                    <View className={`env-tag ${currentRecommendation.air_quality_data.aqi > 100 ? 'warn' : ''}`}>
                      <Text className="env-tag-text">
                        💨 AQI {currentRecommendation.air_quality_data.aqi}
                      </Text>
                    </View>
                  )}
                  {currentRecommendation.location?.city && (
                    <View className="env-tag">
                      <Text className="env-tag-text">
                        📍 {currentRecommendation.location.city}
                      </Text>
                    </View>
                  )}
                </View>
              )}

              {/* 建议内容 - Markdown 渲染 */}
              <View className="rec-body">
                <MarkdownRenderer content={currentRecommendation.content || ''} />
              </View>

              {/* 有效期 */}
              {currentRecommendation.expires_at && (
                <View className="rec-footer">
                  <Text className="rec-expires">
                    ⏱️ 有效期至 {new Date(currentRecommendation.expires_at).toLocaleString('zh-CN', {
                      month: 'numeric',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </Text>
                </View>
              )}
            </View>
          ) : (
            <View className="empty-state">
              <Text className="empty-emoji">🌤️</Text>
              <Text className="empty-text">暂无实时建议</Text>
              <Text className="empty-hint">点击上方按钮生成个性化健康建议</Text>
            </View>
          )}
        </View>
      )}

      <View style={{ height: '40px' }} />
    </ScrollView>
  );
}
