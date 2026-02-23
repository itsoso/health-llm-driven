'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { friendsApi, pkChallengeApi, FriendInfo } from '@/services/api';
import { api } from '@/services/api';

interface CheckinTemplateOption {
  id: number;
  name: string;
  icon: string;
  category: string;
}

const ACTIVITY_CATEGORIES = [
  { value: 'studying', label: '学习', emoji: '📚' },
  { value: 'working', label: '工作', emoji: '💼' },
  { value: 'exercising', label: '运动', emoji: '🏃' },
  { value: 'entertainment', label: '娱乐', emoji: '🎮' },
];

const METRICS = [
  { value: 'total_minutes', label: '总时长' },
  { value: 'count', label: '次数' },
  { value: 'streak', label: '连续天数' },
  { value: 'completion_rate', label: '完成率' },
];

const DURATION_OPTIONS = [
  { minutes: 5, label: '5分钟' },
  { minutes: 10, label: '10分钟' },
  { minutes: 15, label: '15分钟' },
  { minutes: 30, label: '30分钟' },
  { minutes: 60, label: '1小时' },
  { minutes: 120, label: '2小时' },
  { minutes: 180, label: '3小时' },
  { minutes: 240, label: '4小时' },
  { minutes: 480, label: '8小时' },
  { minutes: 1440, label: '1天' },
  { minutes: 4320, label: '3天' },
  { minutes: 10080, label: '7天' },
  { minutes: 20160, label: '14天' },
  { minutes: 43200, label: '30天' },
];

export default function NewChallengePage() {
  const router = useRouter();
  const [friends, setFriends] = useState<FriendInfo[]>([]);
  const [templates, setTemplates] = useState<CheckinTemplateOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // 表单状态
  const [title, setTitle] = useState('');
  const [challengeType, setChallengeType] = useState<'checkin' | 'study_time'>('study_time');
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [activityCategory, setActivityCategory] = useState('studying');
  const [metric, setMetric] = useState('total_minutes');
  const [durationMinutes, setDurationMinutes] = useState(10080); // 默认7天
  const [selectedFriends, setSelectedFriends] = useState<number[]>([]);

  useEffect(() => {
    const loadData = async () => {
      try {
        const [friendsRes, templatesRes] = await Promise.all([
          friendsApi.listFriends(),
          api.get<{ templates: CheckinTemplateOption[]; total: number }>('/checkin/templates'),
        ]);
        setFriends(friendsRes.data);
        setTemplates(templatesRes.data.templates || []);
      } catch (err) {
        console.error('加载数据失败', err);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  const toggleFriend = (id: number) => {
    setSelectedFriends(prev =>
      prev.includes(id) ? prev.filter(f => f !== id) : [...prev, id]
    );
  };

  const handleSubmit = async () => {
    if (!title.trim()) {
      alert('请输入挑战标题');
      return;
    }
    if (selectedFriends.length === 0) {
      alert('请至少选择一位好友');
      return;
    }
    if (challengeType === 'checkin' && !templateId) {
      alert('请选择打卡模板');
      return;
    }

    setSubmitting(true);
    try {
      const res = await pkChallengeApi.create({
        title: title.trim(),
        challenge_type: challengeType,
        checkin_template_id: challengeType === 'checkin' ? templateId! : undefined,
        activity_category: challengeType === 'study_time' ? activityCategory : undefined,
        metric,
        duration_minutes: durationMinutes,
        friend_ids: selectedFriends,
      });
      router.push(`/friends/challenge/${res.data.id}?created=1`);
    } catch (err: any) {
      alert(err.response?.data?.detail || '创建失败');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <ProtectedRoute>
        <div className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white p-4 flex items-center justify-center">
          <div className="text-white/50">加载中...</div>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white p-4 pb-24">
        <div className="flex items-center gap-3 mb-6">
          <button onClick={() => router.back()} className="text-white/50 hover:text-white">
            &larr;
          </button>
          <h1 className="text-xl font-bold">发起PK挑战</h1>
        </div>

        <div className="space-y-6">
          {/* 挑战标题 */}
          <div>
            <label className="text-sm text-white/50 mb-2 block">挑战标题</label>
            <input
              type="text"
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder="例如：7天学习时长PK"
              className="w-full bg-white/10 rounded-xl px-4 py-3 text-sm outline-none"
              maxLength={100}
            />
          </div>

          {/* 挑战类型 */}
          <div>
            <label className="text-sm text-white/50 mb-2 block">挑战类型</label>
            <div className="flex gap-3">
              <button
                onClick={() => { setChallengeType('study_time'); setMetric('total_minutes'); }}
                className={`flex-1 py-3 rounded-xl text-sm text-center ${
                  challengeType === 'study_time' ? 'bg-cyan-600' : 'bg-white/10'
                }`}
              >
                📚 活动时长PK
              </button>
              <button
                onClick={() => { setChallengeType('checkin'); setMetric('count'); }}
                className={`flex-1 py-3 rounded-xl text-sm text-center ${
                  challengeType === 'checkin' ? 'bg-cyan-600' : 'bg-white/10'
                }`}
              >
                &#10003; 打卡PK
              </button>
            </div>
          </div>

          {/* 活动分类（study_time类型） */}
          {challengeType === 'study_time' && (
            <div>
              <label className="text-sm text-white/50 mb-2 block">活动分类</label>
              <div className="grid grid-cols-2 gap-2">
                {ACTIVITY_CATEGORIES.map(cat => (
                  <button
                    key={cat.value}
                    onClick={() => setActivityCategory(cat.value)}
                    className={`py-3 rounded-xl text-sm text-center ${
                      activityCategory === cat.value ? 'bg-cyan-600' : 'bg-white/10'
                    }`}
                  >
                    {cat.emoji} {cat.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 打卡模板（checkin类型） */}
          {challengeType === 'checkin' && (
            <div>
              <label className="text-sm text-white/50 mb-2 block">打卡项目</label>
              <div className="grid grid-cols-2 gap-2 max-h-48 overflow-y-auto">
                {templates.map(t => (
                  <button
                    key={t.id}
                    onClick={() => setTemplateId(t.id)}
                    className={`py-3 px-3 rounded-xl text-sm text-left ${
                      templateId === t.id ? 'bg-cyan-600' : 'bg-white/10'
                    }`}
                  >
                    {t.icon} {t.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 比拼指标 */}
          <div>
            <label className="text-sm text-white/50 mb-2 block">比拼指标</label>
            <div className="flex gap-2 flex-wrap">
              {METRICS.filter(m => {
                if (challengeType === 'study_time') return ['total_minutes', 'count'].includes(m.value);
                return true;
              }).map(m => (
                <button
                  key={m.value}
                  onClick={() => setMetric(m.value)}
                  className={`px-4 py-2 rounded-full text-sm ${
                    metric === m.value ? 'bg-cyan-600' : 'bg-white/10'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {/* PK时长 */}
          <div>
            <label className="text-sm text-white/50 mb-2 block">PK时长</label>
            <select
              value={durationMinutes}
              onChange={e => setDurationMinutes(Number(e.target.value))}
              className="w-full bg-white/10 rounded-xl px-4 py-3 text-sm outline-none appearance-none cursor-pointer"
            >
              {DURATION_OPTIONS.map(d => (
                <option key={d.minutes} value={d.minutes} className="bg-gray-800 text-white">
                  {d.label}
                </option>
              ))}
            </select>
          </div>

          {/* 选择好友 */}
          <div>
            <label className="text-sm text-white/50 mb-2 block">邀请好友 ({selectedFriends.length}人已选)</label>
            {friends.length > 0 ? (
              <div className="space-y-2 max-h-48 overflow-y-auto">
                {friends.map(f => (
                  <button
                    key={f.user_id}
                    onClick={() => toggleFriend(f.user_id)}
                    className={`w-full flex items-center gap-3 p-3 rounded-xl text-left ${
                      selectedFriends.includes(f.user_id) ? 'bg-cyan-600/30 border border-cyan-500/30' : 'bg-white/5'
                    }`}
                  >
                    <div className="w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center text-sm font-bold">
                      {f.name.charAt(0)}
                    </div>
                    <span className="text-sm">{f.name}</span>
                    {selectedFriends.includes(f.user_id) && (
                      <span className="ml-auto text-cyan-400">&#10003;</span>
                    )}
                  </button>
                ))}
              </div>
            ) : (
              <div className="text-center text-white/40 text-sm py-4">
                还没有好友，先去添加好友吧
              </div>
            )}
          </div>

          {/* 提交 */}
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="w-full py-4 bg-gradient-to-r from-cyan-600 to-blue-600 rounded-xl font-medium disabled:opacity-50"
          >
            {submitting ? '创建中...' : '发起挑战'}
          </button>
        </div>
      </div>
    </ProtectedRoute>
  );
}
