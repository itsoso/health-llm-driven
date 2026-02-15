'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { chatApi, ChatMessage } from '@/services/api';
import { useAuth } from '@/contexts/AuthContext';
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
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [isRecording, setIsRecording] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 发送消息
  const handleSend = useCallback(async (text?: string) => {
    const msg = (text || inputText).trim();
    if (!msg || loading) return;

    setInputText('');

    const tempUserMsg: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content: msg,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, tempUserMsg]);
    setLoading(true);

    try {
      const response = await chatApi.sendMessage(msg, conversationId);
      const result = response.data;

      if (!conversationId && result.conversation_id) {
        setConversationId(result.conversation_id);
      }

      const aiMsg: ChatMessage = {
        id: result.message_id,
        role: 'assistant',
        content: result.reply,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, aiMsg]);
    } catch {
      const errorMsg: ChatMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: '哎呀，出了一点小问题，请稍后再试试吧~ 🙈',
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  }, [inputText, loading, conversationId]);

  // 新建对话
  const handleNewChat = () => {
    setMessages([]);
    setConversationId(undefined);
  };

  // 按 Enter 发送
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // 语音录制
  const handleVoiceToggle = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop();
      return;
    }

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
            if (transcribedText) {
              setInputText(prev => prev + transcribedText);
            }
          };
        } catch (err) {
          console.error('语音转文字失败:', err);
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('无法访问麦克风:', err);
    }
  };

  return (
    <div className="flex flex-col h-full min-h-screen">
      {/* 顶栏 */}
      <header className="flex items-center justify-between px-6 py-4 bg-white/60 backdrop-blur-sm border-b border-pink-100">
        <h1 className="text-2xl font-bold text-purple-600 flex items-center gap-2">
          <span className="text-3xl">🌟</span>
          健康小助手
        </h1>
        <button
          onClick={handleNewChat}
          className="px-4 py-2 bg-gradient-to-r from-pink-400 to-purple-400 text-white rounded-full font-bold shadow-md hover:shadow-lg transition-all active:scale-95 text-base"
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
              <div className="text-8xl">🌟</div>
              <h2 className="text-3xl font-bold text-purple-600">
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
                    className="flex flex-col items-center gap-2 px-4 py-5 bg-white rounded-2xl shadow-md border-2 border-pink-100 hover:border-pink-300 hover:shadow-lg transition-all active:scale-95"
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
              <div className="w-12 h-12 rounded-full bg-gradient-to-br from-pink-300 to-purple-300 flex items-center justify-center flex-shrink-0 shadow-md">
                <span className="text-2xl">🌟</span>
              </div>
              <div className="bg-white border-2 border-pink-100 rounded-3xl px-5 py-4 shadow-md">
                <div className="flex gap-2">
                  <div className="w-3 h-3 rounded-full bg-pink-400 animate-bounce" style={{ animationDelay: '0ms' }}></div>
                  <div className="w-3 h-3 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: '150ms' }}></div>
                  <div className="w-3 h-3 rounded-full bg-pink-400 animate-bounce" style={{ animationDelay: '300ms' }}></div>
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 快捷问题横滑栏 (对话中显示) */}
      {messages.length > 0 && !loading && (
        <div className="px-4 py-2 border-t border-pink-100 bg-white/40">
          <div className="max-w-3xl mx-auto overflow-x-auto">
            <div className="flex gap-3">
              {KIDS_QUICK_QUESTIONS.map((q, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(q.text)}
                  className="flex items-center gap-2 px-5 py-3 bg-white rounded-full shadow-sm border-2 border-pink-100 hover:border-pink-300 text-base font-bold whitespace-nowrap transition-all active:scale-95"
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
      <div className="px-4 py-4 bg-white/80 backdrop-blur-sm border-t border-pink-100">
        <div className="flex gap-3 items-center max-w-3xl mx-auto">
          {/* 语音按钮 */}
          <button
            onClick={handleVoiceToggle}
            disabled={loading}
            className={`w-14 h-14 rounded-full flex items-center justify-center transition-all flex-shrink-0 shadow-md ${
              isRecording
                ? 'bg-red-400 text-white animate-pulse shadow-red-200'
                : 'bg-white border-2 border-pink-200 text-gray-600 hover:border-pink-400 active:scale-95'
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
            className="flex-1 px-6 py-4 text-lg rounded-full bg-white border-2 border-pink-200 text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-300 focus:border-purple-300 shadow-sm"
            disabled={isRecording}
          />

          {/* 发送按钮 */}
          <button
            onClick={() => handleSend()}
            disabled={!inputText.trim() || loading}
            className={`w-14 h-14 rounded-full flex items-center justify-center transition-all flex-shrink-0 shadow-md ${
              inputText.trim() && !loading
                ? 'bg-gradient-to-r from-pink-400 to-purple-400 text-white hover:shadow-lg active:scale-95'
                : 'bg-gray-100 text-gray-300 cursor-not-allowed'
            }`}
          >
            <span className="text-2xl">➡️</span>
          </button>
        </div>
      </div>
    </div>
  );
}
