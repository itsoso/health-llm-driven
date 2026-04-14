'use client';

import { useState, useEffect, useCallback } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import ProtectedRoute from '@/components/ProtectedRoute';
import { friendsApi, pkChallengeApi, dmApi, groupApi, FriendInfo, FriendRequestData, UserSearchResultData, PKChallengeData, PKStatsData, GroupListItem } from '@/services/api/social';

type Tab = 'friends' | 'requests' | 'challenges' | 'groups';

export default function FriendsPage() {
  const pathname = usePathname();
  const router = useRouter();
  const isKids = pathname?.startsWith('/kids');
  const [tab, setTab] = useState<Tab>('friends');
  const [friends, setFriends] = useState<FriendInfo[]>([]);
  const [pendingRequests, setPendingRequests] = useState<FriendRequestData[]>([]);
  const [challenges, setChallenges] = useState<PKChallengeData[]>([]);
  const [pkStats, setPkStats] = useState<PKStatsData | null>(null);
  const [groups, setGroups] = useState<GroupListItem[]>([]);
  const [loading, setLoading] = useState(true);

  // 创建群聊状态
  const [showCreateGroup, setShowCreateGroup] = useState(false);
  const [newGroupName, setNewGroupName] = useState('');
  const [selectedMembers, setSelectedMembers] = useState<number[]>([]);
  const [creatingGroup, setCreatingGroup] = useState(false);

  const [unreadMap, setUnreadMap] = useState<Record<number, number>>({});

  // 搜索
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<UserSearchResultData[]>([]);
  const [searching, setSearching] = useState(false);
  const [showSearch, setShowSearch] = useState(false);

  const loadFriends = useCallback(async () => {
    try {
      const [friendsRes, requestsRes, convRes] = await Promise.all([
        friendsApi.listFriends(),
        friendsApi.pendingRequests(),
        dmApi.getConversations().catch(() => ({ data: [] })),
      ]);
      setFriends(friendsRes.data);
      setPendingRequests(requestsRes.data);
      // Build unread map from conversations
      const uMap: Record<number, number> = {};
      for (const c of convRes.data) {
        if (c.unread_count > 0) uMap[c.friend_id] = c.unread_count;
      }
      setUnreadMap(uMap);
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
    if (tab === 'groups') loadGroups();
  }, [tab, loadChallenges]);

  const loadGroups = async () => {
    try {
      const res = await groupApi.list();
      setGroups(res.data);
    } catch (err) {
      console.error('加载群聊失败', err);
    }
  };

  const handleCreateGroup = async () => {
    if (!newGroupName.trim() || selectedMembers.length === 0) return;
    setCreatingGroup(true);
    try {
      await groupApi.create(newGroupName.trim(), selectedMembers);
      setShowCreateGroup(false);
      setNewGroupName('');
      setSelectedMembers([]);
      loadGroups();
    } catch (e: any) {
      alert(e?.response?.data?.detail || '创建失败');
    } finally {
      setCreatingGroup(false);
    }
  };

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
        <div className="flex gap-2 mb-4 overflow-x-auto pb-1">
          {([
            { key: 'friends' as Tab, label: '好友列表' },
            { key: 'requests' as Tab, label: `请求${pendingRequests.length > 0 ? `(${pendingRequests.length})` : ''}` },
            { key: 'groups' as Tab, label: '群聊' },
            { key: 'challenges' as Tab, label: 'PK挑战' },
          ]).map(t => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-2 rounded-full text-sm whitespace-nowrap flex-shrink-0 ${
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
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => router.push(isKids ? `/kids/chat/${f.user_id}` : `/friends/chat/${f.user_id}`)}
                            className="relative px-3 py-1.5 bg-cyan-600/30 hover:bg-cyan-600/50 rounded-lg text-sm transition-colors"
                          >
                            💬
                            {unreadMap[f.user_id] > 0 && (
                              <span className="absolute -top-1 -right-1 w-4 h-4 bg-red-500 rounded-full text-[10px] text-white flex items-center justify-center font-bold">
                                {unreadMap[f.user_id] > 9 ? '9+' : unreadMap[f.user_id]}
                              </span>
                            )}
                          </button>
                          <button
                            onClick={() => handleRemoveFriend(f.friendship_id)}
                            className="text-xs text-red-400/60 hover:text-red-400"
                          >
                            删除
                          </button>
                        </div>
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

            {/* 群聊 Tab */}
            {tab === 'groups' && (
              <div>
                {/* 创建群聊按钮 */}
                <button
                  onClick={() => setShowCreateGroup(!showCreateGroup)}
                  className="w-full bg-white/5 border border-dashed border-white/20 rounded-xl p-3 text-white/40 text-sm mb-4"
                >
                  + 创建新群聊
                </button>

                {/* 创建群聊表单 */}
                {showCreateGroup && (
                  <div className="bg-white/5 border border-white/10 rounded-xl p-4 mb-4 space-y-3">
                    <input
                      type="text"
                      value={newGroupName}
                      onChange={e => setNewGroupName(e.target.value)}
                      placeholder="群聊名称"
                      maxLength={50}
                      className="w-full bg-white/10 rounded-lg px-3 py-2 text-sm outline-none text-white placeholder-white/30"
                    />
                    <div>
                      <p className="text-xs text-white/40 mb-2">选择好友加入群聊（至少1位）</p>
                      <div className="space-y-1.5 max-h-48 overflow-y-auto">
                        {friends.map(f => (
                          <label key={f.user_id} className="flex items-center gap-3 cursor-pointer bg-white/5 rounded-lg px-3 py-2">
                            <input
                              type="checkbox"
                              checked={selectedMembers.includes(f.user_id)}
                              onChange={e => {
                                setSelectedMembers(prev =>
                                  e.target.checked ? [...prev, f.user_id] : prev.filter(id => id !== f.user_id)
                                );
                              }}
                              className="w-4 h-4 accent-cyan-500"
                            />
                            <div className="w-7 h-7 rounded-full bg-purple-500 flex items-center justify-center text-xs font-bold">
                              {f.name.charAt(0)}
                            </div>
                            <span className="text-sm">{f.name}</span>
                          </label>
                        ))}
                      </div>
                    </div>
                    <button
                      onClick={handleCreateGroup}
                      disabled={!newGroupName.trim() || selectedMembers.length === 0 || creatingGroup}
                      className="w-full py-2 bg-cyan-600 disabled:opacity-40 rounded-lg text-sm font-medium"
                    >
                      {creatingGroup ? '创建中...' : `创建群聊（${selectedMembers.length + 1}人）`}
                    </button>
                  </div>
                )}

                {/* 群聊列表 */}
                {groups.length > 0 ? (
                  <div className="space-y-2">
                    {groups.map(g => (
                      <button
                        key={g.id}
                        onClick={() => router.push(isKids ? `/kids/group/${g.id}` : `/friends/group/${g.id}`)}
                        className="w-full flex items-center gap-3 bg-white/5 rounded-xl p-4 text-left hover:bg-white/10 transition-colors"
                      >
                        <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-lg font-bold flex-shrink-0">
                          {g.name.charAt(0)}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-white truncate">{g.name}</div>
                          <div className="text-xs text-white/40 truncate">
                            {g.last_message || '暂无消息'} · {g.member_count}人
                          </div>
                        </div>
                        {g.last_message_at && (
                          <div className="text-[10px] text-white/30 flex-shrink-0">
                            {new Date(g.last_message_at).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })}
                          </div>
                        )}
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="text-center text-white/40 py-8">还没有群聊，快去创建一个吧</div>
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
