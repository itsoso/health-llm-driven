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
 * 专为小程序 RichText 组件设计，使用标准 HTML 标签
 * 注意：RichText 组件需要 HTML 标签（div/span），而非 WXML 标签（view/text）
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
      return `<div class="md-codeblock"><span class="md-code-text">${escaped}</span></div>`;
    });

    // 行内代码
    html = html.replace(/`([^`]+)`/g, (_, code) => {
      const escaped = code
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      return `<span class="md-code">${escaped}</span>`;
    });

    // 标题 h1-h6
    html = html.replace(/^###### (.+)$/gm, '<h6 class="md-h6">$1</h6>');
    html = html.replace(/^##### (.+)$/gm, '<h5 class="md-h5">$1</h5>');
    html = html.replace(/^#### (.+)$/gm, '<h4 class="md-h4">$1</h4>');
    html = html.replace(/^### (.+)$/gm, '<h3 class="md-h3">$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2 class="md-h2">$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1 class="md-h1">$1</h1>');

    // 粗体和斜体（先处理粗斜体组合）
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong class="md-strong"><em class="md-em">$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong class="md-strong">$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em class="md-em">$1</em>');
    html = html.replace(/__(.+?)__/g, '<strong class="md-strong">$1</strong>');
    html = html.replace(/_(.+?)_/g, '<em class="md-em">$1</em>');

    // 删除线
    html = html.replace(/~~(.+?)~~/g, '<del class="md-del">$1</del>');

    // 链接 [text](url)
    html = html.replace(/\[([^\]]+)\]\([^)]+\)/g, '<span class="md-link">$1</span>');

    // 图片 ![alt](url)
    html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img class="md-img" src="$2" />');

    // 分隔线
    html = html.replace(/^[-*_]{3,}$/gm, '<hr class="md-hr" />');

    // 引用块（处理多行引用）
    html = html.replace(/^> (.+)$/gm, '<blockquote class="md-blockquote"><p class="md-p">$1</p></blockquote>');

    // 无序列表
    html = html.replace(/^[-*+] (.+)$/gm, '<div class="md-li"><span class="md-li-marker">•</span><span class="md-li-text">$1</span></div>');

    // 有序列表
    html = html.replace(/^\d+\. (.+)$/gm, (_, text) => {
      return `<div class="md-li"><span class="md-li-marker">•</span><span class="md-li-text">${text}</span></div>`;
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
      if (line.startsWith('<')) {
        processedLines.push(line);
        continue;
      }

      // 普通文本包装成段落
      processedLines.push(`<p class="md-p">${line}</p>`);
    }

    html = processedLines.join('');

    // 清理多余的空白
    html = html.replace(/\n+/g, '');

    return html;
  } catch (error) {
    console.error('[Markdown解析错误]', error);
    // 回退：简单转义并换行
    return `<p class="md-p">${markdown.replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br/>')}</p>`;
  }
}

/**
 * 处理 Markdown 表格
 */
function processTable(html: string): string {
  // 简单的表格正则匹配
  const tableRegex = /\|(.+)\|\n\|[-:\| ]+\|\n((?:\|.+\|\n?)+)/g;

  return html.replace(tableRegex, (match, headerRow, bodyRows) => {
    // 解析表头 - 用 span 包裹确保样式生效
    const headers = headerRow.split('|').map((h: string) => h.trim()).filter(Boolean);
    const headerHtml = headers.map((h: string) => `<th class="md-th"><span class="md-th-text">${h}</span></th>`).join('');

    // 解析表体 - 用 span 包裹确保样式生效
    const rows = bodyRows.trim().split('\n');
    const bodyHtml = rows.map((row: string) => {
      const cells = row.split('|').map((c: string) => c.trim()).filter(Boolean);
      const cellsHtml = cells.map((c: string) => `<td class="md-td"><span class="md-td-text">${c}</span></td>`).join('');
      return `<tr class="md-tr">${cellsHtml}</tr>`;
    }).join('');

    return `<table class="md-table"><thead class="md-thead"><tr class="md-tr">${headerHtml}</tr></thead><tbody class="md-tbody">${bodyHtml}</tbody></table>`;
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
