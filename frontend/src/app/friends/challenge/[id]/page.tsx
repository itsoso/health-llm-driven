'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { useAuth } from '@/contexts/AuthContext';
import { pkChallengeApi, PKChallengeDetailData } from '@/services/api';

export default function ChallengeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const challengeId = Number(params.id);
  const [challenge, setChallenge] = useState<PKChallengeDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadChallenge = useCallback(async () => {
    try {
      const res = await pkChallengeApi.getDetail(challengeId);
      setChallenge(res.data);
    } catch (err) {
      console.error('加载挑战失败', err);
    } finally {
      setLoading(false);
    }
  }, [challengeId]);

  useEffect(() => {
    loadChallenge();
  }, [loadChallenge]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const res = await pkChallengeApi.refresh(challengeId);
      setChallenge(res.data);
    } catch (err) {
      console.error('刷新失败', err);
    } finally {
      setRefreshing(false);
    }
  };

  const handleCancel = async () => {
    if (!confirm('确定要取消这个挑战吗？')) return;
    try {
      await pkChallengeApi.cancel(challengeId);
      router.push('/friends?tab=challenges');
    } catch (err: any) {
      alert(err.response?.data?.detail || '取消失败');
    }
  };

  const getMetricLabel = (metric: string) => {
    const map: Record<string, string> = {
      total_minutes: '总时长',
      streak: '连续天数',
      completion_rate: '完成率',
      count: '次数',
    };
    return map[metric] || metric;
  };

  const getMetricUnit = (metric: string) => {
    const map: Record<string, string> = {
      total_minutes: '分钟',
      streak: '天',
      completion_rate: '%',
      count: '次',
    };
    return map[metric] || '';
  };

  const getRankEmoji = (rank: number | null) => {
    if (rank === 1) return '🥇';
    if (rank === 2) return '🥈';
    if (rank === 3) return '🥉';
    return `#${rank}`;
  };

  const getDaysLeft = () => {
    if (!challenge) return 0;
    const end = new Date(challenge.end_date).getTime();
    const now = Date.now();
    return Math.max(0, Math.ceil((end - now) / 86400000));
  };

  const getProgress = () => {
    if (!challenge) return 0;
    const start = new Date(challenge.start_date).getTime();
    const end = new Date(challenge.end_date).getTime();
    const now = Date.now();
    return Math.min(100, Math.max(0, ((now - start) / (end - start)) * 100));
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

  if (!challenge) {
    return (
      <ProtectedRoute>
        <div className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white p-4 flex items-center justify-center">
          <div className="text-white/50">挑战不存在</div>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white p-4 pb-24">
        {/* 顶部 */}
        <div className="flex items-center gap-3 mb-6">
          <button onClick={() => router.back()} className="text-white/50 hover:text-white">
            &larr;
          </button>
          <h1 className="text-xl font-bold flex-1">{challenge.title}</h1>
          {challenge.status === 'active' && (
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="px-3 py-1 bg-white/10 rounded-lg text-sm"
            >
              {refreshing ? '...' : '刷新'}
            </button>
          )}
        </div>

        {/* 挑战信息卡 */}
        <div className="bg-gradient-to-r from-cyan-600/20 to-blue-600/20 border border-cyan-500/30 rounded-xl p-5 mb-6">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm text-white/50">
              {challenge.challenge_type === 'checkin' ? '打卡PK' : '活动时长PK'}
              {' · '}
              {getMetricLabel(challenge.metric)}
            </div>
            <span className={`px-2 py-0.5 rounded-full text-xs ${
              challenge.status === 'active' ? 'bg-green-500/20 text-green-400' :
              challenge.status === 'completed' ? 'bg-gray-500/20 text-gray-400' :
              'bg-red-500/20 text-red-400'
            }`}>
              {challenge.status === 'active' ? '进行中' : challenge.status === 'completed' ? '已结束' : '已取消'}
            </span>
          </div>

          {challenge.checkin_template_name && (
            <div className="text-sm text-white/60 mb-2">
              打卡项: {challenge.checkin_template_name}
            </div>
          )}
          {challenge.activity_category && (
            <div className="text-sm text-white/60 mb-2">
              活动分类: {challenge.activity_category === 'studying' ? '📚 学习' :
                challenge.activity_category === 'working' ? '💼 工作' :
                challenge.activity_category === 'exercising' ? '🏃 运动' : '🎮 娱乐'}
            </div>
          )}

          <div className="flex items-center gap-4 text-xs text-white/40 mb-3">
            <span>创建: {challenge.creator_name}</span>
            <span>{challenge.duration_days}天</span>
            {challenge.status === 'active' && (
              <span className="text-cyan-400">剩余 {getDaysLeft()} 天</span>
            )}
          </div>

          {/* 进度条 */}
          {challenge.status === 'active' && (
            <div className="bg-white/10 rounded-full h-2 overflow-hidden">
              <div
                className="h-full rounded-full bg-cyan-400 transition-all"
                style={{ width: `${getProgress()}%` }}
              />
            </div>
          )}
        </div>

        {/* 排行榜 */}
        <h2 className="text-sm text-white/50 mb-3">排行榜</h2>
        <div className="space-y-2 mb-6">
          {challenge.leaderboard.map((p, i) => (
            <div
              key={p.user_id}
              className={`flex items-center gap-3 rounded-xl p-4 ${
                i === 0 ? 'bg-gradient-to-r from-yellow-600/20 to-orange-600/20 border border-yellow-500/20' : 'bg-white/5'
              }`}
            >
              <div className="text-xl w-8 text-center">
                {getRankEmoji(p.rank)}
              </div>
              <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-purple-700 flex items-center justify-center text-sm font-bold">
                {p.user_name.charAt(0)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="font-medium truncate">{p.user_name}</div>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold">
                  {challenge.metric === 'total_minutes'
                    ? `${Math.floor(p.score / 60)}h${Math.round(p.score % 60)}m`
                    : challenge.metric === 'completion_rate'
                    ? `${p.score}%`
                    : p.score
                  }
                </div>
                <div className="text-xs text-white/40">{getMetricUnit(challenge.metric)}</div>
              </div>
            </div>
          ))}
        </div>

        {/* 操作按钮 - 仅创建者可取消 */}
        {challenge.status === 'active' && user?.id === challenge.creator_id && (
          <button
            onClick={handleCancel}
            className="w-full py-3 bg-red-500/10 text-red-400 rounded-xl text-sm"
          >
            取消挑战
          </button>
        )}
      </div>
    </ProtectedRoute>
  );
}
