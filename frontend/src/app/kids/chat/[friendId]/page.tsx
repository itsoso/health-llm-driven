'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';
import { useKidsTheme } from '@/contexts/KidsThemeContext';
import { dmApi, friendsApi, DMResponse } from '@/services/api';

export default function KidsChatPage() {
  const params = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const { theme } = useKidsTheme();
  const friendId = Number(params.friendId);

  const [messages, setMessages] = useState<DMResponse[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [friendName, setFriendName] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  // Load initial messages
  useEffect(() => {
    if (!user || !friendId) return;
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      try {
        // Load friend name from friends list
        friendsApi.listFriends().then(fRes => {
          const f = fRes.data.find(fr => fr.user_id === friendId);
          if (f) setFriendName(f.name);
        }).catch(() => {});

        const res = await dmApi.getMessages(friendId);
        if (cancelled) return;
        setMessages(res.data.messages);
        setHasMore(res.data.has_more);
        // Extract friend name from messages as fallback
        if (!friendName) {
          const friendMsg = res.data.messages.find(m => m.sender_id === friendId);
          if (friendMsg?.sender_name) setFriendName(friendMsg.sender_name);
        }
        // Mark as read
        dmApi.markRead(friendId).catch(() => {});
      } catch (err) {
        console.error('Failed to load messages:', err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, [user, friendId]);

  // Scroll to bottom when messages change
  useEffect(() => {
    if (!loading) {
      setTimeout(scrollToBottom, 100);
    }
  }, [messages.length, loading, scrollToBottom]);

  // Poll for new messages every 5 seconds
  useEffect(() => {
    if (!user || !friendId) return;

    pollRef.current = setInterval(async () => {
      try {
        const res = await dmApi.getMessages(friendId);
        setMessages(prev => {
          const newMsgs = res.data.messages;
          // Only update if there are new messages
          if (newMsgs.length !== prev.length || (newMsgs.length > 0 && newMsgs[newMsgs.length - 1].id !== prev[prev.length - 1]?.id)) {
            dmApi.markRead(friendId).catch(() => {});
            return newMsgs;
          }
          return prev;
        });
        setHasMore(res.data.has_more);
      } catch { /* silent */ }
    }, 5000);

    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [user, friendId]);

  // Load more (older messages)
  const loadMore = async () => {
    if (!hasMore || messages.length === 0) return;
    const oldestId = messages[0].id;
    try {
      const res = await dmApi.getMessages(friendId, oldestId);
      setMessages(prev => [...res.data.messages, ...prev]);
      setHasMore(res.data.has_more);
    } catch (err) {
      console.error('Failed to load more:', err);
    }
  };

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;

    setSending(true);
    try {
      const res = await dmApi.sendMessage(friendId, text);
      setMessages(prev => [...prev, res.data]);
      setInput('');
    } catch (err: any) {
      alert(err.response?.data?.detail || '发送失败');
    } finally {
      setSending(false);
    }
  };

  const formatTime = (dateStr: string) => {
    const d = new Date(dateStr);
    const now = new Date();
    // 使用北京时间比较日期
    const bjFormatter = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' });
    const bjDateStr = bjFormatter.format(d);
    const bjNowStr = bjFormatter.format(now);
    const yesterday = new Date(now.getTime() - 86400000);
    const bjYesterdayStr = bjFormatter.format(yesterday);

    const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' });
    if (bjDateStr === bjNowStr) return time;
    if (bjDateStr === bjYesterdayStr) return `昨天 ${time}`;
    const parts = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric' }).format(d);
    return `${parts} ${time}`;
  };

  // Should show time label if gap > 5 minutes
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
          <p className="text-gray-400 text-lg">加载中...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      {/* 顶栏 */}
      <div className={`px-4 py-3 bg-white/60 backdrop-blur-sm border-b-2 ${theme.navBorder} flex-shrink-0`}>
        <div className="flex items-center gap-3 max-w-2xl mx-auto">
          <button
            onClick={() => router.back()}
            className="w-9 h-9 rounded-full bg-gray-100 flex items-center justify-center text-gray-500 active:scale-90 transition-all"
          >
            ‹
          </button>
          <div className="flex items-center gap-2 flex-1 min-w-0">
            <div className={`w-9 h-9 rounded-full bg-gradient-to-br ${theme.btnGrad} flex items-center justify-center text-white text-sm font-bold flex-shrink-0`}>
              {(friendName || '?').charAt(0)}
            </div>
            <h1 className={`text-lg font-bold ${theme.accent} truncate`}>
              {friendName || `用户${friendId}`}
            </h1>
          </div>
        </div>
      </div>

      {/* 消息列表 */}
      <div ref={containerRef} className="flex-1 overflow-y-auto px-4 py-3">
        <div className="max-w-2xl mx-auto">
          {/* 加载更多 */}
          {hasMore && (
            <button
              onClick={loadMore}
              className="w-full text-center text-sm text-gray-400 py-2 mb-2 active:text-gray-600"
            >
              加载更早的消息
            </button>
          )}

          {messages.length === 0 && (
            <div className="text-center py-16">
              <div className="text-6xl mb-3">👋</div>
              <p className="text-gray-400">快来跟好友打个招呼吧！</p>
            </div>
          )}

          {messages.map((msg, idx) => {
            const isMe = msg.sender_id === user?.id;
            return (
              <div key={msg.id}>
                {/* 时间标签 */}
                {shouldShowTime(idx) && (
                  <div className="text-center text-xs text-gray-400 my-3">
                    {formatTime(msg.created_at)}
                  </div>
                )}

                {/* 消息气泡 */}
                <div className={`flex mb-2 ${isMe ? 'justify-end' : 'justify-start'}`}>
                  {!isMe && (
                    <div className="flex flex-col items-center mr-2 mt-1 flex-shrink-0">
                      <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${theme.btnGrad} flex items-center justify-center text-white text-xs font-bold`}>
                        {(msg.sender_name || '?').charAt(0)}
                      </div>
                      <span className="text-[10px] text-gray-400 mt-0.5 max-w-[48px] truncate">{msg.sender_name || friendName}</span>
                    </div>
                  )}
                  <div
                    className={`max-w-[70%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed break-words ${
                      isMe
                        ? `bg-gradient-to-r ${theme.btnGrad} text-white rounded-br-md`
                        : 'bg-white border border-gray-100 text-gray-700 rounded-bl-md shadow-sm'
                    }`}
                  >
                    {msg.content}
                  </div>
                  {isMe && (
                    <div className="flex flex-col items-center ml-2 mt-1 flex-shrink-0">
                      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-gray-500 text-xs font-bold">
                        {(user?.name || '我').charAt(0)}
                      </div>
                      <span className="text-[10px] text-gray-400 mt-0.5 max-w-[48px] truncate">{user?.name || '我'}</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 输入区域 */}
      <div className={`px-4 py-3 bg-white/80 backdrop-blur-sm border-t-2 ${theme.navBorder} flex-shrink-0`}>
        <div className="max-w-2xl mx-auto flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.nativeEvent.isComposing) handleSend();
            }}
            placeholder="输入消息..."
            className={`flex-1 px-4 py-3 border-2 ${theme.inputBorder} rounded-2xl text-sm text-gray-800 placeholder-gray-400 focus:outline-none ${theme.inputFocus}`}
            maxLength={500}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className={`px-5 py-3 rounded-2xl bg-gradient-to-r ${theme.btnGrad} text-white font-bold text-sm active:scale-95 transition-all disabled:opacity-40 disabled:cursor-not-allowed flex-shrink-0`}
          >
            {sending ? '...' : '发送'}
          </button>
        </div>
      </div>
    </div>
  );
}
