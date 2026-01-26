/**
 * 资讯详情页
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, RichText } from '@tarojs/components';
import Taro, { useRouter } from '@tarojs/taro';
import { getNewsDetail, NewsArticle } from '../../services/api';
import './index.scss';

/**
 * 简单的 Markdown 转 HTML 解析器
 * 专为小程序 RichText 组件设计，不依赖外部库
 */
function markdownToHtml(markdown: string): string {
  if (!markdown) return '';

  try {
    let html = markdown;

    // 转义 HTML 特殊字符（先处理，避免后续替换出问题）
    // 注意：我们需要保留 markdown 语法，所以只转义内容中的 < > 但保留我们生成的标签

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
    // 先按行分割
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
    // 回退：简单转义并换行
    return `<view class="md-p">${markdown.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br/>')}</view>`;
  }
}

/**
 * 处理 Markdown 表格
 */
function processTable(html: string): string {
  // 简单的表格正则匹配
  const tableRegex = /\|(.+)\|\n\|[-:\| ]+\|\n((?:\|.+\|\n?)+)/g;

  return html.replace(tableRegex, (match, headerRow, bodyRows) => {
    // 解析表头
    const headers = headerRow.split('|').map((h: string) => h.trim()).filter(Boolean);
    const headerHtml = headers.map((h: string) => `<view class="md-th"><text>${h}</text></view>`).join('');

    // 解析表体
    const rows = bodyRows.trim().split('\n');
    const bodyHtml = rows.map((row: string) => {
      const cells = row.split('|').map((c: string) => c.trim()).filter(Boolean);
      const cellsHtml = cells.map((c: string) => `<view class="md-td"><text>${c}</text></view>`).join('');
      return `<view class="md-tr">${cellsHtml}</view>`;
    }).join('');

    return `<view class="md-table"><view class="md-thead"><view class="md-tr">${headerHtml}</view></view><view class="md-tbody">${bodyHtml}</view></view>`;
  });
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
