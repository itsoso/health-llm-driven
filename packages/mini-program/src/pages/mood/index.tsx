/**
 * 情绪追踪页面
 */
import { useState, useEffect } from 'react';
import { View, Text, ScrollView, Textarea } from '@tarojs/components';
import Taro from '@tarojs/taro';
import {
  createMoodRecord,
  getMoodRecords,
  getTodayMoodRecord,
  updateMoodRecord,
  deleteMoodRecord,
  getMoodStats,
} from '../../services/api';
import type { MoodRecord, MoodStats } from '../../types';
import './index.scss';

// 情绪 Emoji 映射
const MOOD_EMOJIS: Record<number, { emoji: string; label: string; color: string }> = {
  1: { emoji: '😢', label: '很差', color: '#ef4444' },
  2: { emoji: '😟', label: '较差', color: '#f97316' },
  3: { emoji: '😐', label: '一般', color: '#eab308' },
  4: { emoji: '😊', label: '较好', color: '#22c55e' },
  5: { emoji: '😄', label: '很好', color: '#10b981' },
};

const MOOD_TAG_OPTIONS = ['开心', '平静', '感恩', '兴奋', '焦虑', '疲惫', '烦躁', '悲伤', '孤独', '压力大'];
const TRIGGER_OPTIONS = ['工作', '运动', '社交', '天气', '睡眠', '饮食', '家庭', '健康', '财务', '学习'];
const COPING_OPTIONS = ['运动', '冥想', '社交', '音乐', '阅读', '散步', '深呼吸', '写日记', '休息', '倾诉'];

function getBeijingToday(): string {
  const now = new Date();
  const utcTime = now.getTime() + now.getTimezoneOffset() * 60 * 1000;
  const beijingTime = new Date(utcTime + 8 * 60 * 60 * 1000);
  const year = beijingTime.getFullYear();
  const month = String(beijingTime.getMonth() + 1).padStart(2, '0');
  const day = String(beijingTime.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export default function MoodPage() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [records, setRecords] = useState<MoodRecord[]>([]);
  const [todayRecord, setTodayRecord] = useState<MoodRecord | null>(null);
  const [stats, setStats] = useState<MoodStats | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<'records' | 'stats'>('records');

  // 表单数据
  const [moodScore, setMoodScore] = useState(3);
  const [moodTags, setMoodTags] = useState<string[]>([]);
  const [energyLevel, setEnergyLevel] = useState(3);
  const [stressLevel, setStressLevel] = useState(3);
  const [journal, setJournal] = useState('');
  const [triggers, setTriggers] = useState<string[]>([]);
  const [copingMethods, setCopingMethods] = useState<string[]>([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      setLoading(true);
      const [recordsRes, todayRes, statsRes] = await Promise.allSettled([
        getMoodRecords(undefined, undefined, 30),
        getTodayMoodRecord(),
        getMoodStats(7),
      ]);

      if (recordsRes.status === 'fulfilled') setRecords(recordsRes.value);
      if (todayRes.status === 'fulfilled') setTodayRecord(todayRes.value);
      if (statsRes.status === 'fulfilled') setStats(statsRes.value);
    } catch (e) {
      console.error('[Mood] 加载数据失败:', e);
    } finally {
      setLoading(false);
    }
  };

  const resetForm = () => {
    setMoodScore(3);
    setMoodTags([]);
    setEnergyLevel(3);
    setStressLevel(3);
    setJournal('');
    setTriggers([]);
    setCopingMethods([]);
    setEditingId(null);
  };

  const openEditForm = (record: MoodRecord) => {
    setEditingId(record.id);
    setMoodScore(record.mood_score);
    setMoodTags(record.mood_tags || []);
    setEnergyLevel(record.energy_level || 3);
    setStressLevel(record.stress_level || 3);
    setJournal(record.journal || '');
    setTriggers(record.triggers || []);
    setCopingMethods(record.coping_methods || []);
    setShowForm(true);
  };

  const toggleTag = (tag: string, list: string[], setList: (v: string[]) => void) => {
    if (list.includes(tag)) {
      setList(list.filter(t => t !== tag));
    } else {
      setList([...list, tag]);
    }
  };

  const handleSubmit = async () => {
    if (submitting) return;

    try {
      setSubmitting(true);
      const data = {
        record_date: getBeijingToday(),
        mood_score: moodScore,
        mood_tags: moodTags,
        energy_level: energyLevel,
        stress_level: stressLevel,
        journal: journal || undefined,
        triggers,
        coping_methods: copingMethods,
      };

      if (editingId) {
        await updateMoodRecord(editingId, data);
        Taro.showToast({ title: '更新成功', icon: 'success' });
      } else {
        await createMoodRecord(data);
        Taro.showToast({ title: '记录成功', icon: 'success' });
      }

      setShowForm(false);
      resetForm();
      loadData();
    } catch (e) {
      console.error('[Mood] 保存失败:', e);
      Taro.showToast({ title: '保存失败', icon: 'none' });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      const { confirm } = await Taro.showModal({
        title: '确认删除',
        content: '确定要删除这条情绪记录吗？',
      });
      if (!confirm) return;

      await deleteMoodRecord(id);
      Taro.showToast({ title: '已删除', icon: 'success' });
      loadData();
    } catch (e) {
      console.error('[Mood] 删除失败:', e);
      Taro.showToast({ title: '删除失败', icon: 'none' });
    }
  };

  if (loading) {
    return (
      <View className='mood-page loading'>
        <View className='loading-spinner' />
        <Text className='loading-text'>加载中...</Text>
      </View>
    );
  }

  // 记录表单
  if (showForm) {
    return (
      <ScrollView className='mood-page' scrollY>
        <View className='form-header'>
          <Text className='form-title'>{editingId ? '编辑情绪记录' : '记录今日情绪'}</Text>
          <Text className='form-close' onClick={() => { setShowForm(false); resetForm(); }}>取消</Text>
        </View>

        {/* 情绪评分 */}
        <View className='form-section'>
          <Text className='section-label'>你现在感觉怎么样？</Text>
          <View className='mood-selector'>
            {[1, 2, 3, 4, 5].map(score => (
              <View
                key={score}
                className={`mood-option ${moodScore === score ? 'active' : ''}`}
                onClick={() => setMoodScore(score)}
              >
                <Text className='mood-emoji'>{MOOD_EMOJIS[score].emoji}</Text>
                <Text className='mood-label'>{MOOD_EMOJIS[score].label}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* 情绪标签 */}
        <View className='form-section'>
          <Text className='section-label'>情绪标签</Text>
          <View className='tag-grid'>
            {MOOD_TAG_OPTIONS.map(tag => (
              <View
                key={tag}
                className={`tag-item ${moodTags.includes(tag) ? 'active-purple' : ''}`}
                onClick={() => toggleTag(tag, moodTags, setMoodTags)}
              >
                <Text className='tag-text'>{tag}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* 精力/压力 */}
        <View className='form-section'>
          <View className='level-row'>
            <View className='level-group'>
              <Text className='section-label'>精力等级</Text>
              <View className='level-selector'>
                {[1, 2, 3, 4, 5].map(v => (
                  <View
                    key={v}
                    className={`level-btn ${energyLevel === v ? 'active-green' : ''}`}
                    onClick={() => setEnergyLevel(v)}
                  >
                    <Text className='level-text'>{v}</Text>
                  </View>
                ))}
              </View>
            </View>
            <View className='level-group'>
              <Text className='section-label'>压力等级</Text>
              <View className='level-selector'>
                {[1, 2, 3, 4, 5].map(v => (
                  <View
                    key={v}
                    className={`level-btn ${stressLevel === v ? 'active-red' : ''}`}
                    onClick={() => setStressLevel(v)}
                  >
                    <Text className='level-text'>{v}</Text>
                  </View>
                ))}
              </View>
            </View>
          </View>
        </View>

        {/* 触发因素 */}
        <View className='form-section'>
          <Text className='section-label'>触发因素</Text>
          <View className='tag-grid'>
            {TRIGGER_OPTIONS.map(tag => (
              <View
                key={tag}
                className={`tag-item ${triggers.includes(tag) ? 'active-orange' : ''}`}
                onClick={() => toggleTag(tag, triggers, setTriggers)}
              >
                <Text className='tag-text'>{tag}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* 应对方式 */}
        <View className='form-section'>
          <Text className='section-label'>应对方式</Text>
          <View className='tag-grid'>
            {COPING_OPTIONS.map(tag => (
              <View
                key={tag}
                className={`tag-item ${copingMethods.includes(tag) ? 'active-green' : ''}`}
                onClick={() => toggleTag(tag, copingMethods, setCopingMethods)}
              >
                <Text className='tag-text'>{tag}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* 情绪日记 */}
        <View className='form-section'>
          <Text className='section-label'>情绪日记（可选）</Text>
          <Textarea
            className='journal-input'
            value={journal}
            onInput={e => setJournal(e.detail.value)}
            placeholder='记录一下此刻的感受...'
            maxlength={2000}
          />
        </View>

        <View className='form-submit' onClick={handleSubmit}>
          <Text className='submit-text'>{submitting ? '保存中...' : (editingId ? '更新记录' : '保存记录')}</Text>
        </View>
      </ScrollView>
    );
  }

  return (
    <ScrollView className='mood-page' scrollY>
      {/* 今日情绪 */}
      {todayRecord ? (
        <View className='today-card'>
          <View className='today-header'>
            <Text className='today-title'>今日情绪</Text>
            <Text className='today-edit' onClick={() => openEditForm(todayRecord)}>编辑</Text>
          </View>
          <View className='today-content'>
            <Text className='today-emoji'>{MOOD_EMOJIS[todayRecord.mood_score]?.emoji}</Text>
            <View className='today-info'>
              <Text className='today-label' style={{ color: MOOD_EMOJIS[todayRecord.mood_score]?.color }}>
                {MOOD_EMOJIS[todayRecord.mood_score]?.label}
              </Text>
              <View className='today-tags'>
                {todayRecord.mood_tags?.map(tag => (
                  <Text key={tag} className='mini-tag purple'>{tag}</Text>
                ))}
              </View>
              {todayRecord.journal && (
                <Text className='today-journal' numberOfLines={2}>{todayRecord.journal}</Text>
              )}
            </View>
          </View>
        </View>
      ) : (
        <View className='today-empty' onClick={() => { resetForm(); setShowForm(true); }}>
          <Text className='empty-emoji'>😊</Text>
          <Text className='empty-text'>记录今日情绪</Text>
          <Text className='empty-hint'>点击开始记录</Text>
        </View>
      )}

      {/* Tab 切换 */}
      <View className='tab-bar'>
        <View
          className={`tab-item ${activeTab === 'records' ? 'active' : ''}`}
          onClick={() => setActiveTab('records')}
        >
          <Text className='tab-text'>记录列表</Text>
        </View>
        <View
          className={`tab-item ${activeTab === 'stats' ? 'active' : ''}`}
          onClick={() => setActiveTab('stats')}
        >
          <Text className='tab-text'>统计分析</Text>
        </View>
      </View>

      {/* 记录列表 */}
      {activeTab === 'records' && (
        <View className='records-list'>
          {records.length === 0 ? (
            <View className='empty-state'>
              <Text className='empty-state-text'>还没有情绪记录</Text>
            </View>
          ) : (
            records.map(record => (
              <View key={record.id} className='record-card'>
                <View className='record-left'>
                  <Text className='record-emoji'>{MOOD_EMOJIS[record.mood_score]?.emoji}</Text>
                </View>
                <View className='record-content'>
                  <View className='record-header'>
                    <Text className='record-label' style={{ color: MOOD_EMOJIS[record.mood_score]?.color }}>
                      {MOOD_EMOJIS[record.mood_score]?.label}
                    </Text>
                    <Text className='record-date'>{record.record_date.slice(5).replace('-', '/')}</Text>
                  </View>
                  {record.mood_tags?.length > 0 && (
                    <View className='record-tags'>
                      {record.mood_tags.map(tag => (
                        <Text key={tag} className='mini-tag purple'>{tag}</Text>
                      ))}
                    </View>
                  )}
                  {record.journal && (
                    <Text className='record-journal' numberOfLines={2}>{record.journal}</Text>
                  )}
                  <View className='record-meta'>
                    {record.energy_level && <Text className='meta-item'>精力 {record.energy_level}/5</Text>}
                    {record.stress_level && <Text className='meta-item'>压力 {record.stress_level}/5</Text>}
                  </View>
                </View>
                <View className='record-actions'>
                  <Text className='action-btn edit' onClick={() => openEditForm(record)}>编辑</Text>
                  <Text className='action-btn delete' onClick={() => handleDelete(record.id)}>删除</Text>
                </View>
              </View>
            ))
          )}
        </View>
      )}

      {/* 统计 */}
      {activeTab === 'stats' && stats && (
        <View className='stats-section'>
          <View className='stats-grid'>
            <View className='stat-card'>
              <Text className='stat-emoji'>{stats.avg_mood_score ? MOOD_EMOJIS[Math.round(stats.avg_mood_score)]?.emoji : '—'}</Text>
              <Text className='stat-value'>{stats.avg_mood_score?.toFixed(1) || '—'}</Text>
              <Text className='stat-label'>平均情绪</Text>
            </View>
            <View className='stat-card'>
              <Text className='stat-value'>{stats.avg_energy_level?.toFixed(1) || '—'}</Text>
              <Text className='stat-label'>平均精力</Text>
            </View>
            <View className='stat-card'>
              <Text className='stat-value'>{stats.avg_stress_level?.toFixed(1) || '—'}</Text>
              <Text className='stat-label'>平均压力</Text>
            </View>
            <View className='stat-card'>
              <Text className='stat-value'>{stats.total_records}</Text>
              <Text className='stat-label'>记录天数</Text>
            </View>
          </View>

          {/* 情绪分布 */}
          <View className='distribution-section'>
            <Text className='section-title'>情绪分布</Text>
            <View className='distribution-bar'>
              {[1, 2, 3, 4, 5].map(score => {
                const count = stats.mood_distribution[score] || 0;
                const maxCount = Math.max(...Object.values(stats.mood_distribution), 1);
                const width = count > 0 ? Math.max((count / maxCount) * 100, 10) : 0;
                return (
                  <View key={score} className='dist-row'>
                    <Text className='dist-emoji'>{MOOD_EMOJIS[score].emoji}</Text>
                    <View className='dist-bar-bg'>
                      <View
                        className='dist-bar-fill'
                        style={{ width: `${width}%`, backgroundColor: MOOD_EMOJIS[score].color }}
                      />
                    </View>
                    <Text className='dist-count'>{count}</Text>
                  </View>
                );
              })}
            </View>
          </View>

          {/* 常见标签 */}
          {Object.keys(stats.top_mood_tags).length > 0 && (
            <View className='tags-ranking'>
              <Text className='section-title'>常见情绪</Text>
              <View className='ranking-list'>
                {Object.entries(stats.top_mood_tags).slice(0, 5).map(([tag, count]) => (
                  <View key={tag} className='ranking-item'>
                    <Text className='ranking-tag'>{tag}</Text>
                    <Text className='ranking-count'>{count}次</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          {/* 触发因素 */}
          {Object.keys(stats.top_triggers).length > 0 && (
            <View className='tags-ranking'>
              <Text className='section-title'>触发因素</Text>
              <View className='ranking-list'>
                {Object.entries(stats.top_triggers).slice(0, 5).map(([tag, count]) => (
                  <View key={tag} className='ranking-item'>
                    <Text className='ranking-tag'>{tag}</Text>
                    <Text className='ranking-count'>{count}次</Text>
                  </View>
                ))}
              </View>
            </View>
          )}
        </View>
      )}

      {/* 浮动添加按钮 */}
      {!showForm && (
        <View className='fab-button' onClick={() => { resetForm(); setShowForm(true); }}>
          <Text className='fab-text'>+</Text>
        </View>
      )}
    </ScrollView>
  );
}
