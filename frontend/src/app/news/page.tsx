'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { newsApi, NewsArticle } from '@/services/api/content';
import { useAuth } from '@/contexts/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  Newspaper,
  Clock,
  Eye,
  ChevronRight,
  RefreshCw,
  Filter,
  Pin,
  Trash2,
  Globe,
  Lock,
  User,
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

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));

  if (days === 0) {
    const hours = Math.floor(diff / (1000 * 60 * 60));
    if (hours === 0) {
      const minutes = Math.floor(diff / (1000 * 60));
      return minutes <= 1 ? '刚刚' : `${minutes}分钟前`;
    }
    return `${hours}小时前`;
  } else if (days === 1) {
    return '昨天';
  } else if (days < 7) {
    return `${days}天前`;
  } else {
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  }
}

interface NewsCardProps {
  article: NewsArticle;
  isAdmin?: boolean;
  currentUserId?: number;
  onDelete?: (id: number) => void;
  onToggleVisibility?: (id: number, currentVisibility: string) => void;
}

function NewsCard({ article, isAdmin, currentUserId, onDelete, onToggleVisibility }: NewsCardProps) {
  const tags = article.tags || [];
  const isOwner = !!currentUserId && article.user_id === currentUserId;
  const canDelete = isAdmin || isOwner;

  const handleDelete = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (onDelete && confirm(`确定要删除文章「${article.title}」吗？`)) {
      onDelete(article.id);
    }
  };

  const handleToggleVisibility = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (onToggleVisibility) {
      const newVisibility = article.visibility === 'public' ? 'private' : 'public';
      onToggleVisibility(article.id, newVisibility);
    }
  };

  return (
    <Link href={`/news/${article.id}`}>
      <div className="group bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl p-5 hover:bg-white/10 hover:border-purple-500/30 transition-all duration-300 cursor-pointer relative">
        {/* 操作按钮组 */}
        <div className="absolute top-3 right-3 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-all z-10">
          {isOwner && onToggleVisibility && (
            <button
              onClick={handleToggleVisibility}
              className={`p-1.5 rounded-lg text-xs flex items-center gap-1 transition-all ${
                article.visibility === 'public'
                  ? 'bg-green-500/20 hover:bg-green-500/40 text-green-400'
                  : 'bg-gray-500/20 hover:bg-gray-500/40 text-gray-400'
              }`}
              title={article.visibility === 'public' ? '点击设为私密' : '点击设为公开'}
            >
              {article.visibility === 'public'
                ? <Globe className="w-3.5 h-3.5" />
                : <Lock className="w-3.5 h-3.5" />
              }
            </button>
          )}
          {canDelete && (
            <button
              onClick={handleDelete}
              className="p-1.5 bg-red-500/20 hover:bg-red-500/40 rounded-lg text-red-400 transition-all"
              title="删除文章"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* 头部：来源类型和时间 */}
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 flex-wrap">
            {article.is_pinned && (
              <span className="flex items-center gap-1 px-2 py-0.5 bg-amber-500/20 text-amber-300 text-xs rounded-full border border-amber-500/30">
                <Pin className="w-3 h-3" />
                置顶
              </span>
            )}
            <span className={`px-2 py-0.5 text-xs rounded-full border ${sourceTypeColors[article.source_type] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'}`}>
              {sourceTypeLabels[article.source_type] || article.source_type}
            </span>
            {/* 可见性标记（仅本人可见） */}
            {isOwner && article.visibility === 'private' && (
              <span className="flex items-center gap-1 px-2 py-0.5 bg-gray-500/20 text-gray-400 text-xs rounded-full border border-gray-500/30">
                <Lock className="w-3 h-3" />
                私密
              </span>
            )}
            {article.source_group && (
              <span className="text-xs text-gray-500">
                {article.source_group}
              </span>
            )}
          </div>
          <div className={`flex items-center gap-3 text-xs text-gray-500 ${canDelete ? 'mr-14' : ''}`}>
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatDate(article.created_at)}
            </span>
            <span className="flex items-center gap-1">
              <Eye className="w-3 h-3" />
              {article.view_count}
            </span>
          </div>
        </div>

        {/* 标题 */}
        <h3 className="text-lg font-semibold text-white group-hover:text-purple-300 transition-colors mb-2 line-clamp-2">
          {article.title}
        </h3>

        {/* 摘要 */}
        {article.summary && (
          <p className="text-sm text-gray-400 line-clamp-2 mb-3">
            {article.summary}
          </p>
        )}

        {/* 作者信息（社区文章） */}
        {article.author_name && !isOwner && (
          <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-2">
            <User className="w-3 h-3" />
            <span>{article.author_name}</span>
          </div>
        )}

        {/* 底部：标签 */}
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-3">
            {tags.slice(0, 4).map((tag, index) => (
              <span
                key={index}
                className="px-2 py-0.5 bg-white/5 text-gray-400 text-xs rounded-md border border-white/10"
              >
                #{tag}
              </span>
            ))}
            {tags.length > 4 && (
              <span className="px-2 py-0.5 text-gray-500 text-xs">
                +{tags.length - 4}
              </span>
            )}
          </div>
        )}

        {/* 阅读更多提示 */}
        <div className="flex items-center justify-end mt-3 text-xs text-purple-400 opacity-0 group-hover:opacity-100 transition-opacity">
          阅读全文 <ChevronRight className="w-3 h-3 ml-1" />
        </div>
      </div>
    </Link>
  );
}

function NewsPageContent() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [sourceType, setSourceType] = useState<string>('');
  const [feed, setFeed] = useState<string>('all');
  const pageSize = 12;

  const isAdmin = user?.is_admin ?? false;

  const { data: articles, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['news-articles', page, sourceType, feed],
    queryFn: async () => {
      const response = await newsApi.getArticles(page, pageSize, sourceType || undefined, feed !== 'all' ? feed : undefined);
      return response.data;
    },
  });

  const handleDelete = async (articleId: number) => {
    try {
      await newsApi.deleteArticle(articleId);
      refetch();
    } catch (err) {
      alert('删除失败');
    }
  };

  const handleToggleVisibility = async (articleId: number, newVisibility: string) => {
    try {
      await newsApi.updateVisibility(articleId, newVisibility);
      refetch();
    } catch (err) {
      alert('更新失败');
    }
  };

  const sourceTypes = [
    { value: '', label: '全部类型' },
    { value: 'chatlog_analysis', label: '对话分析' },
    { value: 'daily_recap', label: '每日回顾' },
    { value: 'custom_prompt', label: '自定义' },
    { value: 'ai_generated', label: 'AI生成' },
  ];

  const feedTabs = [
    { value: 'all', label: '全部', icon: <Newspaper className="w-4 h-4" /> },
    { value: 'mine', label: '我的', icon: <User className="w-4 h-4" /> },
    { value: 'community', label: '社区', icon: <Globe className="w-4 h-4" /> },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 pt-4 pb-12">
      <div className="max-w-6xl mx-auto px-4">
        {/* 页面头部 */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-purple-500/20 rounded-lg">
                <Newspaper className="w-6 h-6 text-purple-400" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">健康资讯</h1>
                <p className="text-sm text-gray-400">AI精选健康知识与洞察</p>
              </div>
            </div>
            <button
              onClick={() => refetch()}
              disabled={isFetching}
              className="flex items-center gap-2 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-300 text-sm transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
              刷新
            </button>
          </div>

          {/* Feed 标签 */}
          <div className="flex items-center gap-1 mb-4 bg-white/5 rounded-xl p-1 w-fit">
            {feedTabs.map((tab) => (
              <button
                key={tab.value}
                onClick={() => {
                  setFeed(tab.value);
                  setPage(1);
                }}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  feed === tab.value
                    ? 'bg-purple-600 text-white shadow-lg'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {tab.icon}
                {tab.label}
              </button>
            ))}
          </div>

          {/* 来源类型筛选器 */}
          <div className="flex items-center gap-2 flex-wrap">
            <Filter className="w-4 h-4 text-gray-500" />
            {sourceTypes.map((type) => (
              <button
                key={type.value}
                onClick={() => {
                  setSourceType(type.value);
                  setPage(1);
                }}
                className={`px-3 py-1.5 rounded-lg text-sm transition-all ${
                  sourceType === type.value
                    ? 'bg-purple-600 text-white'
                    : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white'
                }`}
              >
                {type.label}
              </button>
            ))}
          </div>
        </div>

        {/* 内容区域 */}
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="bg-white/5 rounded-xl p-5 animate-pulse">
                <div className="flex items-center gap-2 mb-3">
                  <div className="w-16 h-5 bg-white/10 rounded-full"></div>
                  <div className="w-20 h-4 bg-white/10 rounded"></div>
                </div>
                <div className="w-full h-6 bg-white/10 rounded mb-2"></div>
                <div className="w-3/4 h-6 bg-white/10 rounded mb-3"></div>
                <div className="w-full h-4 bg-white/10 rounded mb-1"></div>
                <div className="w-2/3 h-4 bg-white/10 rounded"></div>
              </div>
            ))}
          </div>
        ) : error ? (
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-8 text-center">
            <p className="text-red-400 mb-4">加载资讯失败</p>
            <button
              onClick={() => refetch()}
              className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-300 rounded-lg transition-all"
            >
              重试
            </button>
          </div>
        ) : articles && articles.length > 0 ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {articles.map((article) => (
                <NewsCard
                  key={article.id}
                  article={article}
                  isAdmin={isAdmin}
                  currentUserId={user?.id}
                  onDelete={handleDelete}
                  onToggleVisibility={handleToggleVisibility}
                />
              ))}
            </div>

            {/* 分页 */}
            <div className="flex items-center justify-center gap-2 mt-8">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-300 text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                上一页
              </button>
              <span className="px-4 py-2 text-gray-400 text-sm">
                第 {page} 页
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={articles.length < pageSize}
                className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg text-gray-300 text-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                下一页
              </button>
            </div>
          </>
        ) : (
          <div className="bg-white/5 border border-white/10 rounded-xl p-12 text-center">
            <Newspaper className="w-12 h-12 text-gray-600 mx-auto mb-4" />
            <p className="text-gray-400 mb-2">
              {feed === 'mine' ? '还没有发布任何资讯' : '暂无资讯'}
            </p>
            <p className="text-gray-500 text-sm">
              {feed === 'mine'
                ? '在小程序的 AI 分析页面点击「发布到资讯」即可推送'
                : '资讯内容将在这里显示'}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function NewsPage() {
  return (
    <ProtectedRoute>
      <NewsPageContent />
    </ProtectedRoute>
  );
}
