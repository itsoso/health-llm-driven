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
  const [waterToday, setWaterToday] = useState<{total_ml: number; goal_ml: number; count: number}>({ total_ml: 0, goal_ml: 2000, count: 0 });
  const [weatherData, setWeatherData] = useState<any>(null);
  const [airData, setAirData] = useState<any>(null);
  const [rhinitisToday, setRhinitisToday] = useState<any>(null);
  const [dietToday, setDietToday] = useState<any>(null);
  const [weightStats, setWeightStats] = useState<any>(null);
  const [quickToast, setQuickToast] = useState<string | null>(null);
  const [bpLatest, setBpLatest] = useState<any>(null);
  const [moodToday, setMoodToday] = useState<any>(null);
  const [medToday, setMedToday] = useState<any[]>([]);
  const [goalsData, setGoalsData] = useState<any[]>([]);
  const [workoutRecent, setWorkoutRecent] = useState<any[]>([]);
  const [examTrends, setExamTrends] = useState<any>(null);
  const [inlineMode, setInlineMode] = useState(true); // 首页内联模式：回复显示在dashboard上
  const [inlineResponse, setInlineResponse] = useState<{question: string; answer: string; loading: boolean} | null>(null);

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
    const results = await Promise.allSettled([
      healthScoreApi.getDailyScore(today),           // 0
      supplementApi.getMyRecordsWithStatus(today),    // 1
      dailyHealthApi.getMyGarminData(                 // 2
        new Date(Date.now() - 13 * 86400000).toISOString().slice(0, 10),
        today
      ),
      api.get(`/water/records/me/date/${today}`),     // 3
      api.get('/environment/weather'),                // 4
      api.get('/environment/air-quality'),             // 5
      api.get('/checkin/me/today'),                    // 6
      api.get(`/diet/records/me/date/${today}`),       // 7
      api.get('/weight/records/me/stats'),             // 8
      api.get('/environment/weather/forecast?days=1'), // 9
      api.get('/blood-pressure/records/me/stats'),     // 10
      api.get('/mood/records/me/today'),               // 11
      api.get('/medication/today/me'),                 // 12
      api.get('/goals/me?status=active'),              // 13
      api.get('/workout/me?days=7'),                   // 14
      api.get('/medical-exams/me/indicator-trends?indicators=HCY,ALT,GGT,TC,FBG,UA'), // 15
    ]);
    const ok = (i: number) => results[i].status === 'fulfilled' ? (results[i] as any).value.data : null;
    if (ok(0)) setHealthScore(ok(0));
    if (ok(1)) {
      const raw = ok(1);
      setSupplementStatus(Array.isArray(raw) ? raw : raw?.records || []);
    }
    if (ok(2)) {
      const records = ok(2) || [];
      setGarminHistory(
        [...records].sort((a: any, b: any) => (a.record_date || '').localeCompare(b.record_date || ''))
      );
    }
    if (ok(3)) {
      const w = ok(3);
      setWaterToday({ total_ml: w?.total_amount || w?.total_ml || 0, goal_ml: w?.target_amount || w?.goal_ml || 2000, count: w?.records_count || w?.count || 0 });
    }
    if (ok(4)) {
      const raw = ok(4);
      // Flatten: API returns { weather: {...}, exercise_advice: {...} }
      const wd = raw?.weather || raw || {};
      // merge forecast temp_min/max
      const fc = ok(9);
      const todayFc = fc?.forecasts?.[0] || (Array.isArray(fc) ? fc[0] : null);
      if (todayFc) {
        wd.temp_min = todayFc.temp_min;
        wd.temp_max = todayFc.temp_max;
      }
      // Get city from user profile
      try {
        const profileRes = await api.get('/profile/me');
        wd.city = profileRes.data?.city || '杭州';
      } catch { wd.city = '杭州'; }
      setWeatherData(wd);
    }
    if (ok(5)) setAirData(ok(5));
    if (ok(6)) setRhinitisToday(ok(6));
    if (ok(7)) setDietToday(ok(7));
    if (ok(8)) setWeightStats(ok(8));
    if (ok(10)) setBpLatest(ok(10));
    if (ok(11)) setMoodToday(ok(11));
    if (ok(12)) setMedToday(Array.isArray(ok(12)) ? ok(12) : []);
    if (ok(13)) setGoalsData(Array.isArray(ok(13)) ? ok(13) : ok(13)?.items || []);
    if (ok(14)) setWorkoutRecent(Array.isArray(ok(14)) ? ok(14) : ok(14)?.items || []);
    if (ok(15)) setExamTrends(ok(15));
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

  // 内联发送（首页模式，不切换到聊天窗口，复用openclawApi.streamMessage）
  const handleInlineSend = async (text?: string) => {
    const msg = (text || inputText).trim();
    if (!msg) return;
    setInputText('');
    setInlineResponse({ question: msg, answer: '', loading: true });
    try {
      let fullText = '';
      const streamIterator = openclawApi.streamMessage(msg, conversationId);
      for await (const data of streamIterator) {
        if (data.conversation_id && !conversationId) setConversationId(data.conversation_id);
        const token = data.choices?.[0]?.delta?.content || data.content || data.token || '';
        if (token) {
          fullText += token;
          setInlineResponse(prev => prev ? { ...prev, answer: fullText } : null);
        }
      }
      setInlineResponse(prev => prev ? { ...prev, loading: false } : null);
    } catch (e) {
      console.error('Inline send error:', e);
      setInlineResponse(prev => prev ? { ...prev, answer: prev?.answer || '请求失败，请重试', loading: false } : null);
    }
  };

  // 发送消息（流式优先，降级到非流式）
  const handleSend = async (text?: string, imageBase64?: string, imageType?: string) => {
    const msg = (text || inputText).trim();
    const hasAttachment = pendingImage || pendingFile;
    if (!msg && !hasAttachment) return;

    // 内联模式：在首页直接显示回复
    if (inlineMode && !hasAttachment) {
      handleInlineSend(text);
      return;
    }

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
  const isWelcome = inlineMode || (visibleMessages.length === 0 && !loading);

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
          <aside className="flex w-[330px] shrink-0 flex-col border-r border-gray-200 bg-white/95 backdrop-blur-xl">
            <div className="border-b border-gray-100 px-4 py-3">
              <div className="flex items-center gap-2">
                <button
                  onClick={handleNewChat}
                  className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-emerald-500 px-4 py-2.5 text-sm font-medium text-white transition-all hover:bg-emerald-600 active:scale-[0.98] shadow-sm"
                >
                  <span className="text-lg leading-none">+</span>
                  新建对话
                </button>
                <button
                  onClick={toggleHistory}
                  className="flex h-10 w-10 items-center justify-center rounded-xl border border-gray-200 bg-gray-50 text-gray-400 transition-all hover:bg-gray-100 hover:text-gray-600"
                  title="收起侧边栏"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11 19l-7-7 7-7M18 19l-7-7 7-7" />
                  </svg>
                </button>
              </div>
              <div className="relative mt-3">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setCurrentPage(1);
                  }}
                  placeholder="搜索对话..."
                  className="w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-2.5 pl-10 text-sm text-gray-700 placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30 focus:border-emerald-400"
                />
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400 text-xs">🔍</span>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto px-3 py-2">
              {conversations.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-gray-200 bg-gray-50 px-6 py-10 text-center text-gray-400">
                  <div className="text-4xl">💬</div>
                  <div className="mt-3 text-sm">还没有历史对话</div>
                </div>
              ) : paginatedConversations.length === 0 ? (
                <div className="rounded-2xl border border-dashed border-gray-200 bg-gray-50 px-6 py-10 text-center text-gray-400">
                  <div className="text-4xl">🔍</div>
                  <div className="mt-3 text-sm">没有找到匹配结果</div>
                </div>
              ) : (
                <div className="space-y-1.5">
                  {paginatedConversations.map(conv => {
                    const isBriefing = conv.title === BRIEFING_TITLE;
                    const isWeekly = conv.title === WEEKLY_TITLE;
                    const isPinned = isBriefing || isWeekly;
                    return (
                    <button
                      key={conv.id}
                      onClick={() => loadConversation(conv.id)}
                      className={`group w-full rounded-2xl border px-3.5 py-3 text-left transition-all ${
                        conv.id === conversationId
                          ? 'border-emerald-200 bg-emerald-50 shadow-sm'
                          : isBriefing
                            ? 'border-amber-100 bg-amber-50/60 hover:border-amber-200 hover:bg-amber-50'
                            : isWeekly
                              ? 'border-purple-100 bg-purple-50/60 hover:border-purple-200 hover:bg-purple-50'
                              : 'border-transparent bg-transparent hover:border-gray-200 hover:bg-gray-50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${isBriefing ? 'bg-amber-100' : isWeekly ? 'bg-purple-100' : 'bg-emerald-100'}`}>
                          {isBriefing
                            ? <span className="text-sm">🌅</span>
                            : isWeekly
                              ? <span className="text-sm">📊</span>
                              : <span className="text-sm">💬</span>
                          }
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className={`flex items-center gap-2 text-sm font-medium leading-6 ${isBriefing ? 'text-amber-700' : isWeekly ? 'text-purple-700' : 'text-gray-800'}`}>
                            <span className="line-clamp-1">{conv.title}</span>
                            {isBriefing && <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold text-amber-600">每日</span>}
                            {isWeekly && <span className="shrink-0 rounded-full bg-purple-100 px-2 py-0.5 text-[10px] font-semibold text-purple-600">周报</span>}
                          </div>
                          {conv.last_message && (
                            <div className="mt-0.5 text-xs leading-5 text-gray-500 truncate">{conv.last_message.length > 30 ? conv.last_message.slice(0, 30) + '...' : conv.last_message}</div>
                          )}
                          {conv.updated_at && (
                            <div className="mt-0.5 text-[11px] text-gray-400">{relativeTime(conv.updated_at)}</div>
                          )}
                        </div>
                      </div>
                      <div className="mt-2 flex items-center justify-between">
                        <span className="text-[11px] text-gray-400">
                          {isBriefing ? '📊 日报' : isWeekly ? '📈 周报' : `#${conv.id}`}
                        </span>
                        <div className="flex items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleShareConversation(conv.id);
                            }}
                            className="text-xs text-gray-400 transition-colors hover:text-gray-700"
                            title="分享对话"
                          >
                            分享
                          </button>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDeleteConversation(conv.id);
                            }}
                            className="text-xs text-gray-400 transition-colors hover:text-red-500"
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
              <div className="border-t border-gray-100 px-4 py-3">
                <div className="flex items-center justify-between text-xs text-gray-500">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="rounded-full border border-gray-200 px-3 py-1.5 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    上一页
                  </button>
                  <span>{currentPage} / {totalPages}</span>
                  <button
                    onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="rounded-full border border-gray-200 px-3 py-1.5 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
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
                <div className="max-w-5xl mx-auto space-y-4">

                  {/* ════════════ HERO — modern gradient card ════════════ */}
                  {(() => {
                    const h = new Date().getHours();
                    const greeting = h < 6 ? '夜深了' : h < 11 ? '早上好' : h < 14 ? '中午好' : h < 18 ? '下午好' : '晚上好';
                    const displayName = user?.name || user?.username || '';
                    const score = healthScore?.total_score || 0;
                    const scoreColor = score >= 80 ? '#34d399' : score >= 60 ? '#fbbf24' : '#f87171';
                    const scoreLabel = score >= 80 ? '状态优秀' : score >= 60 ? '需要关注' : '需要改善';
                    const insightText = dailyInsight?.summary
                      ? dailyInsight.summary.replace(/[✅☑️🟢#*_`|>\[\]]/g, '').replace(/\n+/g, ' ').trim().slice(0, 120)
                      : `睡眠${todayGarmin?.sleep_score || '--'}分 · HRV ${todayGarmin?.hrv || '--'}ms · ${todayGarmin?.steps?.toLocaleString() || '--'}步 · 饮水${waterToday.total_ml}ml`;
                    return (
                      <div className="rounded-3xl p-6 relative overflow-hidden shadow-lg"
                        style={{ background: 'linear-gradient(135deg, #065f46 0%, #047857 40%, #059669 100%)' }}>
                        {/* 装饰圆 */}
                        <div className="absolute -top-12 -right-12 w-40 h-40 rounded-full" style={{ background: 'rgba(255,255,255,0.06)' }} />
                        <div className="absolute -bottom-8 -left-8 w-24 h-24 rounded-full" style={{ background: 'rgba(255,255,255,0.04)' }} />

                        <div className="relative z-10">
                          <div className="flex items-start justify-between mb-4">
                            <div>
                              <h1 className="text-xl font-bold text-white tracking-tight">{greeting}{displayName ? `，${displayName}` : ''}</h1>
                              <p className="text-emerald-200/70 text-sm mt-0.5">{new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })}</p>
                            </div>
                            <button onClick={() => { loadTodayGarmin(); loadDashboardData(); }}
                              className="text-xs text-white/50 hover:text-white transition-colors flex items-center gap-1 bg-white/10 rounded-full px-3 py-1.5">
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                              刷新
                            </button>
                          </div>

                          <div className="flex items-center gap-5">
                            <div className="relative shrink-0">
                              <AnimatedRing score={score} size={88} strokeWidth={7} />
                              <div className="absolute inset-0 flex flex-col items-center justify-center">
                                <span className="text-3xl font-extrabold text-white">{score || '--'}</span>
                                <span className="text-[10px] text-emerald-200/60 font-medium">健康分</span>
                              </div>
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-xs font-bold px-2.5 py-1 rounded-full text-white" style={{ background: `${scoreColor}40`, border: `1px solid ${scoreColor}60` }}>{scoreLabel}</span>
                                {healthScore?.dimensions && Array.isArray(healthScore.dimensions) && (() => {
                                  const dims = healthScore.dimensions as any[];
                                  const worst = dims.reduce((a: any, b: any) => (b.score < a.score ? b : a), dims[0]);
                                  return worst && worst.score < 40 ? (
                                    <span className="text-[11px] px-2 py-0.5 rounded-full font-medium bg-red-500/20 text-red-200 border border-red-400/30">
                                      {worst.name} 偏低
                                    </span>
                                  ) : null;
                                })()}
                              </div>
                              <p className="text-sm text-emerald-100/80 leading-relaxed line-clamp-2">{insightText}</p>
                            </div>
                          </div>

                          {/* 维度条 */}
                          {healthScore?.dimensions && Array.isArray(healthScore.dimensions) && (
                            <div className="grid grid-cols-6 gap-3 mt-5 pt-4 border-t border-white/15">
                              {(healthScore.dimensions as any[]).map((dim: any) => {
                                const s = dim.score || 0;
                                const barColor = s >= 70 ? '#34d399' : s >= 40 ? '#fbbf24' : '#f87171';
                                return (
                                  <div key={dim.name} className="text-center">
                                    <div className="text-xs font-medium text-white/80 mb-1.5">{dim.name}</div>
                                    <div className="h-3 rounded-full bg-white/15 overflow-hidden">
                                      <div className="h-full rounded-full transition-all duration-700" style={{ width: `${s}%`, background: barColor }} />
                                    </div>
                                    <div className="text-xs font-bold text-white/70 mt-1">{s}</div>
                                  </div>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })()}

                  {/* ── 2. Alerts — inline quick actions ── */}
                  {(() => {
                    const alerts: {icon: string; text: string; actionLabel: string; onAction: () => void; color: string; bg: string}[] = [];
                    const hour = new Date().getHours();
                    const today = new Date().toISOString().slice(0, 10);
                    const quickDrinkWater = async (amount: number) => {
                      try {
                        await api.post('/water/records', { record_date: today, amount, drink_type: '水', user_id: 0 });
                        setWaterToday(prev => ({ ...prev, total_ml: prev.total_ml + amount, count: prev.count + 1 }));
                      } catch (e) { console.error('记录饮水失败', e); }
                    };
                    if (hour >= 7) {
                      const waterExpected = hour >= 18 ? 1500 : hour >= 12 ? 800 : 300;
                      if (waterToday.total_ml < waterExpected * 0.3) {
                        alerts.push({ icon: '💧', text: `已${hour}点，饮水仅 ${waterToday.total_ml}ml，需要补充`, actionLabel: '+500ml', onAction: () => quickDrinkWater(500), color: '#ef4444', bg: '#fef2f2' });
                      } else if (waterToday.total_ml < waterExpected * 0.6) {
                        alerts.push({ icon: '💧', text: `今日饮水 ${waterToday.total_ml}ml，建议多喝水`, actionLabel: '+250ml', onAction: () => quickDrinkWater(250), color: '#f59e0b', bg: '#fffbeb' });
                      }
                    }
                    const suppRemaining = suppTotal - suppChecked;
                    if (suppRemaining > 0 && suppTotal > 0 && hour >= 7) {
                      alerts.push({ icon: '💊', text: `${suppRemaining}项补剂待服用`, actionLabel: '去打卡', onAction: () => router.push('/supplements'), color: '#8b5cf6', bg: '#f5f3ff' });
                    }
                    // SpO2 低值告警
                    if (todayGarmin?.spo2_avg && todayGarmin.spo2_avg < 95) {
                      alerts.push({ icon: '🫁', text: `血氧 ${todayGarmin.spo2_avg}% 低于正常值(95%)，注意休息`, actionLabel: '查看', onAction: () => router.push('/garmin'), color: '#ef4444', bg: '#fef2f2' });
                    }
                    // HRV 异常
                    if (todayGarmin?.hrv && todayGarmin.hrv < 40) {
                      alerts.push({ icon: '💓', text: `HRV ${todayGarmin.hrv}ms 偏低，身体恢复不足`, actionLabel: '分析', onAction: () => handleSend('分析我最近的HRV趋势，给出恢复建议'), color: '#ef4444', bg: '#fef2f2' });
                    }
                    if (alerts.length === 0) return null;
                    return (
                      <div className="space-y-2">
                        {alerts.map((a, i) => (
                          <div key={i} className="rounded-xl px-4 py-2.5 flex items-center gap-3" style={{ background: a.bg, border: `1px solid ${a.color}20` }}>
                            <span className="text-base shrink-0">{a.icon}</span>
                            <span className="flex-1 text-sm font-medium" style={{ color: a.color }}>{a.text}</span>
                            <button onClick={a.onAction} className="shrink-0 px-3 py-1 rounded-lg text-xs font-semibold text-white active:scale-95" style={{ background: a.color }}>{a.actionLabel}</button>
                          </div>
                        ))}
                      </div>
                    );
                  })()}

                  {/* ── 3. Core Metrics — 4 compact cards ── */}
                  <div className="grid grid-cols-4 gap-2.5">
                    {[
                      { icon: '❤️', value: todayGarmin?.resting_heart_rate || todayGarmin?.avg_heart_rate, unit: 'bpm', label: '心率', ok: (v: number) => v >= 45 && v <= 75 },
                      { icon: '🔋', value: todayGarmin?.body_battery_most_charged, unit: '', label: '电量', sub: todayGarmin?.body_battery_current != null ? `当前${todayGarmin.body_battery_current}` : '', ok: (v: number) => v >= 60 },
                      { icon: '😴', value: todayGarmin?.sleep_score, unit: '分', label: '睡眠', sub: sleepTotal > 0 ? `${sleepH}h${sleepM > 0 ? sleepM + 'm' : ''}` : '', ok: (v: number) => v >= 70 },
                      { icon: '😌', value: todayGarmin?.stress_level, unit: '', label: '压力', ok: (v: number) => v <= 40 },
                    ].map(m => {
                      const v = (m as any).value;
                      const isWarn = v != null && !m.ok(v);
                      return (
                        <div key={m.label} className={`rounded-2xl p-4 text-center transition-all ${isWarn ? 'bg-amber-50 border-2 border-amber-200' : 'bg-white border border-gray-100'} shadow-sm hover:shadow-md`}>
                          <span className="text-2xl">{m.icon}</span>
                          <div className={`text-2xl font-extrabold mt-1 ${isWarn ? 'text-amber-500' : 'text-gray-800'}`}>
                            {v ?? '--'}<span className="text-xs font-normal text-gray-400 ml-0.5">{m.unit}</span>
                          </div>
                          <div className="text-xs text-gray-500 font-medium mt-0.5">{m.label}</div>
                          {(m as any).sub && <div className="text-[11px] text-gray-400 mt-0.5">{(m as any).sub}</div>}
                        </div>
                      );
                    })}
                  </div>

                  {/* ── 4. Context Row — weather, diet, rhinitis, weight ── */}
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    <div className="bg-white rounded-2xl p-4 border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-xs font-semibold text-gray-600">{weatherData?.city || '天气'}</span>
                        <span className="text-[10px] text-gray-400">{weatherData?.weather || ''}</span>
                      </div>
                      <div className="flex items-baseline gap-1">
                        <span className="text-2xl font-bold text-gray-800">{weatherData ? Math.round(weatherData.temperature ?? 0) : '--'}°</span>
                        {weatherData?.temp_min != null && <span className="text-[10px] text-gray-400">{Math.round(weatherData.temp_min)}°/{Math.round(weatherData.temp_max)}°</span>}
                      </div>
                      {airData && (
                        <div className="flex gap-1 mt-1">
                          <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${(airData.aqi||0) <= 50 ? 'bg-green-100 text-green-700' : (airData.aqi||0) <= 100 ? 'bg-yellow-100 text-yellow-700' : 'bg-red-100 text-red-700'}`}>AQI {airData.aqi||'--'}</span>
                          {airData.pm25 != null && <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${airData.pm25 <= 35 ? 'bg-green-50 text-green-600' : 'bg-yellow-50 text-yellow-600'}`}>PM2.5 {airData.pm25}</span>}
                        </div>
                      )}
                    </div>
                    <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-xs font-semibold text-gray-600">饮食</span>
                        {dietToday?.meals_count > 0 && <span className="text-[10px] text-gray-400">{dietToday.meals_count}餐</span>}
                      </div>
                      <div className="text-2xl font-bold text-gray-800">{dietToday?.total_calories ? Math.round(dietToday.total_calories) : 0}<span className="text-[10px] font-normal text-gray-400 ml-0.5">kcal</span></div>
                      <div className="flex gap-2 mt-1 text-[10px] text-gray-500">
                        <span><span className="text-red-500 font-medium">{Math.round(dietToday?.total_protein || 0)}</span>g 蛋白</span>
                        <span><span className="text-amber-500 font-medium">{Math.round(dietToday?.total_carbs || 0)}</span>g 碳水</span>
                        <span><span className="text-green-500 font-medium">{Math.round(dietToday?.total_fat || 0)}</span>g 脂肪</span>
                      </div>
                    </div>
                    <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
                      <span className="text-xs font-semibold text-gray-600">👃 鼻炎追踪</span>
                      <div className="grid grid-cols-2 gap-2 mt-2">
                        <div className="text-center">
                          <div className="text-2xl font-bold text-gray-800">{rhinitisToday?.sneeze_count || 0}</div>
                          <div className="text-[11px] text-gray-400 mt-0.5">喷嚏</div>
                        </div>
                        <div className="text-center">
                          <div className="text-2xl font-bold text-gray-800">{rhinitisToday?.nasal_wash_count || 0}<span className="text-sm font-normal text-gray-400">/2</span></div>
                          <div className="text-[11px] text-gray-400 mt-0.5">洗鼻</div>
                        </div>
                      </div>
                    </div>
                    <div className="bg-white rounded-xl p-3 border border-gray-100 shadow-sm">
                      <span className="text-xs font-semibold text-gray-600">⚖️ 体重</span>
                      <div className="text-2xl font-bold text-gray-800 mt-1">{weightStats?.current_weight || '--'}<span className="text-[10px] font-normal text-gray-400 ml-0.5">kg</span></div>
                      {weightStats?.weight_change_30d != null && (
                        <div className={`text-[10px] font-medium mt-0.5 ${weightStats.weight_change_30d > 0 ? 'text-red-500' : 'text-green-600'}`}>
                          30天 {weightStats.weight_change_30d > 0 ? '+' : ''}{weightStats.weight_change_30d}kg
                        </div>
                      )}
                    </div>
                  </div>

                  {/* ── 5. Progress Row — steps, water, supplements ── */}
                  {(() => {
                    const stepsTarget = 8000;
                    const stepsVal = todayGarmin?.steps || 0;
                    const stepsPct = Math.min(100, Math.round((stepsVal / stepsTarget) * 100));
                    const waterPct = Math.min(100, Math.round((waterToday.total_ml / waterToday.goal_ml) * 100));
                    const suppPct = suppTotal > 0 ? Math.round((suppChecked / suppTotal) * 100) : 0;
                    const rings = [
                      { label: '步数', pct: stepsPct, val: stepsVal.toLocaleString(), sub: `/${stepsTarget.toLocaleString()}`, color: '#6366f1' },
                      { label: '饮水', pct: waterPct, val: `${waterToday.total_ml}`, sub: `/${waterToday.goal_ml}ml`, color: '#3b82f6' },
                      { label: '补剂', pct: suppPct, val: `${suppChecked}/${suppTotal}`, sub: '', color: '#8b5cf6' },
                    ];
                    return (
                      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow p-4">
                        <div className="grid grid-cols-3 gap-4">
                          {rings.map(r => {
                            const sz = 52, sw = 4, rad = (sz - sw) / 2, circ = 2 * Math.PI * rad;
                            return (
                              <div key={r.label} className="flex flex-col items-center">
                                <div className="relative" style={{ width: sz, height: sz }}>
                                  <svg width={sz} height={sz} className="-rotate-90">
                                    <circle cx={sz/2} cy={sz/2} r={rad} fill="none" stroke="#f3f4f6" strokeWidth={sw} />
                                    <circle cx={sz/2} cy={sz/2} r={rad} fill="none" stroke={r.color} strokeWidth={sw}
                                      strokeDasharray={circ} strokeDashoffset={circ - (r.pct / 100) * circ} strokeLinecap="round" className="transition-all duration-700" />
                                  </svg>
                                  <div className="absolute inset-0 flex items-center justify-center"><span className="text-[10px] font-bold text-gray-600">{r.pct}%</span></div>
                                </div>
                                <span className="text-xs font-semibold text-gray-700 mt-1.5">{r.val}</span>
                                {r.sub && <span className="text-[10px] text-gray-400">{r.sub}</span>}
                                <span className="text-[10px] text-gray-400">{r.label}</span>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })()}

                  {/* ── 6. Sleep Detail — stages bar ── */}
                  {sleepTotal > 0 && (
                    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-gray-600">昨夜睡眠详情</span>
                        <span className="text-xs text-gray-400">{sleepH}h{sleepM > 0 ? `${sleepM}m` : ''}</span>
                      </div>
                      <div className="flex h-3 rounded-full overflow-hidden mb-2">
                        {sleepDeep > 0 && <div className="bg-indigo-600" style={{ width: `${(sleepDeep / sleepTotal) * 100}%` }} />}
                        {sleepRem > 0 && <div className="bg-purple-400" style={{ width: `${(sleepRem / sleepTotal) * 100}%` }} />}
                        {sleepLight > 0 && <div className="bg-blue-200" style={{ width: `${(sleepLight / sleepTotal) * 100}%` }} />}
                      </div>
                      <div className="flex items-center gap-4">
                        <div className="text-2xl font-bold text-gray-800">{todayGarmin?.sleep_score || '--'}<span className="text-[10px] text-gray-400 ml-0.5">睡眠分</span></div>
                        <div className="text-sm text-gray-500">{todayGarmin?.hrv || '--'}<span className="text-[10px] text-gray-400 ml-0.5">HRV ms</span></div>
                        <div className="text-sm text-gray-500">{todayGarmin?.spo2_avg || '--'}<span className="text-[10px] text-gray-400 ml-0.5">SpO2 %</span></div>
                      </div>
                      <div className="flex gap-4 mt-1.5 text-[10px] text-gray-400">
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-indigo-600 inline-block" /> 深睡 {Math.round(sleepDeep * 60)}m</span>
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-400 inline-block" /> REM {Math.round(sleepRem * 60)}m</span>
                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-200 inline-block" /> 浅睡 {Math.round(sleepLight * 60)}m</span>
                      </div>
                    </div>
                  )}

                  {/* ── 6.5 Blood Pressure ── */}
                  {bpLatest && bpLatest.total_records > 0 && (
                    <div className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow cursor-pointer" onClick={() => router.push('/blood-pressure')}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-gray-600">🩺 血压（近30天均值）</span>
                        <span className="text-[10px] text-gray-400">{bpLatest.total_records}次记录</span>
                      </div>
                      <div className="flex items-baseline gap-3 mt-1">
                        <span className="text-2xl font-bold text-gray-800">
                          {Math.round(bpLatest.average_systolic)}/{Math.round(bpLatest.average_diastolic)}
                        </span>
                        <span className="text-sm text-gray-500">mmHg</span>
                        {bpLatest.average_pulse && (
                          <span className="text-sm text-gray-400">脉搏 {Math.round(bpLatest.average_pulse)} bpm</span>
                        )}
                        <span className={`text-xs px-1.5 py-0.5 rounded ${bpLatest.normal_count >= bpLatest.total_records * 0.8 ? 'bg-emerald-100 text-emerald-700' : bpLatest.high_count > 0 ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                          {bpLatest.normal_count >= bpLatest.total_records * 0.8 ? '正常' : bpLatest.high_count > 0 ? '偏高' : '关注'}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* ── 6.55 Medical Exam Trends (multi-year) ── */}
                  {examTrends && Object.keys(examTrends).length > 0 && (
                    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow p-4 cursor-pointer" onClick={() => router.push('/medical-exams')}>
                      <div className="flex items-center justify-between mb-3">
                        <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">体检指标趋势</span>
                        <span className="text-[10px] text-emerald-600">查看详情</span>
                      </div>
                      <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                        {Object.entries(examTrends).map(([code, info]: [string, any]) => {
                          const pts = info.data || [];
                          if (pts.length < 2) return null;
                          const latest = pts[pts.length - 1];
                          const prev = pts[pts.length - 2];
                          const diff = latest.value - prev.value;
                          const pctChange = prev.value ? ((diff / prev.value) * 100).toFixed(1) : '0';
                          const isDown = diff < 0;
                          const isAbnormal = latest.is_abnormal;
                          // Mini sparkline SVG
                          const maxV = Math.max(...pts.map((p: any) => p.value));
                          const minV = Math.min(...pts.map((p: any) => p.value));
                          const range = maxV - minV || 1;
                          const svgW = 80;
                          const svgH = 24;
                          const pathD = pts.map((p: any, i: number) => {
                            const x = (i / (pts.length - 1)) * svgW;
                            const y = svgH - ((p.value - minV) / range) * (svgH - 4) - 2;
                            return `${i === 0 ? 'M' : 'L'}${x},${y}`;
                          }).join(' ');
                          const lineColor = isAbnormal ? '#ef4444' : '#10b981';
                          return (
                            <div key={code} className="flex items-center justify-between">
                              <div className="min-w-0">
                                <div className="text-[11px] text-gray-500">{info.name}</div>
                                <div className="flex items-baseline gap-1">
                                  <span className={`text-base font-bold ${isAbnormal ? 'text-red-500' : 'text-gray-800'}`}>{latest.value}</span>
                                  <span className="text-[10px] text-gray-400">{info.unit}</span>
                                </div>
                                <div className={`text-[10px] ${isDown ? 'text-emerald-500' : 'text-red-400'}`}>
                                  {isDown ? '↓' : '↑'}{Math.abs(Number(pctChange))}%
                                </div>
                              </div>
                              <svg width={svgW} height={svgH} className="shrink-0">
                                <path d={pathD} fill="none" stroke={lineColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                                {/* ref range band */}
                                {info.reference_low != null && info.reference_high != null && (
                                  <rect x="0" y={svgH - ((info.reference_high - minV) / range) * (svgH - 4) - 2}
                                    width={svgW} height={Math.max(1, ((info.reference_high - info.reference_low) / range) * (svgH - 4))}
                                    fill="#10b981" opacity="0.08" rx="2" />
                                )}
                              </svg>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* ── 6.6 Mood Today ── */}
                  {moodToday && (
                    <div className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow cursor-pointer" onClick={() => router.push('/mood')}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-gray-600">😊 今日情绪</span>
                        <div className="flex items-center gap-3 text-sm">
                          <span>心情 <strong className="text-gray-800">{moodToday.mood_score || '--'}</strong>/10</span>
                          <span>精力 <strong className="text-gray-800">{moodToday.energy_level || '--'}</strong>/5</span>
                          <span>焦虑 <strong className="text-gray-800">{moodToday.anxiety_level || '--'}</strong>/5</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* ── 6.7 Medication Today ── */}
                  {medToday.length > 0 && (
                    <div className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow cursor-pointer" onClick={() => router.push('/medication')}>
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-semibold text-gray-600">💊 今日用药</span>
                        <span className="text-[10px] text-gray-400">{medToday.filter((m: any) => m.taken_count > 0).length}/{medToday.length}</span>
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {medToday.map((m: any) => (
                          <span key={m.medication_id} className={`text-xs px-2 py-0.5 rounded-full ${m.taken_count > 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-gray-100 text-gray-600'}`}>
                            {m.name} {m.dosage ? `(${m.dosage})` : ''}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* ── 6.8 Goals Progress ── */}
                  {goalsData.length > 0 && (
                    <div className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow cursor-pointer" onClick={() => router.push('/goals')}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-gray-600">🎯 进行中的目标</span>
                        <span className="text-[10px] text-emerald-600">查看全部</span>
                      </div>
                      <div className="space-y-2">
                        {goalsData.slice(0, 3).map((g: any, i: number) => {
                          const pct = Math.min(100, Math.round((g.current_value || 0) / (g.target_value || 1) * 100));
                          return (
                            <div key={i}>
                              <div className="flex justify-between text-xs mb-0.5">
                                <span className="text-gray-700">{g.title || g.description || '目标'}</span>
                                <span className="text-gray-400">{pct}%</span>
                              </div>
                              <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div className="h-full bg-indigo-500 rounded-full transition-all" style={{ width: `${pct}%` }} />
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* ── 6.85 Today's Activity Status ── */}
                  {todayGarmin && (todayGarmin.active_minutes > 0 || todayGarmin.active_calories > 0) && (
                    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow p-4 cursor-pointer" onClick={() => router.push('/garmin')}>
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-gray-600">🏃 今日活动</span>
                        <span className="text-[10px] text-gray-400">{new Date().toLocaleDateString('zh-CN')}</span>
                      </div>
                      <div className="flex items-center gap-6 mt-2">
                        <div>
                          <span className="text-2xl font-bold text-gray-800">{todayGarmin.active_minutes || 0}</span>
                          <span className="text-xs text-gray-400 ml-1">活动分钟</span>
                        </div>
                        <div>
                          <span className="text-2xl font-bold text-gray-800">{todayGarmin.active_calories || 0}</span>
                          <span className="text-xs text-gray-400 ml-1">活动卡路里</span>
                        </div>
                        <div>
                          <span className="text-2xl font-bold text-gray-800">{todayGarmin.floors_climbed || 0}</span>
                          <span className="text-xs text-gray-400 ml-1">爬楼层</span>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* ── 6.9 Recent Workouts ── */}
                  {workoutRecent.length > 0 && (
                    <div className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow cursor-pointer" onClick={() => router.push('/workout')}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-xs font-semibold text-gray-600">🏃 最近运动</span>
                        <span className="text-[10px] text-emerald-600">查看全部</span>
                      </div>
                      <div className="space-y-2">
                        {workoutRecent.slice(0, 3).map((w: any, i: number) => {
                          const dist = w.distance_meters ? (w.distance_meters / 1000).toFixed(2) : null;
                          const dur = w.duration_seconds ? Math.round(w.duration_seconds / 60) : null;
                          const typeMap: Record<string, string> = { running: '🏃 跑步', cycling: '🚴 骑行', swimming: '🏊 游泳', walking: '🚶 步行', hiking: '🥾 徒步', strength: '🏋️ 力量', yoga: '🧘 瑜伽' };
                          const typeName = typeMap[w.workout_type] || w.workout_type || '运动';
                          return (
                            <div key={i} className="flex items-center justify-between text-xs">
                              <div className="flex items-center gap-2">
                                <span className="text-gray-700 font-medium">{typeName}</span>
                                <span className="text-gray-400">{w.workout_name || ''}</span>
                              </div>
                              <div className="flex items-center gap-2 text-gray-500">
                                {dist && <span>{dist}km</span>}
                                {dur && <span>{dur}min</span>}
                                {w.calories && <span className="font-medium text-orange-500">{w.calories}kcal</span>}
                                <span className="text-gray-300">{w.workout_date}</span>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* ── 7. Trend Cards — 2x2 grid with sparklines ── */}
                  {garminHistory.length > 3 && (
                    <div className="grid grid-cols-2 gap-2.5">
                      {[
                        { icon: '❤️', label: '心率 7日', data: hrValues, avg: hrAvg, prevAvg: prevHrAvg, unit: 'bpm', color: '#ef4444', goodDown: true },
                        { icon: '💜', label: 'HRV 7日', data: hrvValues, avg: hrvAvg, prevAvg: prevHrvAvg, unit: 'ms', color: '#8b5cf6', goodDown: false },
                        { icon: '😰', label: '压力 7日', data: stressValues, avg: stressAvg, prevAvg: prevStressAvg, unit: '', color: '#f59e0b', goodDown: true },
                        { icon: '🚶', label: '步数 7日', data: last7.map((r: any) => r.steps || 0), avg: stepsAvg, prevAvg: prevStepsAvg, unit: '步', color: '#6366f1', goodDown: false },
                      ].map(t => {
                        const change = Number(pctChange(t.avg, t.prevAvg));
                        const isGood = t.goodDown ? change <= 0 : change >= 0;
                        return (
                          <div key={t.label} className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow">
                            <div className="flex items-center justify-between mb-0.5">
                              <span className="text-xs font-medium text-gray-500">{t.icon} {t.label}</span>
                              <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full ${isGood ? 'bg-green-50 text-green-600' : 'bg-red-50 text-red-500'}`}>{change >= 0 ? '+' : ''}{change}%</span>
                            </div>
                            <div className="flex items-baseline gap-1 mb-1.5">
                              <span className="text-lg font-bold text-gray-800">{t.avg || '--'}</span>
                              <span className="text-[10px] text-gray-400">{t.unit}</span>
                            </div>
                            <WelcomeSparkline data={t.data} color={t.color} />
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* ── 8. Supplements — inline checkin ── */}
                  {suppFlat.length > 0 && (
                    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow p-4">
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-1.5">
                          <span className="text-sm">💊</span>
                          <span className="text-xs font-semibold text-gray-600">今日补剂</span>
                        </div>
                        <span className="text-xs font-semibold text-gray-500">{suppChecked}/{suppTotal}</span>
                      </div>
                      {(() => {
                        const today = new Date().toISOString().slice(0, 10);
                        const toggleSupp = async (suppId: number, currentTaken: boolean) => {
                          const newTaken = !currentTaken;
                          setSupplementStatus(prev => prev.map((s: any) => {
                            const sid = s.supplement?.id || s.supplement_id || s.id;
                            if (sid === suppId) return { ...s, record: { ...(s.record || {}), taken: newTaken }, is_taken: newTaken, checked: newTaken };
                            return s;
                          }));
                          try {
                            await supplementApi.batchCheckin({ record_date: today, checkins: [{ supplement_id: suppId, taken: newTaken }] });
                          } catch (e) {
                            console.error('补剂打卡失败', e);
                            setSupplementStatus(prev => prev.map((s: any) => {
                              const sid = s.supplement?.id || s.supplement_id || s.id;
                              if (sid === suppId) return { ...s, record: { ...(s.record || {}), taken: currentTaken }, is_taken: currentTaken, checked: currentTaken };
                              return s;
                            }));
                          }
                        };
                        let lastTiming = '';
                        return (
                          <>
                            {suppVisible.map((s: any, i: number) => {
                              const taken = s.record?.taken || s.is_taken || s.checked;
                              const name = s.supplement?.name || s.supplement_name || s.name;
                              const dosage = s.supplement?.dosage || s.dosage || s.dose;
                              const suppId = s.supplement?.id || s.supplement_id || s.id;
                              const showHeader = s._timing !== lastTiming;
                              lastTiming = s._timing;
                              return (
                                <div key={i}>
                                  {showHeader && <p className="text-[10px] font-medium text-gray-400 mt-2 mb-0.5 first:mt-0">{timingLabels[s._timing]}</p>}
                                  <div className="flex items-center gap-2 py-1 cursor-pointer group" onClick={() => toggleSupp(suppId, !!taken)}>
                                    <div className={`w-4.5 h-4.5 rounded flex items-center justify-center shrink-0 transition-all ${taken ? 'bg-emerald-500' : 'border-2 border-gray-300 group-hover:border-emerald-400'}`} style={{ width: 18, height: 18 }}>
                                      {taken && <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                                    </div>
                                    <span className={`flex-1 text-sm ${taken ? 'text-gray-400 line-through' : 'text-gray-700'}`}>{name}</span>
                                    {dosage && <span className="text-[10px] text-gray-400">{dosage}</span>}
                                  </div>
                                </div>
                              );
                            })}
                            {suppHasMore && (
                              <button onClick={() => setSuppExpanded(!suppExpanded)} className="w-full mt-1.5 py-1 text-xs text-emerald-600 hover:text-emerald-700">
                                {suppExpanded ? '收起' : `展开全部 (${suppFlat.length})`}
                              </button>
                            )}
                          </>
                        );
                      })()}
                    </div>
                  )}

                  {/* ── 9. Quick Record — one-tap API actions ── */}
                  {(() => {
                    const today = new Date().toISOString().slice(0, 10);
                    const showQuickToast = (msg: string) => { setQuickToast(msg); setTimeout(() => setQuickToast(null), 1500); };

                    const quickActions = [
                      { icon: '💧', label: '250ml', action: async () => {
                        await api.post('/water/records', { record_date: today, amount: 250, drink_type: '水', user_id: 0 });
                        setWaterToday(prev => ({ ...prev, total_ml: prev.total_ml + 250, count: prev.count + 1 }));
                        showQuickToast('已记录喝水 250ml');
                      }},
                      { icon: '💧', label: '500ml', action: async () => {
                        await api.post('/water/records', { record_date: today, amount: 500, drink_type: '水', user_id: 0 });
                        setWaterToday(prev => ({ ...prev, total_ml: prev.total_ml + 500, count: prev.count + 1 }));
                        showQuickToast('已记录喝水 500ml');
                      }},
                      { icon: '👃', label: '洗鼻+1', action: async () => {
                        const cur = rhinitisToday?.nasal_wash_count || 0;
                        await api.post('/checkin/', { checkin_date: today, nasal_wash_count: cur + 1 });
                        setRhinitisToday((prev: any) => ({ ...prev, nasal_wash_count: cur + 1 }));
                        showQuickToast(`已记录洗鼻 ${cur + 1} 次`);
                      }},
                      { icon: '🤧', label: '喷嚏+1', action: async () => {
                        const cur = rhinitisToday?.sneeze_count || 0;
                        await api.post('/checkin/', { checkin_date: today, sneeze_count: cur + 1 });
                        setRhinitisToday((prev: any) => ({ ...prev, sneeze_count: cur + 1 }));
                        showQuickToast(`已记录喷嚏 ${cur + 1} 次`);
                      }},
                      { icon: '💉', label: '注射替尔泊肽', action: async () => {
                        // 查找或创建药物记录
                        const medsRes = await api.get('/medication/medications/me');
                        const meds = medsRes.data || [];
                        let med = meds.find((m: any) => m.name === '替尔泊肽' || m.name === 'Tirzepatide');
                        if (!med) {
                          const createRes = await api.post('/medication/medications', {
                            name: '替尔泊肽', dosage: '2.4ml', frequency: '每周1次',
                            times_per_day: 1, category: 'prescription', purpose: '体重管理/GLP-1',
                            notes: '皮下注射，每周固定时间'
                          });
                          med = createRes.data;
                        }
                        const now = new Date();
                        const timeStr = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
                        await api.post('/medication/logs', {
                          medication_id: med.id, taken_time: timeStr, status: 'taken',
                          actual_dosage: '2.4ml', notes: `${today} ${timeStr} 注射`
                        });
                        showQuickToast(`已记录注射替尔泊肽 2.4ml (${timeStr})`);
                      }},
                    ];

                    return (
                      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow p-4">
                        <div className="text-xs font-bold text-gray-500 mb-3 uppercase tracking-wider">快速记录</div>
                        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                          {quickActions.map((a, i) => (
                            <button key={i} onClick={async () => { try { await a.action(); } catch (e) { console.error(e); } }}
                              className="flex flex-col items-center gap-1 px-2 py-3 rounded-2xl border border-gray-100 bg-gray-50/80 text-xs text-gray-600 hover:bg-emerald-50 hover:border-emerald-300 hover:text-emerald-700 active:scale-95 transition-all">
                              <span className="text-xl">{a.icon}</span>
                              <span className="font-medium">{a.label}</span>
                            </button>
                          ))}
                        </div>
                        {quickToast && (
                          <div className="mt-3 px-4 py-2 rounded-xl bg-emerald-50 border border-emerald-200 text-sm text-emerald-700 font-medium text-center">
                            {quickToast}
                          </div>
                        )}
                      </div>
                    );
                  })()}

                  {/* ── 10. Navigation Grid ── */}
                  <div className="bg-white rounded-2xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow p-4">
                    <div className="text-xs font-bold text-gray-500 mb-3 uppercase tracking-wider">健康管理</div>
                    <div className="grid grid-cols-7 gap-2">
                      {[
                        { href: '/supplements', icon: '💊', name: '补剂' },
                        { href: '/diet', icon: '🍽️', name: '饮食' },
                        { href: '/water', icon: '💧', name: '饮水' },
                        { href: '/rhinitis', icon: '👃', name: '鼻炎' },
                        { href: '/mood', icon: '😊', name: '情绪' },
                        { href: '/workout', icon: '🏋️', name: '运动' },
                        { href: '/supplement-products', icon: '📦', name: '产品库' },
                        { href: '/sleep', icon: '🌙', name: '睡眠' },
                        { href: '/weight', icon: '⚖️', name: '体重' },
                        { href: '/heart-rate', icon: '❤️', name: '心率' },
                        { href: '/blood-pressure', icon: '🩺', name: '血压' },
                        { href: '/garmin', icon: '⌚', name: 'Garmin' },
                        { href: '/genetic', icon: '🧬', name: '基因' },
                        { href: '/settings', icon: '⚙️', name: '设置' },
                      ].map(item => (
                        <button key={item.href} onClick={() => router.push(item.href)} className="flex flex-col items-center gap-1.5 py-2 rounded-xl hover:bg-gray-50 active:scale-95 transition-all">
                          <span className="text-2xl">{item.icon}</span>
                          <span className="text-[11px] text-gray-500 font-medium">{item.name}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* ── 11. Quick Ask ── */}
                  <div className="flex flex-wrap gap-2">
                    {[
                      { text: '帮我分析一下最近的睡眠质量', label: '睡眠分析' },
                      { text: '根据我的身体数据，今天适合做什么运动？', label: '运动建议' },
                      { text: '帮我记录一下刚才吃的饭', label: '记录饮食' },
                      { text: '查看今日 AI 洞察和健康分析详情', label: 'AI 洞察' },
                      { text: '分析我最近的HRV趋势，给出恢复建议', label: '趋势报告' },
                    ].map(q => (
                      <button key={q.label} onClick={() => handleSend(q.text)}
                        className="px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-xs text-gray-600 hover:border-emerald-300 hover:text-emerald-700 hover:bg-emerald-50 active:scale-[0.97] transition-all">
                        {q.label}
                      </button>
                    ))}
                  </div>

                  {/* ── 12. Inline AI Response (bottom, near input) ── */}
                  {inlineResponse && (
                    <div className="rounded-2xl border border-emerald-100 shadow-lg overflow-hidden" style={{ background: 'linear-gradient(to bottom, #f0fdf4, #ffffff)' }}>
                      <div className="px-5 pt-4 pb-2 flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <div className="w-5 h-5 rounded-lg bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center">
                            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" /></svg>
                          </div>
                          <span className="text-xs text-emerald-700 bg-emerald-50 rounded-full px-2.5 py-0.5 font-medium">{inlineResponse.question}</span>
                        </div>
                        <button onClick={() => setInlineResponse(null)}
                          className="w-6 h-6 rounded-full flex items-center justify-center text-gray-300 hover:text-gray-500 hover:bg-gray-100 transition-all text-sm">×</button>
                      </div>
                      <div className="px-5 pb-4 text-sm text-gray-700 leading-relaxed max-h-[50vh] overflow-y-auto">
                        {inlineResponse.answer ? (
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                              ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>,
                              ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>,
                              li: ({ children }) => <li className="leading-6">{children}</li>,
                              h1: ({ children }) => <h1 className="mb-2 mt-3 text-lg font-bold text-gray-900 first:mt-0">{children}</h1>,
                              h2: ({ children }) => <h2 className="mb-2 mt-3 text-base font-bold text-gray-900 first:mt-0">{children}</h2>,
                              h3: ({ children }) => <h3 className="mb-1 mt-2 text-sm font-bold text-gray-800 first:mt-0">{children}</h3>,
                              strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
                              em: ({ children }) => <em className="italic text-gray-500">{children}</em>,
                              code: ({ ...props }: any) => {
                                const inline = !props.className?.includes('language-');
                                return inline ? (
                                  <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-xs text-emerald-700" {...props} />
                                ) : (
                                  <code className="my-2 block overflow-x-auto rounded-xl bg-gray-50 px-3 py-2 font-mono text-xs" {...props} />
                                );
                              },
                              pre: ({ children }) => <pre className="my-2 overflow-x-auto rounded-xl bg-gray-50 p-3">{children}</pre>,
                              blockquote: ({ children }) => <blockquote className="my-2 border-l-3 border-emerald-300 bg-emerald-50/50 py-1 pl-3 italic text-gray-600">{children}</blockquote>,
                              table: ({ children }) => <div className="my-2 overflow-x-auto"><table className="min-w-full text-xs border border-gray-200 rounded-lg">{children}</table></div>,
                              thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
                              tr: ({ children }) => <tr className="border-b border-gray-100">{children}</tr>,
                              th: ({ children }) => <th className="px-2 py-1.5 text-left font-semibold text-gray-700 border border-gray-200">{children}</th>,
                              td: ({ children }) => <td className="px-2 py-1.5 border border-gray-200">{children}</td>,
                              a: ({ children, href }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-emerald-600 underline hover:text-emerald-800">{children}</a>,
                            }}
                          >{inlineResponse.answer}</ReactMarkdown>
                        ) : inlineResponse.loading ? (
                          <div className="flex items-center gap-2 py-2 text-emerald-500">
                            <div className="flex gap-1">
                              <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                              <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                              <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                            </div>
                            <span className="text-xs">思考中...</span>
                          </div>
                        ) : null}
                      </div>
                      {inlineResponse.loading && inlineResponse.answer && (
                        <div className="px-5 pb-3 flex items-center gap-1.5">
                          <div className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-pulse" />
                          <span className="text-[11px] text-emerald-500">生成中...</span>
                        </div>
                      )}
                    </div>
                  )}
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

                {/* 新开对话按钮（仅内联模式显示） */}
                {inlineMode && (
                  <button
                    onClick={() => { setInlineMode(false); setInlineResponse(null); setMessages([]); setConversationId(undefined); }}
                    className="shrink-0 px-2.5 py-1.5 rounded-lg text-[11px] font-medium text-emerald-600 hover:bg-emerald-50 border border-emerald-200 transition-all"
                    title="切换到完整对话模式"
                  >
                    新开对话
                  </button>
                )}
                {/* 返回首页按钮（仅对话模式显示） */}
                {!inlineMode && visibleMessages.length > 0 && (
                  <button
                    onClick={() => { setInlineMode(true); setMessages([]); setConversationId(undefined); }}
                    className="shrink-0 px-2.5 py-1.5 rounded-lg text-[11px] font-medium text-gray-500 hover:bg-gray-100 border border-gray-200 transition-all"
                    title="返回首页"
                  >
                    首页
                  </button>
                )}
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
