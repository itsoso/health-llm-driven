'use client';

import { useState, useEffect, useCallback } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { useAuth } from '@/contexts/AuthContext';
import { pkChallengeApi, PKChallengeDetailData } from '@/services/api';

export default function ChallengeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const challengeId = Number(params.id);
  const isJustCreated = searchParams.get('created') === '1';
  const [challenge, setChallenge] = useState<PKChallengeDetailData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showGuide, setShowGuide] = useState(isJustCreated);
  const [copied, setCopied] = useState(false);

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

  const shareLink = typeof window !== 'undefined'
    ? `https://health.executor.life/friends/challenge/${challengeId}`
    : '';

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // 降级方案
      const input = document.createElement('input');
      input.value = shareLink;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
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

  const getTimeLeft = () => {
    if (!challenge) return '0';
    const end = new Date(challenge.end_date).getTime();
    const now = Date.now();
    const diffMs = Math.max(0, end - now);
    const diffMin = Math.ceil(diffMs / 60000);
    if (diffMin < 60) return `${diffMin}分钟`;
    const diffHours = Math.ceil(diffMs / 3600000);
    if (diffHours < 24) return `${diffHours}小时`;
    return `${Math.ceil(diffMs / 86400000)}天`;
  };

  const formatDuration = () => {
    if (!challenge) return '';
    const start = new Date(challenge.start_date).getTime();
    const end = new Date(challenge.end_date).getTime();
    const diffMin = Math.round((end - start) / 60000);
    if (diffMin < 60) return `${diffMin}分钟`;
    if (diffMin < 1440) return `${Math.round(diffMin / 60)}小时`;
    return `${Math.round(diffMin / 1440)}天`;
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
          <button onClick={() => router.push('/friends')} className="text-white/50 hover:text-white">
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

        {/* 创建成功指引 */}
        {showGuide && (
          <div className="bg-gradient-to-r from-green-600/20 to-emerald-600/20 border border-green-500/30 rounded-xl p-5 mb-6 relative">
            <button
              onClick={() => setShowGuide(false)}
              className="absolute top-3 right-3 text-white/30 hover:text-white text-sm"
            >
              &times;
            </button>
            <div className="text-lg font-bold text-green-400 mb-3">PK挑战创建成功!</div>
            <div className="space-y-2 text-sm text-white/70">
              <div className="flex items-start gap-2">
                <span className="text-green-400 font-bold mt-0.5">1</span>
                <span>挑战已开始计时，参与者的数据会自动统计</span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-green-400 font-bold mt-0.5">2</span>
                <span>
                  {challenge.challenge_type === 'checkin'
                    ? '每天完成打卡，系统自动记录成绩'
                    : '通过智能助理记录活动（如"我在学习"），系统自动计时'}
                </span>
              </div>
              <div className="flex items-start gap-2">
                <span className="text-green-400 font-bold mt-0.5">3</span>
                <span>挑战结束后按排名发放积分（第1名10分，第2名8分...）</span>
              </div>
            </div>
            <div className="mt-4 pt-3 border-t border-green-500/20">
              <div className="text-xs text-white/40 mb-2">分享链接给好友查看：</div>
              <div className="flex items-center gap-2">
                <div className="flex-1 bg-black/20 rounded-lg px-3 py-2 text-xs text-cyan-300 truncate">
                  {shareLink}
                </div>
                <button
                  onClick={handleCopyLink}
                  className={`px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap ${
                    copied ? 'bg-green-600 text-white' : 'bg-cyan-600 text-white'
                  }`}
                >
                  {copied ? '已复制' : '复制'}
                </button>
              </div>
            </div>
          </div>
        )}

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
            <span>{formatDuration()}</span>
            {challenge.status === 'active' && (
              <span className="text-cyan-400">剩余 {getTimeLeft()}</span>
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
                {challenge.status === 'completed' && p.points > 0 && (
                  <div className="text-xs text-cyan-400 mt-0.5">+{p.points}积分</div>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* 分享链接 */}
        {!showGuide && challenge.status === 'active' && (
          <div className="bg-white/5 rounded-xl p-4 mb-4">
            <div className="text-xs text-white/40 mb-2">分享挑战链接：</div>
            <div className="flex items-center gap-2">
              <div className="flex-1 bg-black/20 rounded-lg px-3 py-2 text-xs text-cyan-300 truncate">
                {shareLink}
              </div>
              <button
                onClick={handleCopyLink}
                className={`px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap ${
                  copied ? 'bg-green-600 text-white' : 'bg-cyan-600 text-white'
                }`}
              >
                {copied ? '已复制' : '复制'}
              </button>
            </div>
          </div>
        )}

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
