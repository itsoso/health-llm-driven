/**
 * 多模型分析页面
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { View, Text, Textarea, ScrollView, RichText, Picker } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { llmAPI } from '../../services/llmApi';
import { markdownToHtml } from '../../utils/markdown';
import type { Batch, ModelResult } from '../../types/llm';
import { getSiteInfo } from '../../types/llm';
import './index.scss';

// 可用模型配置
const BROWSER_MODELS = [
  { id: 'chatgpt', name: 'ChatGPT', icon: '🤖' },
  { id: 'gemini', name: 'Gemini', icon: '✨' },
  { id: 'grok', name: 'Grok', icon: '🧠' },
  { id: 'claude', name: 'Claude', icon: '🎭' },
];

const API_MODELS = [
  { id: 'lb-gemini-3-pro', name: 'Gemini 3 Pro', icon: '✨' },
  { id: 'lb-claude-4.5-sonnet', name: 'Claude 4.5', icon: '🎭' },
  { id: 'lb-gpt-5.1', name: 'GPT 5.1', icon: '🤖' },
  { id: 'lb-claude-4-sonnet-think', name: 'Claude 4 Think', icon: '🎭' },
];

const AGGREGATOR_OPTIONS = [
  { value: 'gemini', label: 'Gemini' },
  { value: 'chatgpt', label: 'ChatGPT' },
  { value: 'claude', label: 'Claude' },
  { value: 'lb-gemini-3-pro', label: 'Gemini 3 Pro (API)' },
  { value: 'lb-claude-4.5-sonnet', label: 'Claude 4.5 (API)' },
];

const STATUS_ICONS: Record<string, string> = {
  pending: '⬜',
  processing: '⏳',
  completed: '✅',
  failed: '❌',
  cancelled: '⛔',
};

function formatElapsed(seconds?: number): string {
  if (!seconds) return '';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m${Math.round(seconds % 60)}s`;
}

export default function LLMAnalysisPage() {
  // 输入状态
  const [prompt, setPrompt] = useState('');
  const [selectedSites, setSelectedSites] = useState<string[]>(['chatgpt', 'gemini', 'grok']);
  const [adapterMode, setAdapterMode] = useState<'browser' | 'api'>('api');
  const [aggregatorSite, setAggregatorSite] = useState('gemini');
  const [showApiModels, setShowApiModels] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);

  // 分析状态
  const [submitting, setSubmitting] = useState(false);
  const [currentBatch, setCurrentBatch] = useState<Batch | null>(null);
  const [expandedModels, setExpandedModels] = useState<Set<string>>(new Set());

  // 轮询
  const pollingRef = useRef<any>(null);
  const batchIdRef = useRef<string | null>(null);

  // 页面显示时检查是否有正在处理的批次
  useEffect(() => {
    checkExistingBatch();
    return () => stopPolling();
  }, []);

  // 从模板页面返回时，读取选中的模板
  Taro.useDidShow(() => {
    try {
      const stored = Taro.getStorageSync('_selected_template');
      if (stored) {
        const tpl = JSON.parse(stored);
        if (tpl.prompt) setPrompt(tpl.prompt);
        Taro.removeStorageSync('_selected_template');
      }
    } catch {}
  });

  const checkExistingBatch = async () => {
    try {
      const res = await llmAPI.checkProcessing();
      if (res.has_processing && res.processing_batches?.length) {
        const batchId = res.processing_batches[0];
        batchIdRef.current = batchId;
        startPolling(batchId);
      }
    } catch {}
  };

  const startPolling = useCallback((batchId: string) => {
    stopPolling();
    // 立即获取一次
    pollStatus(batchId);
    pollingRef.current = setInterval(() => pollStatus(batchId), 3000);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const pollStatus = async (batchId: string) => {
    try {
      const res = await llmAPI.getBatchStatus(batchId);
      if (res.ok && res.batch) {
        setCurrentBatch(res.batch);
        const status = res.batch.status;
        if (['completed', 'failed', 'partial', 'cancelled'].includes(status)) {
          stopPolling();
          setSubmitting(false);
        }
      }
    } catch (err) {
      console.error('轮询失败:', err);
    }
  };

  const toggleSite = (siteId: string) => {
    setSelectedSites(prev =>
      prev.includes(siteId)
        ? prev.filter(s => s !== siteId)
        : [...prev, siteId]
    );
  };

  const toggleExpand = (site: string) => {
    setExpandedModels(prev => {
      const next = new Set(prev);
      if (next.has(site)) next.delete(site);
      else next.add(site);
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!prompt.trim()) {
      Taro.showToast({ title: '请输入分析内容', icon: 'none' });
      return;
    }
    if (selectedSites.length === 0) {
      Taro.showToast({ title: '请至少选择一个模型', icon: 'none' });
      return;
    }

    setSubmitting(true);
    setCurrentBatch(null);

    try {
      // 检查是否可以提交
      const checkRes = await llmAPI.checkProcessing();
      if (!checkRes.can_submit) {
        Taro.showToast({ title: '有批次正在处理中', icon: 'none' });
        setSubmitting(false);
        return;
      }

      // 创建批次
      const createRes = await llmAPI.createBatch({
        prompt: prompt.trim(),
        llm_sites: selectedSites,
        aggregator_site: aggregatorSite,
        adapter_mode: adapterMode,
        web_search_enabled: webSearchEnabled,
      });

      if (!createRes.ok || !createRes.batch_id) {
        throw new Error('创建批次失败');
      }

      const batchId = createRes.batch_id;
      batchIdRef.current = batchId;
      setCurrentBatch(createRes.batch);

      // 开始处理
      await llmAPI.processBatch(batchId);

      // 开始轮询
      startPolling(batchId);

      Taro.showToast({ title: '分析已开始', icon: 'success' });
    } catch (err: any) {
      Taro.showToast({ title: err.message || '提交失败', icon: 'none' });
      setSubmitting(false);
    }
  };

  const handleCancel = async () => {
    if (!batchIdRef.current) return;
    try {
      await llmAPI.cancelBatch(batchIdRef.current);
      stopPolling();
      setSubmitting(false);
      Taro.showToast({ title: '已取消', icon: 'none' });
    } catch {}
  };

  const handleRetry = async () => {
    if (!batchIdRef.current) return;
    try {
      await llmAPI.retryBatch(batchIdRef.current);
      setSubmitting(true);
      startPolling(batchIdRef.current);
      Taro.showToast({ title: '重试已开始', icon: 'success' });
    } catch (err: any) {
      Taro.showToast({ title: err.message || '重试失败', icon: 'none' });
    }
  };

  const goToTemplates = () => {
    Taro.navigateTo({ url: '/pages/llm-templates/index' });
  };

  const goToHistory = () => {
    Taro.navigateTo({ url: '/pages/llm-history/index' });
  };

  const isProcessing = currentBatch && ['pending', 'processing'].includes(currentBatch.status);
  const isFinished = currentBatch && ['completed', 'failed', 'partial', 'cancelled'].includes(currentBatch.status);

  return (
    <ScrollView scrollY className="analysis-page">
      {/* 输入区 */}
      <View className="input-section">
        <Textarea
          className="prompt-input"
          value={prompt}
          onInput={(e) => setPrompt(e.detail.value)}
          placeholder="输入你想分析的问题..."
          maxlength={5000}
          autoHeight
          disabled={submitting}
        />
        <View className="quick-actions">
          <View className="action-btn" onClick={goToTemplates}>
            📋 模板
          </View>
          <View className="action-btn" onClick={goToHistory}>
            📜 历史
          </View>
          <View
            className={`action-btn ${webSearchEnabled ? 'active' : ''}`}
            onClick={() => setWebSearchEnabled(!webSearchEnabled)}
          >
            🔍 搜索增强
          </View>
        </View>
      </View>

      {/* 模型选择 */}
      <View className="model-section">
        <Text className="section-title">分析模型</Text>
        <View className="model-grid">
          {BROWSER_MODELS.map(m => (
            <View
              key={m.id}
              className={`model-chip ${selectedSites.includes(m.id) ? 'selected' : ''}`}
              onClick={() => toggleSite(m.id)}
            >
              <Text>{m.icon} {m.name}</Text>
            </View>
          ))}
        </View>

        <View className="toggle-api" onClick={() => setShowApiModels(!showApiModels)}>
          <Text className="toggle-text">API 模型 {showApiModels ? '▾' : '▸'}</Text>
        </View>

        {showApiModels && (
          <View className="model-grid">
            {API_MODELS.map(m => (
              <View
                key={m.id}
                className={`model-chip ${selectedSites.includes(m.id) ? 'selected' : ''}`}
                onClick={() => toggleSite(m.id)}
              >
                <Text>{m.icon} {m.name}</Text>
              </View>
            ))}
          </View>
        )}
      </View>

      {/* 高级设置 */}
      <View className="settings-section">
        <View className="setting-row">
          <Text className="setting-label">汇总模型</Text>
          <Picker
            mode="selector"
            range={AGGREGATOR_OPTIONS.map(o => o.label)}
            value={AGGREGATOR_OPTIONS.findIndex(o => o.value === aggregatorSite)}
            onChange={(e) => setAggregatorSite(AGGREGATOR_OPTIONS[Number(e.detail.value)].value)}
          >
            <View className="picker-value">
              {AGGREGATOR_OPTIONS.find(o => o.value === aggregatorSite)?.label || aggregatorSite} ▾
            </View>
          </Picker>
        </View>

        <View className="setting-row">
          <Text className="setting-label">适配器</Text>
          <View className="adapter-toggle">
            <View
              className={`adapter-btn ${adapterMode === 'api' ? 'active' : ''}`}
              onClick={() => setAdapterMode('api')}
            >
              API
            </View>
            <View
              className={`adapter-btn ${adapterMode === 'browser' ? 'active' : ''}`}
              onClick={() => setAdapterMode('browser')}
            >
              Browser
            </View>
          </View>
        </View>
      </View>

      {/* 提交按钮 */}
      <View className="submit-section">
        {isProcessing ? (
          <View className="cancel-btn" onClick={handleCancel}>
            ⛔ 取消分析
          </View>
        ) : (
          <View
            className={`submit-btn ${submitting || !prompt.trim() ? 'disabled' : ''}`}
            onClick={handleSubmit}
          >
            🚀 开始分析
          </View>
        )}
      </View>

      {/* 分析结果 */}
      {currentBatch && (
        <View className="results-section">
          {/* 进度状态 */}
          <View className="progress-header">
            <Text className="section-title">分析进度</Text>
            {currentBatch.total_elapsed_seconds ? (
              <Text className="elapsed">总耗时: {formatElapsed(currentBatch.total_elapsed_seconds)}</Text>
            ) : null}
          </View>

          <View className="model-status-list">
            {currentBatch.task?.model_results?.map((mr: ModelResult) => {
              const info = getSiteInfo(mr.llm_site);
              return (
                <View key={mr.llm_site} className="model-status-item">
                  <View
                    className="model-status-header"
                    onClick={() => mr.result_content && toggleExpand(mr.llm_site)}
                  >
                    <Text className="status-icon">{STATUS_ICONS[mr.status] || '⬜'}</Text>
                    <Text className="model-name">{info.icon} {info.name}</Text>
                    <Text className="model-elapsed">{formatElapsed(mr.elapsed_seconds)}</Text>
                    {mr.result_content && (
                      <Text className="expand-icon">{expandedModels.has(mr.llm_site) ? '▾' : '▸'}</Text>
                    )}
                  </View>

                  {mr.error_message && (
                    <View className="error-msg">
                      <Text>{mr.error_message}</Text>
                    </View>
                  )}

                  {expandedModels.has(mr.llm_site) && mr.result_content && (
                    <View className="model-result-content">
                      <RichText nodes={markdownToHtml(mr.result_content)} />
                    </View>
                  )}
                </View>
              );
            })}
          </View>

          {/* 汇总结果 */}
          {currentBatch.task?.aggregation_result && (
            <View className="aggregation-section">
              <Text className="section-title">📊 汇总结果</Text>
              <View className="aggregation-content">
                <RichText nodes={markdownToHtml(currentBatch.task.aggregation_result)} />
              </View>
            </View>
          )}

          {/* 操作按钮 */}
          {isFinished && (
            <View className="result-actions">
              {currentBatch.status === 'failed' || currentBatch.status === 'partial' ? (
                <View className="retry-btn" onClick={handleRetry}>
                  🔄 重试失败模型
                </View>
              ) : null}
              <View
                className="detail-btn"
                onClick={() => Taro.navigateTo({ url: `/pages/llm-detail/index?batchId=${currentBatch.batch_id}` })}
              >
                📄 查看详情
              </View>
            </View>
          )}
        </View>
      )}

      <View className="bottom-spacer" />
    </ScrollView>
  );
}
