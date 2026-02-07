/**
 * 外部健康建议页面 - 展示来自第三方系统的健康建议
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Picker, RichText } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getTodayExternalRecommendations, getExternalRecommendations } from '../../services/api';
import type { ExternalRecommendation, TodayExternalRecommendations } from '../../types';
import './index.scss';

/**
 * 简单的 Markdown 转 HTML 解析器
 * 专为小程序 RichText 组件设计，不依赖外部库
 */
function markdownToHtml(markdown: string): string {
  if (!markdown) return '';

  try {
    let html = markdown;

    // 处理代码块（先处理，避免内部内容被其他规则影响）
    html = html.replace(/```[\s\S]*?```/g, (match) => {
      const code = match.slice(3, -3).replace(/^\w*\n?/, ''); // 移除语言标识
      const escaped = code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      return `<view class="md-codeblock"><text class="md-code-text">${escaped}</text></view>`;
    });

    // 行内代码
    html = html.replace(/`([^`]+)`/g, (_, code) => {
      const escaped = code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      return `<text class="md-code">${escaped}</text>`;
    });

    // 标题 h1-h6
    html = html.replace(/^###### (.+)$/gm, '<view class="md-h6">$1</view>');
    html = html.replace(/^##### (.+)$/gm, '<view class="md-h5">$1</view>');
    html = html.replace(/^#### (.+)$/gm, '<view class="md-h4">$1</view>');
    html = html.replace(/^### (.+)$/gm, '<view class="md-h3">$1</view>');
    html = html.replace(/^## (.+)$/gm, '<view class="md-h2">$1</view>');
    html = html.replace(/^# (.+)$/gm, '<view class="md-h1">$1</view>');

    // 粗体和斜体（先处理粗斜体组合）
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<text class="md-strong"><text class="md-em">$1</text></text>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<text class="md-strong">$1</text>');
    html = html.replace(/\*(.+?)\*/g, '<text class="md-em">$1</text>');
    html = html.replace(/__(.+?)__/g, '<text class="md-strong">$1</text>');
    html = html.replace(/_(.+?)_/g, '<text class="md-em">$1</text>');

    // 删除线
    html = html.replace(/~~(.+?)~~/g, '<text class="md-del">$1</text>');

    // 链接 [text](url)
    html = html.replace(/\[([^\]]+)\]\([^)]+\)/g, '<text class="md-link">$1</text>');

    // 图片 ![alt](url)
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<image class="md-img" src="$2" mode="widthFix"></image>');

    // 分隔线
    html = html.replace(/^[-*_]{3,}$/gm, '<view class="md-hr"></view>');

    // 引用块（处理多行引用）
    html = html.replace(/^> (.+)$/gm, '<view class="md-blockquote"><view class="md-p">$1</view></view>');

    // 无序列表
    html = html.replace(/^[-*+] (.+)$/gm, '<view class="md-li"><text class="md-li-marker">•</text><text class="md-li-text">$1</text></view>');

    // 有序列表
    html = html.replace(/^\d+\. (.+)$/gm, (_, text) => {
      return `<view class="md-li"><text class="md-li-marker">•</text><text class="md-li-text">${text}</text></view>`;
    });

    // 处理表格
    html = processTable(html);

    // 处理段落：将连续的非标签文本包装成段落
    const lines = html.split('\n');
    const processedLines: string[] = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      // 跳过空行
      if (!line) {
        processedLines.push('');
        continue;
      }

      // 如果已经是标签包裹的内容，保持不变
      if (line.startsWith('<view') || line.startsWith('<text') || line.startsWith('<image')) {
        processedLines.push(line);
        continue;
      }

      // 普通文本包装成段落
      processedLines.push(`<view class="md-p">${line}</view>`);
    }

    html = processedLines.join('');

    // 清理多余的空白
    html = html.replace(/\n+/g, '');

    return html;
  } catch (error) {
    console.error('[Markdown解析错误]', error);
    return `<view class="md-p">${markdown.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br/>')}</view>`;
  }
}

/**
 * 处理 Markdown 表格
 */
function processTable(html: string): string {
  const tableRegex = /\|(.+)\|\n\|[-:\| ]+\|\n((?:\|.+\|\n?)+)/g;

  return html.replace(tableRegex, (match, headerRow, bodyRows) => {
    const headers = headerRow.split('|').map((h: string) => h.trim()).filter(Boolean);
    const headerHtml = headers.map((h: string) => `<view class="md-th"><text>${h}</text></view>`).join('');

    const rows = bodyRows.trim().split('\n');
    const bodyHtml = rows.map((row: string) => {
      const cells = row.split('|').map((c: string) => c.trim()).filter(Boolean);
      const cellsHtml = cells.map((c: string) => `<view class="md-td"><text>${c}</text></view>`).join('');
      return `<view class="md-tr">${cellsHtml}</view>`;
    }).join('');

    return `<view class="md-table"><view class="md-thead"><view class="md-tr">${headerHtml}</view></view><view class="md-tbody">${bodyHtml}</view></view>`;
  });
}

// 类别配置
const CATEGORY_CONFIG: Record<string, { icon: string; label: string }> = {
  exercise: { icon: '\u{1F3C3}', label: '运动建议' },
  diet: { icon: '\u{1F957}', label: '饮食建议' },
  sleep: { icon: '\u{1F634}', label: '睡眠建议' },
  supplement: { icon: '\u{1F48A}', label: '补剂建议' },
  general: { icon: '\u{2728}', label: '综合建议' },
};

// 类别顺序
const CATEGORY_ORDER = ['exercise', 'diet', 'sleep', 'supplement', 'general'];

export default function ExternalAdvicePage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
  const [todayData, setTodayData] = useState<TodayExternalRecommendations | null>(null);
  const [historyData, setHistoryData] = useState<ExternalRecommendation[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'today' | 'history'>('today');
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set()); // 已展开的建议ID

  // 切换展开/收起状态
  const toggleExpand = (id: number) => {
    setExpandedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  };

  useEffect(() => {
    // 检查登录状态
    const token = Taro.getStorageSync('access_token');
    if (!token) {
      Taro.switchTab({ url: '/pages/index/index' });
      return;
    }
    loadData();
  }, [viewMode, selectedDate, selectedCategory]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      if (viewMode === 'today') {
        const data = await getTodayExternalRecommendations();
        setTodayData(data);
      } else {
        const data = await getExternalRecommendations(
          selectedDate,
          selectedCategory || undefined,
          50
        );
        setHistoryData(data);
      }
    } catch (e: any) {
      console.error('加载外部建议失败:', e);
      setError(e?.message || '加载失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = () => {
    loadData();
  };

  const handleDateChange = (e: any) => {
    setSelectedDate(e.detail.value);
  };

  const handleCategoryFilter = (category: string | null) => {
    setSelectedCategory(category);
  };

  const formatTime = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
    } catch {
      return '';
    }
  };

  // 清理标题中的 Markdown 标记
  const cleanTitle = (title: string) => {
    if (!title) return '';
    return title
      .replace(/^#{1,6}\s*/, '')  // 移除开头的标题标记
      .replace(/\*\*([^*]+)\*\*/g, '$1')  // 移除粗体
      .replace(/\*([^*]+)\*/g, '$1')  // 移除斜体
      .trim();
  };

  // 截取内容摘要（前100个字符）
  const getContentPreview = (content: string) => {
    if (!content) return '';
    // 移除 Markdown 标记，获取纯文本摘要
    const plainText = content
      .replace(/#{1,6}\s/g, '')  // 移除标题标记
      .replace(/\*\*([^*]+)\*\*/g, '$1')  // 移除粗体
      .replace(/\*([^*]+)\*/g, '$1')  // 移除斜体
      .replace(/`([^`]+)`/g, '$1')  // 移除代码
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // 移除链接
      .replace(/\n+/g, ' ')  // 换行转空格
      .trim();
    return plainText.length > 100 ? plainText.slice(0, 100) + '...' : plainText;
  };

  // 渲染类别区块
  const renderCategorySection = (category: string, recommendations: ExternalRecommendation[]) => {
    const config = CATEGORY_CONFIG[category] || { icon: '\u{1F4CB}', label: category };

    return (
      <View key={category} className={`category-section category-${category}`}>
        <View className="category-header">
          <Text className="category-icon">{config.icon}</Text>
          <Text className="category-title">{config.label}</Text>
          <Text className="category-count">({recommendations.length})</Text>
        </View>

        {recommendations.map((rec) => {
          const isExpanded = expandedIds.has(rec.id);

          return (
            <View key={rec.id} className={`advice-card ${isExpanded ? 'expanded' : ''}`} onClick={() => toggleExpand(rec.id)}>
              <View className="advice-header">
                <Text className="advice-title">{cleanTitle(rec.title)}</Text>
              </View>
              <View className="advice-meta">
                <View className="advice-source">
                  <Text className="source-name">{rec.source_name}</Text>
                </View>
                <Text className="advice-time">{formatTime(rec.created_at)}</Text>
              </View>

              {/* 收起状态：显示摘要 */}
              {!isExpanded && (
                <View className="advice-preview">
                  <Text className="preview-text">{getContentPreview(rec.content)}</Text>
                </View>
              )}

              {/* 展开状态：显示完整内容 */}
              {isExpanded && (
                <View className="advice-content">
                  <RichText nodes={markdownToHtml(rec.content)} />
                </View>
              )}

              {/* 展开/收起提示 */}
              <View className="advice-action">
                <Text className="action-text">{isExpanded ? '点击收起 ▲' : '点击展开 ▼'}</Text>
              </View>
            </View>
          );
        })}
      </View>
    );
  };

  // 加载中
  if (loading) {
    return (
      <View className="external-advice-page loading">
        <View className="loading-spinner" />
        <Text className="loading-text">加载中...</Text>
      </View>
    );
  }

  // 错误状态
  if (error) {
    return (
      <View className="external-advice-page error-state">
        <Text className="error-icon">{'\u{1F614}'}</Text>
        <Text className="error-text">{error}</Text>
        <View className="retry-btn" onClick={handleRefresh}>
          <Text className="retry-text">点击重试</Text>
        </View>
      </View>
    );
  }

  // 空状态
  const isEmpty = viewMode === 'today'
    ? !todayData?.has_recommendations
    : historyData.length === 0;

  if (isEmpty) {
    return (
      <ScrollView className="external-advice-page" scrollY>
        <View className="header">
          <View className="header-top">
            <Text className="title">{'\u{1F4E1}'} 外部建议</Text>
          </View>
          <Text className="subtitle">来自 AI 助手和外部健康服务的个性化建议</Text>

          {/* 视图切换 */}
          <View className="category-filter">
            <View
              className={`filter-tag ${viewMode === 'today' ? 'active' : ''}`}
              onClick={() => setViewMode('today')}
            >
              <Text>今日</Text>
            </View>
            <View
              className={`filter-tag ${viewMode === 'history' ? 'active' : ''}`}
              onClick={() => setViewMode('history')}
            >
              <Text>历史</Text>
            </View>
          </View>

          {viewMode === 'history' && (
            <View className="date-row">
              <Picker mode="date" value={selectedDate} onChange={handleDateChange}>
                <View className="date-picker">
                  <Text className="date-text">{selectedDate}</Text>
                  <Text className="date-arrow">{'\u{25BC}'}</Text>
                </View>
              </Picker>
            </View>
          )}
        </View>

        <View className="empty-state" style={{ marginTop: '100px' }}>
          <Text className="empty-icon">{'\u{1F4ED}'}</Text>
          <Text className="empty-title">暂无外部建议</Text>
          <Text className="empty-text">
            外部 AI 健康助手（如 Browser-LLM-Driven、GPT Health 等）分析您的健康数据后，会在这里展示个性化建议。
          </Text>
        </View>
      </ScrollView>
    );
  }

  return (
    <ScrollView className="external-advice-page" scrollY>
      {/* 头部 */}
      <View className="header">
        <View className="header-top">
          <Text className="title">{'\u{1F4E1}'} 外部建议</Text>
          <View className="refresh-btn" onClick={handleRefresh}>
            <Text>{'\u{21BB}'} 刷新</Text>
          </View>
        </View>
        <Text className="subtitle">来自 AI 助手和外部健康服务的个性化建议</Text>

        {/* 视图切换 */}
        <View className="category-filter">
          <View
            className={`filter-tag ${viewMode === 'today' ? 'active' : ''}`}
            onClick={() => setViewMode('today')}
          >
            <Text>今日</Text>
          </View>
          <View
            className={`filter-tag ${viewMode === 'history' ? 'active' : ''}`}
            onClick={() => setViewMode('history')}
          >
            <Text>历史</Text>
          </View>
        </View>

        {viewMode === 'history' && (
          <>
            <View className="date-row">
              <Picker mode="date" value={selectedDate} onChange={handleDateChange}>
                <View className="date-picker">
                  <Text className="date-text">{selectedDate}</Text>
                  <Text className="date-arrow">{'\u{25BC}'}</Text>
                </View>
              </Picker>
            </View>

            {/* 类别筛选 */}
            <View className="category-filter">
              <View
                className={`filter-tag ${selectedCategory === null ? 'active' : ''}`}
                onClick={() => handleCategoryFilter(null)}
              >
                <Text>全部</Text>
              </View>
              {CATEGORY_ORDER.map((cat) => (
                <View
                  key={cat}
                  className={`filter-tag ${selectedCategory === cat ? 'active' : ''}`}
                  onClick={() => handleCategoryFilter(cat)}
                >
                  <Text>{CATEGORY_CONFIG[cat].icon} {CATEGORY_CONFIG[cat].label}</Text>
                </View>
              ))}
            </View>
          </>
        )}
      </View>

      {/* 今日视图 - 按类别分组展示 */}
      {viewMode === 'today' && todayData && (
        <>
          {CATEGORY_ORDER.map((category) => {
            const recs = todayData.categories[category];
            if (!recs || recs.length === 0) return null;
            return renderCategorySection(category, recs);
          })}
        </>
      )}

      {/* 历史视图 - 列表展示 */}
      {viewMode === 'history' && historyData.length > 0 && (
        <>
          {/* 按类别分组 */}
          {(() => {
            const grouped: Record<string, ExternalRecommendation[]> = {};
            historyData.forEach((rec) => {
              if (!grouped[rec.category]) {
                grouped[rec.category] = [];
              }
              grouped[rec.category].push(rec);
            });

            return CATEGORY_ORDER.map((category) => {
              const recs = grouped[category];
              if (!recs || recs.length === 0) return null;
              return renderCategorySection(category, recs);
            });
          })()}
        </>
      )}

      <View style={{ height: '100px' }} />
    </ScrollView>
  );
}
