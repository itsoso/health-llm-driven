/**
 * 资讯列表页 - VIP/管理员专属
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { getNewsList, NewsArticle } from '../../services/api';
import './index.scss';

export default function NewsPage() {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadArticles = async (pageNum: number = 1, refresh: boolean = false) => {
    try {
      if (refresh) {
        setRefreshing(true);
      } else if (pageNum === 1) {
        setLoading(true);
      }

      const data = await getNewsList(pageNum, 20);

      if (refresh || pageNum === 1) {
        setArticles(data);
      } else {
        setArticles(prev => [...prev, ...data]);
      }

      setHasMore(data.length >= 20);
      setPage(pageNum);
      setError(null);
    } catch (e: any) {
      console.error('[资讯] 加载失败:', e);
      if (e?.statusCode === 403) {
        setError('需要 VIP 或管理员权限访问');
      } else {
        setError('加载失败，请重试');
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadArticles(1);
  }, []);

  const handleRefresh = () => {
    loadArticles(1, true);
  };

  const handleLoadMore = () => {
    if (!loading && hasMore) {
      loadArticles(page + 1);
    }
  };

  const handleArticleClick = (article: NewsArticle) => {
    Taro.navigateTo({
      url: `/pages/news-detail/index?id=${article.id}`
    });
  };

  const getSourceTypeLabel = (sourceType: string) => {
    const labels: Record<string, string> = {
      'chatlog_analysis': '群聊总结',
      'custom_prompt': '研究分析',
      'daily_recap': '每日复盘',
    };
    return labels[sourceType] || sourceType;
  };

  const getSourceTypeColor = (sourceType: string) => {
    const colors: Record<string, string> = {
      'chatlog_analysis': 'blue',
      'custom_prompt': 'purple',
      'daily_recap': 'green',
    };
    return colors[sourceType] || 'gray';
  };

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));

    if (days === 0) {
      const hours = Math.floor(diff / (1000 * 60 * 60));
      if (hours === 0) {
        const minutes = Math.floor(diff / (1000 * 60));
        return minutes <= 0 ? '刚刚' : `${minutes}分钟前`;
      }
      return `${hours}小时前`;
    } else if (days === 1) {
      return '昨天';
    } else if (days < 7) {
      return `${days}天前`;
    } else {
      return `${date.getMonth() + 1}/${date.getDate()}`;
    }
  };

  if (loading && articles.length === 0) {
    return (
      <View className="news-page">
        <View className="loading-state">
          <Text className="loading-icon">...</Text>
          <Text className="loading-text">加载中</Text>
        </View>
      </View>
    );
  }

  if (error && articles.length === 0) {
    return (
      <View className="news-page">
        <View className="error-state">
          <Text className="error-icon">!</Text>
          <Text className="error-text">{error}</Text>
          <View className="retry-btn" onClick={() => loadArticles(1)}>
            <Text>重试</Text>
          </View>
        </View>
      </View>
    );
  }

  return (
    <View className="news-page">
      <ScrollView
        className="news-scroll"
        scrollY
        refresherEnabled
        refresherTriggered={refreshing}
        onRefresherRefresh={handleRefresh}
        onScrollToLower={handleLoadMore}
      >
        {/* 页面标题 */}
        <View className="page-header">
          <Text className="page-title">资讯</Text>
          <Text className="page-subtitle">群聊精华 · 研究结论</Text>
        </View>

        {/* 文章列表 */}
        <View className="article-list">
          {articles.map(article => (
            <View
              key={article.id}
              className={`article-card ${article.is_pinned ? 'pinned' : ''}`}
              onClick={() => handleArticleClick(article)}
            >
              {article.is_pinned && (
                <View className="pinned-badge">
                  <Text>置顶</Text>
                </View>
              )}

              <View className="article-header">
                <View className={`source-tag ${getSourceTypeColor(article.source_type)}`}>
                  <Text>{getSourceTypeLabel(article.source_type)}</Text>
                </View>
                {article.source_group && (
                  <Text className="source-group">{article.source_group}</Text>
                )}
                <Text className="article-time">{formatDate(article.created_at)}</Text>
              </View>

              <Text className="article-title">{article.title}</Text>

              {article.summary && (
                <Text className="article-summary">{article.summary}</Text>
              )}

              <View className="article-footer">
                {article.tags && article.tags.length > 0 && (
                  <View className="tags-row">
                    {article.tags.slice(0, 3).map((tag, idx) => (
                      <View key={idx} className="tag">
                        <Text>#{tag}</Text>
                      </View>
                    ))}
                  </View>
                )}
                <View className="view-count">
                  <Text>{article.view_count} 阅读</Text>
                </View>
              </View>
            </View>
          ))}
        </View>

        {/* 加载更多 */}
        {articles.length > 0 && (
          <View className="load-more">
            {hasMore ? (
              <Text className="load-more-text">上拉加载更多</Text>
            ) : (
              <Text className="load-more-text">没有更多了</Text>
            )}
          </View>
        )}

        {/* 空状态 */}
        {articles.length === 0 && !loading && (
          <View className="empty-state">
            <Text className="empty-icon">📰</Text>
            <Text className="empty-text">暂无资讯</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}
