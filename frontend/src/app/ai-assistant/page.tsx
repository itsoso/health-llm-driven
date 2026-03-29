'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api, chatApi, openclawApi, sharedApi, feedbackApi, ChatMessage, Conversation, DietSavedData, ActivitySavedData } from '@/services/api';

interface InsightItem { id: number; notification_type: string; title: string; content: string; created_at: string }

function InsightsCard({ insights, accentClass }: { insights: InsightItem[]; accentClass: string }) {
  const CONFIG: Record<string, { icon: string; color: string }> = {
    health_alert: { icon: '\u26A0', color: 'border-red-500/30 bg-red-500/10' },
    morning_summary: { icon: '\u2600', color: 'border-emerald-500/30 bg-emerald-500/10' },
    daily_insights: { icon: '\u2139', color: 'border-blue-500/30 bg-blue-500/10' },
    trend_report: { icon: '\u2191', color: 'border-cyan-500/30 bg-cyan-500/10' },
    family_daily_brief: { icon: '\u2764', color: 'border-purple-500/30 bg-purple-500/10' },
  };
  // 按 notification_type 去重（保留最新的）
  const seen = new Set<string>();
  const unique = insights.filter(ins => {
    if (seen.has(ins.notification_type)) return false;
    seen.add(ins.notification_type);
    return true;
  });
  return (
    <div className="rounded-[30px] border border-white/10 bg-slate-950/60 p-5 shadow-[0_20px_60px_rgba(2,6,23,0.35)] backdrop-blur-xl">
      <div className={`text-[10px] uppercase tracking-[0.3em] ${accentClass}`}>{"today\u2019s insights"}</div>
      <div className="mt-3 space-y-3">
        {unique.map(ins => {
          const cfg = CONFIG[ins.notification_type] || { icon: '*', color: 'border-white/10 bg-white/5' };
          return (
            <div key={ins.id} className={`rounded-xl border p-3 ${cfg.color}`}>
              <div className="flex items-start gap-2">
                <span className="text-base shrink-0 w-5 text-center" aria-hidden="true">{cfg.icon}</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-white">{ins.title}</div>
                  <div className="mt-1 text-xs leading-5 text-slate-300 line-clamp-2">{ins.content}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
import { useAuth } from '@/contexts/AuthContext';
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

type QuickQuestion = {
  label: string;
  text: string;
  eyebrow: string;
  summary: string;
};

const DISPLAY_FONT_STACK = '"Iowan Old Style", "Noto Serif SC", "Songti SC", serif';
const UI_FONT_STACK = '"Avenir Next", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';

// 静态 fallback（API 加载前或失败时使用）
const DEFAULT_QUESTIONS: QuickQuestion[] = [
  { label: '今日概览', text: '查一下我今天的健康数据概览', eyebrow: '实时查询', summary: '拉取今天的关键数据、打卡状态和待办提醒。' },
  { label: '运动建议', text: '根据我的身体数据和天气，今天适合做什么运动？', eyebrow: '训练安排', summary: '结合恢复状态、天气和最近训练，给出最合适的建议。' },
  { label: '睡眠分析', text: '帮我分析一下最近的睡眠质量', eyebrow: '恢复质量', summary: '把睡眠、压力和日间表现放到同一个结论里看。' },
  { label: '饮食建议', text: '根据我的健康目标，今天午餐吃什么好？', eyebrow: '营养策略', summary: '围绕目标和今日已摄入，推荐具体的餐食方案。' },
  { label: '记录饮水', text: '记录喝水250ml', eyebrow: '快速记录', summary: '一句话完成记录，不用跳页面。' },
  { label: '运动完成', text: '我刚运动完，帮我同步Garmin数据并分析本次训练', eyebrow: '即时分析', summary: '触发 Garmin 同步和恢复建议。' },
];

const UNIFIED_METRICS = [
  {
    label: '技能驱动',
    value: '查询 / 记录 / 分析',
    description: '一句话描述目标，AI 自动选择合适的技能组合完成任务。',
  },
  {
    label: '数据感知',
    value: '语音 / 图片 / 文件',
    description: '同一输入栏就能完成记录、分析和补充说明。',
  },
  {
    label: '行动建议',
    value: '饮食 / 运动 / 节奏',
    description: '把建议收敛成可执行动作，而不是泛泛健康话术。',
  },
];

const STYLE = {
  eyebrow: 'Health AI',
  title: '健康助理',
  description: '把记录、分析、提醒和训练恢复收拢到一个会话里，用最少的跳转完成今天的健康决策。',
  support: '支持图片、文件、语音',
  subSupport: '也可以直接说"我刚运动完"，自动触发 Garmin 同步和恢复分析。',
  panelClass: 'from-slate-950/95 via-slate-900/90 to-emerald-950/80',
  badgeClass: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-100',
  bubbleClass: 'bg-slate-900/80 border border-emerald-400/15 text-white shadow-[0_24px_80px_rgba(4,120,87,0.12)]',
  userBubbleClass: 'bg-gradient-to-br from-emerald-500 via-cyan-500 to-sky-500 text-white shadow-[0_20px_50px_rgba(20,184,166,0.35)]',
  accentTextClass: 'text-emerald-200',
  accentBorderClass: 'border-emerald-400/20',
  chipClass: 'border border-emerald-400/15 bg-emerald-400/10 text-emerald-50',
  subtleClass: 'text-emerald-100/75',
};

export default function AIAssistantPage() {
  const router = useRouter();
  const { user } = useAuth();
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
  const [imageUploading, setImageUploading] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [pendingImage, setPendingImage] = useState<{base64: string; type: string} | null>(null);
  const [pendingFile, setPendingFile] = useState<{base64: string; name: string} | null>(null);
  // Unified OpenClaw mode — no more dual mode switching
  const [messageFeedback, setMessageFeedback] = useState<Record<number, 1 | 5>>({});
  const [doneMessageIds, setDoneMessageIds] = useState<Set<number>>(new Set());
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
      const response = await openclawApi.getConversations();
      setConversations(response.data || []);
    } catch (e) {
      console.error('加载对话列表失败:', e);
    }
  }, []);

  // 加载指定对话的消息
  const loadConversation = useCallback(async (convId: number, _convMode?: string) => {
    try {
      const response = await openclawApi.getConversation(convId);
      const msgs = response.data.messages || [];
      setMessages(msgs);
      setDoneMessageIds(new Set(msgs.filter((m: ChatMessage) => m.role === 'assistant').map((m: ChatMessage) => m.id)));
      setConversationId(convId);
    } catch (e) {
      console.error('加载对话失败:', e);
      showToast('加载失败', 'error');
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
    const hasAttachment = pendingImage || pendingFile;
    if (!msg && !hasAttachment) return;
    // 如果有待发送图片但未传入参数，使用 pendingImage
    const finalImageBase64 = imageBase64 || pendingImage?.base64;
    const finalImageType = imageType || pendingImage?.type;
    const finalFileBase64 = pendingFile?.base64;
    const finalFileName = pendingFile?.name;
    const finalMsg = msg || (finalImageBase64 ? '请看这张图片，帮我分析一下' : (finalFileBase64 ? `请分析这个文件：${finalFileName}` : ''));
    if (!finalMsg) return;

    setInputText('');
    clearPendingAttachment();

    // 乐观更新：先显示用户消息（附带图片/文件预览）
    const tempUserMsg: ChatMessage = {
      id: Date.now(),
      role: 'user',
      content: finalMsg,
      created_at: new Date().toISOString(),
      image_preview: finalImageBase64 ? `data:image/${finalImageType || 'jpeg'};base64,${finalImageBase64}` : undefined,
      file_name: finalFileName,
    };
    setMessages(prev => [...prev, tempUserMsg]);
    setLoading(true);

    // 检测运动完成意图 - 如果匹配，并行触发分析 API（仅健康助理模式）
    const isWorkoutDone = isPostWorkoutMessage(finalMsg);
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
      // 等待进度提示：超过 8 秒没收到 token 时更新占位消息
      const waitTimer = setTimeout(() => {
        if (firstToken) {
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, content: '⏳ AI 正在思考中，复杂分析可能需要 1-2 分钟...' } : m
          ));
        }
      }, 8000);
      const waitTimer2 = setTimeout(() => {
        if (firstToken) {
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, content: '⏳ 正在调用多个 AI 模型进行深度分析，请耐心等待...' } : m
          ));
        }
      }, 30000);
      // 每次调用独立的缓冲区，支持并行流
      const buf = { content: '', timer: null as NodeJS.Timeout | null };
      const streamIterator = openclawApi.streamMessage(finalMsg, conversationId, finalImageBase64, finalImageType, finalFileBase64, finalFileName);
      for await (const event of streamIterator) {
        if (event.event === 'token') {
          if (firstToken) {
            firstToken = false;
            clearTimeout(waitTimer);
            clearTimeout(waitTimer2);
            // 清除等待提示，用真实内容替换
            setMessages(prev => prev.map(m =>
              m.id === aiMsgId ? { ...m, content: '' } : m
            ));
            setLoading(false);
          }
          // 缓冲 token，批量更新减少渲染次数
          buf.content += event.data.content;
          if (!buf.timer) {
            buf.timer = setTimeout(() => {
              const buffered = buf.content;
              buf.content = '';
              buf.timer = null;
              setMessages(prev => prev.map(m =>
                m.id === aiMsgId ? { ...m, content: m.content + buffered } : m
              ));
            }, 50);
          }
        } else if (event.event === 'done') {
          gotDone = true;
          // 先刷新缓冲区（done 事件会更改 message id，必须在此之前刷新）
          if (buf.content) {
            if (buf.timer) {
              clearTimeout(buf.timer);
              buf.timer = null;
            }
            const buffered = buf.content;
            buf.content = '';
            setMessages(prev => prev.map(m =>
              m.id === aiMsgId ? { ...m, content: m.content + buffered } : m
            ));
          }
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
            setDoneMessageIds(prev => new Set(prev).add(result.message_id));
          }
          handleDoneEvent(result);
        } else if (event.event === 'error') {
          clearTimeout(waitTimer);
          clearTimeout(waitTimer2);
          const errText = event.data.message || '';
          const friendlyMsg = errText.includes('timeout') || errText.includes('Timeout')
            ? '⏱ 分析超时了，可能是数据量较大。请稍后重试，或换一个更具体的问题。'
            : errText.includes('Gateway') || errText.includes('502') || errText.includes('503')
            ? '🔧 AI 服务暂时繁忙，请稍后再试。'
            : errText || '抱歉，出了点问题，请重试。';
          setMessages(prev => prev.map(m =>
            m.id === aiMsgId ? { ...m, content: friendlyMsg } : m
          ));
        }
      }

      clearTimeout(waitTimer);
      clearTimeout(waitTimer2);

      // 如果流没有返回 done 事件且消息为空，显示错误
      if (!gotDone) {
        setMessages(prev => {
          const aiMsg = prev.find(m => m.id === aiMsgId);
          if (aiMsg && (!aiMsg.content || aiMsg.content.startsWith('⏳'))) {
            return prev.map(m =>
              m.id === aiMsgId ? { ...m, content: '抱歉，OpenClaw 暂时无法响应，请稍后再试。' } : m
            );
          }
          return prev;
        });
      }

      // 刷新剩余缓冲
      if (buf.content) {
        if (buf.timer) {
          clearTimeout(buf.timer);
          buf.timer = null;
        }
        const remaining = buf.content;
        buf.content = '';
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
      console.warn('流式请求失败:', e);
      setMessages(prev => prev.map(m =>
        m.id === aiMsgId ? { ...m, content: '抱歉，请求失败了，请稍后再试。' } : m
      ));
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
      await openclawApi.deleteConversation(convId);
      setConversations(prev => prev.filter(c => c.id !== convId));
      if (conversationId === convId) {
        handleNewChat();
      }
      showToast('已删除', 'success');
    } catch (e) {
      showToast('删除失败', 'error');
    }
  };

  // 分享对话
  const handleShareConversation = async (convId: number) => {
    try {
      const sourceType = 'openclaw';
      const res = await sharedApi.createShare(convId, sourceType);
      const url = res.data.share_url;
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(url);
        showToast('分享链接已复制到剪贴板', 'success');
      } else {
        prompt('分享链接：', url);
      }
    } catch (e) {
      showToast('分享失败', 'error');
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

  // 文件/图片上传处理
  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 重置 input 以便再次选择同一文件
    e.target.value = '';

    const isImage = file.type.startsWith('image/');
    setImageUploading(true);
    try {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onloadend = () => {
        const dataUrl = reader.result as string;
        const base64 = dataUrl.split(',')[1];
        if (isImage) {
          const imgType = file.type.replace('image/', '') || 'jpeg';
          setImagePreview(dataUrl);
          setPendingImage({ base64, type: imgType });
        } else {
          setPendingFile({ base64, name: file.name });
        }
        setImageUploading(false);
      };
    } catch (err) {
      console.error('读取文件失败:', err);
      setImageUploading(false);
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        e.preventDefault();
        const file = items[i].getAsFile();
        if (!file) return;
        setImageUploading(true);
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onloadend = () => {
          const dataUrl = reader.result as string;
          const base64 = dataUrl.split(',')[1];
          const imgType = file.type.replace('image/', '') || 'png';
          setImagePreview(dataUrl);
          setPendingImage({ base64, type: imgType });
          setImageUploading(false);
        };
        return;
      }
    }
  };

  const clearPendingAttachment = () => {
    setImagePreview(null);
    setPendingImage(null);
    setPendingFile(null);
  };

  const modeCopy = STYLE;
  const [dynamicQuestions, setDynamicQuestions] = useState<QuickQuestion[]>(DEFAULT_QUESTIONS);
  const [insights, setInsights] = useState<Array<{id: number; notification_type: string; title: string; content: string; created_at: string}>>([]);

  // 加载动态快速问题 + 今日洞察
  useEffect(() => {
    api.get('/quick-questions/me?limit=6').then(res => {
      if (res.data && Array.isArray(res.data) && res.data.length > 0) {
        setDynamicQuestions(res.data);
      }
    }).catch(() => {});

    // 加载最近的 AI 洞察（通知日志）
    api.get('/notification/logs?limit=5').then(res => {
      const logs = res.data?.logs || res.data || [];
      if (Array.isArray(logs)) {
        // 只展示有价值的类型，排除重复的睡眠提醒
        const valuable = logs.filter((l: any) =>
          ['morning_summary', 'health_alert', 'daily_insights', 'trend_report', 'family_daily_brief'].includes(l.notification_type)
        );
        setInsights(valuable.slice(0, 3));
      }
    }).catch(() => {});
  }, []);

  const activeQuickQuestions = dynamicQuestions;
  const activeMetrics = UNIFIED_METRICS;
  const handleFeedback = async (msgId: number, rating: 1 | 5) => {
    if (!conversationId) return;
    const prev = messageFeedback[msgId];
    if (prev === rating) return; // 已经点过相同的
    setMessageFeedback(f => ({ ...f, [msgId]: rating }));
    try {
      await feedbackApi.submit({
        conversation_type: 'openclaw',
        conversation_id: conversationId,
        message_id: msgId,
        rating,
      });
    } catch {
      // 静默失败，不影响用户体验
    }
  };

  const visibleMessages = messages.filter(m => !(m.role === 'assistant' && !m.content));

  return (
    <div className="fixed inset-x-0 bottom-0 top-16 overflow-hidden" style={{ fontFamily: UI_FONT_STACK }}>
      <div className="absolute inset-0 bg-gradient-to-br from-[#04111f] via-[#0b1b24] to-[#041428]" />
      <div
        className="absolute inset-0 opacity-70"
        style={{
          backgroundImage: 'radial-gradient(circle at 16% 14%, rgba(16,185,129,0.24), transparent 30%), radial-gradient(circle at 86% 16%, rgba(45,212,191,0.18), transparent 30%), linear-gradient(to right, rgba(148,163,184,0.07) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.07) 1px, transparent 1px)',
          backgroundSize: 'auto, auto, 56px 56px, 56px 56px',
        }}
      />
      <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-slate-950 via-slate-950/50 to-transparent" />

      <div className="relative flex h-full overflow-hidden">
        {showHistory && (
          <aside className="flex w-[330px] shrink-0 flex-col border-r border-white/10 bg-slate-950/65 backdrop-blur-2xl">
            <div className="border-b border-white/10 px-4 py-4">
              <div className="flex items-center gap-3">
                <button
                  onClick={handleNewChat}
                  className="flex flex-1 items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/10 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-white/15"
                >
                  <span className="text-lg leading-none">+</span>
                  新建对话
                </button>
                <button
                  onClick={toggleHistory}
                  className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-slate-300 transition-all hover:bg-white/10 hover:text-white"
                  title="收起侧边栏"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7M18 19l-7-7 7-7" />
                  </svg>
                </button>
              </div>

              <div className="mt-5">
                <div className={`mb-1 text-[10px] uppercase tracking-[0.32em] ${modeCopy.accentTextClass}`}>Conversation archive</div>
                <h2 className="text-lg text-white" style={{ fontFamily: DISPLAY_FONT_STACK }}>会话档案</h2>
                <p className="mt-1 text-sm text-slate-400">按标题或最后一条消息快速回到上下文。</p>
              </div>
            </div>

            <div className="border-b border-white/10 px-4 py-4">
              <div className="relative">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setCurrentPage(1);
                  }}
                  placeholder="搜索对话..."
                  className="w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3 pl-11 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-white/20"
                />
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500">⌕</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-3 py-3">
              {conversations.length === 0 ? (
                <div className="rounded-[28px] border border-dashed border-white/10 bg-white/5 px-6 py-10 text-center text-slate-400">
                  <div className="text-4xl">◌</div>
                  <div className="mt-3 text-sm">还没有历史对话</div>
                </div>
              ) : paginatedConversations.length === 0 ? (
                <div className="rounded-[28px] border border-dashed border-white/10 bg-white/5 px-6 py-10 text-center text-slate-400">
                  <div className="text-4xl">⌕</div>
                  <div className="mt-3 text-sm">没有找到匹配结果</div>
                </div>
              ) : (
                <div className="space-y-2">
                  {paginatedConversations.map(conv => (
                    <button
                      key={conv.id}
                      onClick={() => loadConversation(conv.id)}
                      className={`group w-full rounded-[26px] border px-4 py-4 text-left transition-all ${
                        conv.id === conversationId
                          ? `border-white/15 bg-white/10 shadow-[0_20px_50px_rgba(15,23,42,0.35)] ${modeCopy.accentTextClass}`
                          : 'border-transparent bg-white/[0.03] hover:border-white/10 hover:bg-white/[0.06]'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${modeCopy.badgeClass}`}>
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m6-6H6" /></svg>
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="line-clamp-2 text-sm font-medium leading-6 text-white">{conv.title}</div>
                          {conv.last_message && (
                            <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">{conv.last_message}</div>
                          )}
                        </div>
                      </div>
                      <div className="mt-3 flex items-center justify-between">
                        <span className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
                          #{conv.id}
                        </span>
                        <div className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleShareConversation(conv.id);
                            }}
                            className="text-xs text-slate-400 transition-colors hover:text-white"
                            title="分享对话"
                          >
                            分享
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteConversation(conv.id);
                            }}
                            className="text-xs text-slate-400 transition-colors hover:text-red-300"
                            title="删除对话"
                          >
                            删除
                          </button>
                        </div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {filteredConversations.length > itemsPerPage && (
              <div className="border-t border-white/10 px-4 py-3">
                <div className="flex items-center justify-between text-xs text-slate-400">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="rounded-full border border-white/10 px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    上一页
                  </button>
                  <span>{currentPage} / {totalPages}</span>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="rounded-full border border-white/10 px-3 py-1.5 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    下一页
                  </button>
                </div>
              </div>
            )}
          </aside>
        )}

        <section className="relative flex min-w-0 flex-1 flex-col">
          <div className="border-b border-white/10 bg-slate-950/45 backdrop-blur-2xl">
            <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-4">
              <div className="flex min-w-0 items-center gap-3">
                {!showHistory && (
                  <button
                    onClick={toggleHistory}
                    className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-slate-300 transition-all hover:bg-white/10 hover:text-white"
                    title="打开历史记录"
                  >
                    <span className="text-lg leading-none">☰</span>
                  </button>
                )}
                <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-[18px] ${modeCopy.badgeClass}`}>
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m6-6H6" /><path strokeLinecap="round" strokeLinejoin="round" d="M7.5 12a4.5 4.5 0 019-0" opacity="0.4" /></svg>
                </div>
                <div className="min-w-0">
                  <div className={`mb-1 text-[10px] uppercase tracking-[0.34em] ${modeCopy.accentTextClass}`}>{modeCopy.eyebrow}</div>
                  <div className="truncate text-sm text-white">{modeCopy.description}</div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleNewChat}
                  className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white transition-all hover:bg-white/10"
                >
                  新对话
                </button>
                {conversationId && visibleMessages.length > 0 && (
                  <button
                    onClick={() => handleShareConversation(conversationId)}
                    className="rounded-2xl border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white transition-all hover:bg-white/10"
                    title="分享对话"
                  >
                    分享
                  </button>
                )}
              </div>
            </div>
          </div>

          {dietNotification && (
            <div className="absolute left-1/2 top-5 z-20 w-[min(92vw,420px)] -translate-x-1/2 animate-in fade-in slide-in-from-top duration-300">
              <div className="rounded-[24px] border border-emerald-300/20 bg-emerald-500/90 px-5 py-4 text-white shadow-2xl backdrop-blur-xl">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold">饮食已自动记录</div>
                    <div className="mt-1 text-xs text-emerald-50/90">
                      {dietNotification.total_calories ? `${Math.round(dietNotification.total_calories)} kcal` : ''} · {{ breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' }[dietNotification.meal_type] || '加餐'}
                    </div>
                  </div>
                  <button onClick={() => setDietNotification(null)} className="text-emerald-50/80 transition-colors hover:text-white">×</button>
                </div>
              </div>
            </div>
          )}

          {activityNotifications.length > 0 && (
            <div className="absolute left-1/2 top-5 z-20 w-[min(92vw,420px)] -translate-x-1/2 animate-in fade-in slide-in-from-top duration-300">
              <div className="rounded-[24px] border border-cyan-300/20 bg-cyan-500/90 px-5 py-4 text-white shadow-2xl backdrop-blur-xl">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold">已自动记录</div>
                    <div className="mt-1 space-y-1 text-xs text-cyan-50/90">
                      {activityNotifications.map((a, idx) => (
                        <div key={idx}>{a.message}</div>
                      ))}
                    </div>
                  </div>
                  <button onClick={() => setActivityNotifications([])} className="text-cyan-50/80 transition-colors hover:text-white">×</button>
                </div>
              </div>
            </div>
          )}

          {planCreatedNotification && (
            <div className="absolute left-1/2 top-5 z-20 w-[min(92vw,420px)] -translate-x-1/2 animate-in fade-in slide-in-from-top duration-300">
              <div className="rounded-[24px] border border-blue-300/20 bg-blue-500/95 px-5 py-4 text-white shadow-2xl backdrop-blur-xl">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-sm font-semibold">智能计划已生成</div>
                    <div className="mt-1 text-xs text-blue-50/90">{planCreatedNotification.message}</div>
                  </div>
                  <button onClick={() => setPlanCreatedNotification(null)} className="text-blue-50/80 transition-colors hover:text-white">×</button>
                </div>
                <button
                  onClick={() => { setPlanCreatedNotification(null); router.push('/smart-plan'); }}
                  className="mt-3 w-full rounded-2xl bg-white/15 px-3 py-2 text-sm font-medium text-white transition-all hover:bg-white/20"
                >
                  前往智能计划
                </button>
              </div>
            </div>
          )}

          <div className="flex-1 overflow-y-auto px-4 py-6">
            <div className="mx-auto max-w-6xl">
              {visibleMessages.length === 0 && !loading ? (
                <div className="grid gap-6 lg:grid-cols-[1.3fr_0.9fr]">
                  <div className={`relative overflow-hidden rounded-[34px] border border-white/10 bg-gradient-to-br ${modeCopy.panelClass} p-8 shadow-[0_35px_120px_rgba(2,6,23,0.55)]`}>
                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.14),transparent_32%),radial-gradient(circle_at_bottom_left,rgba(255,255,255,0.08),transparent_32%)]" />
                    <div className="relative">
                      <div className={`inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.32em] ${modeCopy.badgeClass}`}>
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m6-6H6" /></svg>
                        {modeCopy.eyebrow}
                      </div>

                      <div className="mt-7 flex items-start gap-4">
                        <div className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-[22px] ${modeCopy.badgeClass}`}>
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-7 w-7" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m6-6H6" /><path strokeLinecap="round" strokeLinejoin="round" d="M7.5 12a4.5 4.5 0 019-0" opacity="0.4" /></svg>
                        </div>
                        <div>
                          <h1 className="text-4xl leading-tight text-white md:text-5xl" style={{ fontFamily: DISPLAY_FONT_STACK }}>
                            {modeCopy.title}
                          </h1>
                          <p className="mt-4 max-w-2xl text-base leading-8 text-slate-100">
                            {modeCopy.description}
                          </p>
                        </div>
                      </div>

                      <div className="mt-7 flex flex-wrap gap-3">
                        <span className={`rounded-full px-4 py-2 text-sm ${modeCopy.chipClass}`}>{modeCopy.support}</span>
                        <span className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">一屏完成记录、提问和复盘</span>
                        <span className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200">历史会话可回溯</span>
                      </div>

                      <p className={`mt-4 text-sm leading-7 ${modeCopy.subtleClass}`}>{modeCopy.subSupport}</p>

                      <div className="mt-8 grid gap-3 md:grid-cols-2">
                        {activeQuickQuestions.map((q) => (
                          <button
                            key={q.label}
                            onClick={() => handleSend(q.text)}
                            className="group rounded-[26px] border border-white/10 bg-white/5 p-4 text-left transition-all hover:-translate-y-0.5 hover:border-white/20 hover:bg-white/10"
                          >
                            <div className={`text-[10px] uppercase tracking-[0.3em] ${modeCopy.accentTextClass}`}>{q.eyebrow}</div>
                            <div className="mt-3 text-lg text-white">{q.label}</div>
                            <div className="mt-2 text-sm leading-6 text-slate-300">{q.summary}</div>
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-4 content-start">
                    {activeMetrics.map((metric) => (
                      <div key={metric.label} className="rounded-[30px] border border-white/10 bg-slate-950/60 p-5 shadow-[0_20px_60px_rgba(2,6,23,0.35)] backdrop-blur-xl">
                        <div className={`text-[10px] uppercase tracking-[0.3em] ${modeCopy.accentTextClass}`}>{metric.label}</div>
                        <div className="mt-3 text-2xl leading-tight text-white" style={{ fontFamily: DISPLAY_FONT_STACK }}>
                          {metric.value}
                        </div>
                        <div className="mt-3 text-sm leading-7 text-slate-400">{metric.description}</div>
                      </div>
                    ))}

                    {insights.length > 0 && (
                      <InsightsCard insights={insights} accentClass={modeCopy.accentTextClass} />
                    )}
                    {insights.length === 0 && (
                      <div className="rounded-[30px] border border-white/10 bg-white/[0.04] p-5 backdrop-blur-xl">
                        <div className={`text-[10px] uppercase tracking-[0.3em] ${modeCopy.accentTextClass}`}>{"会话方式"}</div>
                        <div className="mt-3 text-lg text-white" style={{ fontFamily: DISPLAY_FONT_STACK }}>
                          {"先问结果，再追细节"}
                        </div>
                        <div className="mt-3 text-sm leading-7 text-slate-400">
                          {"例如先问\"今天状态如何\"，再继续追问\"为什么\"和\"下一步做什么\"。"}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="mx-auto max-w-5xl space-y-5">
                  {visibleMessages.map(msg => (
                    <div key={msg.id} className={`group flex gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                      {msg.role === 'assistant' && (
                        <div className={`mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-[18px] ${modeCopy.badgeClass}`}>
                          <svg xmlns="http://www.w3.org/2000/svg" className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m6-6H6" /></svg>
                        </div>
                      )}
                      {msg.role === 'user' && msg.created_at && (
                        <span className="self-center text-[11px] text-slate-500 opacity-0 transition-opacity group-hover:opacity-100 select-none shrink-0">
                          {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                        </span>
                      )}
                      <div
                        className={`max-w-[min(100%,48rem)] rounded-[28px] px-5 py-4 ${
                          msg.role === 'user' ? modeCopy.userBubbleClass : modeCopy.bubbleClass
                        }`}
                      >
                        {msg.role === 'assistant' ? (
                          <div className="text-sm leading-8 text-white">
                            <ReactMarkdown
                              remarkPlugins={[remarkGfm]}
                              components={{
                                p: ({ children }) => <p className="mb-3 last:mb-0 whitespace-pre-wrap">{children}</p>,
                                ul: ({ children }) => <ul className="mb-3 ml-5 list-disc space-y-1.5">{children}</ul>,
                                ol: ({ children }) => <ol className="mb-3 ml-5 list-decimal space-y-1.5">{children}</ol>,
                                li: ({ children }) => <li className="leading-7">{children}</li>,
                                h1: ({ children }) => <h1 className={`mb-3 mt-4 text-xl first:mt-0 ${modeCopy.accentTextClass}`} style={{ fontFamily: DISPLAY_FONT_STACK }}>{children}</h1>,
                                h2: ({ children }) => <h2 className={`mb-2 mt-4 text-lg first:mt-0 ${modeCopy.accentTextClass}`} style={{ fontFamily: DISPLAY_FONT_STACK }}>{children}</h2>,
                                h3: ({ children }) => <h3 className={`mb-2 mt-3 text-base first:mt-0 ${modeCopy.accentTextClass}`} style={{ fontFamily: DISPLAY_FONT_STACK }}>{children}</h3>,
                                strong: ({ children }) => <strong className={`font-semibold ${modeCopy.accentTextClass}`}>{children}</strong>,
                                em: ({ children }) => <em className="italic text-slate-200/80">{children}</em>,
                                code: ({ ...props }: any) => {
                                  const inline = !props.className?.includes('language-');
                                  return inline ? (
                                    <code className={`rounded bg-slate-950/80 px-1.5 py-0.5 font-mono text-xs ${modeCopy.accentTextClass}`} {...props} />
                                  ) : (
                                    <code className="my-2 block overflow-x-auto rounded-2xl bg-slate-950/90 px-4 py-3 font-mono text-xs" {...props} />
                                  );
                                },
                                pre: ({ children }) => <pre className="my-3 overflow-x-auto rounded-2xl bg-slate-950/90 p-4">{children}</pre>,
                                blockquote: ({ children }) => (
                                  <blockquote className={`my-3 rounded-r-2xl border-l-4 ${modeCopy.accentBorderClass} bg-white/[0.03] py-2 pl-4 italic text-slate-200/80`}>
                                    {children}
                                  </blockquote>
                                ),
                                table: ({ children }) => (
                                  <div className="my-3 overflow-x-auto">
                                    <table className="min-w-full overflow-hidden rounded-2xl border border-white/10">{children}</table>
                                  </div>
                                ),
                                thead: ({ children }) => <thead className="bg-white/[0.06]">{children}</thead>,
                                tbody: ({ children }) => <tbody className="bg-slate-950/30">{children}</tbody>,
                                tr: ({ children }) => <tr className="border-b border-white/10 last:border-0">{children}</tr>,
                                th: ({ children }) => <th className={`border border-white/10 px-3 py-2 text-left text-sm font-medium ${modeCopy.accentTextClass}`}>{children}</th>,
                                td: ({ children }) => <td className="border border-white/10 px-3 py-2 text-sm">{children}</td>,
                                hr: () => <hr className="my-4 border-white/10" />,
                                a: ({ children, href }) => (
                                  <a
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className={`${modeCopy.accentTextClass} underline transition-colors hover:text-white`}
                                  >
                                    {children}
                                  </a>
                                ),
                              }}
                            >
                              {msg.content}
                            </ReactMarkdown>
                          </div>
                        ) : (
                          <div>
                            {msg.image_preview && (
                              <img
                                src={msg.image_preview}
                                alt="上传图片"
                                className="mb-3 max-h-56 max-w-xs rounded-2xl object-cover"
                              />
                            )}
                            {msg.file_name && (
                              <div className="mb-3 flex items-center gap-2 rounded-2xl bg-white/10 px-3 py-2 text-sm">
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                                </svg>
                                <span className="truncate">{msg.file_name}</span>
                              </div>
                            )}
                            <div className="whitespace-pre-wrap leading-7">{msg.content}</div>
                          </div>
                        )}
                      </div>
                      {msg.role === 'assistant' && msg.created_at && (
                        <span className="self-end text-[11px] text-slate-500 opacity-0 transition-opacity group-hover:opacity-100 select-none shrink-0 ml-1 mb-1">
                          {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
                        </span>
                      )}
                      {msg.role === 'assistant' && msg.content && doneMessageIds.has(msg.id) && (
                        <div className="ml-1 mt-1 flex items-center gap-1 self-end">
                          <button
                            onClick={() => handleFeedback(msg.id, 5)}
                            className={`rounded-full p-1.5 transition-all ${
                              messageFeedback[msg.id] === 5
                                ? 'bg-white/20 text-emerald-300'
                                : 'text-white/30 hover:bg-white/10 hover:text-white/60'
                            }`}
                            title="helpful"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z" />
                            </svg>
                          </button>
                          <button
                            onClick={() => handleFeedback(msg.id, 1)}
                            className={`rounded-full p-1.5 transition-all ${
                              messageFeedback[msg.id] === 1
                                ? 'bg-white/20 text-red-300'
                                : 'text-white/30 hover:bg-white/10 hover:text-white/60'
                            }`}
                            title="not helpful"
                          >
                            <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z" />
                            </svg>
                          </button>
                        </div>
                      )}
                    </div>
                  ))}

                  {loading && (
                    <div className="flex gap-4">
                      <div className={`mt-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-[18px] ${modeCopy.badgeClass}`}>
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m6-6H6" /></svg>
                      </div>
                      <div className={`rounded-[28px] px-5 py-4 ${modeCopy.bubbleClass}`}>
                        <div className="flex gap-2">
                          <div className={`h-2.5 w-2.5 animate-bounce rounded-full bg-emerald-300`} style={{ animationDelay: '0ms' }} />
                          <div className={`h-2.5 w-2.5 animate-bounce rounded-full bg-emerald-300`} style={{ animationDelay: '150ms' }} />
                          <div className={`h-2.5 w-2.5 animate-bounce rounded-full bg-emerald-300`} style={{ animationDelay: '300ms' }} />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>
          </div>

          {visibleMessages.length > 0 && (
            <div className="border-t border-white/10 bg-slate-950/35 px-4 py-3 backdrop-blur-xl">
              <div className="mx-auto flex max-w-5xl items-center gap-3 overflow-x-auto">
                <span className={`shrink-0 text-[10px] uppercase tracking-[0.3em] ${modeCopy.accentTextClass}`}>继续推进</span>
                {activeQuickQuestions.map((q) => (
                  <button
                    key={q.label}
                    onClick={() => handleSend(q.text)}
                    className="shrink-0 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-slate-200 transition-all hover:bg-white/10 hover:text-white"
                  >
                    {q.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {(imagePreview || pendingFile) && (
            <div className="border-t border-white/10 bg-slate-950/50 px-4 py-3 backdrop-blur-xl">
              <div className="mx-auto flex max-w-5xl items-center gap-4 rounded-[24px] border border-white/10 bg-white/[0.04] px-4 py-3">
                <div className="relative">
                  {imagePreview ? (
                    <img
                      src={imagePreview}
                      alt="待发送图片"
                      className="h-16 w-16 rounded-2xl border border-white/10 object-cover"
                    />
                  ) : (
                    <div className="flex h-16 w-16 flex-col items-center justify-center rounded-2xl border border-white/10 bg-slate-900">
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                      </svg>
                    </div>
                  )}
                  <button
                    onClick={clearPendingAttachment}
                    className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full bg-red-500 text-xs text-white transition-colors hover:bg-red-400"
                  >
                    ×
                  </button>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-white">{imagePreview ? '图片已就绪' : pendingFile?.name}</div>
                  <div className="mt-1 text-xs text-slate-400">补一句目标或上下文后直接发送，AI 会结合附件内容理解你的需求。</div>
                </div>
              </div>
            </div>
          )}

          <div className="border-t border-white/10 bg-slate-950/55 px-4 py-4 backdrop-blur-2xl">
            <div className="mx-auto max-w-5xl rounded-[30px] border border-white/10 bg-white/[0.04] shadow-[0_20px_60px_rgba(2,6,23,0.35)]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-3">
                <div>
                  <div className={`text-[10px] uppercase tracking-[0.32em] ${modeCopy.accentTextClass}`}>{modeCopy.support}</div>
                  <div className="mt-1 text-xs text-slate-400">{modeCopy.subSupport}</div>
                </div>
                <div className="text-xs text-slate-500">Enter 发送</div>
              </div>

              <div className="flex items-center gap-3 px-4 py-4">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*,.pdf,.txt,.md,.csv,.json,.py,.js,.ts,.html,.xml,.log,.yaml,.yml"
                  className="hidden"
                  onChange={handleImageUpload}
                />

                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={imageUploading}
                  className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/10 transition-all ${
                    imageUploading ? 'bg-white/15 text-white animate-pulse' : 'bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white'
                  }`}
                  title="上传图片或文件"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13" />
                  </svg>
                </button>

                <button
                  onClick={handleVoiceToggle}
                  className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/10 transition-all ${
                    isRecording ? 'bg-red-500 text-white animate-pulse' : 'bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white'
                  }`}
                  title={isRecording ? '停止录音' : '语音输入'}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    {isRecording ? (
                      <rect x="6" y="6" width="12" height="12" rx="2" />
                    ) : (
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
                    )}
                  </svg>
                </button>

                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  onPaste={handlePaste}
                  placeholder={isRecording ? '正在录音...' : (pendingImage || pendingFile) ? '输入描述或问题（可直接发送）' : '用一句完整目标开始，例如：分析今天状态，或帮我安排训练恢复'}
                  className="flex-1 bg-transparent px-2 py-3 text-[15px] text-white placeholder:text-slate-500 focus:outline-none"
                  disabled={isRecording}
                />

                <button
                  onClick={() => handleSend()}
                  disabled={!inputText.trim() && !pendingImage && !pendingFile}
                  className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl transition-all ${
                    (inputText.trim() || pendingImage || pendingFile)
                      ? 'bg-white text-slate-950 hover:scale-[1.02]'
                      : 'bg-white/8 text-slate-500 cursor-not-allowed'
                  }`}
                >
                  <span className="text-xl leading-none">↑</span>
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
