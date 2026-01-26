/**
 * 外部健康建议页面 - 展示来自第三方系统的健康建议
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Picker, RichText } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { marked } from 'marked';
import { getTodayExternalRecommendations, getExternalRecommendations } from '../../services/api';
import type { ExternalRecommendation, TodayExternalRecommendations } from '../../types';
import './index.scss';

// 配置 marked 渲染器以适配小程序 RichText
function setupMarkedRenderer() {
  const renderer = new marked.Renderer();

  // 标题 h1-h6
  renderer.heading = ({ text, depth }) => {
    const className = `md-h${depth}`;
    return `<view class="${className}">${text}</view>`;
  };

  // 段落
  renderer.paragraph = ({ text }) => {
    return `<view class="md-p">${text}</view>`;
  };

  // 粗体
  renderer.strong = ({ text }) => {
    return `<text class="md-strong">${text}</text>`;
  };

  // 斜体
  renderer.em = ({ text }) => {
    return `<text class="md-em">${text}</text>`;
  };

  // 链接
  renderer.link = ({ text }) => {
    return `<text class="md-link">${text}</text>`;
  };

  // 列表
  renderer.list = ({ body, ordered }) => {
    const className = ordered ? 'md-ol' : 'md-ul';
    return `<view class="${className}">${body}</view>`;
  };

  // 列表项
  renderer.listitem = ({ text }) => {
    return `<view class="md-li"><text class="md-li-marker">•</text><text class="md-li-text">${text}</text></view>`;
  };

  // 代码块
  renderer.code = ({ text }) => {
    const escaped = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    return `<view class="md-codeblock"><text class="md-code-text">${escaped}</text></view>`;
  };

  // 行内代码
  renderer.codespan = ({ text }) => {
    return `<text class="md-code">${text}</text>`;
  };

  // 引用块
  renderer.blockquote = ({ text }) => {
    return `<view class="md-blockquote">${text}</view>`;
  };

  // 分隔线
  renderer.hr = () => {
    return `<view class="md-hr"></view>`;
  };

  // 表格
  renderer.table = ({ header, body }) => {
    return `<view class="md-table"><view class="md-thead">${header}</view><view class="md-tbody">${body}</view></view>`;
  };

  renderer.tablerow = ({ text }) => {
    return `<view class="md-tr">${text}</view>`;
  };

  renderer.tablecell = ({ text, header }) => {
    const className = header ? 'md-th' : 'md-td';
    return `<view class="${className}"><text>${text}</text></view>`;
  };

  // 换行
  renderer.br = () => {
    return `<view class="md-br"></view>`;
  };

  // 图片
  renderer.image = ({ href }) => {
    return `<image class="md-img" src="${href}" mode="widthFix"></image>`;
  };

  return renderer;
}

// Markdown 转 HTML
function markdownToHtml(markdown: string): string {
  if (!markdown) return '';

  try {
    const renderer = setupMarkedRenderer();
    marked.setOptions({
      renderer,
      gfm: true,
      breaks: true,
    });
    return marked.parse(markdown) as string;
  } catch (error) {
    console.error('[Markdown解析错误]', error);
    return `<view class="md-p">${markdown.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br/>')}</view>`;
  }
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

        {recommendations.map((rec) => (
          <View key={rec.id} className="advice-card">
            <View className="advice-header">
              <Text className="advice-title">{rec.title}</Text>
              <View className="advice-source">
                <Text className="source-icon">{'\u{1F517}'}</Text>
                <Text className="source-name">{rec.source_name}</Text>
              </View>
            </View>
            <View className="advice-content">
              <RichText nodes={markdownToHtml(rec.content)} />
            </View>
            <View className="advice-footer">
              <Text className="advice-time">{formatTime(rec.created_at)}</Text>
            </View>
          </View>
        ))}
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
