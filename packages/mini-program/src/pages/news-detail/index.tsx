/**
 * 资讯详情页
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, RichText } from '@tarojs/components';
import Taro, { useRouter } from '@tarojs/taro';
import { getNewsDetail, NewsArticle } from '../../services/api';
import './index.scss';

// Markdown 转 HTML（支持表格、粗体、列表等）
function markdownToHtml(markdown: string): string {
  if (!markdown) return '';

  // 按段落分割处理
  const blocks = markdown.split(/\n\n+/);
  const htmlBlocks: string[] = [];

  for (const block of blocks) {
    const trimmedBlock = block.trim();
    if (!trimmedBlock) continue;

    // 检测表格（包含 | 且有分隔行 |---|）
    if (trimmedBlock.includes('|') && trimmedBlock.includes('---')) {
      const tableHtml = parseTable(trimmedBlock);
      if (tableHtml) {
        htmlBlocks.push(tableHtml);
        continue;
      }
    }

    // 按行处理
    const lines = trimmedBlock.split('\n');
    const processedLines: string[] = [];

    for (const line of lines) {
      const trimmedLine = line.trim();
      if (!trimmedLine) continue;

      // 标题
      if (trimmedLine.startsWith('#### ')) {
        processedLines.push(`<h4>${processInline(trimmedLine.slice(5))}</h4>`);
      } else if (trimmedLine.startsWith('### ')) {
        processedLines.push(`<h3>${processInline(trimmedLine.slice(4))}</h3>`);
      } else if (trimmedLine.startsWith('## ')) {
        processedLines.push(`<h2>${processInline(trimmedLine.slice(3))}</h2>`);
      } else if (trimmedLine.startsWith('# ')) {
        processedLines.push(`<h1>${processInline(trimmedLine.slice(2))}</h1>`);
      }
      // 水平分割线
      else if (trimmedLine === '---' || trimmedLine === '***' || trimmedLine === '___') {
        processedLines.push('<hr/>');
      }
      // 引用
      else if (trimmedLine.startsWith('> ')) {
        processedLines.push(`<blockquote>${processInline(trimmedLine.slice(2))}</blockquote>`);
      }
      // 带数字的标题行（如 "1. 核心结论"，"2. 关键论据"）- 短文本视为标题
      else if (/^\d+\.\s+.+$/.test(trimmedLine) && trimmedLine.length < 50) {
        processedLines.push(`<p class="numbered-header"><strong>${processInline(trimmedLine)}</strong></p>`);
      }
      // 无序列表项（支持 -、*、•、·）
      else if (/^[-*•·]\s+/.test(trimmedLine)) {
        const content = trimmedLine.replace(/^[-*•·]\s+/, '');
        processedLines.push(`<p class="list-item">• ${processInline(content)}</p>`);
      }
      // 有序列表项（较长内容）
      else if (/^\d+\.\s+/.test(trimmedLine) && trimmedLine.length >= 50) {
        processedLines.push(`<p class="list-item">${processInline(trimmedLine)}</p>`);
      }
      // 代码块标记跳过
      else if (trimmedLine.startsWith('```')) {
        continue;
      }
      // 普通段落
      else {
        processedLines.push(`<p>${processInline(trimmedLine)}</p>`);
      }
    }

    htmlBlocks.push(processedLines.join(''));
  }

  return htmlBlocks.join('');
}

// 处理行内元素（粗体、斜体、代码、链接）
function processInline(text: string): string {
  if (!text) return '';

  return text
    // 转义 HTML 特殊字符（但保留 &nbsp; 等）
    .replace(/&(?!amp;|lt;|gt;|nbsp;|quot;)/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    // 粗斜体
    .replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>')
    // 粗体（支持跨越多个词）
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    // 斜体
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // 行内代码
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // 链接
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
}

// 解析表格
function parseTable(block: string): string | null {
  const lines = block.split('\n').filter(l => l.trim());
  if (lines.length < 2) return null;

  // 找到分隔行（包含 |---）
  const separatorIndex = lines.findIndex(l => /^\|?\s*[-:]+\s*\|/.test(l) || /\|\s*[-:]+\s*\|/.test(l));
  if (separatorIndex < 1) return null;

  // 表头
  const headerLine = lines[separatorIndex - 1];
  const headers = headerLine.split('|').map(h => h.trim()).filter(h => h);

  // 表格行
  const rows: string[][] = [];
  for (let i = separatorIndex + 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.includes('|')) continue;
    const cells = line.split('|').map(c => c.trim()).filter(c => c);
    if (cells.length > 0) {
      rows.push(cells);
    }
  }

  if (headers.length === 0) return null;

  // 生成 HTML 表格
  let html = '<div class="table-wrapper"><table>';

  // 表头
  html += '<thead><tr>';
  for (const header of headers) {
    html += `<th>${processInline(header)}</th>`;
  }
  html += '</tr></thead>';

  // 表体
  if (rows.length > 0) {
    html += '<tbody>';
    for (const row of rows) {
      html += '<tr>';
      for (let i = 0; i < headers.length; i++) {
        const cell = row[i] || '';
        html += `<td>${processInline(cell)}</td>`;
      }
      html += '</tr>';
    }
    html += '</tbody>';
  }

  html += '</table></div>';
  return html;
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
