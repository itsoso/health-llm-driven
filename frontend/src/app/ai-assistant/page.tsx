'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api, chatApi, openclawApi, ChatMessage, Conversation, DietSavedData, ActivitySavedData } from '@/services/api';
import { useToast } from '@/contexts/ToastContext';
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
  { label: '运动完成', text: '我刚运动完，帮我同步Garmin数据并分析本次训练，给出拉伸和恢复建议' },
];

const PROXY_QUICK_QUESTIONS = [
  { label: '你好', text: '你好，你能做什么？' },
  { label: '今日健康', text: '查一下我今天的健康数据' },
  { label: '记录饮水', text: '记录喝水250ml' },
  { label: '健康分析', text: '分析我最近的健康趋势' },
];

export default function AIAssistantPage() {
  const router = useRouter();
  const { showToast } = useToast();
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
  const [planCreatedNotification, setPlanCreatedNotification] = useState<{message: string; planId?: number} | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [imageUploading] = useState(false);
  const [chatMode, setChatMode] = useState<'health' | 'openclaw'>('health');
  const itemsPerPage = 10;
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamBufferRef = useRef('');
  const flushTimerRef = useRef<NodeJS.Timeout | null>(null);

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
      const response = chatMode === 'openclaw'
        ? await openclawApi.getConversations()
        : await chatApi.getConversations();
      setConversations(response.data || []);
    } catch (e) {
      console.error('加载对话列表失败:', e);
    }
  }, [chatMode]);

  // 加载指定对话的消息
  const loadConversation = useCallback(async (convId: number, convMode?: string) => {
    try {
      const isOpenClaw = convMode === 'openclaw' || chatMode === 'openclaw';
      const response = isOpenClaw
        ? await openclawApi.getConversation(convId)
        : await chatApi.getConversation(convId);
      setMessages(response.data.messages || []);
      setConversationId(convId);
      if (convMode) setChatMode(convMode as 'health' | 'openclaw');
    } catch (e) {
      console.error('加载对话失败:', e);
      showToast('加载失败', 'error');
    }
  }, [chatMode]);

  useEffect(() => {
    const token = localStorage.getItem('auth_token');
    if (!token) {
      router.push('/login');
      return;
    }
    loadConversations();
  }, [loadConversations, router]);

  // 检测是否是运动完成意图
  const isPostWorkoutMessage = (msg: string): boolean => {
    const keywords = ['跑完了', '运动结束', '锻炼完了', '训练结束', '跑步结束', '运动完成',
      '刚跑完', '刚运动完', '刚锻炼完', '刚练完', '骑完车', '游完泳', '运动完了',
      '同步Garmin', '同步garmin', '分析本次训练', '分析刚才的运动'];
    return keywords.some(kw => msg.includes(kw));
  };

  // 处理流式完成事件中的通知（饮食、活动、提醒等）
  const handleDoneEvent = (result: any) => {
    // 运动分析结果作为追加对话消息展示
    if (result.workout_analysis && result.workout_analysis.content) {
      const analysisMsg: ChatMessage = {
        id: result.workout_analysis.message_id,
        role: 'assistant',
        content: result.workout_analysis.content,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, analysisMsg]);
    }

    // 显示饮食记录保存通知
    if (result.diet_saved && result.diet_data) {
      setDietNotification(result.diet_data);
      setTimeout(() => setDietNotification(null), 5000);
    }

    // 显示活动记录通知
    if (result.activities_saved && result.activities) {
      const saved = result.activities.filter((a: ActivitySavedData) => a.status !== 'already_exists');
      const planResult = saved.find((a: ActivitySavedData & {type?: string; plan_id?: number}) => a.type === 'create_plan') as (ActivitySavedData & {type?: string; plan_id?: number}) | undefined;
      if (planResult) {
        setPlanCreatedNotification({ message: planResult.message, planId: planResult.plan_id });
        setTimeout(() => setPlanCreatedNotification(null), 8000);
      }
      const nonPlan = saved.filter((a: ActivitySavedData & {type?: string}) => a.type !== 'create_plan');
      if (nonPlan.length > 0) {
        setActivityNotifications(nonPlan);
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
  };

  // 发送消息（流式优先，降级到非流式）
  const handleSend = async (text?: string, imageBase64?: string, imageType?: string) => {
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

    // 检测运动完成意图 - 如果匹配，并行触发分析 API（仅健康助理模式）
    const isWorkoutDone = chatMode === 'health' && isPostWorkoutMessage(msg);
    let workoutAnalysisPromise: Promise<any> | null = null;
    if (isWorkoutDone) {
      workoutAnalysisPromise = api.post('/workout/post-run-analyze?format=full').catch(() => {
        return null;
      });
    }

    // AI 消息占位 ID（用于流式更新）
    const aiMsgId = Date.now() + 1;

    try {
      // 流式模式
      const aiPlaceholder: ChatMessage = {
        id: aiMsgId,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, aiPlaceholder]);

      let gotDone = false;
      let firstToken = true;
      const streamIterator = chatMode === 'openclaw'
        ? openclawApi.streamMessage(msg, conversationId)
        : chatApi.streamMessage(msg, conversationId, undefined, imageBase64, imageType);
      for await (const event of streamIterator) {
        if (event.event === 'token') {
          if (firstToken) {
            firstToken = false;
            setLoading(false);
          }
          // 缓冲 token，批量更新减少渲染次数
          streamBufferRef.current += event.data.content;
          if (!flushTimerRef.current) {
            flushTimerRef.current = setTimeout(() => {
              const buffered = streamBufferRef.current;
              streamBufferRef.current = '';
              flushTimerRef.current = null;
              setMessages(prev => prev.map(m =>
                m.id === aiMsgId ? { ...m, content: m.content + buffered } : m
              ));
            }, 50);
          }
        } else if (event.event === 'done') {
          gotDone = true;
          const result = event.data;
          // 更新会话 ID
          if (!conversationId && result.conversation_id) {
            setConversationId(result.conversation_id);
          }
          // 更新消息 ID 为真实数据库 ID
          if (result.message_id) {
            setMessages(prev => prev.map(m =>
              m.id === aiMsgId ? { ...m, id: result.message_id } : m
            ));
          }
          if (chatMode === 'health') handleDoneEvent(result);
        } else if (event.event === 'error') {
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, content: event.data.message || '服务异常，请重试' } : m
          ));
        }
      }

      // 如果流没有返回 done 事件且消息为空，显示错误
      if (!gotDone) {
        setMessages(prev => {
          const aiMsg = prev.find(m => m.id === aiMsgId);
          if (aiMsg && !aiMsg.content) {
            return prev.map(m =>
              m.id === aiMsgId ? { ...m, content: '抱歉，响应异常中断，请重试。' } : m
            );
          }
          return prev;
        });
      }

      // 刷新剩余缓冲
      if (streamBufferRef.current) {
        if (flushTimerRef.current) {
          clearTimeout(flushTimerRef.current);
          flushTimerRef.current = null;
        }
        const remaining = streamBufferRef.current;
        streamBufferRef.current = '';
        setMessages(prev => prev.map(m =>
          m.id === aiMsgId ? { ...m, content: m.content + remaining } : m
        ));
      }

      // 如果前端触发了运动分析，等待结果并追加为消息
      if (workoutAnalysisPromise && !gotDone) {
        // fallback: 没收到 done 事件时跳过
      } else if (workoutAnalysisPromise) {
        setLoading(false);
        const loadingMsgId = Date.now() + 2;
        const loadingMsg: ChatMessage = {
          id: loadingMsgId,
          role: 'assistant',
          content: '正在同步 Garmin 数据并进行多模型分析，请稍等约 30-60 秒...',
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, loadingMsg]);

        const analysisResp = await workoutAnalysisPromise;
        if (analysisResp?.data?.success) {
          const data = analysisResp.data;
          const workout = data.workout || {};
          const analysis = data.multi_model_analysis || {};

          const parts: string[] = [];
          if (workout.name) parts.push(workout.name);
          if (workout.distance_km) parts.push(`${workout.distance_km}km`);
          if (workout.duration_min) parts.push(`${workout.duration_min}分钟`);
          if (workout.pace) parts.push(`配速${workout.pace}`);
          const workoutLine = parts.join(' | ');

          let content = `**运动分析完成：${workoutLine}**\n\n`;
          if (analysis.aggregation) {
            content += `**综合分析：**\n${analysis.aggregation}\n\n`;
          }
          if (analysis.model_results?.length > 0) {
            content += '**各模型视角：**\n\n';
            for (const mr of analysis.model_results) {
              const name = (mr.site || '').replace('lb-', '').replace(/-/g, ' ');
              if (mr.content) {
                const preview = mr.content.length > 400 ? mr.content.slice(0, 400) + '...' : mr.content;
                content += `**${name}**:\n${preview}\n\n---\n\n`;
              }
            }
          }

          setMessages(prev => prev.map(m =>
            m.id === loadingMsgId ? { ...m, content } : m
          ));
        } else {
          const errMsg = analysisResp?.data?.message || '运动分析未完成，可能 Garmin 数据尚未同步。请稍后再试。';
          setMessages(prev => prev.map(m =>
            m.id === loadingMsgId ? { ...m, content: errMsg } : m
          ));
        }
      }

      // 重新加载对话列表
      loadConversations();
    } catch (e: any) {
      // 流式失败 → 降级到非流式
      console.warn('流式请求失败，降级到非流式模式:', e);
      // 先移除空的 AI 占位消息
      setMessages(prev => prev.filter(m => m.id !== aiMsgId));
      try {
        const response = await chatApi.sendMessage(msg, conversationId, undefined, imageBase64, imageType);
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
        handleDoneEvent(result);
        loadConversations();
      } catch {
        const errorMsg: ChatMessage = {
          id: Date.now() + 3,
          role: 'assistant',
          content: '抱歉，请求失败了，请稍后再试。',
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, errorMsg]);
      }
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
      const deleteApi = chatMode === 'openclaw' ? openclawApi : chatApi;
      await deleteApi.deleteConversation(convId);
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (conversationId === convId) {
        handleNewChat();
      }
      showToast('已删除', 'success');
    } catch (e) {
      showToast('删除失败', 'error');
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
              // 先尝试语音快捷指令
              try {
                const voiceRes = await chatApi.voiceCommand(text);
                if (voiceRes.data.matched) {
                  // 快捷指令执行成功，显示结果通知
                  showToast(voiceRes.data.message || '指令已执行', 'success');
                  return;
                }
              } catch (e) {
                console.warn('语音指令检测失败，回退到输入框:', e);
              }
              // 未匹配快捷指令，填入输入框
              setInputText(prev => prev + text);
            }
          };
        } catch (err) {
          console.error('语音转文字失败:', err);
          showToast('语音识别失败，请重试', 'error');
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error('无法访问麦克风:', err);
      showToast('无法访问麦克风，请检查浏览器权限', 'warning');
    }
  };

  // 图片上传处理 - 直接发送给 OpenClaw 识别
  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 重置 input 以便再次选择同一文件
    e.target.value = '';

    try {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onloadend = async () => {
        const base64 = (reader.result as string).split(',')[1];
        const imgType = file.type?.replace('image/', '') || 'jpeg';
        const msg = inputText.trim() || '请识别这张图片中的食物，帮我分析营养并记录';
        handleSend(msg, base64, imgType);
      };
    } catch (err) {
      console.error('读取图片失败:', err);
    }
  };

  return (
    <div className="fixed inset-0 top-16 bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex overflow-hidden">
      {/* 历史对话侧栏 */}
      {showHistory && (
        <div className="w-80 bg-slate-800/80 border-r border-purple-500/30 flex flex-col shadow-lg">
          {/* 侧边栏顶部 - 新建对话按钮 + 收起按钮 */}
          <div className="p-3 border-b border-purple-500/30 bg-slate-900/50 flex items-center gap-2">
            <button
              onClick={handleNewChat}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-purple-600 hover:bg-purple-500 transition-all text-white font-medium shadow-lg"
            >
              <span className="text-xl">+</span>
              <span>新建对话</span>
            </button>
            <button
              onClick={toggleHistory}
              className="w-10 h-10 rounded-lg bg-slate-700/60 hover:bg-slate-600/80 border border-white/10 flex items-center justify-center text-slate-300 hover:text-white transition-all flex-shrink-0"
              title="收起侧边栏"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7M18 19l-7-7 7-7" />
              </svg>
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
                    <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-sm ${
                      chatMode === 'openclaw' ? 'bg-blue-600/30' : 'bg-purple-600/30'
                    }`}>
                      {chatMode === 'openclaw' ? (
                        <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-blue-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                      ) : '💬'}
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
          {/* 顶部栏：侧边栏按钮 + 模式切换 */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-white/10 bg-slate-800/30">
            <div className="flex items-center gap-2">
              {!showHistory && (
                <button
                  onClick={toggleHistory}
                  className="w-9 h-9 rounded-lg bg-slate-700/60 hover:bg-slate-600/80 border border-white/10 flex items-center justify-center text-purple-300 hover:text-purple-200 transition-all"
                  title="打开历史记录"
                >
                  <span className="text-lg">💬</span>
                </button>
              )}
            </div>
            {/* 模式切换 */}
            <div className="flex rounded-xl bg-slate-700/50 border border-white/10 p-0.5">
              <button
                onClick={() => { if (chatMode !== 'health') { setChatMode('health'); setMessages([]); setConversationId(undefined); } }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  chatMode === 'health'
                    ? 'bg-purple-600 text-white shadow-lg'
                    : 'text-slate-300 hover:text-white'
                }`}
              >
                健康助理
              </button>
              <button
                onClick={() => { if (chatMode !== 'openclaw') { setChatMode('openclaw'); setMessages([]); setConversationId(undefined); } }}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                  chatMode === 'openclaw'
                    ? 'bg-blue-600 text-white shadow-lg'
                    : 'text-slate-300 hover:text-white'
                }`}
              >
                OpenClaw
              </button>
            </div>
            <div className="w-9" /> {/* spacer for centering */}
          </div>

          {/* 饮食记录保存通知 (仅健康助理模式) */}
          {chatMode === 'health' && dietNotification && (
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

          {/* 活动记录通知 (仅健康助理模式) */}
          {chatMode === 'health' && activityNotifications.length > 0 && (
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

          {/* 智能计划创建通知 (仅健康助理模式) */}
          {chatMode === 'health' && planCreatedNotification && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 z-20 animate-in fade-in slide-in-from-top duration-300 w-80">
              <div className="bg-blue-600/95 backdrop-blur-sm text-white px-5 py-3 rounded-xl shadow-lg">
                <div className="flex items-center justify-between gap-3 mb-1">
                  <div className="font-medium text-sm flex items-center gap-2">
                    <span>📋</span>
                    智能计划已生成
                  </div>
                  <button onClick={() => setPlanCreatedNotification(null)} className="text-blue-200 hover:text-white text-lg leading-none">×</button>
                </div>
                <div className="text-xs text-blue-100 mb-2">{planCreatedNotification.message}</div>
                <button
                  onClick={() => { setPlanCreatedNotification(null); router.push('/smart-plan'); }}
                  className="w-full text-xs py-1.5 bg-white/20 hover:bg-white/30 rounded-lg text-center font-medium transition-colors"
                >
                  前往「智能计划」查看 →
                </button>
              </div>
            </div>
          )}

          {/* 消息列表 */}
          <div className="flex-1 overflow-y-auto px-4 py-6">
            <div className="max-w-4xl mx-auto space-y-4">
            {messages.length === 0 && !loading && (
              <div className="max-w-3xl mx-auto text-center space-y-6 mt-20">
                <div className="text-6xl">{chatMode === 'openclaw' ? (
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-16 h-16 mx-auto text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                ) : '💬'}</div>
                <h2 className="text-2xl font-bold text-white">
                  {chatMode === 'openclaw' ? 'OpenClaw 对话模式' : '你好，我是你的智能助理'}
                </h2>
                <p className="text-slate-400">
                  {chatMode === 'openclaw'
                    ? '直接与 OpenClaw 对话，支持健康数据查询、记录和分析'
                    : '我了解你的健康数据，可以为你提供个性化的健康建议'}
                </p>
                <div className="grid grid-cols-2 gap-3 max-w-2xl mx-auto mt-8">
                  {(chatMode === 'openclaw' ? PROXY_QUICK_QUESTIONS : QUICK_QUESTIONS).map((q, idx) => (
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
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
                    </svg>
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
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
                  </svg>
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
                  {(chatMode === 'openclaw' ? PROXY_QUICK_QUESTIONS : QUICK_QUESTIONS).map((q, idx) => (
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
              {/* 图片按钮 (仅健康助理模式) */}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleImageUpload}
              />
              {chatMode === 'health' && (
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
              )}
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
                placeholder={isRecording ? '正在录音...' : '有什么可以帮你的...'}
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
