import React, { useState, useEffect, useCallback } from 'react';
import { View, Text, Input } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { get, post, put, del } from '../../services/request';
import './index.scss';

type Status = 'active' | 'improving' | 'resolved';

interface IllnessUpdate {
  id: number;
  update_date: string;
  severity: number | null;
  status: string | null;
  notes: string | null;
}

interface IllnessEpisode {
  id: number;
  name: string;
  start_date: string;
  end_date: string | null;
  status: Status;
  severity: number;
  notes: string | null;
  created_at: string;
  updates?: IllnessUpdate[];
}

type View = 'list' | 'detail' | 'create';

const STATUS_LABEL: Record<string, string> = {
  active: '发作中',
  improving: '好转中',
  resolved: '已痊愈',
};

function daysSince(dateStr: string) {
  const d = new Date(dateStr);
  const now = new Date();
  return Math.floor((now.getTime() - d.getTime()) / 86400000) + 1;
}

function today() {
  return new Date().toISOString().split('T')[0];
}

export default function IllnessPage() {
  const [view, setView] = useState<View>('list');
  const [episodes, setEpisodes] = useState<IllnessEpisode[]>([]);
  const [history, setHistory] = useState<IllnessEpisode[]>([]);
  const [detail, setDetail] = useState<IllnessEpisode | null>(null);
  const [loading, setLoading] = useState(true);
  const [showHistory, setShowHistory] = useState(false);

  // 新建表单状态
  const [newName, setNewName] = useState('');
  const [newSeverity, setNewSeverity] = useState(5);
  const [newNotes, setNewNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [active, all] = await Promise.all([
        get<IllnessEpisode[]>('/illness/episodes'),
        get<IllnessEpisode[]>('/illness/episodes/all'),
      ]);
      setEpisodes(active || []);
      setHistory((all || []).filter(e => e.status === 'resolved'));
    } catch (e) {
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadData(); }, []);

  async function loadDetail(id: number) {
    try {
      const data = await get<IllnessEpisode>(`/illness/episodes/${id}`);
      setDetail(data);
      setView('detail');
    } catch {
      Taro.showToast({ title: '加载详情失败', icon: 'none' });
    }
  }

  async function quickUpdate(episode: IllnessEpisode, status: Status, severity?: number) {
    const body: any = { status };
    if (severity !== undefined) body.severity = severity;
    try {
      await put(`/illness/episodes/${episode.id}`, body);
      Taro.showToast({ title: STATUS_LABEL[status] + '已更新', icon: 'success' });
      loadData();
      if (detail?.id === episode.id) loadDetail(episode.id);
    } catch {
      Taro.showToast({ title: '更新失败', icon: 'none' });
    }
  }

  async function deleteEpisode(id: number) {
    Taro.showModal({
      title: '确认删除',
      content: '删除后无法恢复',
      success: async ({ confirm }) => {
        if (!confirm) return;
        try {
          await del(`/illness/episodes/${id}`);
          Taro.showToast({ title: '已删除', icon: 'success' });
          loadData();
          if (view === 'detail') setView('list');
        } catch {
          Taro.showToast({ title: '删除失败', icon: 'none' });
        }
      },
    });
  }

  async function handleCreate() {
    if (!newName.trim()) {
      Taro.showToast({ title: '请填写病症名称', icon: 'none' });
      return;
    }
    setSubmitting(true);
    try {
      await post('/illness/episodes', {
        name: newName.trim(),
        start_date: today(),
        severity: newSeverity,
        status: 'active',
        notes: newNotes.trim() || undefined,
      });
      Taro.showToast({ title: '已记录', icon: 'success' });
      setNewName(''); setNewSeverity(5); setNewNotes('');
      setView('list');
      loadData();
    } catch {
      Taro.showToast({ title: '创建失败', icon: 'none' });
    } finally {
      setSubmitting(false);
    }
  }

  // ── 列表视图 ──────────────────────────────────────────────────────
  if (view === 'list') {
    if (loading) {
      return (
        <View className="illness-page">
          <View className="loading">
            <Text className="loading-text">加载中...</Text>
          </View>
        </View>
      );
    }

    return (
      <View className="illness-page">
        <View className="header-bar">
          <Text className="header-title">当前病症</Text>
          <View className="add-btn" onClick={() => setView('create')}>+ 记录</View>
        </View>

        {/* 当前病症 */}
        {episodes.length === 0 ? (
          <View className="empty-state">
            <Text className="empty-icon">💪</Text>
            <Text className="empty-text">目前身体状况良好</Text>
            <Text className="empty-sub">如有不适，点右上角记录</Text>
          </View>
        ) : (
          <View className="illness-list">
            {episodes.map(ep => (
              <EpisodeCard
                key={ep.id}
                episode={ep}
                onDetail={() => loadDetail(ep.id)}
                onImprove={() => quickUpdate(ep, 'improving', Math.max(1, ep.severity - 2))}
                onResolve={() => quickUpdate(ep, 'resolved')}
                onWorsen={() => quickUpdate(ep, 'active', Math.min(10, ep.severity + 1))}
                onDelete={() => deleteEpisode(ep.id)}
              />
            ))}
          </View>
        )}

        {/* 历史病症 */}
        {history.length > 0 && (
          <View>
            <View className="section-title" onClick={() => setShowHistory(!showHistory)}>
              历史病症（{history.length}）{showHistory ? ' ▲' : ' ▼'}
            </View>
            {showHistory && (
              <View className="illness-list">
                {history.map(ep => (
                  <EpisodeCard
                    key={ep.id}
                    episode={ep}
                    onDetail={() => loadDetail(ep.id)}
                    onDelete={() => deleteEpisode(ep.id)}
                  />
                ))}
              </View>
            )}
          </View>
        )}
      </View>
    );
  }

  // ── 详情视图 ──────────────────────────────────────────────────────
  if (view === 'detail' && detail) {
    const days = daysSince(detail.start_date);
    return (
      <View className="illness-page">
        <View className="detail-header">
          <Text className="back-btn" onClick={() => setView('list')}>‹</Text>
          <Text className="detail-title">{detail.name}</Text>
          <View style="display:flex;gap:8px">
            <View className="action-btn delete" onClick={() => deleteEpisode(detail.id)}>删除</View>
          </View>
        </View>

        <View className="info-card">
          <View className="info-row">
            <Text className="info-item">📅 发作：{detail.start_date}</Text>
            <Text className="info-item">⏱ {days}天</Text>
            <Text className="info-item">
              严重度：{detail.severity}/10
            </Text>
            <Text className={'info-item status-badge ' + detail.status}>
              {STATUS_LABEL[detail.status]}
            </Text>
          </View>
          {detail.notes && <Text className="info-notes">{detail.notes}</Text>}
        </View>

        {detail.status !== 'resolved' && (
          <View className="card-actions" style="margin-bottom:16px">
            <View className="action-btn improve" onClick={() => quickUpdate(detail, 'improving', Math.max(1, detail.severity - 2))}>好转了</View>
            <View className="action-btn resolve" onClick={() => quickUpdate(detail, 'resolved')}>已痊愈</View>
            <View className="action-btn worsen" onClick={() => quickUpdate(detail, 'active', Math.min(10, detail.severity + 1))}>加重了</View>
          </View>
        )}

        <Text className="timeline-title">进展记录</Text>
        {(!detail.updates || detail.updates.length === 0) ? (
          <Text className="empty-text" style="font-size:24px;color:#64748B">暂无进展记录</Text>
        ) : (
          detail.updates.slice().reverse().map(u => (
            <View key={u.id} className="update-item">
              <Text className="update-dot">·</Text>
              <View className="update-content">
                <Text className="update-date">{u.update_date}</Text>
                <Text className="update-text">
                  {u.status ? STATUS_LABEL[u.status] || u.status : ''}
                  {u.severity ? ` 严重度${u.severity}/10` : ''}
                  {u.notes ? ` — ${u.notes}` : ''}
                </Text>
              </View>
            </View>
          ))
        )}
      </View>
    );
  }

  // ── 新建表单 ──────────────────────────────────────────────────────
  return (
    <View className="illness-page">
      <View className="detail-header">
        <Text className="back-btn" onClick={() => setView('list')}>‹</Text>
        <Text className="detail-title">记录病症</Text>
      </View>

      <View className="form-section">
        <Text className="form-title">基本信息</Text>

        <View className="form-group">
          <Text className="form-label">病症名称 *</Text>
          <Input
            className="form-input"
            placeholder="如：口腔溃疡、嘴唇起泡..."
            value={newName}
            onInput={e => setNewName(e.detail.value)}
          />
        </View>

        <View className="form-group">
          <Text className="form-label">严重程度（1=轻微  10=剧烈）当前：{newSeverity}</Text>
          <View className="severity-slider">
            {[1,2,3,4,5,6,7,8,9,10].map(n => (
              <View
                key={n}
                className={'sev-btn' + (newSeverity === n ? ' selected' : '')}
                onClick={() => setNewSeverity(n)}
              >
                {n}
              </View>
            ))}
          </View>
        </View>

        <View className="form-group">
          <Text className="form-label">备注（可选）</Text>
          <Input
            className="form-input"
            placeholder="如：右侧两个、进食疼痛..."
            value={newNotes}
            onInput={e => setNewNotes(e.detail.value)}
          />
        </View>
      </View>

      <View
        className={'submit-btn' + (submitting || !newName.trim() ? ' disabled' : '')}
        onClick={handleCreate}
      >
        {submitting ? '记录中...' : '确认记录'}
      </View>
    </View>
  );
}

// ── 病症卡片组件 ──────────────────────────────────────────────────
function EpisodeCard({
  episode,
  onDetail,
  onImprove,
  onResolve,
  onWorsen,
  onDelete,
}: {
  episode: IllnessEpisode;
  onDetail: () => void;
  onImprove?: () => void;
  onResolve?: () => void;
  onWorsen?: () => void;
  onDelete: () => void;
}) {
  const days = daysSince(episode.start_date);
  const pct = (episode.severity / 10) * 100;

  return (
    <View className="illness-card">
      <View className="card-top">
        <Text className="illness-name">{episode.name}</Text>
        <Text className={'status-badge ' + episode.status}>{STATUS_LABEL[episode.status]}</Text>
      </View>

      <View className="severity-bar-wrap">
        <View className="severity-label">
          <Text>严重程度</Text>
          <Text>{episode.severity}/10</Text>
        </View>
        <View className="severity-bar">
          <View className="severity-fill" style={`width:${pct}%`} />
        </View>
      </View>

      <Text className="card-meta">
        发作于 {episode.start_date}，已持续 {days} 天
        {episode.end_date ? `，痊愈：${episode.end_date}` : ''}
      </Text>

      <View className="card-actions">
        {episode.status !== 'resolved' && onImprove && (
          <View className="action-btn improve" onClick={onImprove}>好转</View>
        )}
        {episode.status !== 'resolved' && onResolve && (
          <View className="action-btn resolve" onClick={onResolve}>痊愈</View>
        )}
        {episode.status === 'improving' && onWorsen && (
          <View className="action-btn worsen" onClick={onWorsen}>加重</View>
        )}
        <View className="action-btn detail" onClick={onDetail}>详情</View>
        <View className="action-btn delete" onClick={onDelete}>删除</View>
      </View>
    </View>
  );
}
