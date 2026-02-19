/**
 * 模板选择页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Input } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { llmAPI } from '../../services/llmApi';
import type { PromptTemplate } from '../../types/llm';
import './index.scss';

const SCENE_TABS = [
  { key: '', label: '全部' },
  { key: 'general', label: '通用' },
  { key: 'health', label: '健康' },
  { key: 'chatlog', label: '群聊' },
  { key: 'twitter', label: 'Twitter' },
  { key: 'kim', label: 'Kim' },
  { key: 'telegram', label: 'Telegram' },
];

export default function LLMTemplatesPage() {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeScene, setActiveScene] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadTemplates();
  }, [activeScene]);

  const loadTemplates = async () => {
    setLoading(true);
    try {
      const res = await llmAPI.getTemplates('analysis', activeScene || undefined);
      if (res.ok) {
        setTemplates(res.templates || []);
      }
    } catch (err: any) {
      Taro.showToast({ title: err.message || '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  const filteredTemplates = searchQuery
    ? templates.filter(t =>
        t.name.includes(searchQuery) ||
        t.description?.includes(searchQuery) ||
        t.prompt.includes(searchQuery)
      )
    : templates;

  const handleSelect = (template: PromptTemplate) => {
    // 返回分析页面并填充 prompt
    const pages = Taro.getCurrentPages();
    if (pages.length >= 2) {
      const prevPage = pages[pages.length - 2];
      // 通过 eventChannel 或 globalData 传递
      Taro.setStorageSync('_selected_template', JSON.stringify(template));
    }
    Taro.navigateBack();
  };

  return (
    <View className="templates-page">
      {/* 搜索栏 */}
      <View className="search-bar">
        <Input
          className="search-input"
          value={searchQuery}
          onInput={(e) => setSearchQuery(e.detail.value)}
          placeholder="搜索模板..."
        />
      </View>

      {/* 场景标签 */}
      <ScrollView scrollX className="scene-tabs">
        {SCENE_TABS.map(tab => (
          <View
            key={tab.key}
            className={`scene-tab ${activeScene === tab.key ? 'active' : ''}`}
            onClick={() => setActiveScene(tab.key)}
          >
            <Text>{tab.label}</Text>
          </View>
        ))}
      </ScrollView>

      {/* 模板列表 */}
      <ScrollView scrollY className="template-list">
        {loading ? (
          <View className="loading-tip">
            <Text>加载中...</Text>
          </View>
        ) : filteredTemplates.length === 0 ? (
          <View className="empty-tip">
            <Text>暂无模板</Text>
          </View>
        ) : (
          filteredTemplates.map(tpl => (
            <View key={tpl.id} className="template-card" onClick={() => handleSelect(tpl)}>
              <View className="tpl-header">
                <Text className="tpl-name">{tpl.name}</Text>
                {tpl.scene_type && (
                  <Text className="tpl-scene">{tpl.scene_type}</Text>
                )}
              </View>
              {tpl.description && (
                <Text className="tpl-desc">{tpl.description}</Text>
              )}
              <Text className="tpl-prompt" numberOfLines={3}>{tpl.prompt}</Text>
              {tpl.tags && tpl.tags.length > 0 && (
                <View className="tpl-tags">
                  {tpl.tags.map(tag => (
                    <Text key={tag} className="tpl-tag">{tag}</Text>
                  ))}
                </View>
              )}
            </View>
          ))
        )}
      </ScrollView>
    </View>
  );
}
