'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { chatApi, ChatMessage, Conversation, DietSavedData, ActivitySavedData } from '@/services/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// 扩展 Window 类型以支持 webkitSpeechRecognition
declare global {
  interface Window {
    webkitSpeechRecognition: any;
    SpeechRecognition: any;
  }
}

const QUICK_QUESTIONS = [
  { label: '分析打卡', text: '请分析一下我今天的打卡完成情况，给出建议' },
  { label: '运动建议', text: '根据我的身体数据，今天适合做什么运动？' },
  { label: '睡眠分析', text: '帮我分析一下最近的睡眠质量，有什么改善建议？' },
  { label: '饮食建议', text: '根据我的健康目标，今天的饮食应该注意什么？' },
];

export default function AIAssistantPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [dietNotification, setDietNotification] = useState<DietSavedData | null>(null);
  const [activityNotifications, setActivityNotifications] = useState<ActivitySavedData[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [imageUploading, setImageUploading] = useState(false);
  const itemsPerPage = 10;
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // 滚动到底部
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // 加载对话列表
  const loadConversations = useCallback(async () => {
    try {
      const response = await chatApi.getConversations();
      setConversations(response.data || []);
    } catch (e) {
      console.error('加载对话列表失败:', e);
    }
  }, []);

  // 加载指定对话的消息
  const loadConversation = useCallback(async (convId: number) => {
    try {
      const response = await chatApi.getConversation(convId);
      setMessages(response.data.messages || []);
      setConversationId(convId);
      // 保持历史记录面板打开，不自动关闭
    } catch (e) {
      console.error('加载对话失败:', e);
      alert('加载失败');
    }
  }, []);

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      router.push('/login');
      return;
    }
    loadConversations();
  }, [loadConversations, router]);

  // 发送消息
  const handleSend = async (text?: string) => {
    const msg = (text || inputText).trim();
    if (!msg || loading) return;

    setInputText('');

    // 乐观更新：先显示用户消息
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

      // 更新会话 ID
      if (!conversationId && result.conversation_id) {
        setConversationId(result.conversation_id);
      }

      // 添加 AI 回复
      const aiMsg: ChatMessage = {
        id: result.message_id,
        role: 'assistant',
        content: result.reply,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, aiMsg]);

      // 显示饮食记录保存通知
      if (result.diet_saved && result.diet_data) {
        setDietNotification(result.diet_data);
        setTimeout(() => setDietNotification(null), 5000);
      }

      // 显示活动记录通知
      if (result.activities_saved && result.activities) {
        const saved = result.activities.filter((a: ActivitySavedData) => a.status !== 'already_exists');
        if (saved.length > 0) {
          setActivityNotifications(saved);
          setTimeout(() => setActivityNotifications([]), 5000);
        }
      }

      // 设置休息提醒（浏览器通知）
      if (result.reminder && result.reminder.reminder_minutes > 0) {
        const { reminder_minutes, reminder_message, activity_name } = result.reminder;
        if ('Notification' in window) {
          if (Notification.permission === 'granted') {
            setTimeout(() => {
              new Notification(`${activity_name} - 休息提醒`, { body: reminder_message, icon: '/icon-192x192.png' });
            }, reminder_minutes * 60 * 1000);
          } else if (Notification.permission !== 'denied') {
            Notification.requestPermission().then(perm => {
              if (perm === 'granted') {
                setTimeout(() => {
                  new Notification(`${activity_name} - 休息提醒`, { body: reminder_message, icon: '/icon-192x192.png' });
                }, reminder_minutes * 60 * 1000);
              }
            });
          }
        }
      }

      // 重新加载对话列表
      loadConversations();
    } catch (e: any) {
      const errorMsg: ChatMessage = {
        id: Date.now() + 1,
        role: 'assistant',
        content: '抱歉，请求失败了，请稍后再试。',
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  // 新建对话
  const handleNewChat = () => {
    setMessages([]);
    setConversationId(undefined);
    setShowHistory(false);
  };

  // 删除对话
  const handleDeleteConversation = async (convId: number) => {
    try {
      await chatApi.deleteConversation(convId);
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (conversationId === convId) {
        handleNewChat();
      }
      alert('已删除');
    } catch (e) {
      alert('删除失败');
    }
  };

  // 切换历史面板
  const toggleHistory = () => {
    if (!showHistory) {
      loadConversations();
      setSearchQuery('');
      setCurrentPage(1);
    }
    setShowHistory(!showHistory);
  };

  // 过滤和分页对话列表
  const filteredConversations = conversations.filter(conv =>
    conv.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (conv.last_message && conv.last_message.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const totalPages = Math.ceil(filteredConversations.length / itemsPerPage);
  const paginatedConversations = filteredConversations.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // 按 Enter 发送消息（忽略中文输入法组合阶段）
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSend();
    }
  };

  // 语音录制
  const handleVoiceToggle = async () => {
    if (isRecording) {
      // 停止录音
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
        if (audioBlob.size < 1000) return; // 太短忽略

        try {
          const reader = new FileReader();
          reader.readAsDataURL(audioBlob);
          reader.onloadend = async () => {
            const base64 = (reader.result as string).split(',')[1];
            const res = await chatApi.transcribe(base64, 'webm');
            const text = res.data.text?.trim();
            if (text) {
              setInputText(prev => prev + text);
            }
          };
        } catch (err) {
          console.error('语音转文字失败:', err);
          alert('语音识别失败，请重试');
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('无法访问麦克风:', err);
      alert('无法访问麦克风，请检查浏览器权限');
    }
  };

  // 图片上传处理
  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 重置 input 以便再次选择同一文件
    e.target.value = '';

    setImageUploading(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onloadend = async () => {
        const base64 = (reader.result as string).split(',')[1];
        const imageType = file.type || 'image/jpeg';

        try {
          const res = await chatApi.recognizeFood(base64, imageType);
          const data = res.data;
          if (data.success && data.meal_description) {
            // 将识别结果作为消息发送给AI
            const foodText = `我刚吃了：${data.meal_description}，请帮我计算热量并记录`;
            handleSend(foodText);
          } else {
            alert('未能识别食物，请拍摄更清晰的食物照片');
          }
        } catch (err) {
          console.error('食物识别失败:', err);
          alert('食物识别失败，请重试');
        } finally {
          setImageUploading(false);
        }
      };
    } catch (err) {
      console.error('读取图片失败:', err);
      setImageUploading(false);
    }
  };

  return (
    <div className="fixed inset-0 top-16 bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex overflow-hidden">
      {/* 历史对话侧栏 */}
      {showHistory && (
        <div className="w-80 bg-slate-800/80 border-r border-purple-500/30 flex flex-col shadow-lg">
          {/* 侧边栏顶部 - 新建对话按钮 */}
          <div className="p-3 border-b border-purple-500/30 bg-slate-900/50">
            <button
              onClick={handleNewChat}
              className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-purple-600 hover:bg-purple-500 transition-all text-white font-medium shadow-lg"
            >
              <span className="text-xl">+</span>
              <span>新建对话</span>
            </button>
          </div>

          {/* 搜索框 */}
          <div className="p-4 border-b border-purple-500/30 bg-slate-900/50">
            <h2 className="text-lg font-bold text-white flex items-center gap-2 mb-3">
              <span>💬</span>
              <span>对话记录</span>
            </h2>
            <div className="relative">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setCurrentPage(1); // 搜索时重置到第一页
                }}
                placeholder="搜索对话..."
                className="w-full px-3 py-2 pl-9 rounded-lg bg-slate-700/50 border border-white/10 text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-purple-500 text-sm"
              />
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400">🔍</span>
            </div>
          </div>
            <div className="flex-1 overflow-y-auto">
              {conversations.length === 0 ? (
                <div className="p-8 text-center text-slate-400">
                  <div className="text-4xl mb-3">📝</div>
                  <div>暂无对话记录</div>
                </div>
              ) : paginatedConversations.length === 0 ? (
                <div className="p-8 text-center text-slate-400">
                  <div className="text-4xl mb-3">🔍</div>
                  <div>未找到匹配的对话</div>
                </div>
              ) : (
                paginatedConversations.map(conv => (
                  <div
                    key={conv.id}
                    className={`group flex items-start gap-3 p-4 border-b border-white/5 hover:bg-purple-900/20 cursor-pointer transition-all ${
                      conv.id === conversationId ? 'bg-purple-900/30 border-l-4 border-l-purple-500' : 'border-l-4 border-l-transparent'
                    }`}
                    onClick={() => loadConversation(conv.id)}
                  >
                    <div className="flex-shrink-0 w-8 h-8 rounded-full bg-purple-600/30 flex items-center justify-center text-sm">
                      💬
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-white line-clamp-2 mb-1 leading-snug">
                        {conv.title}
                      </div>
                      {conv.last_message && (
                        <div className="text-xs text-slate-400 line-clamp-1">
                          {conv.last_message}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteConversation(conv.id);
                      }}
                      className="flex-shrink-0 opacity-0 group-hover:opacity-100 ml-2 text-slate-400 hover:text-red-400 text-xl transition-opacity"
                      title="删除对话"
                    >
                      ×
                    </button>
                  </div>
                ))
              )}
            </div>

            {/* 分页控件 */}
            {filteredConversations.length > itemsPerPage && (
              <div className="p-3 border-t border-purple-500/30 bg-slate-900/50">
                <div className="flex items-center justify-between text-sm">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className={`px-3 py-1.5 rounded-lg transition-colors ${
                      currentPage === 1
                        ? 'text-slate-500 cursor-not-allowed'
                        : 'text-purple-300 hover:bg-purple-600/20'
                    }`}
                  >
                    ← 上一页
                  </button>
                  <span className="text-slate-300">
                    {currentPage} / {totalPages}
                  </span>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className={`px-3 py-1.5 rounded-lg transition-colors ${
                      currentPage === totalPages
                        ? 'text-slate-500 cursor-not-allowed'
                        : 'text-purple-300 hover:bg-purple-600/20'
                    }`}
                  >
                    下一页 →
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* 主聊天区域 */}
        <div className="flex-1 flex flex-col relative">
          {/* 切换侧边栏按钮 (仅当侧边栏关闭时显示) */}
          {!showHistory && (
            <button
              onClick={toggleHistory}
              className="absolute top-4 left-4 z-10 w-10 h-10 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 border border-white/10 flex items-center justify-center text-purple-300 hover:text-purple-200 transition-all shadow-lg"
              title="打开历史记录"
            >
              <span className="text-xl">💬</span>
            </button>
          )}

          {/* 饮食记录保存通知 */}
          {dietNotification && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 animate-in fade-in slide-in-from-top duration-300">
              <div className="bg-green-600/90 backdrop-blur-sm text-white px-5 py-3 rounded-xl shadow-lg flex items-center gap-3">
                <span className="text-xl">🍽</span>
                <div>
                  <div className="font-medium text-sm">饮食已自动记录</div>
                  <div className="text-xs text-green-100">
                    {dietNotification.total_calories ? `${Math.round(dietNotification.total_calories)} kcal` : ''} · {{'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'snack': '加餐'}[dietNotification.meal_type] || '加餐'}
                  </div>
                </div>
                <button onClick={() => setDietNotification(null)} className="ml-2 text-green-200 hover:text-white">×</button>
              </div>
            </div>
          )}

          {/* 活动记录通知 */}
          {activityNotifications.length > 0 && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 animate-in fade-in slide-in-from-top duration-300">
              <div className="bg-emerald-600/90 backdrop-blur-sm text-white px-5 py-3 rounded-xl shadow-lg">
                <div className="flex items-center justify-between gap-3 mb-1">
                  <div className="font-medium text-sm">已自动记录</div>
                  <button onClick={() => setActivityNotifications([])} className="text-emerald-200 hover:text-white text-lg leading-none">×</button>
                </div>
                <div className="space-y-0.5">
                  {activityNotifications.map((a, idx) => (
                    <div key={idx} className="text-xs text-emerald-100">{a.message}</div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 消息列表 */}
          <div className="flex-1 overflow-y-auto px-4 py-6">
            <div className="max-w-4xl mx-auto space-y-4">
            {messages.length === 0 && !loading && (
              <div className="max-w-3xl mx-auto text-center space-y-6 mt-20">
                <div className="text-6xl">💬</div>
                <h2 className="text-2xl font-bold text-white">你好，我是你的健康顾问</h2>
                <p className="text-slate-400">
                  我了解你的健康数据，可以为你提供个性化的健康建议
                </p>
                <div className="grid grid-cols-2 gap-3 max-w-2xl mx-auto mt-8">
                  {QUICK_QUESTIONS.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(q.text)}
                      className="px-4 py-3 bg-slate-700/50 hover:bg-slate-600/50 rounded-xl text-left transition-colors border border-white/10"
                    >
                      <div className="font-medium text-white">{q.label}</div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map(msg => (
              <div
                key={msg.id}
                className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                {msg.role === 'assistant' && (
                  <div className="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center flex-shrink-0">
                    <span className="text-lg">💬</span>
                  </div>
                )}
                <div
                  className={`max-w-2xl rounded-2xl px-4 py-3 ${
                    msg.role === 'user'
                      ? 'bg-purple-600 text-white'
                      : 'bg-slate-700/50 text-white border border-white/10'
                  }`}
                >
  {msg.role === 'assistant' ? (
                    <div className="text-white text-sm leading-relaxed">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: ({ children }) => <p className="mb-3 last:mb-0 whitespace-pre-wrap">{children}</p>,
                          ul: ({ children }) => <ul className="list-disc ml-5 mb-3 space-y-1.5">{children}</ul>,
                          ol: ({ children }) => <ol className="list-decimal ml-5 mb-3 space-y-1.5">{children}</ol>,
                          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
                          h1: ({ children }) => <h1 className="text-xl font-bold mb-3 mt-4 first:mt-0 text-purple-300">{children}</h1>,
                          h2: ({ children }) => <h2 className="text-lg font-bold mb-2 mt-4 first:mt-0 text-purple-300">{children}</h2>,
                          h3: ({ children }) => <h3 className="text-base font-bold mb-2 mt-3 first:mt-0 text-purple-300">{children}</h3>,
                          strong: ({ children }) => <strong className="font-bold text-purple-200">{children}</strong>,
                          em: ({ children }) => <em className="italic text-slate-300">{children}</em>,
                          code: ({ node, ...props }: any) => {
                            const inline = !props.className?.includes('language-');
                            return inline ? (
                              <code className="px-1.5 py-0.5 bg-slate-800 rounded text-purple-300 font-mono text-xs" {...props} />
                            ) : (
                              <code className="block px-4 py-3 bg-slate-800 rounded-lg overflow-x-auto font-mono text-xs my-2" {...props} />
                            );
                          },
                          pre: ({ children }) => <pre className="bg-slate-800 rounded-lg p-4 overflow-x-auto my-3">{children}</pre>,
                          blockquote: ({ children }) => (
                            <blockquote className="border-l-4 border-purple-500 pl-4 py-2 my-3 italic text-slate-300 bg-slate-800/30 rounded-r">
                              {children}
                            </blockquote>
                          ),
                          table: ({ children }) => (
                            <div className="overflow-x-auto my-3">
                              <table className="min-w-full border-collapse border border-slate-600 rounded-lg overflow-hidden">
                                {children}
                              </table>
                            </div>
                          ),
                          thead: ({ children }) => <thead className="bg-slate-700">{children}</thead>,
                          tbody: ({ children }) => <tbody className="bg-slate-800/30">{children}</tbody>,
                          tr: ({ children }) => <tr className="border-b border-slate-600 last:border-0">{children}</tr>,
                          th: ({ children }) => <th className="border border-slate-600 px-3 py-2 text-left font-semibold text-purple-300">{children}</th>,
                          td: ({ children }) => <td className="border border-slate-600 px-3 py-2">{children}</td>,
                          hr: () => <hr className="my-4 border-slate-600" />,
                          a: ({ children, href }) => (
                            <a href={href} target="_blank" rel="noopener noreferrer" className="text-purple-400 hover:text-purple-300 underline">
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : (
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                  )}
                </div>
              </div>
            ))}

            {loading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center flex-shrink-0">
                  <span className="text-lg">💬</span>
                </div>
                <div className="bg-slate-700/50 rounded-2xl px-4 py-3 border border-white/10">
                  <div className="flex gap-2">
                    <div className="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: '0ms' }}></div>
                    <div className="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: '150ms' }}></div>
                    <div className="w-2 h-2 rounded-full bg-purple-400 animate-bounce" style={{ animationDelay: '300ms' }}></div>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
            </div>
          </div>

          {/* 快捷提问栏 (对话进行中也显示) */}
          {messages.length > 0 && !loading && (
            <div className="px-4 py-2 border-t border-white/10">
              <div className="max-w-4xl mx-auto overflow-x-auto">
                <div className="flex gap-2">
                  {QUICK_QUESTIONS.map((q, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(q.text)}
                      className="px-3 py-1.5 bg-slate-700/50 hover:bg-slate-600/50 rounded-full text-sm whitespace-nowrap transition-colors border border-white/10 text-slate-200 hover:text-white"
                    >
                      {q.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* 输入区域 */}
          <div className="p-4 bg-slate-800/50 border-t border-white/10">
            <div className="max-w-4xl mx-auto flex gap-2 items-center">
              {/* 图片按钮 */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleImageUpload}
              />
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={imageUploading || loading}
                className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all flex-shrink-0 ${
                  imageUploading ? 'bg-purple-600/50 animate-pulse' : 'bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white'
                }`}
                title="拍照/上传食物图片"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </button>
              {/* 语音按钮 */}
              <button
                onClick={handleVoiceToggle}
                disabled={loading}
                className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all flex-shrink-0 ${
                  isRecording
                    ? 'bg-red-500 text-white animate-pulse'
                    : 'bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white'
                }`}
                title={isRecording ? '停止录音' : '语音输入'}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  {isRecording ? (
                    <rect x="6" y="6" width="12" height="12" rx="2" />
                  ) : (
                    <>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
                    </>
                  )}
                </svg>
              </button>
              {/* 文本输入 */}
              <input
                type="text"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isRecording ? '正在录音...' : '输入健康相关问题...'}
                className="flex-1 px-4 py-3 rounded-xl bg-slate-700 border border-white/10 text-white placeholder-slate-300 focus:outline-none focus:ring-2 focus:ring-purple-500"
                disabled={isRecording}
              />
              {/* 发送按钮 */}
              <button
                onClick={() => handleSend()}
                disabled={!inputText.trim() || loading}
                className={`w-11 h-11 rounded-xl flex items-center justify-center transition-all flex-shrink-0 ${
                  inputText.trim() && !loading
                    ? 'bg-purple-600 hover:bg-purple-500 text-white'
                    : 'bg-slate-700 text-slate-400 cursor-not-allowed'
                }`}
              >
                <span className="text-xl">↑</span>
              </button>
            </div>
          </div>
        </div>
    </div>
  );
}
