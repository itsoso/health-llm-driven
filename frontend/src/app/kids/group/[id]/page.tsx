'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useKidsTheme } from '@/contexts/KidsThemeContext';
import { groupApi, GroupMsgData, GroupMemberInfo } from '@/services/api/social';

const AVATAR_EMOJIS = ['🐶', '🐱', '🐭', '🐹', '🐰', '🦊', '🐻', '🐼', '🐨', '🦁', '🐯', '🐸'];
const getEmoji = (id: number) => AVATAR_EMOJIS[id % AVATAR_EMOJIS.length];

const avatarBgs = [
  'from-blue-400 to-blue-500',
  'from-purple-400 to-purple-500',
  'from-green-400 to-green-500',
  'from-rose-400 to-rose-500',
  'from-amber-400 to-amber-500',
  'from-teal-400 to-teal-500',
  'from-indigo-400 to-indigo-500',
  'from-orange-400 to-orange-500',
];
const getAvatarBg = (id: number) => avatarBgs[id % avatarBgs.length];

export default function KidsGroupChatPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const { theme } = useKidsTheme();
  const groupId = Number(params.id);

  const [messages, setMessages] = useState<GroupMsgData[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [groupName, setGroupName] = useState('群聊');
  const [members, setMembers] = useState<GroupMemberInfo[]>([]);
  const [myRole, setMyRole] = useState<'owner' | 'member'>('member');
  const [showMembers, setShowMembers] = useState(false);
  const [confirmLeave, setConfirmLeave] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const latestIdRef = useRef<number>(0);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // 初始加载
  useEffect(() => {
    if (!user || !groupId) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        const [detailRes, msgRes] = await Promise.all([
          groupApi.getDetail(groupId),
          groupApi.getMessages(groupId),
        ]);
        if (cancelled) return;
        setGroupName(detailRes.data.name);
        setMembers(detailRes.data.members);
        const me = detailRes.data.members.find((m: GroupMemberInfo) => m.user_id === user.id);
        if (me) setMyRole(me.role as 'owner' | 'member');
        setMessages(msgRes.data.messages);
        setHasMore(msgRes.data.has_more);
        if (msgRes.data.messages.length > 0) {
          latestIdRef.current = msgRes.data.messages[msgRes.data.messages.length - 1].id;
        }
      } catch {
        router.back();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [user, groupId, router]);

  useEffect(() => {
    if (!loading) setTimeout(scrollToBottom, 100);
  }, [loading, scrollToBottom]);

  // 轮询新消息
  useEffect(() => {
    if (loading || !user) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await groupApi.getMessages(groupId);
        const newMsgs = res.data.messages;
        if (newMsgs.length > 0 && newMsgs[newMsgs.length - 1].id > latestIdRef.current) {
          latestIdRef.current = newMsgs[newMsgs.length - 1].id;
          setMessages(newMsgs);
          scrollToBottom();
        }
      } catch {}
    }, 4000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loading, user, groupId, scrollToBottom]);

  const handleSend = async () => {
    if (!input.trim() || sending) return;
    const content = input.trim();
    setInput('');
    setSending(true);
    try {
      const res = await groupApi.sendMessage(groupId, content);
      setMessages(prev => [...prev, res.data]);
      latestIdRef.current = res.data.id;
      scrollToBottom();
    } catch {
      setInput(content);
    } finally {
      setSending(false);
    }
  };

  const handleLoadMore = async () => {
    const firstId = messages[0]?.id;
    const res = await groupApi.getMessages(groupId, firstId);
    setMessages(prev => [...res.data.messages, ...prev]);
    setHasMore(res.data.has_more);
  };

  const handleLeave = async () => {
    try {
      if (myRole === 'owner') {
        await groupApi.dissolve(groupId);
      } else {
        await groupApi.leave(groupId);
      }
      router.push('/kids/friends');
    } catch (e: any) {
      alert(e?.response?.data?.detail || '操作失败');
    }
  };

  const handleRemoveMember = async (uid: number) => {
    try {
      await groupApi.removeMember(groupId, uid);
      setMembers(prev => prev.filter(m => m.user_id !== uid));
    } catch {}
  };

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const bjFormatter = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' });
    const isToday = bjFormatter.format(d) === bjFormatter.format(now);
    const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' });
    if (isToday) return time;
    const dateStr = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric' }).format(d);
    return `${dateStr} ${time}`;
  };

  const shouldShowTime = (idx: number) => {
    if (idx === 0) return true;
    const prev = new Date(messages[idx - 1].created_at).getTime();
    const curr = new Date(messages[idx].created_at).getTime();
    return curr - prev > 5 * 60 * 1000;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-5xl mb-3 animate-bounce">💬</div>
          <p className="text-gray-500 text-lg">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* 顶栏 */}
      <div className={`px-4 py-3 bg-white/70 backdrop-blur-sm border-b-2 ${theme.navBorder} flex-shrink-0`}>
        <div className="flex items-center gap-3 max-w-2xl mx-auto">
          <button
            onClick={() => router.back()}
            className="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center text-gray-500 text-xl active:scale-90 transition-all"
          >
            ‹
          </button>

          {/* 群头像 + 名称 */}
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className={`w-10 h-10 rounded-2xl bg-gradient-to-br ${theme.btnGrad} flex items-center justify-center text-xl flex-shrink-0 shadow-sm`}>
              👥
            </div>
            <div className="min-w-0">
              <h1 className={`text-base font-bold ${theme.accent} truncate`}>{groupName}</h1>
              <p className="text-xs text-gray-400">{members.length} 人</p>
            </div>
          </div>

          {/* 成员按钮 */}
          <button
            onClick={() => setShowMembers(true)}
            className={`w-9 h-9 rounded-full bg-gradient-to-br ${theme.btnGrad} flex items-center justify-center text-white text-sm active:scale-90 transition-all shadow-sm`}
          >
            👤
          </button>
        </div>
      </div>

      {/* 消息列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-3">
        <div className="max-w-2xl mx-auto">
          {hasMore && (
            <button
              onClick={handleLoadMore}
              className="w-full text-center text-sm text-gray-400 py-2 mb-2 active:text-gray-600"
            >
              📜 加载更早的消息
            </button>
          )}

          {messages.length === 0 && (
            <div className="text-center py-16">
              <div className="text-6xl mb-3">🎉</div>
              <p className="text-gray-400">群聊刚创建，快来发第一条消息吧！</p>
            </div>
          )}

          {messages.map((msg, idx) => {
            const isMe = msg.sender_id === user?.id;
            const showSenderName = !isMe && (idx === 0 || messages[idx - 1].sender_id !== msg.sender_id);

            return (
              <div key={msg.id}>
                {/* 时间戳 */}
                {shouldShowTime(idx) && (
                  <div className="text-center text-xs text-gray-400 my-3">
                    {formatTime(msg.created_at)}
                  </div>
                )}

                {/* 消息行 */}
                <div className={`flex mb-2 ${isMe ? 'justify-end' : 'justify-start'}`}>
                  {/* 他人：左侧头像 */}
                  {!isMe && (
                    <div className="flex flex-col items-center mr-2 flex-shrink-0 mt-1">
                      <div className={`w-9 h-9 rounded-full bg-gradient-to-br ${getAvatarBg(msg.sender_id)} flex items-center justify-center text-lg shadow-sm`}>
                        {getEmoji(msg.sender_id)}
                      </div>
                      {showSenderName && (
                        <span className="text-[10px] text-gray-400 mt-0.5 max-w-[52px] truncate text-center">
                          {msg.sender_name}
                        </span>
                      )}
                    </div>
                  )}

                  {/* 气泡 */}
                  <div className={`max-w-[68%] flex flex-col ${isMe ? 'items-end' : 'items-start'}`}>
                    {showSenderName && !isMe && (
                      <span className="text-xs text-gray-400 mb-1 px-1">{msg.sender_name}</span>
                    )}
                    <div
                      className={`px-4 py-2.5 rounded-2xl text-sm leading-relaxed break-words shadow-sm ${
                        isMe
                          ? `bg-gradient-to-r ${theme.btnGrad} text-white rounded-br-md`
                          : 'bg-white border border-gray-100 text-gray-700 rounded-bl-md'
                      }`}
                    >
                      {msg.content}
                    </div>
                  </div>

                  {/* 自己：右侧头像 */}
                  {isMe && (
                    <div className="flex flex-col items-center ml-2 flex-shrink-0 mt-1">
                      <div className="w-9 h-9 rounded-full bg-gradient-to-br from-gray-200 to-gray-300 flex items-center justify-center text-lg shadow-sm">
                        {user?.name?.charAt(0) || '🙂'}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 输入区 */}
      <div className={`px-4 py-3 bg-white/80 backdrop-blur-sm border-t-2 ${theme.navBorder} flex-shrink-0`}>
        <div className="max-w-2xl mx-auto flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleSend();
            }}
            placeholder="跟大家说点什么..."
            className={`flex-1 px-4 py-3 border-2 ${theme.inputBorder} rounded-2xl text-sm text-gray-800 placeholder-gray-400 focus:outline-none ${theme.inputFocus}`}
            maxLength={500}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className={`px-5 py-3 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-white font-bold text-sm active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0 shadow-sm`}
          >
            {sending ? '...' : '发送'}
          </button>
        </div>
      </div>

      {/* 成员面板（从底部滑出） */}
      {showMembers && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end">
          <div className="flex-1 bg-black/30" onClick={() => setShowMembers(false)} />
          <div className={`bg-white rounded-t-3xl shadow-2xl border-t-4 ${theme.navBorder} max-h-[70vh] flex flex-col`}>
            {/* 面板顶部 */}
            <div className={`px-5 py-4 border-b-2 ${theme.navBorder} flex items-center justify-between`}>
              <h2 className={`text-lg font-bold ${theme.accent}`}>
                👥 群成员（{members.length}人）
              </h2>
              <button
                onClick={() => setShowMembers(false)}
                className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center text-gray-500 text-lg active:scale-90"
              >
                ×
              </button>
            </div>

            {/* 成员列表 */}
            <div className="flex-1 overflow-y-auto py-3 px-4 space-y-2">
              {members.map(m => (
                <div key={m.user_id} className="flex items-center gap-3 bg-gray-50 rounded-2xl px-4 py-3">
                  <div className={`w-10 h-10 rounded-full bg-gradient-to-br ${getAvatarBg(m.user_id)} flex items-center justify-center text-xl shadow-sm flex-shrink-0`}>
                    {getEmoji(m.user_id)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-bold text-gray-800 truncate">{m.name}</p>
                    {m.role === 'owner' && (
                      <span className="text-xs text-amber-500 font-medium">👑 群主</span>
                    )}
                  </div>
                  {myRole === 'owner' && m.user_id !== user?.id && (
                    <button
                      onClick={() => handleRemoveMember(m.user_id)}
                      className="text-xs text-red-400 bg-red-50 px-2 py-1 rounded-lg active:scale-95"
                    >
                      移出
                    </button>
                  )}
                </div>
              ))}
            </div>

            {/* 退出/解散 */}
            <div className="p-4 border-t border-gray-100">
              {!confirmLeave ? (
                <button
                  onClick={() => setConfirmLeave(true)}
                  className="w-full py-3 text-red-400 bg-red-50 rounded-2xl text-sm font-bold active:scale-95 transition-all"
                >
                  {myRole === 'owner' ? '🗑️ 解散群聊' : '🚪 退出群聊'}
                </button>
              ) : (
                <div className="flex gap-3">
                  <button
                    onClick={() => setConfirmLeave(false)}
                    className="flex-1 py-3 bg-gray-100 rounded-2xl text-sm font-bold text-gray-600 active:scale-95"
                  >
                    取消
                  </button>
                  <button
                    onClick={handleLeave}
                    className="flex-1 py-3 bg-red-400 text-white rounded-2xl text-sm font-bold active:scale-95"
                  >
                    {myRole === 'owner' ? '确认解散' : '确认退出'}
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
