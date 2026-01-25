/**
 * 资讯详情页
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, RichText } from '@tarojs/components';
import Taro, { useRouter } from '@tarojs/taro';
import { getNewsDetail, NewsArticle } from '../../services/api';
import './index.scss';

// 简单的 Markdown 转换（仅支持基础语法）
function markdownToHtml(markdown: string): string {
  if (!markdown) return '';

  let html = markdown
    // 转义 HTML 特殊字符
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // 标题 (h1-h4)
    .replace(/^#### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // 粗体和斜体
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // 代码块
    .replace(/```[\s\S]*?```/g, (match) => {
      const code = match.replace(/```\w*\n?/g, '').trim();
      return `<pre><code>${code}</code></pre>`;
    })
    // 行内代码
    .replace(/`(.+?)`/g, '<code>$1</code>')
    // 引用
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    // 无序列表
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
    // 有序列表
    .replace(/^\d+\. (.+)$/gm, '<oli>$1</oli>')
    .replace(/(<oli>.*<\/oli>\n?)+/g, (match) => {
      return '<ol>' + match.replace(/<\/?oli>/g, (tag) => tag.replace('oli', 'li')) + '</ol>';
    })
    // 水平分割线
    .replace(/^---$/gm, '<hr/>')
    // 链接
    .replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2">$1</a>')
    // 段落
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br/>');

  return `<p>${html}</p>`;
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
