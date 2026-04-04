'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { api, chatApi, openclawApi, sharedApi, feedbackApi, dailyHealthApi, healthScoreApi, supplementApi, garminAnalysisApi, ChatMessage, Conversation, DietSavedData, ActivitySavedData } from '@/services/api';
import { relativeTime } from '@/utils/timeFormat';
import NotificationCenter from '@/components/NotificationCenter';

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
/* ── Animated Score Ring ── */
function AnimatedRing({ score, size = 130, strokeWidth = 10 }: { score: number; size?: number; strokeWidth?: number }) {
  const [offset, setOffset] = useState(0);
  const r = (size - strokeWidth) / 2;
  const c = 2 * Math.PI * r;
  const target = c - (score / 100) * c;
  useEffect(() => { setOffset(c); const t = setTimeout(() => setOffset(target), 80); return () => clearTimeout(t); }, [score, c, target]);
  const color = score >= 80 ? '#22c55e' : score >= 60 ? '#f59e0b' : '#ef4444';
  return (
    <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#dcfce7" strokeWidth={strokeWidth} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={strokeWidth}
        strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
        style={{ transition: 'stroke-dashoffset 1.5s cubic-bezier(0.4,0,0.2,1)' }} />
    </svg>
  );
}

/* ── SVG Sparkline ── */
function WelcomeSparkline({ data, color = '#22c55e', w = 130, h = 36 }: { data: number[]; color?: string; w?: number; h?: number }) {
  if (!data.length) return null;
  const max = Math.max(...data), min = Math.min(...data), range = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * (h - 4) - 2}`).join(' ');
  const gid = 'g' + color.replace('#', '');
  return (
    <svg width={w} height={h} style={{ overflow: 'visible' }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.15" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon fill={`url(#${gid})`} points={`0,${h} ${pts} ${w},${h}`} />
      <polyline fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" points={pts} />
    </svg>
  );
}

/* ── Mini Bar Chart ── */
function MiniBarChart({ data, color = '#22c55e', w = 150, h = 40 }: { data: { label: string; value: number }[]; color?: string; w?: number; h?: number }) {
  const max = Math.max(...data.map(d => d.value)) || 1;
  const bw = w / data.length - 4;
  return (
    <svg width={w} height={h + 14}>
      {data.map((d, i) => {
        const bh = d.value > 0 ? Math.max((d.value / max) * h, 3) : 3;
        return (
          <g key={i}>
            <rect x={i * (bw + 4)} y={h - bh} width={bw} height={bh} rx={3}
              fill={d.value > 0 ? color : '#e5e7eb'} opacity={d.value > 0 ? 1 : 0.4} />
            <text x={i * (bw + 4) + bw / 2} y={h + 11} textAnchor="middle" fontSize="9" fill="#9ca3af">{d.label}</text>
          </g>
        );
      })}
    </svg>
  );
}

/* ── Sleep Stage Bar ── */
function SleepStageBar({ deep, rem, light }: { deep: number; rem: number; light: number }) {
  const t = deep + rem + light;
  if (t <= 0) return null;
  return (
    <div style={{ display: 'flex', height: 10, borderRadius: 8, overflow: 'hidden', background: '#f3f4f6' }}>
      <div style={{ width: `${(deep / t) * 100}%`, background: '#065f46', transition: 'width 1s' }} />
      <div style={{ width: `${(rem / t) * 100}%`, background: '#22c55e', transition: 'width 1s' }} />
      <div style={{ width: `${(light / t) * 100}%`, background: '#bbf7d0', transition: 'width 1s' }} />
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

// 静态兜底 Metrics（无 Garmin 数据时展示）
const STATIC_METRICS = [
  { label: '技能驱动', value: '查询 / 记录 / 分析', description: '一句话描述目标，AI 自动选择合适的技能组合完成任务。' },
  { label: '数据感知', value: '语音 / 图片 / 文件', description: '同一输入栏就能完成记录、分析和补充说明。' },
  { label: '行动建议', value: '饮食 / 运动 / 节奏', description: '把建议收敛成可执行动作，而不是泛泛健康话术。' },
];

type RichMetric = {
  label: string;
  icon: string;
  primary: string;        // 大数字
  secondary?: string;     // 大数字旁的副文
  subs: { icon: string; label: string; value: string; color?: string }[];
  gradient: string;
  border: string;
  accent: string;
};

function buildRichMetrics(g: any): RichMetric[] {
  if (!g) return [];
  const metrics: RichMetric[] = [];

  // 睡眠
  if (g.sleep_score != null) {
    const hours = g.total_sleep_duration ? (g.total_sleep_duration / 60) : 0;
    const h = Math.floor(hours);
    const m = Math.round((hours - h) * 60);
    const durationText = hours > 0 ? `${h}小时${m > 0 ? m + '分钟' : ''}` : '';
    const subs: RichMetric['subs'] = [];
    if (durationText) subs.push({ icon: '◷', label: '持续时间', value: durationText });
    if (g.deep_sleep_duration) subs.push({ icon: '●', label: '深睡', value: `${(g.deep_sleep_duration / 60).toFixed(1)}h`, color: 'text-indigo-400' });
    if (g.rem_sleep_duration) subs.push({ icon: '●', label: 'REM', value: `${(g.rem_sleep_duration / 60).toFixed(1)}h`, color: 'text-purple-400' });
    if (g.light_sleep_duration) subs.push({ icon: '●', label: '浅睡', value: `${(g.light_sleep_duration / 60).toFixed(1)}h`, color: 'text-sky-400' });
    metrics.push({
      label: '昨夜睡眠', icon: '🌙',
      primary: `${g.sleep_score}分`,
      secondary: hours > 0 ? `${hours.toFixed(1)}h` : undefined,
      subs,
      gradient: 'from-indigo-500/20 to-purple-600/10', border: 'border-indigo-400/20', accent: 'text-indigo-300',
    });
  }

  // HRV
  if (g.hrv != null) {
    const statusMap: Record<string, [string, string]> = { balanced: ['均衡', 'text-emerald-400'], unbalanced: ['不平衡', 'text-amber-400'], low: ['偏低', 'text-red-400'] };
    const [statusText, statusColor] = statusMap[g.hrv_status] || ['—', 'text-slate-400'];
    const subs: RichMetric['subs'] = [
      { icon: '●', label: '状态', value: statusText, color: statusColor },
    ];
    if (g.hrv_7day_avg) subs.push({ icon: '∅', label: '7日均值', value: `${Math.round(g.hrv_7day_avg)} ms` });
    if (g.resting_heart_rate) subs.push({ icon: '♡', label: '静息心率', value: `${g.resting_heart_rate} bpm` });
    metrics.push({
      label: 'HRV 状态', icon: '💓',
      primary: `${Math.round(g.hrv)}`,
      secondary: '毫秒',
      subs,
      gradient: 'from-rose-500/20 to-pink-600/10', border: 'border-rose-400/20', accent: 'text-rose-300',
    });
  }

  // Body Battery
  if (g.body_battery_most_charged != null) {
    const level = g.body_battery_most_charged >= 75 ? '充沛' : g.body_battery_most_charged >= 50 ? '中等' : '偏低';
    const levelColor = g.body_battery_most_charged >= 75 ? 'text-emerald-400' : g.body_battery_most_charged >= 50 ? 'text-amber-400' : 'text-red-400';
    const subs: RichMetric['subs'] = [
      { icon: '↑', label: '峰值', value: `${g.body_battery_most_charged}`, color: 'text-emerald-400' },
    ];
    if (g.body_battery_lowest != null) subs.push({ icon: '↓', label: '最低', value: `${g.body_battery_lowest}` });
    if (g.body_battery_drained != null) subs.push({ icon: '⚡', label: '消耗', value: `${g.body_battery_drained > 0 ? '-' : ''}${g.body_battery_drained}`, color: 'text-red-400' });
    if (g.stress_level != null) subs.push({ icon: '◎', label: '压力', value: `${g.stress_level}` });
    metrics.push({
      label: '身体电量', icon: '🔋',
      primary: `${g.body_battery_current ?? g.body_battery_most_charged}`,
      secondary: `/ 100  ${level}`,
      subs,
      gradient: 'from-amber-500/20 to-orange-600/10', border: 'border-amber-400/20', accent: 'text-amber-300',
    });
  }

  // 步数 + 心率（第四张卡）
  if (g.steps != null) {
    const subs: RichMetric['subs'] = [];
    if (g.active_calories) subs.push({ icon: '~', label: '活动卡路里', value: `${g.active_calories} kcal`, color: 'text-orange-400' });
    if (g.resting_heart_rate && !g.hrv) subs.push({ icon: '♡', label: '静息心率', value: `${g.resting_heart_rate} bpm` });
    if (g.calories_burned) subs.push({ icon: '∑', label: '总消耗', value: `${g.calories_burned} kcal` });
    metrics.push({
      label: '今日活动', icon: '👟',
      primary: g.steps.toLocaleString(),
      secondary: '步',
      subs,
      gradient: 'from-cyan-500/20 to-teal-600/10', border: 'border-cyan-400/20', accent: 'text-cyan-300',
    });
  }

  return metrics.slice(0, 4);
}

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
  const [briefingPreview, setBriefingPreview] = useState<string | null>(null);
  const [briefingConvId, setBriefingConvId] = useState<number | undefined>();
  const [todayGarmin, setTodayGarmin] = useState<any>(null);
  // 首页聚合数据
  const [healthScore, setHealthScore] = useState<any>(null);
  const [supplementStatus, setSupplementStatus] = useState<any[]>([]);
  const [suppExpanded, setSuppExpanded] = useState(false);
  const [garminHistory, setGarminHistory] = useState<any[]>([]);

  useEffect(() => { document.title = 'AI 助理 | 健康管理'; }, []);
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [dietNotification, setDietNotification] = useState<DietSavedData | null>(null);
  const [activityNotifications, setActivityNotifications] = useState<ActivitySavedData[]>([]);
  const [planCreatedNotification, setPlanCreatedNotification] = useState<{message: string; planId?: number} | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [showAppsMenu, setShowAppsMenu] = useState(false);
  const appsMenuRef = useRef<HTMLDivElement>(null);
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
      const convList: Conversation[] = response.data || [];
      setConversations(convList);
      // 提取每日简报摘要，用于欢迎屏展示
      const briefingConv = convList.find(c => c.title === '每日健康简报');
      if (briefingConv) {
        setBriefingConvId(briefingConv.id);
        setBriefingPreview(briefingConv.last_message || null);
      }
    } catch (e) {
      console.error('加载对话列表失败:', e);
    }
  }, []);

  // 加载今日 Garmin 数据，用于欢迎屏实时指标
  const loadTodayGarmin = useCallback(async () => {
    try {
      // 尝试今天的数据，没有则回退到昨天（Garmin 可能还没同步今天的）
      const today = new Date().toISOString().slice(0, 10);
      const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
      const res = await dailyHealthApi.getMyGarminData(yesterday, today);
      const records: any[] = res.data || [];
      // 优先用最新的有数据的记录
      const latest = records.sort((a: any, b: any) =>
        (b.record_date || '').localeCompare(a.record_date || '')
      ).find((r: any) => r.sleep_score || r.hrv || r.steps > 0);
      if (latest) setTodayGarmin(latest);
      else if (records.length > 0) setTodayGarmin(records[records.length - 1]);
    } catch (e) {
      // 非关键，静默处理
    }
  }, []);

  // 加载首页聚合数据（健康评分、补剂、7日趋势）
  const loadDashboardData = useCallback(async () => {
    const today = new Date().toISOString().slice(0, 10);
    // 并行请求
    const [scoreRes, suppRes, histRes] = await Promise.allSettled([
      healthScoreApi.getDailyScore(today),
      supplementApi.getMyRecordsWithStatus(today),
      dailyHealthApi.getMyGarminData(
        new Date(Date.now() - 13 * 86400000).toISOString().slice(0, 10),
        today
      ),
    ]);
    if (scoreRes.status === 'fulfilled') setHealthScore(scoreRes.value.data);
    if (suppRes.status === 'fulfilled') {
      const raw = suppRes.value.data;
      setSupplementStatus(Array.isArray(raw) ? raw : raw?.records || []);
    }
    if (histRes.status === 'fulfilled') {
      const records = histRes.value.data || [];
      setGarminHistory(
        [...records].sort((a: any, b: any) => (a.record_date || '').localeCompare(b.record_date || ''))
      );
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
    loadTodayGarmin();
    loadDashboardData();
  }, [loadConversations, loadTodayGarmin, loadDashboardData, router]);

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
  const BRIEFING_TITLE = '每日健康简报';
  const WEEKLY_TITLE = '每周健康周报';
  const PINNED_TITLES = [BRIEFING_TITLE, WEEKLY_TITLE];

  const filteredConversations = conversations.filter(conv =>
    conv.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (conv.last_message && conv.last_message.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  // 简报/周报始终置顶，日报在周报之前
  const sortedConversations = [
    ...filteredConversations.filter(c => c.title === BRIEFING_TITLE),
    ...filteredConversations.filter(c => c.title === WEEKLY_TITLE),
    ...filteredConversations.filter(c => !PINNED_TITLES.includes(c.title)),
  ];

  const totalPages = Math.ceil(sortedConversations.length / itemsPerPage);
  const paginatedConversations = sortedConversations.slice(
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
  const [dailyInsight, setDailyInsight] = useState<{summary?: string; content?: string; review_date?: string} | null>(null);

  // 加载动态快速问题 + 每日AI洞察
  useEffect(() => {
    api.get('/quick-questions/me?limit=6').then(res => {
      if (res.data && Array.isArray(res.data) && res.data.length > 0) {
        setDynamicQuestions(res.data);
      }
    }).catch(() => {});

    // 加载最近的每日AI洞察
    api.get('/ai-insights/insights/daily?days=2').then(res => {
      const items = res.data?.items || [];
      if (items.length > 0) {
        setDailyInsight(items[0]);
      }
    }).catch(() => {});
  }, []);

  const activeQuickQuestions = dynamicQuestions;
  const richMetrics = buildRichMetrics(todayGarmin);
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
  const isWelcome = visibleMessages.length === 0 && !loading;

  // 首页趋势数据
  const last7 = garminHistory.slice(-7);
  const prev7 = garminHistory.slice(-14, -7);
  const avg = (arr: number[]) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
  const pctChange = (cur: number, prev: number) => prev > 0 ? ((cur - prev) / prev * 100).toFixed(1) : '0';
  const hrValues = last7.map((r: any) => r.resting_heart_rate || r.avg_heart_rate).filter(Boolean);
  const hrvValues = last7.map((r: any) => r.hrv).filter(Boolean);
  const stressValues = last7.map((r: any) => r.stress_level).filter(Boolean);
  const stepsWeekData = last7.map((r: any) => ({
    label: ['日', '一', '二', '三', '四', '五', '六'][new Date(r.record_date).getDay()],
    value: r.steps || 0,
  }));
  const hrAvg = Math.round(avg(hrValues));
  const hrvAvg = Math.round(avg(hrvValues));
  const stressAvg = Math.round(avg(stressValues));
  const stepsAvg = Math.round(avg(last7.map((r: any) => r.steps || 0)));
  const prevHrAvg = Math.round(avg(prev7.map((r: any) => r.resting_heart_rate || r.avg_heart_rate).filter(Boolean)));
  const prevHrvAvg = Math.round(avg(prev7.map((r: any) => r.hrv).filter(Boolean)));
  const prevStressAvg = Math.round(avg(prev7.map((r: any) => r.stress_level).filter(Boolean)));
  const prevStepsAvg = Math.round(avg(prev7.map((r: any) => r.steps || 0)));

  // 补剂进度（去重 + 已服用排前面 + 分页）
  const timingLabels: Record<string, string> = { morning: '早晨', noon: '中午', evening: '晚上', bedtime: '睡前' };
  const suppDeduped = (() => {
    const seen = new Set<string>();
    return supplementStatus.filter((s: any) => {
      const name = s.supplement?.name || s.supplement_name || s.name;
      const timing = s.supplement?.timing || s.timing || 'morning';
      const key = `${name}_${timing}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  })();
  const suppChecked = suppDeduped.filter((s: any) => s.record?.taken || s.is_taken || s.checked).length;
  const suppTotal = suppDeduped.length;
  const SUPP_PAGE_SIZE = 6;
  const suppGrouped = (() => {
    const groups: Record<string, any[]> = {};
    for (const s of suppDeduped) {
      const timing = s.supplement?.timing || s.timing || 'morning';
      if (!groups[timing]) groups[timing] = [];
      groups[timing].push(s);
    }
    // 每组内已服用排前面
    for (const key of Object.keys(groups)) {
      groups[key].sort((a: any, b: any) => {
        const aTaken = a.record?.taken || a.is_taken || a.checked ? 1 : 0;
        const bTaken = b.record?.taken || b.is_taken || b.checked ? 1 : 0;
        return bTaken - aTaken;
      });
    }
    return groups;
  })();
  // 扁平化用于分页
  const suppFlat = ['morning', 'noon', 'evening', 'bedtime'].flatMap(t =>
    (suppGrouped[t] || []).map((s: any) => ({ ...s, _timing: t }))
  );
  const suppVisible = suppExpanded ? suppFlat : suppFlat.slice(0, SUPP_PAGE_SIZE);
  const suppHasMore = suppFlat.length > SUPP_PAGE_SIZE;

  // 睡眠分析数据
  const sleepDeep = todayGarmin?.deep_sleep_duration ? todayGarmin.deep_sleep_duration / 60 : 0;
  const sleepRem = todayGarmin?.rem_sleep_duration ? todayGarmin.rem_sleep_duration / 60 : 0;
  const sleepLight = todayGarmin?.light_sleep_duration ? todayGarmin.light_sleep_duration / 60 : 0;
  const sleepTotal = todayGarmin?.total_sleep_duration ? todayGarmin.total_sleep_duration / 60 : 0;
  const sleepH = Math.floor(sleepTotal);
  const sleepM = Math.round((sleepTotal - sleepH) * 60);

  return (
    <div className="fixed inset-0 overflow-hidden" style={{ fontFamily: UI_FONT_STACK }}>
      {/* Header */}
      <header className="relative z-50 backdrop-blur-md bg-white/80 border-b border-gray-100">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <button onClick={handleNewChat} className="flex items-center gap-2 hover:opacity-80 transition-opacity">
              <div className="w-8 h-8 rounded-lg bg-green-500 flex items-center justify-center">
                <span className="text-white text-sm font-bold">H</span>
              </div>
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
                    {[
                      { label: '概览', items: [{ href: '/overview', name: '健康概览', icon: '📊' }, { href: '/daily-insights', name: '今日建议', icon: '✨' }, { href: '/smart-plan', name: '智能计划', icon: '📅' }, { href: '/family', name: '家庭', icon: '👨‍👩‍👦' }] },
                      { label: '追踪', items: [{ href: '/workout', name: '运动', icon: '🏋️' }, { href: '/sleep', name: '睡眠', icon: '🌙' }, { href: '/garmin', name: 'Garmin', icon: '⌚' }, { href: '/weight', name: '体重', icon: '⚖️' }, { href: '/heart-rate', name: '心率', icon: '❤️' }, { href: '/blood-pressure', name: '血压', icon: '🩺' }, { href: '/mood', name: '情绪', icon: '😊' }] },
                      { label: '记录', items: [{ href: '/supplements', name: '补剂', icon: '💊' }, { href: '/diet', name: '饮食', icon: '🍽️' }, { href: '/water', name: '饮水', icon: '💧' }, { href: '/checkin', name: '打卡', icon: '✅' }, { href: '/rhinitis', name: '鼻炎', icon: '👃' }] },
                      { label: '管理', items: [{ href: '/genetic', name: '基因', icon: '🧬' }, { href: '/medical-exams', name: '体检', icon: '📋' }, { href: '/goals', name: '目标', icon: '🎯' }, { href: '/settings', name: '设置', icon: '⚙️' }] },
                    ].map(group => (
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

      {/* 背景：欢迎屏用浅色，对话用深色 */}
      {isWelcome ? (
        <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, #f0fdf4 0%, #f9fafb 25%)' }} />
      ) : (
        <>
          <div className="absolute inset-0 bg-gradient-to-br from-[#04111f] via-[#0b1b24] to-[#041428]" />
          <div
            className="absolute inset-0 opacity-70"
            style={{
              backgroundImage: 'radial-gradient(circle at 16% 14%, rgba(16,185,129,0.24), transparent 30%), radial-gradient(circle at 86% 16%, rgba(45,212,191,0.18), transparent 30%), linear-gradient(to right, rgba(148,163,184,0.07) 1px, transparent 1px), linear-gradient(to bottom, rgba(148,163,184,0.07) 1px, transparent 1px)',
              backgroundSize: 'auto, auto, 56px 56px, 56px 56px',
            }}
          />
          <div className="absolute inset-x-0 bottom-0 h-40 bg-gradient-to-t from-slate-950 via-slate-950/50 to-transparent" />
        </>
      )}

      <div className="relative flex overflow-hidden" style={{ height: 'calc(100vh - 56px)' }}>
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
                  {paginatedConversations.map(conv => {
                    const isBriefing = conv.title === BRIEFING_TITLE;
                    const isWeekly = conv.title === WEEKLY_TITLE;
                    const isPinned = isBriefing || isWeekly;
                    return (
                    <button
                      key={conv.id}
                      onClick={() => loadConversation(conv.id)}
                      className={`group w-full rounded-[26px] border px-4 py-4 text-left transition-all ${
                        conv.id === conversationId
                          ? `border-white/15 bg-white/10 shadow-[0_20px_50px_rgba(15,23,42,0.35)] ${modeCopy.accentTextClass}`
                          : isBriefing
                            ? 'border-amber-400/20 bg-amber-400/[0.06] hover:border-amber-400/30 hover:bg-amber-400/[0.10]'
                            : isWeekly
                              ? 'border-purple-400/20 bg-purple-400/[0.06] hover:border-purple-400/30 hover:bg-purple-400/[0.10]'
                              : 'border-transparent bg-white/[0.03] hover:border-white/10 hover:bg-white/[0.06]'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl ${isBriefing ? 'bg-amber-400/20' : isWeekly ? 'bg-purple-400/20' : modeCopy.badgeClass}`}>
                          {isBriefing
                            ? <span className="text-base">🌅</span>
                            : isWeekly
                              ? <span className="text-base">📊</span>
                              : <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m6-6H6" /></svg>
                          }
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className={`flex items-center gap-2 text-sm font-medium leading-6 ${isBriefing ? 'text-amber-200' : isWeekly ? 'text-purple-200' : 'text-white'}`}>
                            <span className="line-clamp-1">{conv.title}</span>
                            {isBriefing && <span className="shrink-0 rounded-full bg-amber-400/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-300">每日</span>}
                            {isWeekly && <span className="shrink-0 rounded-full bg-purple-400/20 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-purple-300">周报</span>}
                          </div>
                          {conv.last_message && (
                            <div className="mt-1 text-xs leading-5 text-slate-400 truncate">{conv.last_message.length > 30 ? conv.last_message.slice(0, 30) + '...' : conv.last_message}</div>
                          )}
                          {conv.updated_at && (
                            <div className="mt-0.5 text-[11px] text-slate-500">{relativeTime(conv.updated_at)}</div>
                          )}
                        </div>
                      </div>
                      <div className="mt-3 flex items-center justify-between">
                        <span className="text-[11px] uppercase tracking-[0.24em] text-slate-500">
                          {isBriefing ? '📊 日报' : isWeekly ? '📈 周报' : `#${conv.id}`}
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
                  );})}
                </div>
              )}
            </div>

            {sortedConversations.length > itemsPerPage && (
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
          {/* HEALTH AI toolbar removed */}

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
              {isWelcome ? (
                <div className="space-y-4">
                  {/* Greeting */}
                  {(() => {
                    const h = new Date().getHours();
                    const greeting = h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好';
                    const displayName = user?.name || user?.username || '';
                    return (
                      <div className="mb-4">
                        <h1 className="text-2xl font-bold text-gray-800 mb-1">
                          {greeting}{displayName ? `，${displayName}` : ''} 👋
                        </h1>
                        {(user as any)?.created_at && (
                          <p className="text-sm text-gray-400">
                            今天是你保持健康记录的第 {Math.max(1, Math.ceil((Date.now() - new Date((user as any).created_at).getTime()) / 86400000))} 天
                          </p>
                        )}
                      </div>
                    );
                  })()}

                  {/* Score + Metric Cards */}
                  <div className="grid grid-cols-12 gap-4">
                    {/* Health Score Ring */}
                    <div className="col-span-12 md:col-span-3 bg-white rounded-2xl border border-gray-100 p-5 shadow-sm flex flex-col items-center justify-center py-6">
                      <div className="relative mb-3">
                        <AnimatedRing score={healthScore?.total_score || 0} />
                        <div className="absolute inset-0 flex flex-col items-center justify-center">
                          <span className="text-4xl font-bold text-gray-800">{healthScore?.total_score || '--'}</span>
                          <span className="text-xs text-gray-400">健康评分</span>
                        </div>
                      </div>
                      {sleepTotal > 0 && (
                        <div className="flex items-center gap-1.5 text-xs text-gray-400">
                          <span>🌙</span> {sleepH}小时{sleepM > 0 ? `${sleepM}分钟` : ''}
                        </div>
                      )}
                    </div>

                    {/* 4 Metric Cards */}
                    <div className="col-span-12 md:col-span-9 grid grid-cols-2 lg:grid-cols-4 gap-3">
                      {richMetrics.length > 0 ? richMetrics.map((m) => (
                        <div key={m.label} className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm hover:shadow-md hover:border-gray-200 transition-all duration-300 flex items-center gap-4 group cursor-pointer">
                          <div className="w-11 h-11 rounded-xl flex items-center justify-center text-lg transition-transform duration-300 group-hover:scale-110"
                            style={{ background: m.gradient.includes('indigo') ? '#8b5cf615' : m.gradient.includes('rose') ? '#ef444415' : m.gradient.includes('amber') ? '#f59e0b15' : '#22c55e15' }}>
                            {m.icon}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-xs text-gray-400 mb-0.5">{m.label}</p>
                            <div className="flex items-baseline gap-1">
                              <span className="text-xl font-semibold text-gray-800">{m.primary}</span>
                              {m.secondary && <span className="text-xs text-gray-400">{m.secondary}</span>}
                            </div>
                            {m.subs[0] && <p className="text-xs text-gray-400 truncate mt-0.5">{m.subs[0].label} {m.subs[0].value}</p>}
                          </div>
                          <svg className="w-4 h-4 text-gray-300 group-hover:text-gray-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" /></svg>
                        </div>
                      )) : (
                        STATIC_METRICS.map((m) => (
                          <div key={m.label} className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
                            <div className="text-xs text-gray-400 mb-1">{m.label}</div>
                            <div className="text-lg font-semibold text-gray-800">{m.value}</div>
                            <div className="mt-1 text-xs text-gray-400">{m.description}</div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>

                  {/* Trend Cards */}
                  {garminHistory.length > 0 && (
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                      {/* Heart Rate */}
                      <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col justify-between">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium text-gray-600">心率趋势</span>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${Number(pctChange(hrAvg, prevHrAvg)) <= 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-500'}`}>
                            {Number(pctChange(hrAvg, prevHrAvg)) <= 0 ? '↓' : '↑'} {Math.abs(Number(pctChange(hrAvg, prevHrAvg)))}%
                          </span>
                        </div>
                        <div className="flex items-baseline gap-1 mb-3">
                          <span className="text-lg font-semibold text-gray-800">{hrAvg || '--'}</span>
                          <span className="text-xs text-gray-400">7日均值 bpm</span>
                        </div>
                        <div className="flex justify-center"><WelcomeSparkline data={hrValues} color="#ef4444" /></div>
                      </div>

                      {/* HRV */}
                      <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col justify-between">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium text-gray-600">HRV 趋势</span>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${Number(pctChange(hrvAvg, prevHrvAvg)) >= 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-500'}`}>
                            {Number(pctChange(hrvAvg, prevHrvAvg)) >= 0 ? '↑' : '↓'} {Math.abs(Number(pctChange(hrvAvg, prevHrvAvg)))}%
                          </span>
                        </div>
                        <div className="flex items-baseline gap-1 mb-3">
                          <span className="text-lg font-semibold text-gray-800">{hrvAvg || '--'}</span>
                          <span className="text-xs text-gray-400">7日均值 ms</span>
                        </div>
                        <div className="flex justify-center"><WelcomeSparkline data={hrvValues} color="#6366f1" /></div>
                      </div>

                      {/* Steps */}
                      <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col justify-between">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium text-gray-600">本周步数</span>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${Number(pctChange(stepsAvg, prevStepsAvg)) >= 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-500'}`}>
                            {Number(pctChange(stepsAvg, prevStepsAvg)) >= 0 ? '↑' : '↓'} {Math.abs(Number(pctChange(stepsAvg, prevStepsAvg)))}%
                          </span>
                        </div>
                        <div className="flex items-baseline gap-1 mb-3">
                          <span className="text-lg font-semibold text-gray-800">{stepsAvg ? stepsAvg.toLocaleString() : '--'}</span>
                          <span className="text-xs text-gray-400">日均</span>
                        </div>
                        <div className="flex justify-center"><MiniBarChart data={stepsWeekData} /></div>
                      </div>

                      {/* Stress */}
                      <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm hover:shadow-md transition-all duration-300 flex flex-col justify-between">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-medium text-gray-600">压力趋势</span>
                          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${Number(pctChange(stressAvg, prevStressAvg)) <= 0 ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-500'}`}>
                            {Number(pctChange(stressAvg, prevStressAvg)) <= 0 ? '↓' : '↑'} {Math.abs(Number(pctChange(stressAvg, prevStressAvg)))}%
                          </span>
                        </div>
                        <div className="flex items-baseline gap-1 mb-3">
                          <span className="text-lg font-semibold text-gray-800">{stressAvg || '--'}</span>
                          <span className="text-xs text-gray-400">7日均值</span>
                        </div>
                        <div className="flex justify-center"><WelcomeSparkline data={stressValues} color="#f59e0b" /></div>
                      </div>
                    </div>
                  )}

                  {/* Bottom 3-column: Supplements / Quick Actions / Sleep */}
                  <div className="grid grid-cols-12 gap-4">
                    {/* Supplements */}
                    <div className="col-span-12 md:col-span-4 bg-white rounded-2xl border border-gray-100 p-5 shadow-sm hover:shadow-md transition-all duration-300">
                      <div className="flex items-center justify-between mb-4">
                        <div>
                          <h3 className="text-base font-bold text-gray-800">今日补剂</h3>
                        </div>
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-20 bg-gray-100 rounded-full overflow-hidden">
                            <div className="h-full bg-green-500 rounded-full transition-all duration-500"
                              style={{ width: suppTotal > 0 ? `${(suppChecked / suppTotal) * 100}%` : '0%' }} />
                          </div>
                          <span className="text-sm font-semibold text-gray-600">{suppChecked}/{suppTotal}</span>
                        </div>
                      </div>
                      <div>
                        {suppFlat.length > 0 ? (() => {
                          let lastTiming = '';
                          return (
                            <>
                              {suppVisible.map((s: any, i: number) => {
                                const taken = s.record?.taken || s.is_taken || s.checked;
                                const name = s.supplement?.name || s.supplement_name || s.name;
                                const dosage = s.supplement?.dosage || s.dosage || s.dose;
                                const showHeader = s._timing !== lastTiming;
                                lastTiming = s._timing;
                                return (
                                  <div key={i}>
                                    {showHeader && <p className="text-xs font-medium text-gray-400 mt-3 mb-1 first:mt-0">{timingLabels[s._timing]}</p>}
                                    <div className="flex items-center gap-3 py-2 px-1 rounded-lg hover:bg-gray-50 transition-colors group">
                                      <div className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 transition-all duration-200 ${
                                        taken ? 'bg-green-500' : 'border-2 border-gray-200 group-hover:border-green-400'
                                      }`}>
                                        {taken && (
                                          <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>
                                        )}
                                      </div>
                                      <span className={`flex-1 text-sm ${taken ? 'text-green-600 font-medium' : 'text-gray-700'}`}>{name}</span>
                                      {dosage && <span className="text-xs text-gray-400 shrink-0">{dosage}</span>}
                                    </div>
                                  </div>
                                );
                              })}
                              {suppHasMore && (
                                <button
                                  onClick={() => setSuppExpanded(!suppExpanded)}
                                  className="w-full mt-2 py-2 text-xs font-medium text-green-600 hover:text-green-700 hover:bg-green-50 rounded-lg transition-colors"
                                >
                                  {suppExpanded ? '收起' : `展开全部 (${suppFlat.length})`}
                                </button>
                              )}
                            </>
                          );
                        })() : (
                          <p className="text-sm text-gray-400 py-4 text-center">暂无补剂计划</p>
                        )}
                      </div>
                    </div>

                    {/* Quick Actions */}
                    <div className="col-span-12 md:col-span-4 bg-white rounded-2xl border border-gray-100 p-5 shadow-sm hover:shadow-md transition-all duration-300">
                      <h3 className="text-sm font-semibold text-gray-700 mb-4">快捷操作</h3>
                      <div className="grid grid-cols-3 gap-2">
                        {[
                          { icon: '⚠️', label: '查看预警', color: '#ef4444', text: '查看今日健康预警和异常提醒' },
                          { icon: '📊', label: '今日概览', color: '#6366f1', text: '查一下我今天的健康数据概览' },
                          { icon: '💊', label: '补剂提醒', color: '#f59e0b', text: '今天还需要吃什么补剂？' },
                          { icon: '💧', label: '记录饮水', color: '#3b82f6', text: '记录喝水250ml' },
                          { icon: '🏃', label: '运动建议', color: '#22c55e', text: '根据我的身体数据和天气，今天适合做什么运动？' },
                          { icon: '🌙', label: '睡眠分析', color: '#8b5cf6', text: '帮我分析一下最近的睡眠质量' },
                        ].map((action) => (
                          <button
                            key={action.label}
                            onClick={() => handleSend(action.text)}
                            className="flex flex-col items-center gap-2 p-3 rounded-xl hover:bg-gray-50 active:scale-95 transition-all duration-200 group"
                          >
                            <div className="w-10 h-10 rounded-xl flex items-center justify-center text-base transition-transform duration-300 group-hover:scale-110"
                              style={{ background: action.color + '12', color: action.color }}>
                              {action.icon}
                            </div>
                            <span className="text-xs text-gray-500 group-hover:text-gray-700 transition-colors">{action.label}</span>
                          </button>
                        ))}
                      </div>
                    </div>

                    {/* Sleep Analysis */}
                    <div className="col-span-12 md:col-span-4 bg-white rounded-2xl border border-gray-100 p-5 shadow-sm hover:shadow-md transition-all duration-300">
                      <div className="flex items-center justify-between mb-5">
                        <h3 className="text-sm font-semibold text-gray-700">睡眠分析</h3>
                        {sleepTotal > 0 && (
                          <span className="text-xs font-medium text-green-600 bg-green-50 px-2 py-0.5 rounded-full">
                            {sleepH}小时{sleepM > 0 ? `${sleepM}分钟` : ''}
                          </span>
                        )}
                      </div>
                      {sleepTotal > 0 ? (
                        <>
                          <SleepStageBar deep={sleepDeep} rem={sleepRem} light={sleepLight} />
                          <div className="mt-5 space-y-3">
                            {[
                              { l: '深睡', v: `${sleepDeep.toFixed(1)}h`, c: '#065f46' },
                              { l: 'REM', v: `${sleepRem.toFixed(1)}h`, c: '#22c55e' },
                              { l: '浅睡', v: `${sleepLight.toFixed(1)}h`, c: '#bbf7d0' },
                            ].map(x => (
                              <div key={x.l} className="flex items-center justify-between">
                                <div className="flex items-center gap-2">
                                  <span className="w-2.5 h-2.5 rounded-full" style={{ background: x.c }} />
                                  <span className="text-sm text-gray-500">{x.l}</span>
                                </div>
                                <span className="text-sm font-medium text-gray-700">{x.v}</span>
                              </div>
                            ))}
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-gray-400 py-8 text-center">暂无睡眠数据</p>
                      )}
                    </div>
                  </div>

                  {/* AI Insights Banner */}
                  <div className="rounded-2xl p-4 flex items-center justify-between border border-green-100"
                    style={{ background: 'linear-gradient(135deg, #f0fdf4, #ecfdf5)' }}>
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-white shadow-sm flex items-center justify-center">
                        <svg className="w-5 h-5 text-emerald-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456z" />
                        </svg>
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-gray-700">AI 洞察</p>
                        <p className="text-xs text-gray-500 mt-0.5 line-clamp-2">
                          {dailyInsight?.summary
                            ? dailyInsight.summary.replace(/[✅☑️🟢#*_`|>\[\]]/g, '').replace(/\n+/g, ' ').trim().slice(0, 100)
                            : todayGarmin
                              ? `步数 ${todayGarmin.steps?.toLocaleString() || '-'} · 睡眠 ${todayGarmin.total_sleep_duration ? Math.floor(todayGarmin.total_sleep_duration / 60) + 'h' + Math.round((todayGarmin.total_sleep_duration / 60 % 1) * 60) + 'm' : '-'} · 点击查看完整分析`
                              : '暂无洞察数据，点击生成今日健康分析'}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={() => handleSend('查看今日 AI 洞察和健康分析详情')}
                      className="px-4 py-2 text-xs font-medium text-white bg-green-500 rounded-xl hover:bg-green-600 active:scale-95 transition-all shadow-sm"
                    >
                      查看详情
                    </button>
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

          {/* 继续推进 bar removed */}

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

          <div className={`px-4 py-4 ${isWelcome ? 'bg-transparent' : 'border-t border-white/10 bg-slate-950/55 backdrop-blur-2xl'}`}>
            <div className={`mx-auto max-w-5xl ${isWelcome
              ? 'rounded-2xl bg-white border border-gray-200 shadow-sm'
              : 'rounded-[30px] border border-white/10 bg-white/[0.04] shadow-[0_20px_60px_rgba(2,6,23,0.35)]'
            }`}>
              {/* Support text + Enter hint removed */}

              <div className="flex items-center gap-3 px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
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
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-all ${
                    isWelcome
                      ? 'text-gray-400 hover:text-gray-600'
                      : imageUploading ? 'bg-white/15 text-white animate-pulse' : 'bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white'
                  }`}
                  title="上传图片或文件"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" />
                  </svg>
                </button>

                <button
                  onClick={handleVoiceToggle}
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition-all ${
                    isWelcome
                      ? isRecording ? 'text-red-500' : 'text-gray-400 hover:text-gray-600'
                      : isRecording ? 'bg-red-500 text-white animate-pulse' : 'bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white'
                  }`}
                  title={isRecording ? '停止录音' : '语音输入'}
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    {isRecording ? (
                      <rect x="6" y="6" width="12" height="12" rx="2" />
                    ) : (
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
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
                  className={`flex-1 bg-transparent text-sm outline-none ${isWelcome ? 'text-gray-600 placeholder-gray-300' : 'text-white placeholder:text-slate-500'}`}
                  disabled={isRecording}
                />

                <button
                  onClick={() => handleSend()}
                  disabled={!inputText.trim() && !pendingImage && !pendingFile}
                  className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all active:scale-95 ${
                    (inputText.trim() || pendingImage || pendingFile)
                      ? 'bg-green-500 hover:bg-green-600 text-white shadow-sm'
                      : isWelcome ? 'bg-gray-100 text-gray-400 cursor-not-allowed' : 'bg-white/8 text-slate-500 cursor-not-allowed'
                  }`}
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 10.5L12 3m0 0l7.5 7.5M12 3v18" /></svg>
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
