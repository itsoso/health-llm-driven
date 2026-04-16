'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { api } from '@/services/api/client';
import { feedbackApi } from '@/services/api/user';
import { openclawApi, sharedApi, ChatMessage, Conversation, DietSavedData, ActivitySavedData } from '@/services/api/ai';
import NotificationCenter from '@/components/NotificationCenter';
import { useAuth } from '@/contexts/AuthContext';
import { useToast } from '@/contexts/ToastContext';
import { useDashboardData } from '@/hooks/useDashboardData';
import { pinMessageToCard } from '@/services/api/actionCard';
import { arrayMove } from '@/components/assistant/DndDashboard';
import QuickRecordBar from '@/components/assistant/QuickRecordBar';
import ChatView from '@/components/assistant/ChatView';
import HistorySidebar from '@/components/assistant/HistorySidebar';
import {
  AssistantDashboardDeviceLayout,
  AssistantLayoutDevice,
  detectAssistantLayoutDevice,
  getDefaultDashboardLayout,
  getWelcomeContentBottomPaddingClass,
  normalizeDashboardLayout,
} from '@/components/assistant/dashboardLayout';
import { useChat } from './hooks/useChat';
import { useMediaInput } from './hooks/useMediaInput';
import WelcomeDashboard, { DASHBOARD_CARD_LABELS } from './components/WelcomeDashboard';

declare global { interface Window { webkitSpeechRecognition: any; SpeechRecognition: any; } }

const UI_FONT_STACK = '"Avenir Next", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif';

const APP_MENU = [
  { label: '概览', items: [{ href: '/overview', name: '健康概览', icon: '📊' }, { href: '/daily-insights', name: '今日建议', icon: '✨' }, { href: '/smart-plan', name: '智能计划', icon: '📅' }, { href: '/family', name: '家庭', icon: '👨‍👩‍👦' }] },
  { label: '追踪', items: [{ href: '/workout', name: '运动', icon: '🏋️' }, { href: '/sleep', name: '睡眠', icon: '🌙' }, { href: '/garmin', name: 'Garmin', icon: '⌚' }, { href: '/weight', name: '体重', icon: '⚖️' }, { href: '/heart-rate', name: '心率', icon: '❤️' }, { href: '/blood-pressure', name: '血压', icon: '🩺' }, { href: '/mood', name: '情绪', icon: '😊' }] },
  { label: '记录', items: [{ href: '/supplements', name: '补剂', icon: '💊' }, { href: '/diet', name: '饮食', icon: '🍽️' }, { href: '/water', name: '饮水', icon: '💧' }, { href: '/checkin', name: '打卡', icon: '✅' }, { href: '/rhinitis', name: '鼻炎', icon: '👃' }] },
  { label: '管理', items: [{ href: '/genetic', name: '基因', icon: '🧬' }, { href: '/medical-exams', name: '体检', icon: '📋' }, { href: '/goals', name: '目标', icon: '🎯' }, { href: '/settings', name: '设置', icon: '⚙️' }] },
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
          <button onClick={onClose} className="text-gray-300 hover:text-gray-500 text-lg leading-none">x</button>
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

  // Media / file upload (extracted hook)
  const media = useMediaInput({ setInputText, showToast });

  const [showAppsMenu, setShowAppsMenu] = useState(false);
  const [dashboardEditMode, setDashboardEditMode] = useState(false);
  const [layoutDevice, setLayoutDevice] = useState<AssistantLayoutDevice>('web');
  const [dashboardLayout, setDashboardLayout] = useState<AssistantDashboardDeviceLayout>(getDefaultDashboardLayout);
  const [layoutLoaded, setLayoutLoaded] = useState(false);
  const [layoutSaving, setLayoutSaving] = useState(false);
  const [layoutSaveError, setLayoutSaveError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const appsMenuRef = useRef<HTMLDivElement>(null);
  const layoutHydratedRef = useRef(false);
  const layoutSaveTimerRef = useRef<NodeJS.Timeout | null>(null);
  const convCacheRef = useRef<Map<number, ChatMessage[]>>(new Map());

  // ── Conversations ──
  const loadConversations = useCallback(async () => {
    try {
      const response = await openclawApi.getConversations();
      setConversations(response.data || []);
    } catch (e) { console.error('加载对话列表失败:', e); }
  }, []);

  // ── Chat hook ──
  const { handleSend, handleInlineSend } = useChat({
    conversationId, setConversationId, setMessages, setLoading,
    setDoneMessageIds, setInputText, setInlineResponse, inlineResponseRef,
    inlineMode, inputText, pendingImage: media.pendingImage, pendingFile: media.pendingFile,
    clearPendingAttachment: media.clearPendingAttachment,
    setDietNotification, setActivityNotifications, setPlanCreatedNotification,
    dashboardRefreshAfterAction: dashboard.refreshAfterAction,
    loadConversations,
  });

  // ── Effects ──
  useEffect(() => { document.title = 'AI 助理 | 健康管理'; }, []);
  useEffect(() => { setLayoutDevice(detectAssistantLayoutDevice()); }, []);
  useEffect(() => () => { if (layoutSaveTimerRef.current) clearTimeout(layoutSaveTimerRef.current); }, []);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(() => { if (messages.length > 0 && !inlineMode) scrollToBottom(); }, [messages, inlineMode]);

  const loadConversation = useCallback(async (convId: number) => {
    try {
      // 使用缓存避免重复请求
      const cached = convCacheRef.current.get(convId);
      if (cached) {
        setMessages(cached);
        setDoneMessageIds(new Set(cached.filter((m: ChatMessage) => m.role === 'assistant').map((m: ChatMessage) => m.id)));
        setConversationId(convId);
        setInlineMode(false);
        setInlineResponse(null);
        return;
      }
      const response = await openclawApi.getConversation(convId);
      const msgs = response.data.messages || [];
      convCacheRef.current.set(convId, msgs);
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
    dashboard.loadDashboardData();
  }, [loadConversations, dashboard.loadDashboardData, router]);

  useEffect(() => {
    if (!localStorage.getItem('auth_token')) return;
    let cancelled = false;
    const loadDashboardLayout = async () => {
      try {
        const response = await api.get('/profile/me');
        if (cancelled) return;
        const rawLayout = response.data?.assistant_dashboard_layouts?.['web'];
        setDashboardLayout(normalizeDashboardLayout(rawLayout));
        setLayoutSaveError(null);
      } catch {
        if (cancelled) return;
        setDashboardLayout(getDefaultDashboardLayout());
        setLayoutSaveError('云端布局加载失败，已使用默认布局');
      } finally {
        if (cancelled) return;
        layoutHydratedRef.current = true;
        setLayoutLoaded(true);
      }
    };
    setLayoutLoaded(false);
    layoutHydratedRef.current = false;
    loadDashboardLayout();
    return () => { cancelled = true; };
  }, [layoutDevice]);

  useEffect(() => {
    if (!layoutHydratedRef.current || !layoutLoaded) return;
    if (layoutSaveTimerRef.current) clearTimeout(layoutSaveTimerRef.current);
    layoutSaveTimerRef.current = setTimeout(async () => {
      setLayoutSaving(true);
      setLayoutSaveError(null);
      try {
        await api.put('/profile/me', { assistant_dashboard_layouts: { web: dashboardLayout } });
      } catch {
        setLayoutSaveError('布局同步失败，请稍后重试');
      } finally { setLayoutSaving(false); }
    }, 500);
    return () => { if (layoutSaveTimerRef.current) clearTimeout(layoutSaveTimerRef.current); };
  }, [dashboardLayout, layoutDevice, layoutLoaded]);

  // ── Helpers ──
  const handleNewChat = () => { setMessages([]); setConversationId(undefined); setShowHistory(false); };
  const handleDeleteConversation = async (convId: number) => { try { await openclawApi.deleteConversation(convId); setConversations(prev => prev.filter(c => c.id !== convId)); if (conversationId === convId) handleNewChat(); showToast('已删除', 'success'); } catch { showToast('删除失败', 'error'); } };
  const handleShareConversation = async (convId: number) => { try { const res = await sharedApi.createShare(convId, 'openclaw'); const url = res.data.share_url; if (navigator.clipboard) { await navigator.clipboard.writeText(url); showToast('分享链接已复制到剪贴板', 'success'); } else prompt('分享链接：', url); } catch { showToast('分享失败', 'error'); } };
  const toggleHistory = () => { if (!showHistory) loadConversations(); setShowHistory(!showHistory); };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); handleSend(); } };

  const handleFeedback = async (msgId: number, rating: 1 | 5) => {
    if (!conversationId || messageFeedback[msgId] === rating) return;
    setMessageFeedback(f => ({ ...f, [msgId]: rating }));
    try { await feedbackApi.submit({ conversation_type: 'openclaw', conversation_id: conversationId, message_id: msgId, rating }); } catch {}
  };

  // ── Derived data ──
  const hasMessages = messages.some(m => !(m.role === 'assistant' && !m.content));
  const isWelcome = inlineMode || (!hasMessages && !loading);

  const suppDeduped = useMemo(() => {
    const seen = new Set<string>();
    return dashboard.supplementStatus.filter((s: any) => {
      const key = `${s.supplement?.name || s.supplement_name || s.name}_${s.supplement?.timing || s.timing || 'morning'}`;
      if (seen.has(key)) return false; seen.add(key); return true;
    });
  }, [dashboard.supplementStatus]);
  const suppChecked = suppDeduped.filter((s: any) => s.record?.taken || s.is_taken || s.checked).length;
  const suppTotal = suppDeduped.length;

  const handleWaterRecord = (amount: number) => {
    dashboard.setWaterToday(prev => ({
      ...prev,
      total_ml: Math.max(0, prev.total_ml + amount),
      count: Math.max(0, prev.count + (amount >= 0 ? 1 : -1)),
    }));
  };

  const handleRefresh = useCallback(async () => {
    showToast('正在同步 Garmin 数据（含运动和睡眠）...', 'info');
    try {
      const res = await api.post('/data-collection/garmin/me/sync?days=1');
      const d = res.data;
      const parts = [];
      if (d?.success_count > 0) parts.push(`${d.success_count}天健康数据`);
      if (d?.activities_count > 0) parts.push(`${d.activities_count}条运动`);
      api.post('/twin/me/invalidate').catch(() => {});
      await dashboard.loadDashboardData(true);
      showToast(parts.length > 0 ? `同步成功：${parts.join('、')}` : '数据已是最新', 'success');
    } catch {
      await dashboard.loadDashboardData(true);
      showToast('同步失败，已刷新本地数据', 'error');
    }
  }, [showToast, dashboard]);

  // ── Dashboard layout ──
  const visibleDashboardCardIds = dashboardLayout.order.filter((id) => !dashboardLayout.hidden.includes(id));
  const isMobileLayout = layoutDevice === 'mobile';
  const showFooterLayoutControls = dashboardEditMode || dashboardLayout.hidden.length > 0;
  const welcomeBottomPaddingClass = getWelcomeContentBottomPaddingClass({
    isMobile: isMobileLayout,
    hasFooterControls: showFooterLayoutControls,
  });

  const handleDashboardDragEnd = (oldIndex: number, newIndex: number) => {
    const reorderedVisibleIds = arrayMove(visibleDashboardCardIds, oldIndex, newIndex);
    const hiddenIds = dashboardLayout.order.filter((id) => dashboardLayout.hidden.includes(id));
    setDashboardLayout({ order: [...reorderedVisibleIds, ...hiddenIds], hidden: dashboardLayout.hidden });
  };

  const handleHideDashboardCard = (cardId: string) => {
    if (dashboardLayout.hidden.includes(cardId)) return;
    setDashboardLayout((current) => ({ ...current, hidden: [...current.hidden, cardId] }));
  };

  const handleRestoreDashboardCard = (cardId: string) => {
    setDashboardLayout((current) => ({ ...current, hidden: current.hidden.filter((id) => id !== cardId) }));
  };

  const handleResetDashboardLayout = () => {
    setDashboardLayout(getDefaultDashboardLayout());
    setDashboardEditMode(false);
  };

  return (
    <div className="fixed inset-0 z-[100] overflow-hidden" style={{ fontFamily: UI_FONT_STACK, overscrollBehavior: 'none' }}>
      {/* Header */}
      <header className="relative z-50 backdrop-blur-md bg-white/80 border-b border-gray-100" style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}>
        <div className="max-w-7xl mx-auto px-4 h-12 flex items-center justify-between">
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

      <div className="relative flex overflow-hidden" style={{ height: 'calc(100dvh - 48px - env(safe-area-inset-top, 0px))' }}>
        {showHistory && (
          <HistorySidebar conversations={conversations} currentConversationId={conversationId} onLoadConversation={loadConversation} onNewChat={handleNewChat} onClose={toggleHistory} onDelete={handleDeleteConversation} onShare={handleShareConversation} />
        )}

        {/* Main content */}
        <section className="relative flex min-w-0 flex-1 flex-col">
          {/* Toast notifications */}
          {dietNotification && <Toast color="emerald" title="饮食已自动记录" subtitle={`${dietNotification.total_calories ? Math.round(dietNotification.total_calories) + ' kcal' : ''} · ${{ breakfast: '早餐', lunch: '午餐', dinner: '晚餐', snack: '加餐' }[dietNotification.meal_type] || '加餐'}`} onClose={() => setDietNotification(null)} />}
          {activityNotifications.length > 0 && <Toast color="cyan" title="已自动记录" subtitle={activityNotifications.map(a => a.message).join('；')} onClose={() => setActivityNotifications([])} />}
          {planCreatedNotification && <Toast color="blue" title="智能计划已生成" subtitle={planCreatedNotification.message} onClose={() => setPlanCreatedNotification(null)} action={{ label: '前往智能计划', onClick: () => { setPlanCreatedNotification(null); router.push('/smart-plan'); } }} />}

          {/* Scrollable content */}
          <div className="flex-1 overflow-y-auto overflow-x-hidden px-3 sm:px-4 py-3 sm:py-4">
            <div className="mx-auto max-w-7xl">
              {isWelcome ? (
                <WelcomeDashboard
                  user={user}
                  dashboard={dashboard}
                  suppChecked={suppChecked}
                  suppTotal={suppTotal}
                  handleRefresh={handleRefresh}
                  handleWaterRecord={handleWaterRecord}
                  handleSend={handleSend}
                  visibleDashboardCardIds={visibleDashboardCardIds}
                  dashboardEditMode={dashboardEditMode}
                  onDragEnd={handleDashboardDragEnd}
                  onHideCard={handleHideDashboardCard}
                  welcomeBottomPaddingClass={welcomeBottomPaddingClass}
                  layoutSaveError={layoutSaveError}
                  inlineResponse={inlineResponse}
                  inlineResponseRef={inlineResponseRef}
                  onInlineClose={() => setInlineResponse(null)}
                />
              ) : (
                <ChatView messages={messages} loading={loading} doneMessageIds={doneMessageIds} messageFeedback={messageFeedback} onFeedback={handleFeedback} onPinMessage={async (content, msgId) => { try { await pinMessageToCard({ content, source_id: String(msgId), card_type: 'plan' }); showToast('已固化到首页', 'success'); } catch { showToast('固化失败', 'error'); } }} />
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Attachment preview */}
          {(media.imagePreview || media.pendingFile) && (
            <div className="border-t border-white/10 bg-slate-950/50 px-4 py-3 backdrop-blur-xl">
              <div className="mx-auto flex max-w-7xl items-center gap-4 rounded-[24px] border border-white/10 bg-white/[0.04] px-4 py-3">
                <div className="relative">
                  {media.imagePreview ? <img src={media.imagePreview} alt="待发送图片" className="h-16 w-16 rounded-2xl border border-white/10 object-cover" /> : (
                    <div className="flex h-16 w-16 flex-col items-center justify-center rounded-2xl border border-white/10 bg-slate-900">
                      <svg className="h-6 w-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                    </div>
                  )}
                  <button onClick={media.clearPendingAttachment} className="absolute -right-2 -top-2 flex h-6 w-6 items-center justify-center rounded-full bg-red-500 text-xs text-white transition-colors hover:bg-red-400">x</button>
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm text-white">{media.imagePreview ? '图片已就绪' : media.pendingFile?.name}</div>
                  <div className="mt-1 text-xs text-slate-400">补一句目标或上下文后直接发送，AI 会结合附件内容理解你的需求。</div>
                </div>
              </div>
            </div>
          )}

          {/* Bottom fixed area — 钉在 viewport 底部 */}
          <div className={`${isWelcome ? 'fixed bottom-0 left-0 right-0 z-[110]' : ''}`} style={isWelcome ? { paddingBottom: 'env(safe-area-inset-bottom, 0px)', background: 'rgba(255,255,255,0.92)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' } : undefined}>
            {isWelcome && (
              <div className="px-4 pt-2 pb-1 border-t border-gray-100/60">
                <div className="mx-auto max-w-7xl">
                  <QuickRecordBar rhinitisToday={dashboard.rhinitisToday} onWaterRecord={handleWaterRecord} onRhinitisUpdate={dashboard.setRhinitisToday} />
                </div>
              </div>
            )}
            {isWelcome && dashboardEditMode && (
              <div className="px-4 pb-2" style={{ background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)' }}>
                <div className={`mx-auto max-w-7xl rounded-2xl border border-violet-200 bg-violet-50/80 shadow-sm ${isMobileLayout ? 'px-2.5 py-1.5' : 'px-3 py-2'}`}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="min-w-0 text-[11px] text-violet-600 font-medium">
                      编辑模式 · 拖拽排序 / 隐藏卡片
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {dashboardLayout.hidden.length > 0 && dashboardLayout.hidden.map((cardId) => (
                        <button
                          key={cardId}
                          onClick={() => handleRestoreDashboardCard(cardId)}
                          className={`rounded-full border border-gray-200 bg-white text-[11px] text-gray-600 transition-all hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700 ${isMobileLayout ? 'px-2 py-0.5' : 'px-2.5 py-1'}`}
                        >
                          恢复 {DASHBOARD_CARD_LABELS[cardId] || cardId}
                        </button>
                      ))}
                      <button
                        onClick={() => setDashboardEditMode(false)}
                        className="rounded-full bg-violet-600 text-white text-[11px] font-medium px-3 py-1 transition-all"
                      >
                        完成编辑
                      </button>
                      <button
                        onClick={handleResetDashboardLayout}
                        className={`rounded-full border border-gray-200 bg-white text-[11px] text-gray-500 transition-all hover:border-gray-300 ${isMobileLayout ? 'px-2.5 py-0.5' : 'px-3 py-1'}`}
                      >
                        重置
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
            {/* Input */}
            <div className="px-4 py-3" style={isWelcome ? { background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(20px)', WebkitBackdropFilter: 'blur(20px)', paddingBottom: 'max(0.75rem, env(safe-area-inset-bottom))' } : undefined}>
              <div className={`mx-auto max-w-7xl ${isWelcome ? 'rounded-[24px] border border-gray-200' : 'rounded-[30px] border border-white/10 bg-white/[0.04] shadow-[0_20px_60px_rgba(2,6,23,0.35)]'}`}
                style={isWelcome ? { background: '#F2F2F7' } : undefined}>
                <div className={`flex items-center ${isMobileLayout ? 'gap-2 px-3 py-2' : 'gap-3 px-4 py-2.5'} pb-[max(0.625rem,env(safe-area-inset-bottom))]`}>
                  <input ref={media.fileInputRef} type="file" accept="image/*,.pdf,.txt,.md,.csv,.json,.py,.js,.ts,.html,.xml,.log,.yaml,.yml" className="hidden" onChange={media.handleImageUpload} />
                  <button onClick={() => media.fileInputRef.current?.click()} disabled={media.imageUploading}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all"
                    style={isWelcome ? { color: '#AEAEB2' } : { color: media.imageUploading ? '#fff' : '#94a3b8' }} title="上传图片或文件">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M18.375 12.739l-7.693 7.693a4.5 4.5 0 01-6.364-6.364l10.94-10.94A3 3 0 1119.5 7.372L8.552 18.32m.009-.01l-.01.01m5.699-9.941l-7.81 7.81a1.5 1.5 0 002.112 2.13" /></svg>
                  </button>
                  <button onClick={media.handleVoiceToggle}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all"
                    style={isWelcome ? { color: media.isRecording ? '#FF3B30' : '#AEAEB2' } : { color: media.isRecording ? '#fff' : '#94a3b8', background: media.isRecording ? '#FF3B30' : undefined }} title={media.isRecording ? '停止录音' : '语音输入'}>
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      {media.isRecording ? <rect x="6" y="6" width="12" height="12" rx="2" /> : <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />}
                    </svg>
                  </button>
                  <input type="text" value={inputText} onChange={(e) => setInputText(e.target.value)} onKeyDown={handleKeyDown} onPaste={media.handlePaste}
                    placeholder={media.isRecording ? '正在录音...' : (media.pendingImage || media.pendingFile) ? '输入描述或问题（可直接发送）' : '用一句完整目标开始...'}
                    className="flex-1 bg-transparent text-sm outline-none"
                    style={isWelcome ? { color: '#1C1C1E' } : { color: '#fff' }}
                    disabled={media.isRecording} />
                  {isWelcome && !showFooterLayoutControls && (
                    <button
                      onClick={() => setDashboardEditMode(true)}
                      className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-gray-200 text-gray-400 transition-all hover:border-violet-300 hover:text-violet-700"
                      title="编辑布局"
                      aria-label="编辑布局"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 7h10M4 12h16M4 17h7" />
                        <path strokeLinecap="round" strokeLinejoin="round" d="M18 6v2M14 11v2M12 16v2" />
                      </svg>
                    </button>
                  )}
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
                  <button onClick={() => handleSend()} disabled={!inputText.trim() && !media.pendingImage && !media.pendingFile}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all active:scale-95"
                    style={{ background: (inputText.trim() || media.pendingImage || media.pendingFile) ? '#007AFF' : (isWelcome ? '#E5E5EA' : 'rgba(255,255,255,0.08)'), color: (inputText.trim() || media.pendingImage || media.pendingFile) ? '#fff' : '#AEAEB2' }}>
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
