'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api, chatApi, openclawApi, agentApi, sharedApi, feedbackApi, ChatMessage, Conversation, DietSavedData, ActivitySavedData } from '@/services/api';
import NotificationCenter from '@/components/NotificationCenter';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import { useDashboardData } from '@/hooks/useDashboardData';

// Dashboard components
import HeroCard from '@/components/assistant/HeroCard';
import AlertsBanner from '@/components/assistant/AlertsBanner';
import DataGrid from '@/components/assistant/DataGrid';
import ActivityCard from '@/components/assistant/ActivityCard';
import SupplementCheckin from '@/components/assistant/SupplementCheckin';
import TrendsCard from '@/components/assistant/TrendsCard';
import QuickRecordBar from '@/components/assistant/QuickRecordBar';
import InlineResponse from '@/components/assistant/InlineResponse';
import ChatView from '@/components/assistant/ChatView';
import ExerciseCard from '@/components/assistant/ExerciseCard';
import SupplementGuideCard from '@/components/assistant/SupplementGuideCard';
import StrengthCard from '@/components/assistant/StrengthCard';
import WorkoutCard from '@/components/assistant/WorkoutCard';
import HistorySidebar from '@/components/assistant/HistorySidebar';

declare global {
  interface Window { webkitSpeechRecognition: any; SpeechRecognition: any; }
}

const UI_FONT_STACK = '"Avenir Next", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';

const APP_MENU = [
  { label: '概览', items: [{ href: '/overview', name: '健康概览', icon: '📊' }, { href: '/daily-insights', name: '今日建议', icon: '✨' }, { href: '/smart-plan', name: '智能计划', icon: '📅' }, { href: '/family', name: '家庭', icon: '👨‍👩‍👦' }] },
  { label: '追踪', items: [{ href: '/workout', name: '运动', icon: '🏋️' }, { href: '/sleep', name: '睡眠', icon: '🌙' }, { href: '/garmin', name: 'Garmin', icon: '⌚' }, { href: '/weight', name: '体重', icon: '⚖️' }, { href: '/heart-rate', name: '心率', icon: '❤️' }, { href: '/blood-pressure', name: '血压', icon: '🩺' }, { href: '/mood', name: '情绪', icon: '😊' }] },
  { label: '记录', items: [{ href: '/supplements', name: '补剂', icon: '💊' }, { href: '/diet', name: '饮食', icon: '🍽️' }, { href: '/water', name: '饮水', icon: '💧' }, { href: '/checkin', name: '打卡', icon: '✅' }, { href: '/rhinitis', name: '鼻炎', icon: '👃' }] },
  { label: '管理', items: [{ href: '/genetic', name: '基因', icon: '🧬' }, { href: '/medical-exams', name: '体检', icon: '📋' }, { href: '/goals', name: '目标', icon: '🎯' }, { href: '/settings', name: '设置', icon: '⚙️' }] },
];

const QUICK_ASKS = [
  { text: '帮我分析一下最近的睡眠质量', label: '睡眠分析' },
  { text: '根据我的身体数据，今天适合做什么运动？', label: '运动建议' },
  { text: '帮我记录一下刚才吃的饭', label: '记录饮食' },
  { text: '查看今日 AI 洞察和健康分析详情', label: 'AI 洞察' },
  { text: '分析我最近的HRV趋势，给出恢复建议', label: '趋势报告' },
];


function Toast({ color, title, subtitle, onClose, action }: { color: string; title: string; subtitle: string; onClose: () => void; action?: { label: string; onClick: () => void } }) {
  const dotColors: Record<string, string> = { emerald: '#30D158', cyan: '#00C7BE', blue: '#007AFF' };
  return (
    <div className="fixed left-1/2 top-5 z-[60] w-[min(92vw,420px)] -translate-x-1/2 animate-in fade-in slide-in-from-top duration-300">
      <div className="rounded-2xl bg-white px-5 py-4" style={{ boxShadow: '0 4px 20px rgba(0,0,0,0.12)' }}>
        <div className="flex items-start gap-3">
          <div className="w-2 h-2 rounded-full mt-1.5 shrink-0" style={{ background: dotColors[color] || dotColors.emerald }} />
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold" style={{ color: '#1C1C1E' }}>{title}</div>
            <div className="mt-0.5 text-xs" style={{ color: '#8E8E93' }}>{subtitle}</div>
          </div>
          <button onClick={onClose} className="text-gray-300 hover:text-gray-500 text-lg leading-none">×</button>
        </div>
        {action && <button onClick={action.onClick} className="mt-3 w-full rounded-xl px-3 py-2 text-sm font-medium transition-colors" style={{ background: '#F2F2F7', color: '#007AFF' }}>{action.label}</button>}
      </div>
    </div>
  );
}

export default function AIAssistantPage() {
  const router = useRouter();
  const { user } = useAuth();
  const { showToast } = useToast();

  // Dashboard data (extracted hook)
  const dashboard = useDashboardData();

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [conversationId, setConversationId] = useState<number | undefined>();
  const [inlineMode, setInlineMode] = useState(true);
  const [inlineResponse, setInlineResponse] = useState<{question: string; answer: string; loading: boolean} | null>(null);
  const inlineResponseRef = useRef<HTMLDivElement>(null);
  const [doneMessageIds, setDoneMessageIds] = useState<Set<number>>(new Set());
  const [messageFeedback, setMessageFeedback] = useState<Record<number, 1 | 5>>({});

  // History sidebar
  const [showHistory, setShowHistory] = useState(false);
  const [conversations, setConversations] = useState<Conversation[]>([]);

  // Notifications
  const [dietNotification, setDietNotification] = useState<DietSavedData | null>(null);
  const [activityNotifications, setActivityNotifications] = useState<ActivitySavedData[]>([]);
  const [planCreatedNotification, setPlanCreatedNotification] = useState<{message: string; planId?: number} | null>(null);

  // Media / file upload
  const [isRecording, setIsRecording] = useState(false);
  const [imageUploading, setImageUploading] = useState(false);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const [pendingImage, setPendingImage] = useState<{base64: string; type: string} | null>(null);
  const [pendingFile, setPendingFile] = useState<{base64: string; name: string} | null>(null);
  const [showAppsMenu, setShowAppsMenu] = useState(false);
  const [showMoreDashboard, setShowMoreDashboard] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const appsMenuRef = useRef<HTMLDivElement>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  useEffect(() => { document.title = 'AI 助理 | 健康管理'; }, []);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(() => { if (messages.length > 0 && !inlineMode) scrollToBottom(); }, [messages, inlineMode]);

  // ── Conversations ──
  const loadConversations = useCallback(async () => {
    try {
      const response = await openclawApi.getConversations();
      setConversations(response.data || []);
    } catch (e) { console.error('加载对话列表失败:', e); }
  }, []);

  const loadConversation = useCallback(async (convId: number) => {
    try {
      const response = await openclawApi.getConversation(convId);
      const msgs = response.data.messages || [];
      setMessages(msgs);
      setDoneMessageIds(new Set(msgs.filter((m: ChatMessage) => m.role === 'assistant').map((m: ChatMessage) => m.id)));
      setConversationId(convId);
      setInlineMode(false);
      setInlineResponse(null);
    } catch { showToast('加载失败', 'error'); }
  }, [showToast]);

  useEffect(() => {
    if (!localStorage.getItem('auth_token')) { router.push('/login'); return; }
    loadConversations();
    dashboard.loadTodayGarmin();
    dashboard.loadDashboardData();
  }, [loadConversations, dashboard.loadTodayGarmin, dashboard.loadDashboardData, router]);

  // ── Send logic ──
  const isPostWorkoutMessage = (msg: string) => {
    const kw = ['跑完了','运动结束','锻炼完了','训练结束','跑步结束','运动完成','刚跑完','刚运动完','刚锻炼完','刚练完','骑完车','游完泳','运动完了','同步Garmin','同步garmin','分析本次训练','分析刚才的运动'];
    return kw.some(k => msg.includes(k));
  };

  const handleDoneEvent = (result: any) => {
    if (result.workout_analysis?.content) {
      setMessages(prev => [...prev, { id: result.workout_analysis.message_id, role: 'assistant', content: result.workout_analysis.content, created_at: new Date().toISOString() }]);
    }
    if (result.diet_saved && result.diet_data) { setDietNotification(result.diet_data); setTimeout(() => setDietNotification(null), 5000); }
    if (result.activities_saved && result.activities) {
      const saved = result.activities.filter((a: ActivitySavedData) => a.status !== 'already_exists');
      const planResult = saved.find((a: any) => a.type === 'create_plan') as any;
      if (planResult) { setPlanCreatedNotification({ message: planResult.message, planId: planResult.plan_id }); setTimeout(() => setPlanCreatedNotification(null), 8000); }
      const nonPlan = saved.filter((a: any) => a.type !== 'create_plan');
      if (nonPlan.length > 0) { setActivityNotifications(nonPlan); setTimeout(() => setActivityNotifications([]), 5000); }
    }
    if (result.reminder?.reminder_minutes > 0) {
      const { reminder_minutes, reminder_message, activity_name } = result.reminder;
      if ('Notification' in window && Notification.permission === 'granted') {
        setTimeout(() => new Notification(`${activity_name} - 休息提醒`, { body: reminder_message, icon: '/icon-192x192.png' }), reminder_minutes * 60 * 1000);
      }
    }
  };

  const handleInlineSend = async (text?: string) => {
    const msg = (text || inputText).trim();
    if (!msg) return;
    setInputText('');
    setInlineResponse({ question: msg, answer: '', loading: true });
    setTimeout(() => inlineResponseRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 100);
    try {
      let fullText = '';
      for await (const event of agentApi.streamMessage(msg, conversationId)) {
        if (event.event === 'agent_start') {
          // Agent 启动，静默跳过
        } else if (event.event === 'tool_call') {
          const toolName = event.data?.tool || '';
          const round = event.data?.round || '';
          fullText += `🔧 调用工具: \`${toolName}\` (第${round}轮)\n`;
          setInlineResponse(prev => prev ? { ...prev, answer: fullText } : null);
        } else if (event.event === 'tool_result') {
          const toolName = event.data?.tool || '';
          const success = event.data?.success;
          fullText += `${success ? '✅' : '❌'} ${toolName} ${success ? '完成' : '失败'}\n\n`;
          setInlineResponse(prev => prev ? { ...prev, answer: fullText } : null);
        } else if (event.event === 'token') {
          fullText += event.data?.content || '';
          setInlineResponse(prev => prev ? { ...prev, answer: fullText } : null);
        } else if (event.event === 'done') {
          if (event.data?.conversation_id && !conversationId) setConversationId(event.data.conversation_id);
          dashboard.loadDashboardData();
        }
      }
      setInlineResponse(prev => prev ? { ...prev, loading: false } : null);
    } catch {
      setInlineResponse(prev => prev ? { ...prev, answer: prev?.answer || '请求失败，请重试', loading: false } : null);
    }
  };

  const handleSend = async (text?: string, imageBase64?: string, imageType?: string) => {
    const msg = (text || inputText).trim();
    const hasAttachment = pendingImage || pendingFile;
    if (!msg && !hasAttachment) return;
    if (inlineMode && !hasAttachment) { handleInlineSend(text); return; }

    const finalImageBase64 = imageBase64 || pendingImage?.base64;
    const finalImageType = imageType || pendingImage?.type;
    const finalFileBase64 = pendingFile?.base64;
    const finalFileName = pendingFile?.name;
    const finalMsg = msg || (finalImageBase64 ? '请看这张图片，帮我分析一下' : (finalFileBase64 ? `请分析这个文件：${finalFileName}` : ''));
    if (!finalMsg) return;

    setInputText('');
    clearPendingAttachment();

    const tempUserMsg: ChatMessage = { id: Date.now(), role: 'user', content: finalMsg, created_at: new Date().toISOString(), image_preview: finalImageBase64 ? `data:image/${finalImageType || 'jpeg'};base64,${finalImageBase64}` : undefined, file_name: finalFileName };
    setMessages(prev => [...prev, tempUserMsg]);
    setLoading(true);

    const isWorkoutDone = isPostWorkoutMessage(finalMsg);
    let workoutAnalysisPromise: Promise<any> | null = isWorkoutDone ? api.post('/workout/post-run-analyze?format=full').catch(() => null) : null;

    const aiMsgId = Date.now() + 1;
    try {
      setMessages(prev => [...prev, { id: aiMsgId, role: 'assistant', content: '', created_at: new Date().toISOString() }]);
      let gotDone = false, firstToken = true;
      const waitTimer = setTimeout(() => { if (firstToken) setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: '⏳ AI 正在思考中，复杂分析可能需要 1-2 分钟...' } : m)); }, 8000);
      const waitTimer2 = setTimeout(() => { if (firstToken) setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: '⏳ 正在调用多个 AI 模型进行深度分析，请耐心等待...' } : m)); }, 30000);
      const buf = { content: '', timer: null as NodeJS.Timeout | null };

      // 有附件走 OpenClaw（支持图片/文件），纯文本走 Agent
      const hasMedia = !!(finalImageBase64 || finalFileBase64);
      const streamSource = hasMedia
        ? openclawApi.streamMessage(finalMsg, conversationId, finalImageBase64, finalImageType, finalFileBase64, finalFileName)
        : agentApi.streamMessage(finalMsg, conversationId);

      for await (const event of streamSource) {
        if (event.event === 'agent_start') {
          // Don't setLoading(false) here — keep loading indicator until first real content
          clearTimeout(waitTimer); clearTimeout(waitTimer2);
        } else if (event.event === 'tool_call') {
          if (firstToken) { firstToken = false; setLoading(false); }
          const toolName = event.data?.tool || '';
          const round = event.data?.round || '';
          buf.content += `🔧 调用工具: \`${toolName}\` (第${round}轮)\n`;
          if (!buf.timer) {
            buf.timer = setTimeout(() => { const b = buf.content; buf.content = ''; buf.timer = null; setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + b } : m)); }, 50);
          }
        } else if (event.event === 'tool_result') {
          const toolName = event.data?.tool || '';
          const success = event.data?.success;
          buf.content += `${success ? '✅' : '❌'} ${toolName} ${success ? '完成' : '失败'}\n\n`;
          if (!buf.timer) {
            buf.timer = setTimeout(() => { const b = buf.content; buf.content = ''; buf.timer = null; setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + b } : m)); }, 50);
          }
        } else if (event.event === 'token') {
          if (firstToken) { firstToken = false; clearTimeout(waitTimer); clearTimeout(waitTimer2); setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: '' } : m)); setLoading(false); }
          buf.content += event.data.content;
          if (!buf.timer) {
            buf.timer = setTimeout(() => { const b = buf.content; buf.content = ''; buf.timer = null; setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + b } : m)); }, 50);
          }
        } else if (event.event === 'done') {
          gotDone = true;
          if (buf.content) { if (buf.timer) { clearTimeout(buf.timer); buf.timer = null; } const b = buf.content; buf.content = ''; setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + b } : m)); }
          if (!conversationId && event.data.conversation_id) setConversationId(event.data.conversation_id);
          if (event.data.message_id) { setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, id: event.data.message_id } : m)); setDoneMessageIds(prev => new Set(prev).add(event.data.message_id)); }
          handleDoneEvent(event.data);
          dashboard.loadDashboardData();
        } else if (event.event === 'error') {
          clearTimeout(waitTimer); clearTimeout(waitTimer2);
          const errText = event.data.message || '';
          const friendlyMsg = errText.includes('timeout') || errText.includes('Timeout') ? '⏱ 分析超时了，可能是数据量较大。请稍后重试，或换一个更具体的问题。'
            : errText.includes('Gateway') || errText.includes('502') || errText.includes('503') ? '🔧 AI 服务暂时繁忙，请稍后再试。'
            : errText || '抱歉，出了点问题，请重试。';
          setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: friendlyMsg } : m));
        }
      }
      clearTimeout(waitTimer); clearTimeout(waitTimer2);
      if (!gotDone) setMessages(prev => { const ai = prev.find(m => m.id === aiMsgId); if (ai && (!ai.content || ai.content.startsWith('⏳'))) return prev.map(m => m.id === aiMsgId ? { ...m, content: '抱歉，OpenClaw 暂时无法响应，请稍后再试。' } : m); return prev; });
      if (buf.content) { if (buf.timer) { clearTimeout(buf.timer); buf.timer = null; } const remaining = buf.content; buf.content = ''; setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: m.content + remaining } : m)); }

      // Post-workout analysis fallback
      if (workoutAnalysisPromise && gotDone) {
        setLoading(false);
        const loadingMsgId = Date.now() + 2;
        setMessages(prev => [...prev, { id: loadingMsgId, role: 'assistant', content: '正在同步 Garmin 数据并进行多模型分析，请稍等约 30-60 秒...', created_at: new Date().toISOString() }]);
        const analysisResp = await workoutAnalysisPromise;
        if (analysisResp?.data?.success) {
          const { workout = {}, multi_model_analysis: analysis = {} } = analysisResp.data;
          const parts = [workout.name, workout.distance_km && `${workout.distance_km}km`, workout.duration_min && `${workout.duration_min}分钟`, workout.pace && `配速${workout.pace}`].filter(Boolean);
          let content = `**运动分析完成：${parts.join(' | ')}**\n\n`;
          if (analysis.aggregation) content += `**综合分析：**\n${analysis.aggregation}\n\n`;
          if (analysis.model_results?.length > 0) { content += '**各模型视角：**\n\n'; for (const mr of analysis.model_results) { const name = (mr.site || '').replace('lb-', '').replace(/-/g, ' '); if (mr.content) content += `**${name}**:\n${mr.content.slice(0, 400)}${mr.content.length > 400 ? '...' : ''}\n\n---\n\n`; } }
          setMessages(prev => prev.map(m => m.id === loadingMsgId ? { ...m, content } : m));
        } else {
          setMessages(prev => prev.map(m => m.id === loadingMsgId ? { ...m, content: analysisResp?.data?.message || '运动分析未完成，请稍后再试。' } : m));
        }
      }
      loadConversations();
    } catch {
      setMessages(prev => prev.map(m => m.id === aiMsgId ? { ...m, content: '抱歉，请求失败了，请稍后再试。' } : m));
    } finally { setLoading(false); }
  };

  // ── Helpers ──
  const handleNewChat = () => { setMessages([]); setConversationId(undefined); setShowHistory(false); };
  const handleDeleteConversation = async (convId: number) => { try { await openclawApi.deleteConversation(convId); setConversations(prev => prev.filter(c => c.id !== convId)); if (conversationId === convId) handleNewChat(); showToast('已删除', 'success'); } catch { showToast('删除失败', 'error'); } };
  const handleShareConversation = async (convId: number) => { try { const res = await sharedApi.createShare(convId, 'openclaw'); const url = res.data.share_url; if (navigator.clipboard) { await navigator.clipboard.writeText(url); showToast('分享链接已复制到剪贴板', 'success'); } else prompt('分享链接：', url); } catch { showToast('分享失败', 'error'); } };
  const toggleHistory = () => { if (!showHistory) { loadConversations(); } setShowHistory(!showHistory); };
  const clearPendingAttachment = () => { setImagePreview(null); setPendingImage(null); setPendingFile(null); };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); handleSend(); } };

  const handleFeedback = async (msgId: number, rating: 1 | 5) => {
    if (!conversationId || messageFeedback[msgId] === rating) return;
    setMessageFeedback(f => ({ ...f, [msgId]: rating }));
    try { await feedbackApi.submit({ conversation_type: 'openclaw', conversation_id: conversationId, message_id: msgId, rating }); } catch {}
  };

  // ── Voice recording ──
  const handleVoiceToggle = async () => {
    if (isRecording) { mediaRecorderRef.current?.stop(); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;
      audioChunksRef.current = [];
      mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunksRef.current.push(e.data); };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop()); setIsRecording(false);
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        if (audioBlob.size < 1000) return;
        try {
          const reader = new FileReader();
          reader.readAsDataURL(audioBlob);
          reader.onloadend = async () => {
            const base64 = (reader.result as string).split(',')[1];
            const res = await chatApi.transcribe(base64, 'webm');
            const text = res.data.text?.trim();
            if (text) {
              try { const voiceRes = await chatApi.voiceCommand(text); if (voiceRes.data.matched) { showToast(voiceRes.data.message || '指令已执行', 'success'); return; } } catch {}
              setInputText(prev => prev + text);
            }
          };
        } catch { showToast('语音识别失败，请重试', 'error'); }
      };
      mediaRecorder.start(); setIsRecording(true);
    } catch { showToast('无法访问麦克风，请检查浏览器权限', 'warning'); }
  };

  // ── File upload ──
  const handleImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]; if (!file) return;
    e.target.value = '';
    setImageUploading(true);
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onloadend = () => {
      const dataUrl = reader.result as string;
      const base64 = dataUrl.split(',')[1];
      if (file.type.startsWith('image/')) { setImagePreview(dataUrl); setPendingImage({ base64, type: file.type.replace('image/', '') || 'jpeg' }); }
      else setPendingFile({ base64, name: file.name });
      setImageUploading(false);
    };
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items; if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        e.preventDefault();
        const file = items[i].getAsFile(); if (!file) return;
        setImageUploading(true);
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onloadend = () => { const dataUrl = reader.result as string; setImagePreview(dataUrl); setPendingImage({ base64: dataUrl.split(',')[1], type: file.type.replace('image/', '') || 'png' }); setImageUploading(false); };
        return;
      }
    }
  };

  // ── Derived data ──
  const hasMessages = messages.some(m => !(m.role === 'assistant' && !m.content));
  const isWelcome = inlineMode || (!hasMessages && !loading);

  // Supplement dedup (for HeroCard's suppChecked/suppTotal)
  const suppDeduped = (() => {
    const seen = new Set<string>();
    return dashboard.supplementStatus.filter((s: any) => {
      const key = `${s.supplement?.name || s.supplement_name || s.name}_${s.supplement?.timing || s.timing || 'morning'}`;
      if (seen.has(key)) return false; seen.add(key); return true;
    });
  })();
  const suppChecked = suppDeduped.filter((s: any) => s.record?.taken || s.is_taken || s.checked).length;
  const suppTotal = suppDeduped.length;

  // Water record callback
  const handleWaterRecord = async (amount: number) => {
    const today = new Date().toISOString().slice(0, 10);
    try {
      await api.post('/water/records', { record_date: today, amount, drink_type: '水', user_id: 0 });
      dashboard.setWaterToday(prev => ({ ...prev, total_ml: prev.total_ml + amount, count: prev.count + 1 }));
    } catch (e) { console.error('记录饮水失败', e); }
  };

  const handleRefresh = async () => {
    showToast('正在同步 Garmin 数据（含运动和睡眠）...', 'info');
    try {
      const res = await api.post('/data-collection/garmin/me/sync?days=1');
      const d = res.data;
      const parts = [];
      if (d?.success_count > 0) parts.push(`${d.success_count}天健康数据`);
      if (d?.activities_count > 0) parts.push(`${d.activities_count}条运动`);
      await dashboard.loadTodayGarmin();
      await dashboard.loadDashboardData();
      showToast(parts.length > 0 ? `同步成功：${parts.join('、')}` : '数据已是最新', 'success');
    } catch {
      await dashboard.loadTodayGarmin();
      await dashboard.loadDashboardData();
      showToast('同步失败，已刷新本地数据', 'error');
    }
  };

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ fontFamily: UI_FONT_STACK }}>
      {/* Header */}
      <header className="relative z-50 backdrop-blur-md bg-white/80 border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button onClick={handleNewChat} className="flex items-center gap-2 hover:opacity-80 transition-opacity">
              <div className="w-8 h-8 rounded-lg bg-green-500 flex items-center justify-center"><span className="text-white text-sm font-bold">H</span></div>
              <span className="font-semibold text-gray-800 text-sm">智能助理</span>
            </button>
          </div>
          <div className="flex items-center gap-3">
            {!showHistory && (
              <button onClick={toggleHistory} className="text-gray-400 hover:text-gray-600 transition-colors" title="历史记录">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" /></svg>
              </button>
            )}
            <button onClick={handleNewChat} className="text-gray-400 hover:text-gray-600 transition-colors" title="新对话">
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
            </button>
            <div className="relative" ref={appsMenuRef}>
              <button onClick={() => setShowAppsMenu(!showAppsMenu)} className={`text-xs flex items-center gap-1 transition-colors ${showAppsMenu ? 'text-gray-700' : 'text-gray-400 hover:text-gray-600'}`}>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" /></svg>
                功能
              </button>
              {showAppsMenu && (
                <>
                  <div className="fixed inset-0 z-40" onClick={() => setShowAppsMenu(false)} />
                  <div className="absolute right-0 top-full mt-2 w-[340px] max-h-[75vh] overflow-y-auto bg-white rounded-2xl shadow-xl border border-gray-200 p-4 z-50">
                    {APP_MENU.map(group => (
                      <div key={group.label} className="mb-3 last:mb-0">
                        <div className="text-[10px] uppercase tracking-widest text-gray-400 font-medium mb-1.5 px-1">{group.label}</div>
                        <div className="grid grid-cols-4 gap-1">
                          {group.items.map(item => (
                            <button key={item.href} onClick={() => { setShowAppsMenu(false); router.push(item.href); }}
                              className="flex flex-col items-center gap-1 px-1 py-2 rounded-xl hover:bg-gray-50 transition-colors text-center">
                              <span className="text-lg">{item.icon}</span>
                              <span className="text-[10px] text-gray-600 leading-tight">{item.name}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
            <NotificationCenter />
            <button onClick={() => router.push('/settings')} className="w-8 h-8 rounded-full bg-gradient-to-br from-green-400 to-emerald-600 flex items-center justify-center text-white text-xs font-bold shadow-sm">
              {user?.name?.charAt(0) || '?'}
            </button>
          </div>
        </div>
      </header>

      {/* Background */}
      {isWelcome ? (
        <div className="absolute inset-0" style={{ background: '#F2F2F7' }} />
      ) : (
        <>
          <div className="absolute inset-0 bg-gradient-to-br from-[#04111f] via-[#0b1b24] to-[#041428]" />
          <div className="absolute inset-0 opacity-70" style={{ backgroundImage: 'radial-gradient(circle at 16% 14%, rgba(16,185,129,0.24), transparent 30%), radial-gradient(circle at 86% 16%, rgba(45,212,191,0.18), transparent 30%), linear-gradient(to right, rgba(148,163,184,0.07) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.07) 1px, transparent 1px)', backgroundSize: 'auto, auto, 56px 56px, 56px 56px' }} />
          <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-slate-950 via-slate-950/50 to-transparent" />
        </>
      )}

      <div className="relative flex overflow-hidden" style={{ height: 'calc(100vh - 56px)' }}>
        {showHistory && (
          <HistorySidebar conversations={conversations} currentConversationId={conversationId} onLoadConversation={loadConversation} onNewChat={handleNewChat} onClose={toggleHistory} onDelete={handleDeleteConversation} onShare={handleShareConversation} />
        )}

        {/* ── Main content ── */}
        <section className="relative flex min-w-0 flex-1 flex-col">
          {/* Toast notifications */}
          {dietNotification && <Toast color="emerald" title="饮食已自动记录" subtitle={`${dietNotification.total_calories ? Math.round(dietNotification.total_calories) + ' kcal' : ''} · ${{ breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' }[dietNotification.meal_type] || '加餐'}`} onClose={() => setDietNotification(null)} />}
          {activityNotifications.length > 0 && <Toast color="cyan" title="已自动记录" subtitle={activityNotifications.map(a => a.message).join('；')} onClose={() => setActivityNotifications([])} />}
          {planCreatedNotification && <Toast color="blue" title="智能计划已生成" subtitle={planCreatedNotification.message} onClose={() => setPlanCreatedNotification(null)} action={{ label: '前往智能计划', onClick: () => { setPlanCreatedNotification(null); router.push('/smart-plan'); } }} />}

          {/* Scrollable content */}
          <div className="flex-1 overflow-y-auto px-4 py-6">
            <div className="mx-auto max-w-5xl">
              {isWelcome ? (
                <div className="space-y-3 pb-44">
                  <HeroCard user={user} healthScore={dashboard.healthScore} todayGarmin={dashboard.todayGarmin} waterToday={dashboard.waterToday} suppChecked={suppChecked} suppTotal={suppTotal} weatherData={dashboard.weatherData} airData={dashboard.airData} onRefresh={handleRefresh} />
                  <AlertsBanner waterToday={dashboard.waterToday} todayGarmin={dashboard.todayGarmin} onWaterRecord={handleWaterRecord} onAskAI={(text) => handleSend(text)} />
                  <DataGrid todayGarmin={dashboard.todayGarmin} dietToday={dashboard.dietToday} bpLatest={dashboard.bpLatest} rhinitisToday={dashboard.rhinitisToday} weightStats={dashboard.weightStats} />
                  {/* 力量训练：俯卧撑 · 深蹲 */}
                  <div className="grid grid-cols-2 gap-3">
                    <StrengthCard exerciseType="俯卧撑" icon="💪" dailyTarget={100} color="#3b82f6"
                      colorLight="bg-blue-50" colorText="text-blue-600" colorBorder="border-blue-200"
                      colorBar="bg-blue-500" colorBarLight="bg-blue-200" />
                    <StrengthCard exerciseType="深蹲" icon="🦵" dailyTarget={100} color="#8b5cf6"
                      colorLight="bg-violet-50" colorText="text-violet-600" colorBorder="border-violet-200"
                      colorBar="bg-violet-500" colorBarLight="bg-violet-200" />
                  </div>

                  {/* 运动 + 补剂打卡（常驻展示） */}
                  <div className="grid grid-cols-2 gap-3">
                    <WorkoutCard todayGarmin={dashboard.todayGarmin} workoutRecent={dashboard.workoutRecent} />
                    <SupplementCheckin supplementStatus={dashboard.supplementStatus} onStatusChange={dashboard.setSupplementStatus} />
                  </div>

                  {/* 折叠区：补剂指南以下，默认收起 */}
                  {!showMoreDashboard ? (
                    <button onClick={() => setShowMoreDashboard(true)}
                      className="w-full py-2.5 rounded-xl border border-gray-300 bg-gray-50 text-sm text-gray-500 font-medium hover:text-gray-700 hover:bg-gray-100 hover:border-gray-400 transition-all">
                      ▾ 展开更多
                    </button>
                  ) : (
                    <>
                      <SupplementGuideCard />
                      <ActivityCard todayGarmin={dashboard.todayGarmin} workoutRecent={dashboard.workoutRecent} medToday={dashboard.medToday} />
                      {dashboard.exerciseToday.length > 0 && (
                        <ExerciseCard exerciseToday={dashboard.exerciseToday} />
                      )}
                      <TrendsCard garminHistory={dashboard.garminHistory} />
                      <div className="flex flex-wrap gap-1.5">
                        {QUICK_ASKS.map(q => (
                          <button key={q.label} onClick={() => handleSend(q.text)}
                            className="px-2.5 py-1 rounded-lg border border-gray-200 bg-white text-[11px] text-gray-600 hover:border-emerald-300 hover:text-emerald-700 hover:bg-emerald-50 active:scale-[0.97] transition-all">
                            {q.label}
                          </button>
                        ))}
                      </div>
                      <button onClick={() => setShowMoreDashboard(false)}
                        className="w-full py-2.5 rounded-xl border border-gray-300 bg-gray-50 text-sm text-gray-500 font-medium hover:text-gray-700 hover:bg-gray-100 hover:border-gray-400 transition-all">
                        ▴ 收起
                      </button>
                    </>
                  )}

                  {/* Inline AI Response */}
                  {inlineResponse && (
                    <InlineResponse ref={inlineResponseRef} question={inlineResponse.question} answer={inlineResponse.answer} loading={inlineResponse.loading} onClose={() => setInlineResponse(null)} />
                  )}
                </div>
              ) : (
                <ChatView messages={messages} loading={loading} doneMessageIds={doneMessageIds} messageFeedback={messageFeedback} onFeedback={handleFeedback} />
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Attachment preview */}
          {(imagePreview || pendingFile) && (
            <div className="border-t border-white/10 bg-slate-950/50 px-4 py-3 backdrop-blur-xl">
              <div className="mx-auto flex max-w-5xl items-center gap-4 rounded-[24px] border border-white/10 bg-white/[0.04] px-4 py-3">
                <div className="relative">
                  {imagePreview ? <img src={imagePreview} alt="待发送图片" className="h-16 w-16 rounded-2xl border border-white/10 object-cover" /> : (
                    <div className="flex h-16 w-16 flex-col items-center justify-center rounded-2xl border border-white/10 bg-slate-900">
                      <svg className="h-6 w-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                    </div>
                  )}
                  <button onClick={clearPendingAttachment} className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full bg-red-500 text-xs text-white transition-colors hover:bg-red-400">×</button>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-white">{imagePreview ? '图片已就绪' : pendingFile?.name}</div>
                  <div className="mt-1 text-xs text-slate-400">补一句目标或上下文后直接发送，AI 会结合附件内容理解你的需求。</div>
                </div>
              </div>
            </div>
          )}

          {/* Bottom fixed area */}
          <div className={`${isWelcome ? 'absolute bottom-0 left-0 right-0 z-30' : ''}`}>
            {/* Quick record bar (welcome mode only) */}
            {isWelcome && (
              <div className="px-4 pt-3 pb-2" style={{ background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', borderTop: '1px solid #E5E5EA' }}>
                <div className="mx-auto max-w-5xl">
                  <QuickRecordBar rhinitisToday={dashboard.rhinitisToday} onWaterRecord={handleWaterRecord} onRhinitisUpdate={dashboard.setRhinitisToday} />
                </div>
              </div>
            )}
            {/* Input */}
            <div className="px-4 py-3" style={isWelcome ? { background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' } : undefined}>
              <div className={`mx-auto max-w-5xl ${isWelcome ? 'rounded-[24px] border border-gray-200' : 'rounded-[30px] border border-white/10 bg-white/[0.04] shadow-[0_20px_60px_rgba(2,6,23,0.35)]'}`}
                style={isWelcome ? { background: '#F2F2F7' } : undefined}>
                <div className="flex items-center gap-3 px-4 py-2.5 pb-[max(0.625rem,env(safe-area-inset-bottom))]">
                  <input ref={fileInputRef} type="file" accept="image/*,.pdf,.txt,.md,.csv,.json,.py,.js,.ts,.html,.xml,.log,.yaml,.yml" className="hidden" onChange={handleImageUpload} />
                  <button onClick={() => fileInputRef.current?.click()} disabled={imageUploading}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all"
                    style={isWelcome ? { color: '#AEAEB2' } : { color: imageUploading ? '#fff' : '#94a3b8' }} title="上传图片或文件">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" /></svg>
                  </button>
                  <button onClick={handleVoiceToggle}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all"
                    style={isWelcome ? { color: isRecording ? '#FF3B30' : '#AEAEB2' } : { color: isRecording ? '#fff' : '#94a3b8', background: isRecording ? '#FF3B30' : undefined }} title={isRecording ? '停止录音' : '语音输入'}>
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      {isRecording ? <rect x="6" y="6" width="12" height="12" rx="2" /> : <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />}
                    </svg>
                  </button>
                  <input type="text" value={inputText} onChange={(e) => setInputText(e.target.value)} onKeyDown={handleKeyDown} onPaste={handlePaste}
                    placeholder={isRecording ? '正在录音...' : (pendingImage || pendingFile) ? '输入描述或问题（可直接发送）' : '用一句完整目标开始...'}
                    className="flex-1 bg-transparent text-sm outline-none"
                    style={isWelcome ? { color: '#1C1C1E' } : { color: '#fff' }}
                    disabled={isRecording} />
                  {inlineMode && (
                    <button onClick={() => { setInlineMode(false); setInlineResponse(null); setMessages([]); setConversationId(undefined); }}
                      className="shrink-0 px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition-all"
                      style={{ color: '#007AFF', borderColor: 'rgba(0,122,255,0.25)' }}>新开对话</button>
                  )}
                  {!inlineMode && hasMessages && (
                    <button onClick={() => { setInlineMode(true); setMessages([]); setConversationId(undefined); }}
                      className="shrink-0 px-2.5 py-1.5 rounded-lg text-[11px] font-medium border transition-all"
                      style={{ color: '#8E8E93', borderColor: '#E5E5EA' }}>首页</button>
                  )}
                  <button onClick={() => handleSend()} disabled={!inputText.trim() && !pendingImage && !pendingFile}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all active:scale-95"
                    style={{ background: (inputText.trim() || pendingImage || pendingFile) ? '#007AFF' : (isWelcome ? '#E5E5EA' : 'rgba(255,255,255,0.08)'), color: (inputText.trim() || pendingImage || pendingFile) ? '#fff' : '#AEAEB2' }}>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" /></svg>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
