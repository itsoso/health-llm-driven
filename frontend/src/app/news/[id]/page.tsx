'use client';

import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { newsApi, NewsArticle } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  ArrowLeft,
  Clock,
  Eye,
  Tag,
  User,
  Calendar,
  Pin,
  Share2,
  Bookmark,
  Sparkles
} from 'lucide-react';

// 来源类型映射
const sourceTypeLabels: Record<string, string> = {
  chatlog_analysis: '对话分析',
  custom_prompt: '自定义',
  daily_recap: '每日回顾',
  ai_generated: 'AI生成',
};

const sourceTypeColors: Record<string, string> = {
  chatlog_analysis: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  custom_prompt: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  daily_recap: 'bg-green-500/20 text-green-300 border-green-500/30',
  ai_generated: 'bg-amber-500/20 text-amber-300 border-amber-500/30',
};

function formatDateTime(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

// 简单的文本内容渲染（支持换行和基本格式）
function ContentRenderer({ content }: { content: string }) {
  // 处理换行，将连续两个换行作为段落分隔
  const paragraphs = content.split(/\n\n+/);

  return (
    <div className="prose prose-invert prose-lg max-w-none">
      {paragraphs.map((paragraph, index) => {
        // 检查是否是标题（以#开头）
        if (paragraph.startsWith('### ')) {
          return (
            <h3 key={index} className="text-xl font-semibold text-white mt-6 mb-3">
              {paragraph.replace(/^### /, '')}
            </h3>
          );
        }
        if (paragraph.startsWith('## ')) {
          return (
            <h2 key={index} className="text-2xl font-bold text-white mt-8 mb-4">
              {paragraph.replace(/^## /, '')}
            </h2>
          );
        }
        if (paragraph.startsWith('# ')) {
          return (
            <h1 key={index} className="text-3xl font-bold text-white mt-8 mb-4">
              {paragraph.replace(/^# /, '')}
            </h1>
          );
        }

        // 检查是否是列表
        if (paragraph.match(/^[-*]\s/m)) {
          const items = paragraph.split(/\n/).filter(line => line.trim());
          return (
            <ul key={index} className="list-disc list-inside space-y-2 text-gray-300 my-4">
              {items.map((item, i) => (
                <li key={i}>{item.replace(/^[-*]\s+/, '')}</li>
              ))}
            </ul>
          );
        }

        // 检查是否是数字列表
        if (paragraph.match(/^\d+\.\s/m)) {
          const items = paragraph.split(/\n/).filter(line => line.trim());
          return (
            <ol key={index} className="list-decimal list-inside space-y-2 text-gray-300 my-4">
              {items.map((item, i) => (
                <li key={i}>{item.replace(/^\d+\.\s+/, '')}</li>
              ))}
            </ol>
          );
        }

        // 普通段落
        return (
          <p key={index} className="text-gray-300 leading-relaxed my-4 whitespace-pre-line">
            {paragraph}
          </p>
        );
      })}
    </div>
  );
}

function NewsDetailContent() {
  const params = useParams();
  const router = useRouter();
  const articleId = Number(params.id);

  const { data: article, isLoading, error } = useQuery({
    queryKey: ['news-article', articleId],
    queryFn: async () => {
      const response = await newsApi.getArticle(articleId);
      return response.data;
    },
    enabled: !!articleId,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 pt-4 pb-12">
        <div className="max-w-4xl mx-auto px-4">
          <div className="animate-pulse">
            <div className="w-24 h-8 bg-white/10 rounded mb-8"></div>
            <div className="w-3/4 h-10 bg-white/10 rounded mb-4"></div>
            <div className="flex gap-4 mb-8">
              <div className="w-20 h-6 bg-white/10 rounded"></div>
              <div className="w-32 h-6 bg-white/10 rounded"></div>
            </div>
            <div className="space-y-4">
              {[...Array(8)].map((_, i) => (
                <div key={i} className="w-full h-5 bg-white/10 rounded"></div>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !article) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 pt-4 pb-12">
        <div className="max-w-4xl mx-auto px-4">
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-8 text-center">
            <p className="text-red-400 mb-4">文章不存在或加载失败</p>
            <Link
              href="/news"
              className="inline-flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 text-gray-300 rounded-lg transition-all"
            >
              <ArrowLeft className="w-4 h-4" />
              返回资讯列表
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const tags = article.tags || [];
  const topics = article.topics || [];
  const keyPeople = article.key_people || [];
  const llmModels = article.llm_models || [];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 pt-4 pb-12">
      <div className="max-w-4xl mx-auto px-4">
        {/* 返回按钮 */}
        <Link
          href="/news"
          className="inline-flex items-center gap-2 text-gray-400 hover:text-white transition-colors mb-6"
        >
          <ArrowLeft className="w-4 h-4" />
          返回资讯列表
        </Link>

        {/* 文章头部 */}
        <article className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl overflow-hidden">
          {/* 头部信息 */}
          <div className="p-6 md:p-8 border-b border-white/10">
            {/* 标签和状态 */}
            <div className="flex flex-wrap items-center gap-2 mb-4">
              {article.is_pinned && (
                <span className="flex items-center gap-1 px-2.5 py-1 bg-amber-500/20 text-amber-300 text-xs rounded-full border border-amber-500/30">
                  <Pin className="w-3 h-3" />
                  置顶
                </span>
              )}
              <span className={`px-2.5 py-1 text-xs rounded-full border ${sourceTypeColors[article.source_type] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'}`}>
                {sourceTypeLabels[article.source_type] || article.source_type}
              </span>
              {article.source_group && (
                <span className="px-2.5 py-1 bg-white/5 text-gray-400 text-xs rounded-full border border-white/10">
                  {article.source_group}
                </span>
              )}
            </div>

            {/* 标题 */}
            <h1 className="text-2xl md:text-3xl font-bold text-white mb-4 leading-tight">
              {article.title}
            </h1>

            {/* 元信息 */}
            <div className="flex flex-wrap items-center gap-4 text-sm text-gray-400">
              <span className="flex items-center gap-1.5">
                <Calendar className="w-4 h-4" />
                {formatDateTime(article.created_at)}
              </span>
              <span className="flex items-center gap-1.5">
                <Eye className="w-4 h-4" />
                {article.view_count} 次阅读
              </span>
              {llmModels.length > 0 && (
                <span className="flex items-center gap-1.5">
                  <Sparkles className="w-4 h-4" />
                  {llmModels.join(', ')}
                </span>
              )}
            </div>
          </div>

          {/* 摘要 */}
          {article.summary && (
            <div className="px-6 md:px-8 py-4 bg-purple-500/5 border-b border-white/10">
              <p className="text-gray-300 italic">
                {article.summary}
              </p>
            </div>
          )}

          {/* 正文内容 */}
          <div className="p-6 md:p-8">
            {article.content ? (
              <ContentRenderer content={article.content} />
            ) : (
              <p className="text-gray-400">暂无内容</p>
            )}
          </div>

          {/* 底部标签 */}
          {(tags.length > 0 || topics.length > 0 || keyPeople.length > 0) && (
            <div className="px-6 md:px-8 py-4 border-t border-white/10 bg-white/5">
              <div className="flex flex-wrap gap-4">
                {tags.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <Tag className="w-4 h-4 text-gray-500" />
                    {tags.map((tag, index) => (
                      <span
                        key={index}
                        className="px-2 py-0.5 bg-white/5 text-gray-400 text-xs rounded-md border border-white/10"
                      >
                        #{tag}
                      </span>
                    ))}
                  </div>
                )}
                {topics.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-gray-500 text-xs">话题:</span>
                    {topics.map((topic, index) => (
                      <span
                        key={index}
                        className="px-2 py-0.5 bg-blue-500/10 text-blue-300 text-xs rounded-md border border-blue-500/20"
                      >
                        {topic}
                      </span>
                    ))}
                  </div>
                )}
                {keyPeople.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2">
                    <User className="w-4 h-4 text-gray-500" />
                    {keyPeople.map((person, index) => (
                      <span
                        key={index}
                        className="px-2 py-0.5 bg-green-500/10 text-green-300 text-xs rounded-md border border-green-500/20"
                      >
                        {person}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </article>

        {/* 底部导航 */}
        <div className="mt-6 flex justify-between">
          <Link
            href="/news"
            className="inline-flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 rounded-lg transition-all"
          >
            <ArrowLeft className="w-4 h-4" />
            返回列表
          </Link>
        </div>
      </div>
    </div>
  );
}

export default function NewsDetailPage() {
  return (
    <ProtectedRoute>
      <NewsDetailContent />
    </ProtectedRoute>
  );
}
