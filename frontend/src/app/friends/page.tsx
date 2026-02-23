'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import ProtectedRoute from '@/components/ProtectedRoute';
import {
  friendsApi, pkChallengeApi,
  FriendInfo, FriendRequestData, UserSearchResultData,
  PKChallengeData, PKStatsData,
} from '@/services/api';

type Tab = 'friends' | 'requests' | 'challenges';

export default function FriendsPage() {
  const [tab, setTab] = useState<Tab>('friends');
  const [friends, setFriends] = useState<FriendInfo[]>([]);
  const [pendingRequests, setPendingRequests] = useState<FriendRequestData[]>([]);
  const [challenges, setChallenges] = useState<PKChallengeData[]>([]);
  const [pkStats, setPkStats] = useState<PKStatsData | null>(null);
  const [loading, setLoading] = useState(true);

  // 搜索
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<UserSearchResultData[]>([]);
  const [searching, setSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);

  const loadFriends = useCallback(async () => {
    try {
      const [friendsRes, requestsRes] = await Promise.all([
        friendsApi.listFriends(),
        friendsApi.pendingRequests(),
      ]);
      setFriends(friendsRes.data);
      setPendingRequests(requestsRes.data);
    } catch (err) {
      console.error('加载好友列表失败', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadChallenges = useCallback(async () => {
    try {
      const [challengesRes, statsRes] = await Promise.all([
        pkChallengeApi.list(),
        pkChallengeApi.myStats(),
      ]);
      setChallenges(challengesRes.data);
      setPkStats(statsRes.data);
    } catch (err) {
      console.error('加载挑战失败', err);
    }
  }, []);

  useEffect(() => {
    loadFriends();
  }, [loadFriends]);

  useEffect(() => {
    if (tab === 'challenges') loadChallenges();
  }, [tab, loadChallenges]);

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    try {
      const res = await friendsApi.searchUsers(searchQuery.trim());
      setSearchResults(res.data);
    } catch (err) {
      console.error('搜索失败', err);
    } finally {
      setSearching(false);
    }
  };

  const handleSendRequest = async (userId: number) => {
    try {
      await friendsApi.sendRequest(userId);
      // 刷新搜索结果
      if (searchQuery.trim()) handleSearch();
      loadFriends();
    } catch (err: any) {
      alert(err.response?.data?.detail || '发送失败');
    }
  };

  const handleAccept = async (requestId: number) => {
    try {
      await friendsApi.acceptRequest(requestId);
      loadFriends();
    } catch (err) {
      console.error('接受失败', err);
    }
  };

  const handleReject = async (requestId: number) => {
    try {
      await friendsApi.rejectRequest(requestId);
      loadFriends();
    } catch (err) {
      console.error('拒绝失败', err);
    }
  };

  const handleRemoveFriend = async (friendshipId: number) => {
    if (!confirm('确定要删除这个好友吗？')) return;
    try {
      await friendsApi.removeFriend(friendshipId);
      loadFriends();
    } catch (err) {
      console.error('删除失败', err);
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

  const getChallengeTypeLabel = (type: string) => {
    return type === 'checkin' ? '打卡PK' : '学习时长PK';
  };

  const formatChallengeDuration = (startDate: string, endDate: string) => {
    const diffMin = Math.round((new Date(endDate).getTime() - new Date(startDate).getTime()) / 60000);
    if (diffMin < 60) return `${diffMin}分钟`;
    if (diffMin < 1440) return `${Math.round(diffMin / 60)}小时`;
    return `${Math.round(diffMin / 1440)}天`;
  };

  const getStatusBadge = (status: string) => {
    if (status === 'active') return { text: '进行中', cls: 'bg-green-500/20 text-green-400' };
    if (status === 'completed') return { text: '已结束', cls: 'bg-gray-500/20 text-gray-400' };
    return { text: '已取消', cls: 'bg-red-500/20 text-red-400' };
  };

  const formatScore = (score: number, metric: string) => {
    if (metric === 'total_minutes') {
      const h = Math.floor(score / 60);
      const m = Math.round(score % 60);
      if (h > 0 && m > 0) return `${h}h${m}m`;
      if (h > 0) return `${h}h`;
      return `${m}m`;
    }
    if (metric === 'completion_rate') return `${score}%`;
    return `${score}`;
  };

  return (
    <ProtectedRoute>
      <div className="min-h-screen bg-gradient-to-b from-gray-900 to-gray-800 text-white p-4 pb-24">
        <h1 className="text-xl font-bold mb-4">好友 & PK</h1>

        {/* Tab 切换 */}
        <div className="flex gap-2 mb-4">
          {([
            { key: 'friends' as Tab, label: '好友列表' },
            { key: 'requests' as Tab, label: `好友请求${pendingRequests.length > 0 ? ` (${pendingRequests.length})` : ''}` },
            { key: 'challenges' as Tab, label: 'PK挑战' },
          ]).map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 rounded-full text-sm ${
                tab === t.key ? 'bg-cyan-600 text-white' : 'bg-white/10 text-white/60'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div className="text-center text-white/50 py-8">加载中...</div>
        ) : (
          <>
            {/* 好友列表 */}
            {tab === 'friends' && (
              <div>
                {/* 搜索按钮 */}
                <button
                  onClick={() => setShowSearch(!showSearch)}
                  className="w-full bg-white/5 border border-dashed border-white/20 rounded-xl p-3 text-white/40 text-sm mb-4"
                >
                  + 搜索添加好友
                </button>

                {showSearch && (
                  <div className="bg-white/5 border border-white/10 rounded-xl p-4 mb-4">
                    <div className="flex gap-2 mb-3">
                      <input
                        type="text"
                        value={searchQuery}
                        onChange={e => setSearchQuery(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleSearch()}
                        placeholder="输入用户名搜索"
                        className="flex-1 bg-white/10 rounded-lg px-3 py-2 text-sm outline-none"
                      />
                      <button
                        onClick={handleSearch}
                        disabled={searching}
                        className="px-4 py-2 bg-cyan-600 rounded-lg text-sm"
                      >
                        {searching ? '...' : '搜索'}
                      </button>
                    </div>

                    {searchResults.length > 0 && (
                      <div className="space-y-2">
                        {searchResults.map(u => (
                          <div key={u.id} className="flex items-center justify-between bg-white/5 rounded-lg p-3">
                            <div className="flex items-center gap-3">
                              <div className="w-8 h-8 rounded-full bg-purple-500 flex items-center justify-center text-sm font-bold">
                                {u.name.charAt(0)}
                              </div>
                              <span className="text-sm">{u.name}</span>
                            </div>
                            {u.is_friend ? (
                              <span className="text-xs text-green-400">已是好友</span>
                            ) : u.request_pending ? (
                              <span className="text-xs text-yellow-400">请求中</span>
                            ) : (
                              <button
                                onClick={() => handleSendRequest(u.id)}
                                className="px-3 py-1 bg-cyan-600 rounded-lg text-xs"
                              >
                                添加
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {searchResults.length === 0 && searchQuery && !searching && (
                      <div className="text-center text-white/40 text-sm py-2">未找到用户</div>
                    )}
                  </div>
                )}

                {/* 好友列表 */}
                {friends.length > 0 ? (
                  <div className="space-y-2">
                    {friends.map(f => (
                      <div key={f.friendship_id} className="flex items-center justify-between bg-white/5 rounded-xl p-4">
                        <div className="flex items-center gap-3">
                          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-purple-500 to-purple-700 flex items-center justify-center text-sm font-bold">
                            {f.name.charAt(0)}
                          </div>
                          <div>
                            <div className="font-medium">{f.name}</div>
                            <div className="text-xs text-white/40">
                              好友 · {new Date(f.since).toLocaleDateString('zh-CN')}
                            </div>
                          </div>
                        </div>
                        <button
                          onClick={() => handleRemoveFriend(f.friendship_id)}
                          className="text-xs text-red-400/60 hover:text-red-400"
                        >
                          删除
                        </button>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center text-white/40 py-8">
                    还没有好友，搜索添加吧
                  </div>
                )}
              </div>
            )}

            {/* 好友请求 */}
            {tab === 'requests' && (
              <div>
                {pendingRequests.length > 0 ? (
                  <div className="space-y-2">
                    {pendingRequests.map(r => (
                      <div key={r.id} className="bg-white/5 rounded-xl p-4">
                        <div className="flex items-center gap-3 mb-3">
                          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-cyan-500 to-blue-700 flex items-center justify-center text-sm font-bold">
                            {(r.user_name || '?').charAt(0)}
                          </div>
                          <div>
                            <div className="font-medium">{r.user_name || '未知用户'}</div>
                            {r.message && <div className="text-xs text-white/50">{r.message}</div>}
                            <div className="text-xs text-white/30">
                              {new Date(r.created_at).toLocaleDateString('zh-CN')}
                            </div>
                          </div>
                        </div>
                        <div className="flex gap-2">
                          <button
                            onClick={() => handleAccept(r.id)}
                            className="flex-1 py-2 bg-cyan-600 rounded-lg text-sm"
                          >
                            接受
                          </button>
                          <button
                            onClick={() => handleReject(r.id)}
                            className="flex-1 py-2 bg-white/10 rounded-lg text-sm"
                          >
                            拒绝
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center text-white/40 py-8">没有待处理的好友请求</div>
                )}
              </div>
            )}

            {/* PK挑战 */}
            {tab === 'challenges' && (
              <div>
                {/* 统计卡片 */}
                {pkStats && (
                  <div className="grid grid-cols-4 gap-3 mb-4">
                    <div className="bg-white/5 rounded-xl p-3 text-center">
                      <div className="text-2xl font-bold">{pkStats.total_challenges}</div>
                      <div className="text-xs text-white/40">总挑战</div>
                    </div>
                    <div className="bg-white/5 rounded-xl p-3 text-center">
                      <div className="text-2xl font-bold text-yellow-400">{pkStats.wins}</div>
                      <div className="text-xs text-white/40">获胜</div>
                    </div>
                    <div className="bg-white/5 rounded-xl p-3 text-center">
                      <div className="text-2xl font-bold text-green-400">{pkStats.active_challenges}</div>
                      <div className="text-xs text-white/40">进行中</div>
                    </div>
                    <div className="bg-white/5 rounded-xl p-3 text-center">
                      <div className="text-2xl font-bold text-cyan-400">{pkStats.total_points}</div>
                      <div className="text-xs text-white/40">积分</div>
                    </div>
                  </div>
                )}

                {/* 发起挑战入口 */}
                <Link
                  href="/friends/new-challenge"
                  className="block w-full bg-gradient-to-r from-cyan-600/30 to-blue-600/30 border border-cyan-500/30 rounded-xl p-4 text-center mb-4"
                >
                  <span className="text-lg">&#9876;</span>
                  <span className="ml-2 font-medium">发起新挑战</span>
                </Link>

                {/* PK玩法指引 */}
                {challenges.length === 0 && (
                  <div className="bg-white/5 border border-white/10 rounded-xl p-4 mb-4">
                    <div className="text-sm font-medium text-white/70 mb-2">PK挑战玩法</div>
                    <div className="space-y-2 text-xs text-white/50">
                      <div className="flex items-start gap-2">
                        <span className="text-cyan-400 font-bold">1.</span>
                        <span>先在「好友列表」添加好友</span>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="text-cyan-400 font-bold">2.</span>
                        <span>点击「发起新挑战」，选择打卡PK或活动时长PK</span>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="text-cyan-400 font-bold">3.</span>
                        <span>挑战期间正常打卡或记录活动，系统自动统计</span>
                      </div>
                      <div className="flex items-start gap-2">
                        <span className="text-cyan-400 font-bold">4.</span>
                        <span>挑战结束按排名发放积分，第1名10分、第2名8分...</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* 挑战列表 */}
                {challenges.length > 0 ? (
                  <div className="space-y-3">
                    {challenges.map(c => {
                      const badge = getStatusBadge(c.status);
                      return (
                        <Link
                          key={c.id}
                          href={`/friends/challenge/${c.id}`}
                          className="block bg-white/5 rounded-xl p-4 hover:bg-white/10 transition-colors"
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="font-medium">{c.title}</div>
                            <span className={`px-2 py-0.5 rounded-full text-xs ${badge.cls}`}>
                              {badge.text}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 text-xs text-white/50 mb-2">
                            <span>{getChallengeTypeLabel(c.challenge_type)}</span>
                            <span>·</span>
                            <span>{getMetricLabel(c.metric)}</span>
                            <span>·</span>
                            <span>{formatChallengeDuration(c.start_date, c.end_date)}</span>
                          </div>
                          {/* 参与者头像 */}
                          <div className="flex items-center gap-1">
                            {c.participants.slice(0, 5).map((p) => (
                              <div
                                key={p.user_id}
                                className="w-7 h-7 rounded-full bg-purple-500/60 flex items-center justify-center text-xs font-bold border border-gray-800"
                                title={p.user_name}
                              >
                                {p.user_name.charAt(0)}
                              </div>
                            ))}
                            {c.participants.length > 5 && (
                              <span className="text-xs text-white/40 ml-1">+{c.participants.length - 5}</span>
                            )}
                          </div>
                        </Link>
                      );
                    })}
                  </div>
                ) : (
                  <div className="text-center text-white/40 py-8">
                    还没有PK挑战，邀请好友一起来吧
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </ProtectedRoute>
  );
}
