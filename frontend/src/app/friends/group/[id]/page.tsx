'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { groupApi, GroupMsgData, GroupMemberInfo } from '@/services/api';
import { ArrowLeft, Send, Users, UserMinus, UserPlus, LogOut, Settings, X } from 'lucide-react';

export default function GroupChatPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const groupId = Number(params.id);

  const [messages, setMessages] = useState<GroupMsgData[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [groupName, setGroupName] = useState('群聊');
  const [members, setMembers] = useState<GroupMemberInfo[]>([]);
  const [myRole, setMyRole] = useState<'owner' | 'member'>('member');
  const [showPanel, setShowPanel] = useState(false);

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
        const me = detailRes.data.members.find(m => m.user_id === user.id);
        if (me) setMyRole(me.role as 'owner' | 'member');
        setMessages(msgRes.data.messages);
        setHasMore(msgRes.data.has_more);
        if (msgRes.data.messages.length > 0) {
          latestIdRef.current = msgRes.data.messages[msgRes.data.messages.length - 1].id;
        }
      } catch (err) {
        console.error('加载群聊失败', err);
        router.back();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, [user, groupId, router]);

  useEffect(() => {
    if (!loading) scrollToBottom();
  }, [loading, scrollToBottom]);

  // 轮询新消息
  useEffect(() => {
    if (loading || !user) return;
    const poll = async () => {
      try {
        const res = await groupApi.getMessages(groupId);
        const newMsgs = res.data.messages;
        if (newMsgs.length > 0) {
          const latest = newMsgs[newMsgs.length - 1].id;
          if (latest > latestIdRef.current) {
            latestIdRef.current = latest;
            setMessages(newMsgs);
            scrollToBottom();
          }
        }
      } catch {}
    };
    pollRef.current = setInterval(poll, 4000);
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
    } catch (err) {
      setInput(content);
    } finally {
      setSending(false);
    }
  };

  const handleLeave = async () => {
    if (!confirm('确认退出群聊？')) return;
    try {
      await groupApi.leave(groupId);
      router.push('/friends');
    } catch (e: any) {
      alert(e?.response?.data?.detail || '退群失败');
    }
  };

  const handleDissolve = async () => {
    if (!confirm('确认解散群聊？此操作不可恢复。')) return;
    try {
      await groupApi.dissolve(groupId);
      router.push('/friends');
    } catch (e: any) {
      alert(e?.response?.data?.detail || '解散失败');
    }
  };

  const handleRemoveMember = async (uid: number) => {
    if (!confirm('确认移除该成员？')) return;
    try {
      await groupApi.removeMember(groupId, uid);
      setMembers(prev => prev.filter(m => m.user_id !== uid));
    } catch (e: any) {
      alert(e?.response?.data?.detail || '移除失败');
    }
  };

  const formatTime = (iso: string) => {
    const d = new Date(iso);
    const now = new Date();
    const isToday = d.toDateString() === now.toDateString();
    if (isToday) {
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }
    return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' }) + ' ' +
      d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
  };

  const getInitial = (name: string) => name?.charAt(0)?.toUpperCase() || '?';

  const avatarColors = [
    'bg-blue-400', 'bg-purple-400', 'bg-green-400', 'bg-rose-400',
    'bg-amber-400', 'bg-teal-400', 'bg-indigo-400', 'bg-orange-400',
  ];
  const getColor = (id: number) => avatarColors[id % avatarColors.length];

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* 顶栏 */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-b shadow-sm">
        <button onClick={() => router.back()} className="p-1 text-gray-500 hover:text-gray-700">
          <ArrowLeft className="w-5 h-5" />
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="font-semibold text-gray-900 truncate">{groupName}</h1>
          <p className="text-xs text-gray-400">{members.length} 位成员</p>
        </div>
        <button
          onClick={() => setShowPanel(true)}
          className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
        >
          <Users className="w-5 h-5" />
        </button>
      </div>

      {/* 消息区 */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {hasMore && (
          <button
            className="w-full text-center text-xs text-blue-500 py-2"
            onClick={async () => {
              const firstId = messages[0]?.id;
              const res = await groupApi.getMessages(groupId, firstId);
              setMessages(prev => [...res.data.messages, ...prev]);
              setHasMore(res.data.has_more);
            }}
          >
            加载更多历史消息
          </button>
        )}

        {messages.map((msg, idx) => {
          const isMine = msg.sender_id === user?.id;
          const showName = !isMine && (idx === 0 || messages[idx - 1].sender_id !== msg.sender_id);
          return (
            <div key={msg.id} className={`flex gap-2 ${isMine ? 'flex-row-reverse' : ''}`}>
              {/* 头像 */}
              {!isMine && (
                <div className={`w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-white text-xs font-bold ${getColor(msg.sender_id)}`}>
                  {msg.sender_avatar
                    ? <img src={msg.sender_avatar} className="w-8 h-8 rounded-full object-cover" alt="" />
                    : getInitial(msg.sender_name)}
                </div>
              )}
              <div className={`flex flex-col max-w-[70%] ${isMine ? 'items-end' : 'items-start'}`}>
                {showName && (
                  <span className="text-xs text-gray-400 mb-1 px-1">{msg.sender_name}</span>
                )}
                <div className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
                  isMine
                    ? 'bg-blue-500 text-white rounded-tr-sm'
                    : 'bg-white text-gray-800 rounded-tl-sm shadow-sm'
                }`}>
                  {msg.content}
                </div>
                <span className="text-[10px] text-gray-400 mt-1 px-1">{formatTime(msg.created_at)}</span>
              </div>
            </div>
          );
        })}
        <div ref={messagesEndRef} />
      </div>

      {/* 输入框 */}
      <div className="px-4 py-3 bg-white border-t">
        <div className="flex items-center gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
            placeholder="发消息..."
            className="flex-1 px-4 py-2.5 bg-gray-100 rounded-full text-sm outline-none focus:bg-gray-50 focus:ring-2 focus:ring-blue-200"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className="w-10 h-10 flex items-center justify-center bg-blue-500 text-white rounded-full hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 右侧成员面板 */}
      {showPanel && (
        <div className="fixed inset-0 z-50 flex">
          <div className="flex-1 bg-black/30" onClick={() => setShowPanel(false)} />
          <div className="w-72 bg-white h-full flex flex-col shadow-xl">
            <div className="flex items-center justify-between px-4 py-4 border-b">
              <h2 className="font-semibold text-gray-800">群成员 ({members.length})</h2>
              <button onClick={() => setShowPanel(false)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto py-2">
              {members.map(m => (
                <div key={m.user_id} className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50">
                  <div className={`w-9 h-9 rounded-full flex-shrink-0 flex items-center justify-center text-white text-sm font-bold ${getColor(m.user_id)}`}>
                    {m.avatar_url
                      ? <img src={m.avatar_url} className="w-9 h-9 rounded-full object-cover" alt="" />
                      : getInitial(m.name)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-800 truncate">{m.name}</p>
                    {m.role === 'owner' && (
                      <span className="text-xs text-amber-500">群主</span>
                    )}
                  </div>
                  {myRole === 'owner' && m.user_id !== user?.id && (
                    <button
                      onClick={() => handleRemoveMember(m.user_id)}
                      className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                      title="移除成员"
                    >
                      <UserMinus className="w-4 h-4" />
                    </button>
                  )}
                </div>
              ))}
            </div>

            <div className="border-t p-4 space-y-2">
              {myRole === 'owner' ? (
                <button
                  onClick={handleDissolve}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-red-500 border border-red-200 rounded-lg hover:bg-red-50 text-sm font-medium"
                >
                  <X className="w-4 h-4" />
                  解散群聊
                </button>
              ) : (
                <button
                  onClick={handleLeave}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-red-500 border border-red-200 rounded-lg hover:bg-red-50 text-sm font-medium"
                >
                  <LogOut className="w-4 h-4" />
                  退出群聊
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
