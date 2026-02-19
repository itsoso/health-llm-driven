/**
 * 分析详情页面 - 查看某次分析的完整结果
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, RichText } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { llmAPI } from '../../services/llmApi';
import { markdownToHtml } from '../../utils/markdown';
import type { Batch, ModelResult } from '../../types/llm';
import { getSiteInfo } from '../../types/llm';
import './index.scss';

const STATUS_LABELS: Record<string, string> = {
  pending: '等待中',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
  partial: '部分完成',
  cancelled: '已取消',
};

function formatTime(iso?: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
}

function formatElapsed(seconds?: number): string {
  if (!seconds) return '';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`;
}

export default function LLMDetailPage() {
  const [batch, setBatch] = useState<Batch | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedModels, setExpandedModels] = useState<Set<string>>(new Set());
  const [showPrompt, setShowPrompt] = useState(false);

  useEffect(() => {
    const params = Taro.getCurrentInstance()?.router?.params;
    const batchId = params?.batchId;
    if (batchId) {
      loadBatch(batchId);
    }
  }, []);

  const loadBatch = async (batchId: string) => {
    try {
      const res = await llmAPI.getBatchStatus(batchId);
      if (res.ok && res.batch) {
        setBatch(res.batch);
        // 默认展开所有有结果的模型
        const expanded = new Set<string>();
        res.batch.task?.model_results?.forEach(mr => {
          if (mr.result_content) expanded.add(mr.llm_site);
        });
        setExpandedModels(expanded);
      }
    } catch (err: any) {
      Taro.showToast({ title: err.message || '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const toggleExpand = (site: string) => {
    setExpandedModels(prev => {
      const next = new Set(prev);
      if (next.has(site)) next.delete(site);
      else next.add(site);
      return next;
    });
  };

  const handleRetry = async () => {
    if (!batch) return;
    try {
      await llmAPI.retryBatch(batch.batch_id);
      Taro.showToast({ title: '重试已开始', icon: 'success' });
      setTimeout(() => loadBatch(batch.batch_id), 2000);
    } catch (err: any) {
      Taro.showToast({ title: err.message || '重试失败', icon: 'none' });
    }
  };

  const handleReAggregate = async () => {
    if (!batch) return;
    try {
      await llmAPI.reAggregate(batch.batch_id);
      Taro.showToast({ title: '重新汇总已开始', icon: 'success' });
      setTimeout(() => loadBatch(batch.batch_id), 3000);
    } catch (err: any) {
      Taro.showToast({ title: err.message || '汇总失败', icon: 'none' });
    }
  };

  const handleCopyResult = (content: string) => {
    Taro.setClipboardData({ data: content });
  };

  if (loading) {
    return (
      <View className="detail-page loading">
        <Text>加载中...</Text>
      </View>
    );
  }

  if (!batch) {
    return (
      <View className="detail-page loading">
        <Text>批次不存在</Text>
      </View>
    );
  }

  const statusLabel = STATUS_LABELS[batch.status] || batch.status;

  return (
    <ScrollView scrollY className="detail-page">
      {/* 头部信息 */}
      <View className="header-card">
        <View className="header-top">
          <View className={`status-badge status-${batch.status}`}>
            <Text>{statusLabel}</Text>
          </View>
          <Text className="time">{formatTime(batch.created_at)}</Text>
        </View>
        <Text className="title">{batch.title || batch.prompt?.substring(0, 50)}</Text>
        <View className="meta-row">
          <Text className="meta">模型: {batch.llm_sites?.join(', ')}</Text>
        </View>
        <View className="meta-row">
          <Text className="meta">汇总: {batch.aggregator_site}</Text>
          {batch.total_elapsed_seconds ? (
            <Text className="meta">耗时: {formatElapsed(batch.total_elapsed_seconds)}</Text>
          ) : null}
        </View>

        {/* Prompt */}
        <View className="prompt-toggle" onClick={() => setShowPrompt(!showPrompt)}>
          <Text className="prompt-label">📝 原始 Prompt {showPrompt ? '▾' : '▸'}</Text>
        </View>
        {showPrompt && (
          <View className="prompt-content">
            <Text className="prompt-text" selectable>{batch.prompt}</Text>
          </View>
        )}
      </View>

      {/* 各模型结果 */}
      {batch.task?.model_results?.map((mr: ModelResult) => {
        const info = getSiteInfo(mr.llm_site);
        const isExpanded = expandedModels.has(mr.llm_site);

        return (
          <View key={mr.llm_site} className="result-card">
            <View className="result-header" onClick={() => toggleExpand(mr.llm_site)}>
              <Text className="result-icon">{info.icon}</Text>
              <Text className="result-name">{info.name}</Text>
              <View className={`mini-badge status-${mr.status}`}>
                <Text>{STATUS_LABELS[mr.status] || mr.status}</Text>
              </View>
              {mr.elapsed_seconds ? (
                <Text className="result-elapsed">{formatElapsed(mr.elapsed_seconds)}</Text>
              ) : null}
              <Text className="expand-arrow">{isExpanded ? '▾' : '▸'}</Text>
            </View>

            {mr.error_message && (
              <View className="error-bar">
                <Text>{mr.error_message}</Text>
              </View>
            )}

            {isExpanded && mr.result_content && (
              <View className="result-body">
                <RichText nodes={markdownToHtml(mr.result_content)} />
                <View className="copy-btn" onClick={() => handleCopyResult(mr.result_content!)}>
                  <Text>📋 复制</Text>
                </View>
              </View>
            )}
          </View>
        );
      })}

      {/* 汇总结果 */}
      {batch.task?.aggregation_result && (
        <View className="result-card aggregation">
          <View className="result-header">
            <Text className="result-icon">📊</Text>
            <Text className="result-name">汇总结果</Text>
          </View>
          <View className="result-body">
            <RichText nodes={markdownToHtml(batch.task.aggregation_result)} />
            <View className="copy-btn" onClick={() => handleCopyResult(batch.task.aggregation_result!)}>
              <Text>📋 复制全部</Text>
            </View>
          </View>
        </View>
      )}

      {/* 操作按钮 */}
      <View className="actions">
        {(batch.status === 'failed' || batch.status === 'partial') && (
          <View className="action-btn retry" onClick={handleRetry}>
            <Text>🔄 重试</Text>
          </View>
        )}
        {batch.status === 'completed' && (
          <View className="action-btn reagg" onClick={handleReAggregate}>
            <Text>🔀 重新汇总</Text>
          </View>
        )}
      </View>

      <View className="bottom-spacer" />
    </ScrollView>
  );
}
