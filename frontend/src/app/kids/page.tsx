'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { chatApi, ChatMessage, Conversation } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
import { useKidsTheme } from '@/contexts/KidsThemeContext';
import KidsChatBubble from '@/components/kids/KidsChatBubble';

const KIDS_QUICK_QUESTIONS = [
  { label: '今天吃什么好', emoji: '🍎', text: '今天我应该吃什么比较健康？' },
  { label: '运动建议', emoji: '🏃', text: '今天适合做什么运动呢？' },
  { label: '睡眠小知识', emoji: '😴', text: '怎样才能睡得更好呢？' },
  { label: '长高秘诀', emoji: '📏', text: '我怎样才能长得更高呢？' },
  { label: '保护眼睛', emoji: '👀', text: '怎样保护我的眼睛？' },
  { label: '喝水提醒', emoji: '💧', text: '我今天应该喝多少水？' },
];

export default function KidsChatPage() {
  const { user } = useAuth();
  const { theme: t } = useKidsTheme();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [isRecording, setIsRecording] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 8;
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const loadConversations = useCallback(async () => {
    try {
      const response = await chatApi.getConversations();
      setConversations(response.data || []);
    } catch { /* ignore */ }
  }, []);

  const loadConversation = useCallback(async (convId: number) => {
    try {
      const response = await chatApi.getConversation(convId);
      setMessages(response.data.messages || []);
      setConversationId(convId);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    const loadLastConversation = async () => {
      try {
        const res = await chatApi.getConversations(1);
        const convs = res.data;
        if (convs && convs.length > 0) {
          const lastConv = convs[0];
          const detailRes = await chatApi.getConversation(lastConv.id);
          if (detailRes.data?.messages?.length > 0) {
            setConversationId(lastConv.id);
            setMessages(detailRes.data.messages);
          }
        }
      } catch { /* ignore */ }
    };
    loadLastConversation();
  }, []);

  const handleSend = useCallback(async (text?: string) => {
    const msg = (text || inputText).trim();
    if (!msg || loading) return;

    setInputText('');
    const tempUserMsg: ChatMessage = {
      id: Date.now(), role: 'user', content: msg,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMsg]);
    setLoading(true);

    try {
      const response = await chatApi.sendMessage(msg, conversationId, true);
      const result = response.data;
      if (!conversationId && result.conversation_id) setConversationId(result.conversation_id);
      const aiMsg: ChatMessage = {
        id: result.message_id, role: 'assistant', content: result.reply,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, aiMsg]);
      loadConversations();
    } catch {
      const errorMsg: ChatMessage = {
        id: Date.now() + 1, role: 'assistant',
        content: '哎呀，出了一点小问题，请稍后再试试吧~ 🙈',
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  }, [inputText, loading, conversationId, loadConversations]);

  const handleNewChat = () => {
    setMessages([]);
    setConversationId(undefined);
    setShowHistory(false);
  };

  const handleDeleteConversation = async (convId: number) => {
    try {
      await chatApi.deleteConversation(convId);
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (conversationId === convId) { setMessages([]); setConversationId(undefined); }
    } catch { /* ignore */ }
  };

  const toggleHistory = () => {
    if (!showHistory) { loadConversations(); setSearchQuery(''); setCurrentPage(1); }
    setShowHistory(!showHistory);
  };

  const filteredConversations = conversations.filter(conv =>
    conv.title.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const totalPages = Math.ceil(filteredConversations.length / itemsPerPage);
  const paginatedConversations = filteredConversations.slice(
    (currentPage - 1) * itemsPerPage, currentPage * itemsPerPage
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleVoiceToggle = async () => {
    if (isRecording) { mediaRecorderRef.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        setIsRecording(false);
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (audioBlob.size < 1000) return;
        try {
          const reader = new FileReader();
          reader.readAsDataURL(audioBlob);
          reader.onloadend = async () => {
            const base64 = (reader.result as string).split(',')[1];
            const res = await chatApi.transcribe(base64, 'webm');
            const transcribedText = res.data.text?.trim();
            if (transcribedText) setInputText(prev => prev + transcribedText);
          };
        } catch (err) { console.error('语音转文字失败:', err); }
      };
      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) { console.error('无法访问麦克风:', err); }
  };

  return (
    <div className="flex h-full">
      {/* 历史对话侧栏 */}
      {showHistory && (
        <div className={`w-80 bg-white/90 backdrop-blur-sm border-r-2 ${t.sidebarBorder} flex flex-col shadow-lg flex-shrink-0`}>
          {/* 侧栏顶部 */}
          <div className={`p-4 border-b-2 ${t.sidebarBorder}`}>
            <button
              onClick={handleNewChat}
              className={`w-full flex items-center justify-center gap-2 px-4 py-3 rounded-2xl bg-gradient-to-r ${t.btnGrad} text-white font-bold shadow-md hover:shadow-lg transition-all active:scale-95 text-lg`}
            >
              <span className="text-xl">+</span>
              新对话
            </button>
          </div>

          {/* 搜索框 */}
          <div className={`px-4 pt-4 pb-3 border-b ${t.sidebarBorder}`}>
            <h2 className={`text-lg font-bold ${t.accent} flex items-center gap-2 mb-3`}>
              <span>💬</span>
              聊天记录
            </h2>
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                placeholder="搜索对话..."
                className={`w-full px-4 py-2.5 pl-10 rounded-2xl ${t.searchBg} border-2 ${t.searchBorder} text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 ${t.inputFocus} text-base`}
              />
              <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400">🔍</span>
            </div>
          </div>

          {/* 对话列表 */}
          <div className="flex-1 overflow-y-auto">
            {conversations.length === 0 ? (
              <div className="p-8 text-center text-gray-400">
                <div className="text-5xl mb-3">📝</div>
                <div className="text-lg">还没有聊天记录哦~</div>
              </div>
            ) : paginatedConversations.length === 0 ? (
              <div className="p-8 text-center text-gray-400">
                <div className="text-5xl mb-3">🔍</div>
                <div className="text-lg">没找到相关对话</div>
              </div>
            ) : (
              paginatedConversations.map(conv => (
                <div
                  key={conv.id}
                  className={`group flex items-center gap-3 px-4 py-3.5 border-b ${t.sidebarBorder} ${t.hoverBg} cursor-pointer transition-all ${
                    conv.id === conversationId
                      ? `${t.activeBg} border-l-4 ${t.activeAccent}`
                      : 'border-l-4 border-l-transparent'
                  }`}
                  onClick={() => loadConversation(conv.id)}
                >
                  <div className={`flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-br ${t.bubbleGrad} flex items-center justify-center`}>
                    <span className="text-lg">💬</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="font-bold text-gray-700 line-clamp-2 text-base leading-snug">
                      {conv.title}
                    </div>
                  </div>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDeleteConversation(conv.id); }}
                    className="flex-shrink-0 opacity-0 group-hover:opacity-100 w-8 h-8 rounded-full bg-red-100 hover:bg-red-200 flex items-center justify-center text-red-400 hover:text-red-500 text-lg transition-all"
                    title="删除"
                  >
                    ×
                  </button>
                </div>
              ))
            )}
          </div>

          {/* 分页 */}
          {filteredConversations.length > itemsPerPage && (
            <div className={`p-3 border-t-2 ${t.sidebarBorder}`}>
              <div className="flex items-center justify-between text-base">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className={`px-3 py-1.5 rounded-xl font-bold transition-colors ${
                    currentPage === 1 ? 'text-gray-300 cursor-not-allowed' : `${t.paginateBtn} active:scale-95`
                  }`}
                >← 上页</button>
                <span className="text-gray-500 font-bold">{currentPage} / {totalPages}</span>
                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className={`px-3 py-1.5 rounded-xl font-bold transition-colors ${
                    currentPage === totalPages ? 'text-gray-300 cursor-not-allowed' : `${t.paginateBtn} active:scale-95`
                  }`}
                >下页 →</button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* 主聊天区域 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 顶栏 */}
        <header className={`flex items-center justify-between px-6 py-4 bg-white/60 backdrop-blur-sm border-b ${t.navBorder}`}>
          <div className="flex items-center gap-3">
            <button
              onClick={toggleHistory}
              className={`w-11 h-11 rounded-2xl flex items-center justify-center transition-all shadow-sm active:scale-95 ${
                showHistory
                  ? `${t.tabActiveBg} border-2 ${t.inputBorder} ${t.accent}`
                  : `bg-white border-2 ${t.navBorder} text-gray-500 ${t.cardHoverBorder}`
              }`}
              title={showHistory ? '关闭记录' : '聊天记录'}
            >
              <span className="text-xl">💬</span>
            </button>
            <h1 className={`text-2xl font-bold ${t.accent} flex items-center gap-2`}>
              <span className="text-3xl">{t.icon}</span>
              健康小助手
            </h1>
          </div>
          <button
            onClick={handleNewChat}
            className={`px-4 py-2 bg-gradient-to-r ${t.btnGrad} text-white rounded-full font-bold shadow-md hover:shadow-lg transition-all active:scale-95 text-base`}
          >
            + 新对话
          </button>
        </header>

        {/* 消息区域 */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div className="max-w-3xl mx-auto">
            {/* 欢迎屏 */}
            {messages.length === 0 && !loading && (
              <div className="text-center space-y-6 mt-8">
                <div className="text-8xl">{t.icon}</div>
                <h2 className={`text-3xl font-bold ${t.accent}`}>
                  你好！我是你的健康小助手
                </h2>
                <p className="text-xl text-gray-500">
                  有什么想问的吗？点下面的问题试试吧~
                </p>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 max-w-2xl mx-auto mt-8">
                  {KIDS_QUICK_QUESTIONS.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(q.text)}
                      className={`flex flex-col items-center gap-2 px-4 py-5 bg-white rounded-2xl shadow-md border-2 ${t.cardBorder} ${t.cardHoverBorder} hover:shadow-lg transition-all active:scale-95`}
                    >
                      <span className="text-4xl">{q.emoji}</span>
                      <span className="text-base font-bold text-gray-700">{q.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 消息列表 */}
            {messages.map(msg => (
              <KidsChatBubble key={msg.id} message={msg} avatarUrl={user?.avatar_url} />
            ))}

            {/* 加载动画 */}
            {loading && (
              <div className="flex gap-3 mb-4">
                <div className={`w-12 h-12 rounded-full bg-gradient-to-br ${t.bubbleGrad} flex items-center justify-center flex-shrink-0 shadow-md`}>
                  <span className="text-2xl">{t.icon}</span>
                </div>
                <div className={`bg-white border-2 ${t.navBorder} rounded-3xl px-5 py-4 shadow-md`}>
                  <div className="flex gap-2">
                    <div className={`w-3 h-3 rounded-full ${t.dot1} animate-bounce`} style={{ animationDelay: '0ms' }} />
                    <div className={`w-3 h-3 rounded-full ${t.dot2} animate-bounce`} style={{ animationDelay: '150ms' }} />
                    <div className={`w-3 h-3 rounded-full ${t.dot1} animate-bounce`} style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* 快捷问题横滑栏 */}
        {messages.length > 0 && !loading && (
          <div className={`px-4 py-2 border-t ${t.navBorder} bg-white/40`}>
            <div className="max-w-3xl mx-auto overflow-x-auto">
              <div className="flex gap-3">
                {KIDS_QUICK_QUESTIONS.map((q, idx) => (
                  <button
                    key={idx}
                    onClick={() => handleSend(q.text)}
                    className={`flex items-center gap-2 px-5 py-3 bg-white rounded-full shadow-sm border-2 ${t.cardBorder} ${t.cardHoverBorder} text-base font-bold whitespace-nowrap transition-all active:scale-95`}
                  >
                    <span className="text-xl">{q.emoji}</span>
                    <span className="text-gray-700">{q.label}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* 输入区域 */}
        <div className={`px-4 py-4 bg-white/80 backdrop-blur-sm border-t ${t.navBorder}`}>
          <div className="flex gap-3 items-center max-w-3xl mx-auto">
            {/* 语音按钮 */}
            <button
              onClick={handleVoiceToggle}
              disabled={loading}
              className={`w-14 h-14 rounded-full flex items-center justify-center transition-all flex-shrink-0 shadow-md ${
                isRecording
                  ? 'bg-red-400 text-white animate-pulse shadow-red-200'
                  : `bg-white border-2 ${t.inputBorder} text-gray-600 ${t.cardHoverBorder} active:scale-95`
              }`}
            >
              <span className="text-2xl">{isRecording ? '⏹️' : '🎤'}</span>
            </button>

            {/* 文本输入 */}
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isRecording ? '正在听你说话...' : '想问什么就说吧~'}
              className={`flex-1 px-6 py-4 text-lg rounded-full bg-white border-2 ${t.inputBorder} text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 ${t.inputFocus} shadow-sm`}
              disabled={isRecording}
            />

            {/* 发送按钮 */}
            <button
              onClick={() => handleSend()}
              disabled={!inputText.trim() || loading}
              className={`w-14 h-14 rounded-full flex items-center justify-center transition-all flex-shrink-0 shadow-md ${
                inputText.trim() && !loading
                  ? `bg-gradient-to-r ${t.btnGrad} text-white hover:shadow-lg active:scale-95`
                  : 'bg-gray-100 text-gray-300 cursor-not-allowed'
              }`}
            >
              <span className="text-2xl">➡️</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
