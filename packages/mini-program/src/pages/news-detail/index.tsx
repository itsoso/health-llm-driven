/**
 * 资讯详情页
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, RichText } from '@tarojs/components';
import Taro, { useRouter } from '@tarojs/taro';
import { marked } from 'marked';
import { getNewsDetail, NewsArticle } from '../../services/api';
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

  // 链接（小程序不支持a标签跳转，显示为文本）
  renderer.link = ({ href, text }) => {
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
    // 转义 HTML
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

  // 图片（小程序需要特殊处理，这里简单显示占位）
  renderer.image = ({ href, text }) => {
    return `<image class="md-img" src="${href}" mode="widthFix"></image>`;
  };

  return renderer;
}

// Markdown 转 HTML（使用 marked 通用方案）
function markdownToHtml(markdown: string): string {
  if (!markdown) return '';

  try {
    const renderer = setupMarkedRenderer();
    marked.setOptions({
      renderer,
      gfm: true,       // GitHub Flavored Markdown
      breaks: true,    // 将换行符转换为 <br>
    });
    return marked.parse(markdown) as string;
  } catch (error) {
    console.error('[Markdown解析错误]', error);
    // 回退：简单转义并换行
    return `<view class="md-p">${markdown.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br/>')}</view>`;
  }
}

export default function NewsDetailPage() {
  const router = useRouter();
  const articleId = parseInt(router.params.id || '0', 10);

  const [article, setArticle] = useState<NewsArticle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (articleId) {
      loadArticle();
    }
  }, [articleId]);

  const loadArticle = async () => {
    try {
      setLoading(true);
      const data = await getNewsDetail(articleId);
      setArticle(data);
      // 设置页面标题
      Taro.setNavigationBarTitle({ title: data.title.slice(0, 20) });
    } catch (e: any) {
      console.error('[资讯详情] 加载失败:', e);
      if (e?.statusCode === 403) {
        setError('需要 VIP 或管理员权限访问');
      } else if (e?.statusCode === 404) {
        setError('文章不存在');
      } else {
        setError('加载失败，请重试');
      }
    } finally {
      setLoading(false);
    }
  };

  const getSourceTypeLabel = (sourceType: string) => {
    const labels: Record<string, string> = {
      'chatlog_analysis': '群聊总结',
      'custom_prompt': '研究分析',
      'daily_recap': '每日复盘',
    };
    return labels[sourceType] || sourceType;
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
  };

  if (loading) {
    return (
      <View className="detail-page">
        <View className="loading-state">
          <Text className="loading-text">加载中...</Text>
        </View>
      </View>
    );
  }

  if (error || !article) {
    return (
      <View className="detail-page">
        <View className="error-state">
          <Text className="error-icon">!</Text>
          <Text className="error-text">{error || '文章不存在'}</Text>
          <View className="back-btn" onClick={() => Taro.navigateBack()}>
            <Text>返回</Text>
          </View>
        </View>
      </View>
    );
  }

  return (
    <View className="detail-page">
      <ScrollView className="detail-scroll" scrollY>
        {/* 文章头部 */}
        <View className="article-header">
          <View className="header-meta">
            <View className="source-tag">
              <Text>{getSourceTypeLabel(article.source_type)}</Text>
            </View>
            {article.source_group && (
              <Text className="source-group">{article.source_group}</Text>
            )}
          </View>
          <Text className="article-title">{article.title}</Text>
          <View className="article-info">
            <Text className="info-time">{formatDate(article.created_at)}</Text>
            <Text className="info-views">{article.view_count} 阅读</Text>
          </View>
        </View>

        {/* 标签 */}
        {article.tags && article.tags.length > 0 && (
          <View className="tags-section">
            {article.tags.map((tag, idx) => (
              <View key={idx} className="tag">
                <Text>#{tag}</Text>
              </View>
            ))}
          </View>
        )}

        {/* 文章内容 */}
        <View className="article-content">
          <RichText nodes={markdownToHtml(article.content || '')} />
        </View>

        {/* LLM 信息 */}
        {(article.llm_models || article.aggregator_model) && (
          <View className="llm-info">
            <Text className="llm-title">分析模型</Text>
            <View className="llm-models">
              {article.llm_models?.map((model, idx) => (
                <View key={idx} className="llm-tag">
                  <Text>{model}</Text>
                </View>
              ))}
              {article.aggregator_model && (
                <View className="llm-tag aggregator">
                  <Text>聚合: {article.aggregator_model}</Text>
                </View>
              )}
            </View>
          </View>
        )}

        {/* 底部间距 */}
        <View className="bottom-spacer" />
      </ScrollView>
    </View>
  );
}
