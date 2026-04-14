'use client';

import { useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { newsApi, NewsArticle, NewsComment } from '@/services/api/content';
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
  Sparkles,
  MessageCircle,
  Reply,
  Trash2,
  Send,
  Camera,
  Download,
  X,
  Copy,
  Check,
  Globe,
  Lock,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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

// Markdown内容渲染组件 - 使用 react-markdown 通用方案
function ContentRenderer({ content }: { content: string }) {
  return (
    <div className="prose prose-invert prose-lg max-w-none">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // 标题
          h1: ({ children }) => (
            <h1 className="text-3xl font-bold text-white mt-8 mb-4">{children}</h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-2xl font-bold text-white mt-8 mb-4">{children}</h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-xl font-semibold text-white mt-6 mb-3">{children}</h3>
          ),
          h4: ({ children }) => (
            <h4 className="text-lg font-semibold text-white mt-5 mb-2">{children}</h4>
          ),
          h5: ({ children }) => (
            <h5 className="text-base font-semibold text-purple-200 mt-4 mb-2">{children}</h5>
          ),
          h6: ({ children }) => (
            <h6 className="text-sm font-semibold text-purple-300 mt-4 mb-1">{children}</h6>
          ),
          // 段落
          p: ({ children }) => (
            <p className="text-gray-300 leading-relaxed my-4">{children}</p>
          ),
          // 强调
          strong: ({ children }) => (
            <strong className="text-white font-semibold">{children}</strong>
          ),
          em: ({ children }) => (
            <em className="text-gray-200 italic">{children}</em>
          ),
          // 链接
          a: ({ href, children }) => (
            <a href={href} className="text-purple-400 hover:text-purple-300 underline" target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          // 列表
          ul: ({ children }) => (
            <ul className="space-y-2 text-gray-300 my-4 ml-4">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-2 text-gray-300 my-4 ml-2">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="flex">
              <span className="mr-2 text-gray-500">•</span>
              <span>{children}</span>
            </li>
          ),
          // 代码
          code: ({ className, children }) => {
            const isBlock = className?.includes('language-');
            if (isBlock) {
              return (
                <code className="block bg-gray-800/50 p-4 rounded-lg text-sm text-gray-300 overflow-x-auto">
                  {children}
                </code>
              );
            }
            return (
              <code className="bg-gray-800/50 px-1.5 py-0.5 rounded text-sm text-purple-300">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="bg-gray-800/50 rounded-lg my-4 overflow-x-auto">{children}</pre>
          ),
          // 引用
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 border-purple-500/50 pl-4 my-4 text-gray-400 italic">
              {children}
            </blockquote>
          ),
          // 分隔线
          hr: () => <hr className="my-6 border-gray-600" />,
          // 表格
          table: ({ children }) => (
            <div className="my-4 overflow-x-auto">
              <table className="min-w-full text-sm border border-gray-700 rounded-lg">{children}</table>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="bg-gray-800/50 border-b border-gray-600">{children}</thead>
          ),
          tbody: ({ children }) => <tbody>{children}</tbody>,
          tr: ({ children }) => (
            <tr className="border-b border-gray-700/50 hover:bg-gray-800/30">{children}</tr>
          ),
          th: ({ children }) => (
            <th className="px-4 py-3 text-left text-gray-200 font-medium">{children}</th>
          ),
          td: ({ children }) => (
            <td className="px-4 py-3 text-gray-300">{children}</td>
          ),
          // 图片
          img: ({ src, alt }) => (
            <img src={src} alt={alt || ''} className="max-w-full h-auto rounded-lg my-4" />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

// 分享平台配置
const sharePlatforms = [
  {
    id: 'x',
    name: 'X (Twitter)',
    icon: '𝕏',
    color: 'bg-black hover:bg-gray-900',
    getUrl: (url: string, title: string) =>
      `https://twitter.com/intent/tweet?text=${encodeURIComponent(title)}&url=${encodeURIComponent(url)}`,
  },
  {
    id: 'weibo',
    name: '微博',
    icon: '微',
    color: 'bg-red-500 hover:bg-red-600',
    getUrl: (url: string, title: string) =>
      `https://service.weibo.com/share/share.php?url=${encodeURIComponent(url)}&title=${encodeURIComponent(title)}`,
  },
  {
    id: 'xiaohongshu',
    name: '小红书',
    icon: '📕',
    color: 'bg-red-400 hover:bg-red-500',
    getUrl: () => '', // 小红书不支持直接分享链接，需要截图后手动分享
    copyOnly: true,
  },
  {
    id: 'zhihu',
    name: '知乎',
    icon: '知',
    color: 'bg-blue-600 hover:bg-blue-700',
    getUrl: (url: string, title: string) =>
      `https://www.zhihu.com/share?url=${encodeURIComponent(url)}&title=${encodeURIComponent(title)}`,
  },
  {
    id: 'douyin',
    name: '抖音',
    icon: '🎵',
    color: 'bg-black hover:bg-gray-900',
    getUrl: () => '',
    copyOnly: true,
  },
  {
    id: 'kuaishou',
    name: '快手',
    icon: '快',
    color: 'bg-orange-500 hover:bg-orange-600',
    getUrl: () => '',
    copyOnly: true,
  },
];

// 分享弹窗组件
function ShareModal({
  isOpen,
  onClose,
  article,
  contentRef,
}: {
  isOpen: boolean;
  onClose: () => void;
  article: NewsArticle;
  contentRef: React.RefObject<HTMLElement>;
}) {
  const [isCapturing, setIsCapturing] = useState(false);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const currentUrl = typeof window !== 'undefined' ? window.location.href : '';

  // 截图功能
  const handleCapture = async () => {
    if (!contentRef.current) return;

    setIsCapturing(true);
    try {
      const { default: html2canvas } = await import('html2canvas');
      const canvas = await html2canvas(contentRef.current, {
        backgroundColor: '#1e293b',
        scale: 2,
        useCORS: true,
        logging: false,
      });
      const dataUrl = canvas.toDataURL('image/png');
      setCapturedImage(dataUrl);
    } catch (error) {
      console.error('截图失败:', error);
      alert('截图失败，请重试');
    } finally {
      setIsCapturing(false);
    }
  };

  // 下载截图
  const handleDownload = () => {
    if (!capturedImage) return;
    const link = document.createElement('a');
    link.download = `${article.title.slice(0, 30)}-health.executor.life.png`;
    link.href = capturedImage;
    link.click();
  };

  // 复制链接
  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(currentUrl);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (error) {
      // fallback
      const textarea = document.createElement('textarea');
      textarea.value = currentUrl;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // 分享到平台
  const handleShare = (platform: typeof sharePlatforms[0]) => {
    if (platform.copyOnly) {
      handleCopyLink();
      alert(`链接已复制！请打开${platform.name}App，粘贴链接或上传截图进行分享。`);
      return;
    }
    const shareUrl = platform.getUrl(currentUrl, article.title);
    if (shareUrl) {
      window.open(shareUrl, '_blank', 'width=600,height=500');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* 背景遮罩 */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* 弹窗内容 */}
      <div className="relative bg-slate-800 border border-white/10 rounded-2xl w-full max-w-lg max-h-[90vh] overflow-auto">
        {/* 头部 */}
        <div className="flex items-center justify-between p-4 border-b border-white/10">
          <h3 className="text-lg font-semibold text-white flex items-center gap-2">
            <Share2 className="w-5 h-5" />
            分享文章
          </h3>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 内容 */}
        <div className="p-4 space-y-4">
          {/* 截图区域 */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-gray-300">一键截图</h4>
            {capturedImage ? (
              <div className="space-y-3">
                <div className="relative rounded-lg overflow-hidden border border-white/10">
                  <img
                    src={capturedImage}
                    alt="截图预览"
                    className="w-full h-auto"
                  />
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={handleDownload}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors"
                  >
                    <Download className="w-4 h-4" />
                    保存图片
                  </button>
                  <button
                    onClick={() => setCapturedImage(null)}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-gray-300 rounded-lg transition-colors"
                  >
                    重新截图
                  </button>
                </div>
              </div>
            ) : (
              <button
                onClick={handleCapture}
                disabled={isCapturing}
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-600/50 text-white rounded-lg transition-colors"
              >
                <Camera className="w-5 h-5" />
                {isCapturing ? '正在生成截图...' : '生成文章截图'}
              </button>
            )}
          </div>

          {/* 复制链接 */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-gray-300">复制链接</h4>
            <div className="flex gap-2">
              <input
                type="text"
                readOnly
                value={currentUrl}
                className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-gray-300 text-sm"
              />
              <button
                onClick={handleCopyLink}
                className="flex items-center gap-2 px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-colors"
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
                {copied ? '已复制' : '复制'}
              </button>
            </div>
          </div>

          {/* 分享到平台 */}
          <div className="space-y-3">
            <h4 className="text-sm font-medium text-gray-300">分享到社交媒体</h4>
            <div className="grid grid-cols-3 gap-2">
              {sharePlatforms.map((platform) => (
                <button
                  key={platform.id}
                  onClick={() => handleShare(platform)}
                  className={`flex flex-col items-center gap-1.5 px-3 py-3 ${platform.color} text-white rounded-lg transition-colors`}
                >
                  <span className="text-lg">{platform.icon}</span>
                  <span className="text-xs">{platform.name}</span>
                </button>
              ))}
            </div>
            <p className="text-xs text-gray-500 text-center">
              💡 小红书、抖音、快手需要复制链接后在App内分享，或保存截图后上传
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// 单条评论组件
function CommentItem({
  comment,
  articleId,
  currentUserId,
  isAdmin,
  onReply,
  onDelete,
  depth = 0,
}: {
  comment: NewsComment;
  articleId: number;
  currentUserId: number | undefined;
  isAdmin: boolean;
  onReply: (commentId: number, userName: string) => void;
  onDelete: (commentId: number) => void;
  depth?: number;
}) {
  const canDelete = currentUserId === comment.user_id || isAdmin;
  const maxDepth = 3; // 最大嵌套深度

  return (
    <div className={`${depth > 0 ? 'ml-6 pl-4 border-l border-white/10' : ''}`}>
      <div className="py-3">
        <div className="flex items-start gap-3">
          {/* 用户头像 */}
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-white font-semibold text-sm flex-shrink-0">
            {comment.user.name?.[0] || '?'}
          </div>
          <div className="flex-1 min-w-0">
            {/* 用户名和时间 */}
            <div className="flex items-center gap-2 mb-1">
              <span className="text-white font-medium text-sm">{comment.user.name}</span>
              {comment.user.is_admin && (
                <span className="px-1.5 py-0.5 bg-yellow-500/20 text-yellow-300 text-xs rounded">管理员</span>
              )}
              <span className="text-gray-500 text-xs">
                {formatDateTime(comment.created_at)}
              </span>
            </div>
            {/* 评论内容 */}
            <p className="text-gray-300 text-sm whitespace-pre-wrap break-words">{comment.content}</p>
            {/* 操作按钮 */}
            <div className="flex items-center gap-4 mt-2">
              <button
                onClick={() => onReply(comment.id, comment.user.name)}
                className="flex items-center gap-1 text-gray-500 hover:text-purple-400 text-xs transition-colors"
              >
                <Reply className="w-3 h-3" />
                回复
              </button>
              {canDelete && (
                <button
                  onClick={() => onDelete(comment.id)}
                  className="flex items-center gap-1 text-gray-500 hover:text-red-400 text-xs transition-colors"
                >
                  <Trash2 className="w-3 h-3" />
                  删除
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
      {/* 嵌套回复 */}
      {comment.replies && comment.replies.length > 0 && depth < maxDepth && (
        <div className="mt-1">
          {comment.replies.map((reply) => (
            <CommentItem
              key={reply.id}
              comment={reply}
              articleId={articleId}
              currentUserId={currentUserId}
              isAdmin={isAdmin}
              onReply={onReply}
              onDelete={onDelete}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// 评论区组件
function CommentSection({ articleId }: { articleId: number }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [commentText, setCommentText] = useState('');
  const [replyTo, setReplyTo] = useState<{ id: number; name: string } | null>(null);

  // 获取评论列表
  const { data: commentsData, isLoading: commentsLoading } = useQuery({
    queryKey: ['news-comments', articleId],
    queryFn: async () => {
      const response = await newsApi.getComments(articleId);
      return response.data;
    },
    enabled: !!articleId,
  });

  // 发表评论
  const createCommentMutation = useMutation({
    mutationFn: async () => {
      return newsApi.createComment(articleId, commentText, replyTo?.id);
    },
    onSuccess: () => {
      setCommentText('');
      setReplyTo(null);
      queryClient.invalidateQueries({ queryKey: ['news-comments', articleId] });
    },
    onError: (error: any) => {
      alert(error?.response?.data?.detail || '评论失败');
    },
  });

  // 删除评论
  const deleteCommentMutation = useMutation({
    mutationFn: async (commentId: number) => {
      return newsApi.deleteComment(commentId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['news-comments', articleId] });
    },
    onError: (error: any) => {
      alert(error?.response?.data?.detail || '删除失败');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!commentText.trim()) return;
    createCommentMutation.mutate();
  };

  const handleReply = (commentId: number, userName: string) => {
    setReplyTo({ id: commentId, name: userName });
    // 聚焦到输入框
    document.getElementById('comment-input')?.focus();
  };

  const handleDelete = (commentId: number) => {
    if (confirm('确定要删除这条评论吗？')) {
      deleteCommentMutation.mutate(commentId);
    }
  };

  const comments = commentsData?.comments || [];
  const total = commentsData?.total || 0;

  return (
    <div className="mt-8 bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl overflow-hidden">
      {/* 评论区标题 */}
      <div className="px-6 py-4 border-b border-white/10">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-white">
          <MessageCircle className="w-5 h-5" />
          评论 ({total})
        </h2>
      </div>

      {/* 评论输入框 */}
      <div className="px-6 py-4 border-b border-white/10">
        <form onSubmit={handleSubmit}>
          {replyTo && (
            <div className="flex items-center gap-2 mb-2 text-sm">
              <span className="text-gray-400">回复</span>
              <span className="text-purple-400">@{replyTo.name}</span>
              <button
                type="button"
                onClick={() => setReplyTo(null)}
                className="text-gray-500 hover:text-white"
              >
                ✕
              </button>
            </div>
          )}
          <div className="flex gap-3">
            <textarea
              id="comment-input"
              value={commentText}
              onChange={(e) => setCommentText(e.target.value)}
              placeholder={replyTo ? `回复 @${replyTo.name}...` : '写下你的评论...'}
              className="flex-1 px-4 py-3 bg-white/5 border border-white/10 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500/50 focus:border-purple-500/50 resize-none text-sm"
              rows={2}
              maxLength={2000}
            />
            <button
              type="submit"
              disabled={!commentText.trim() || createCommentMutation.isPending}
              className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg transition-colors flex items-center gap-2 self-end"
            >
              <Send className="w-4 h-4" />
              {createCommentMutation.isPending ? '发送中...' : '发送'}
            </button>
          </div>
        </form>
      </div>

      {/* 评论列表 */}
      <div className="px-6 py-4">
        {commentsLoading ? (
          <div className="text-center py-8">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-400 mx-auto"></div>
          </div>
        ) : comments.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            暂无评论，来发表第一条评论吧~
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {comments.map((comment) => (
              <CommentItem
                key={comment.id}
                comment={comment}
                articleId={articleId}
                currentUserId={user?.id}
                isAdmin={user?.is_admin || false}
                onReply={handleReply}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function NewsDetailContent() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const articleId = Number(params.id);
  const articleRef = useRef<HTMLElement>(null);
  const [showShareModal, setShowShareModal] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const { data: article, isLoading, error, refetch } = useQuery({
    queryKey: ['news-article', articleId],
    queryFn: async () => {
      const response = await newsApi.getArticle(articleId);
      return response.data;
    },
    enabled: !!articleId,
  });

  const isOwner = !!user && !!article && article.user_id === user.id;
  const isAdmin = user?.is_admin ?? false;
  const canDelete = isOwner || isAdmin;

  const handleToggleVisibility = async () => {
    if (!article) return;
    setActionLoading(true);
    try {
      const newVisibility = article.visibility === 'public' ? 'private' : 'public';
      await newsApi.updateVisibility(articleId, newVisibility);
      refetch();
    } catch (err) {
      alert('更新失败');
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!article || !confirm(`确定要删除文章「${article.title}」吗？`)) return;
    setActionLoading(true);
    try {
      await newsApi.deleteArticle(articleId);
      router.push('/news');
    } catch (err) {
      alert('删除失败');
      setActionLoading(false);
    }
  };

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
        <article ref={articleRef} className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl overflow-hidden">
          {/* 头部信息 */}
          <div className="p-6 md:p-8 border-b border-white/10">
            {/* 标签和状态 + 分享按钮 */}
            <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
              <div className="flex flex-wrap items-center gap-2">
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

              {/* 操作按钮组 */}
              <div className="flex items-center gap-2">
                {/* 可见性切换（仅本人） */}
                {isOwner && (
                  <button
                    onClick={handleToggleVisibility}
                    disabled={actionLoading}
                    className={`flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg transition-colors disabled:opacity-50 ${
                      article.visibility === 'public'
                        ? 'bg-green-500/20 hover:bg-green-500/30 text-green-400 border border-green-500/30'
                        : 'bg-gray-500/20 hover:bg-gray-500/30 text-gray-400 border border-gray-500/30'
                    }`}
                    title={article.visibility === 'public' ? '点击设为私密' : '点击设为公开'}
                  >
                    {article.visibility === 'public'
                      ? <><Globe className="w-4 h-4" />公开</>
                      : <><Lock className="w-4 h-4" />私密</>
                    }
                  </button>
                )}
                {/* 删除（本人或管理员） */}
                {canDelete && (
                  <button
                    onClick={handleDelete}
                    disabled={actionLoading}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/30 text-sm rounded-lg transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="w-4 h-4" />
                    删除
                  </button>
                )}
                {/* 截图分享 */}
                <button
                  onClick={() => setShowShareModal(true)}
                  className="flex items-center gap-2 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg transition-colors"
                >
                  <Camera className="w-4 h-4" />
                  截图分享
                </button>
              </div>
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
              {article.author_name && !isOwner && (
                <span className="flex items-center gap-1.5">
                  <User className="w-4 h-4" />
                  {article.author_name}
                </span>
              )}
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

        {/* 评论区 */}
        <CommentSection articleId={articleId} />

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

      {/* 分享弹窗 */}
      <ShareModal
        isOpen={showShareModal}
        onClose={() => setShowShareModal(false)}
        article={article}
        contentRef={articleRef}
      />
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
