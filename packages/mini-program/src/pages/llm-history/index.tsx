/**
 * 分析历史记录页面
 */
import { useState, useEffect, useCallback } from 'react';
import { View, Text, ScrollView, Input } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { llmAPI } from '../../services/llmApi';
import type { HistoryItem } from '../../types/llm';
import { getSiteInfo } from '../../types/llm';
import './index.scss';

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  completed: { label: '完成', color: '#16a34a', bg: '#dcfce7' },
  failed: { label: '失败', color: '#dc2626', bg: '#fee2e2' },
  partial: { label: '部分', color: '#d97706', bg: '#fef3c7' },
  processing: { label: '处理中', color: '#4f46e5', bg: '#e0e7ff' },
  pending: { label: '等待', color: '#999', bg: '#f0f0f5' },
  cancelled: { label: '取消', color: '#666', bg: '#f0f0f5' },
};

function formatTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const isToday = d.toDateString() === now.toDateString();
  const time = `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
  if (isToday) return `今天 ${time}`;
  return `${d.getMonth() + 1}/${d.getDate()} ${time}`;
}

export default function LLMHistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [isSearching, setIsSearching] = useState(false);

  const PAGE_SIZE = 20;

  useEffect(() => {
    loadHistory(1, true);
  }, []);

  const loadHistory = async (pageNum: number, reset = false) => {
    if (!reset && !hasMore) return;
    setLoading(true);

    try {
      const res = await llmAPI.getHistory(pageNum, PAGE_SIZE);
      if (res.ok) {
        const newItems = res.items || [];
        setItems(prev => reset ? newItems : [...prev, ...newItems]);
        setTotal(res.total || 0);
        setPage(pageNum);
        setHasMore(newItems.length >= PAGE_SIZE);
      }
    } catch (err: any) {
      Taro.showToast({ title: err.message || '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) {
      setIsSearching(false);
      loadHistory(1, true);
      return;
    }

    setLoading(true);
    setIsSearching(true);

    try {
      const res = await llmAPI.searchHistory(searchQuery.trim());
      if (res.ok) {
        setItems(res.items || []);
        setTotal(res.total || 0);
        setHasMore(false);
      }
    } catch (err: any) {
      Taro.showToast({ title: err.message || '搜索失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const loadMore = () => {
    if (!isSearching && hasMore && !loading) {
      loadHistory(page + 1);
    }
  };

  const handleRefresh = () => {
    setIsSearching(false);
    setSearchQuery('');
    loadHistory(1, true);
  };

  const goToDetail = (batchId: string) => {
    Taro.navigateTo({ url: `/pages/llm-detail/index?batchId=${batchId}` });
  };

  const handleDelete = async (batchId: string) => {
    const res = await Taro.showModal({
      title: '确认删除',
      content: '删除后不可恢复',
    });
    if (!res.confirm) return;

    try {
      await llmAPI.deleteBatch(batchId);
      setItems(prev => prev.filter(i => i.batch_id !== batchId));
      Taro.showToast({ title: '已删除', icon: 'success' });
    } catch (err: any) {
      Taro.showToast({ title: err.message || '删除失败', icon: 'none' });
    }
  };

  return (
    <View className="history-page">
      {/* 搜索栏 */}
      <View className="search-bar">
        <Input
          className="search-input"
          value={searchQuery}
          onInput={(e) => setSearchQuery(e.detail.value)}
          onConfirm={handleSearch}
          placeholder="搜索历史记录..."
          confirmType="search"
        />
        {searchQuery && (
          <View className="search-clear" onClick={handleRefresh}>
            <Text>✕</Text>
          </View>
        )}
      </View>

      <View className="stats-bar">
        <Text className="stats-text">
          {isSearching ? `搜索到 ${total} 条结果` : `共 ${total} 条记录`}
        </Text>
      </View>

      {/* 列表 */}
      <ScrollView
        scrollY
        className="history-list"
        onScrollToLower={loadMore}
      >
        {items.map(item => {
          const statusCfg = STATUS_CONFIG[item.status] || STATUS_CONFIG.pending;
          return (
            <View key={item.batch_id} className="history-item" onClick={() => goToDetail(item.batch_id)}>
              <View className="item-top">
                <Text className="item-title" numberOfLines={1}>
                  {item.title || item.prompt?.substring(0, 40) || '未命名'}
                </Text>
                <View
                  className="item-status"
                  style={{ background: statusCfg.bg, color: statusCfg.color }}
                >
                  <Text>{statusCfg.label}</Text>
                </View>
              </View>

              <Text className="item-prompt" numberOfLines={2}>
                {item.prompt}
              </Text>

              <View className="item-bottom">
                <View className="item-models">
                  {item.llm_sites?.slice(0, 3).map(s => (
                    <Text key={s} className="model-tag">{getSiteInfo(s).icon}</Text>
                  ))}
                  {(item.llm_sites?.length || 0) > 3 && (
                    <Text className="model-tag">+{(item.llm_sites?.length || 0) - 3}</Text>
                  )}
                </View>
                <Text className="item-time">{formatTime(item.created_at)}</Text>
              </View>

              <View
                className="delete-btn"
                onClick={(e) => { e.stopPropagation(); handleDelete(item.batch_id); }}
              >
                <Text>🗑</Text>
              </View>
            </View>
          );
        })}

        {loading && (
          <View className="loading-tip">
            <Text>加载中...</Text>
          </View>
        )}

        {!loading && items.length === 0 && (
          <View className="empty-tip">
            <Text>暂无记录</Text>
          </View>
        )}

        {!loading && !hasMore && items.length > 0 && (
          <View className="end-tip">
            <Text>没有更多了</Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
}
