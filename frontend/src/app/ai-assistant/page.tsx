'use client';

/**
 * /ai-assistant —— Web 智能助理对话页 (2026-05-12 重建, 2026-05-13 切 agentApi).
 *
 * 统一使用 agentApi → /agent/stream，避免多套对话通道带来的成本和状态分裂。
 * 跟 mobile chat tab 同管道, 共享 LLM_PROVIDER (默认 TokenPlan).
 *
 * 历史: 该路由从 nav / dashboard / footer / 测试里被引, 但 page.tsx 一直缺,
 * 用户访问就 404. 此页用小巴 stream + ChatView 渲染.
 */

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ArrowUp,
  CheckSquare,
  FileText,
  Loader2,
  MessageSquarePlus,
  PanelLeft,
  Share2,
  Sparkles,
  X,
} from 'lucide-react';
import { ChatMessage, Conversation, agentApi, sharedApi } from '@/services/api/ai';
import ChatView from '@/components/assistant/ChatView';
import LlmModelPicker, { ModelOption } from '@/components/assistant/LlmModelPicker';
import ConversationHistoryRail from '@/components/assistant/ConversationHistoryRail';
import { api } from '@/services/api/client';
import { buildSelectedChatShareText } from '@/components/assistant/shareSelection';
import {
  clearChatScrollTimers,
  scheduleSettledScrollToBottom,
  type ChatScrollTimer,
} from '@/components/assistant/chatScroll';
import {
  canonicalModelId,
  isAdvancedChatModelId,
  sanitizeLlmPreference,
  sanitizeModelOptions,
} from '@/components/assistant/modelCatalog';
import { executeMedicalExamImportSkillForFile } from '@/services/chatMedicalExamImportSkill';
import { pickPastedMedicalImportFile } from '@/services/pastedMedicalImportFile';
import { statusStagePhrase } from '@/components/assistant/statusStagePhrase';
import {
  type ChatCardActionDescriptor,
} from '@/components/assistant/inlineCards';
import { projectServerCards } from '@/components/assistant/inlineCards/serverCardProjection';

// Reva 暖色亮色系 —— 照抄 mobile/constants/revaTheme.ts (founder 已认可)。
// 局部定义, 不引全局 token 文件; 值就近用 Tailwind arbitrary values 引用下面这张表。
const REVA = {
  paper: '#F7F6F2', // 页面背景 (暖白)
  surface: '#FFFFFF', // 卡片 / 输入框表面
  ink1: '#16201B', // 主文字
  ink2: '#5C6660', // 次要文字
  ink3: '#8A938D', // placeholder / caption
  line: '#E7E5DE', // 发丝边框
  lineStrong: '#D7D5CC', // 输入框等强边框
  green50: '#E8F2EC', // opener 柔和绿底 / hover 底
  green100: '#CDE6D8', // opener 绿边
  green500: '#1F8A5B', // 主强调 / 发送键
  green600: '#176F49', // press / hover-dark
  green700: '#115738', // opener 标签文字
  greenOn: '#FFFFFF', // 绿底上文字
} as const;

const DEFAULT_SUGGESTIONS = [
  '分析我最近的代谢健康',
  '今天怎么安排训练和恢复',
  '结合基因和体检给我建议',
  '帮我复盘最近的睡眠质量',
];

type OpenerQuickReplyAction = 'photo_meal' | 'record_weight' | 'connect_device';

interface OpenerQuickReply {
  text: string;
  action?: OpenerQuickReplyAction;
}

interface ConversationOpener {
  text: string;
  source: string;
  source_id?: number | null;
  quick_replies?: OpenerQuickReply[];
  deep_link?: string | null;
  priority?: number;
}

interface QueuedWebPrompt {
  text: string;
  userMessageId: number;
  assistantMessageId: number;
}

const OPENER_SOURCE_LABEL: Record<string, string> = {
  action_card_due: '今日检验',
  anomaly: '数据异常',
  case_thread: '持续话题',
  memory_fact: '记忆回顾',
};

const OPENER_QUICK_REPLY_ACTIONS = new Set<OpenerQuickReplyAction>([
  'photo_meal',
  'record_weight',
  'connect_device',
]);

function normalizeOpenerQuickReply(reply: unknown): OpenerQuickReply | null {
  if (typeof reply === 'string') {
    const text = reply.trim();
    return text ? { text } : null;
  }
  if (!reply || typeof reply !== 'object') return null;
  const raw = reply as Record<string, unknown>;
  const text =
    typeof raw.text === 'string' && raw.text.trim()
      ? raw.text.trim()
      : typeof raw.label === 'string' && raw.label.trim()
        ? raw.label.trim()
        : '';
  if (!text) return null;
  const action = typeof raw.action === 'string' && OPENER_QUICK_REPLY_ACTIONS.has(raw.action as OpenerQuickReplyAction)
    ? (raw.action as OpenerQuickReplyAction)
    : undefined;
  return action ? { text, action } : { text };
}

const CONV_PAGE_SIZE = 20; // 历史记录每页条数

export default function AIAssistantPage() {
  // useSearchParams 需要 Suspense 边界, 否则 Next.js 14 build 报
  // "useSearchParams() should be wrapped in a suspense boundary".
  return (
    <Suspense fallback={<div className="fixed inset-0 z-40 bg-[#F7F6F2]" />}>
      <AIAssistantInner />
    </Suspense>
  );
}

function AIAssistantInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [activeConvId, setActiveConvId] = useState<number | undefined>(undefined);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [convPage, setConvPage] = useState(1);   // 历史记录当前页(1-based)
  const [convTotal, setConvTotal] = useState(0); // 全部对话条数(翻页用)
  const [historyOpen, setHistoryOpen] = useState(true);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historySearch, setHistorySearch] = useState('');
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [queuedPromptCount, setQueuedPromptCount] = useState(0);
  // 2026-07-02: 实时状态行 (status SSE 事件 → 中文短语), 首 token 到达清空。纯加法。
  const [statusText, setStatusText] = useState<string | null>(null);
  const [doneIds, setDoneIds] = useState<Set<number>>(new Set());
  // 2026-05-13: 当前用户偏好的 LLM 模型 (顶部 chip 用)
  const [llmPref, setLlmPref] = useState<{ label: string | null; model_id: string | null }>({
    label: null, model_id: null,
  });
  const [llmOptions, setLlmOptions] = useState<ModelOption[]>([]);
  const [llmSaving, setLlmSaving] = useState<string | null>(null);
  const [llmError, setLlmError] = useState<string | null>(null);
  const [shareSelectionMode, setShareSelectionMode] = useState(false);
  const [selectedMessageIds, setSelectedMessageIds] = useState<Set<number>>(new Set());
  const [sharing, setSharing] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const streamingRef = useRef(false);
  const activeConvIdRef = useRef<number | undefined>(undefined);
  const historyRequestRef = useRef(0);
  const hasLoadedHistoryRef = useRef(false);
  const queuedPromptsRef = useRef<QueuedWebPrompt[]>([]);
  // 状态行去抖: for-await 循环内读闭包会拿到陈旧 statusText, 用 ref 避免重复 setState。
  const statusRef = useRef<string | null>(null);
  const medicalExamInputRef = useRef<HTMLInputElement | null>(null);
  const scrollTimersRef = useRef<ChatScrollTimer[]>([]);
  const [starterSuggestions, setStarterSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS);
  const [opener, setOpener] = useState<ConversationOpener | null>(null);
  const [medicalExamImporting, setMedicalExamImporting] = useState(false);
  const [medicalExamImportError, setMedicalExamImportError] = useState<string | null>(null);

  const clearScheduledScrolls = useCallback(() => {
    clearChatScrollTimers(scrollTimersRef.current);
    scrollTimersRef.current = [];
  }, []);

  const scheduleScrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    scrollTimersRef.current = scheduleSettledScrollToBottom({
      getElement: () => scrollRef.current,
      clearExisting: clearScheduledScrolls,
      behavior,
    });
  }, [clearScheduledScrolls]);

  useEffect(() => {
    streamingRef.current = streaming;
  }, [streaming]);

  useEffect(() => {
    activeConvIdRef.current = activeConvId;
  }, [activeConvId]);

  // 自动滚到底。Markdown、动态卡片、图片会在首轮渲染后继续撑高,需要短时间内重复校准。
  useEffect(() => {
    scheduleScrollToBottom('smooth');
  }, [messages, streaming, scheduleScrollToBottom]);

  useEffect(() => clearScheduledScrolls, [clearScheduledScrolls]);

  // 拉当前 LLM 偏好显示在顶部
  useEffect(() => {
    let cancelled = false;
    api.get('/me/llm-preference').then(r => {
      if (cancelled) return;
      const pref = sanitizeLlmPreference(r.data);
      const id = pref.model_id;
      const opt = id ? pref.options.find((o: any) => o.id === id) : null;
      setLlmOptions(pref.options || []);
      setLlmPref({ label: opt?.label || (id ? id : null), model_id: id });
    }).catch(() => { /* 401/403 静默 */ });
    return () => { cancelled = true; };
  }, []);

  const selectModel = async (modelId: string | null) => {
    const canonical = canonicalModelId(modelId);
    const nextModelId = canonical && isAdvancedChatModelId(canonical) ? canonical : null;
    if (llmPref.model_id === nextModelId || llmSaving) return;
    setLlmSaving(nextModelId || '__default__');
    setLlmError(null);
    try {
      const res = await api.put('/me/llm-preference', { model_id: nextModelId });
      const pref = sanitizeLlmPreference(res.data);
      const options = sanitizeModelOptions((pref.options || []) as ModelOption[]);
      const activeId = pref.model_id;
      const active = activeId ? options.find(o => o.id === activeId) : null;
      setLlmOptions(options);
      setLlmPref({ model_id: activeId, label: active?.label || (activeId ? activeId : null) });
    } catch (e: any) {
      setLlmError(e?.response?.data?.detail || e?.message || '模型切换失败');
    } finally {
      setLlmSaving(null);
    }
  };

  const refreshConversations = useCallback(async (targetPage: number, search: string) => {
    const requestID = ++historyRequestRef.current;
    setHistoryLoading(true);
    try {
      const offset = (targetPage - 1) * CONV_PAGE_SIZE;
      const res = await agentApi.getConversations(CONV_PAGE_SIZE, offset, search);
      if (requestID !== historyRequestRef.current) return;
      setConversations(res.data.items || []);
      setConvTotal(res.data.total || 0);
      setConvPage(targetPage);
    } catch {
      if (requestID !== historyRequestRef.current) return;
      setConversations([]);
      setConvTotal(0);
    } finally {
      if (requestID === historyRequestRef.current) setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!hasLoadedHistoryRef.current) {
      hasLoadedHistoryRef.current = true;
      void refreshConversations(1, historySearch);
      return;
    }
    const timer = window.setTimeout(() => {
      void refreshConversations(1, historySearch);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [historySearch, refreshConversations]);

  // 把当前 conversation id 写进 URL (?c=<id>), 用 replace 不污染历史栈.
  // id 为空 → 回到无 ?c 的干净 URL (新对话未发消息).
  const syncConvUrl = (id?: number) => {
    const target = id ? `/ai-assistant?c=${id}` : '/ai-assistant';
    if (typeof window !== 'undefined' && window.location.pathname + window.location.search === target) {
      return; // 已是目标 URL, 不重复 replace
    }
    router.replace(target, { scroll: false });
  };

  // 页面 mount: 若 URL 带 ?c=<id> 则自动加载该对话 (支持刷新/直达/分享).
  // 只跑一次 — 后续 URL 变更由用户操作 (load/new/stream done) 主动触发.
  const bootstrappedRef = useRef(false);
  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    const raw = searchParams.get('c');
    const id = raw ? Number(raw) : NaN;
    if (Number.isInteger(id) && id > 0) {
      loadConversation(id).catch(() => {
        // 对话不存在/无权限 → 退回新对话并清掉脏 URL.
        startNewConversation();
        syncConvUrl(undefined);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const refreshConversationStarters = async () => {
    try {
      const res = await api.get('/agent/conversation-starters');
      const items = res.data?.suggestions;
      if (Array.isArray(items) && items.length > 0) {
        // Tolerate both the new {text,key,priority} object shape and the
        // legacy plain-string shape; web only renders the text.
        const texts = items
          .map((s: unknown) =>
            typeof s === 'string'
              ? s
              : s && typeof s === 'object' && typeof (s as { text?: unknown }).text === 'string'
                ? (s as { text: string }).text
                : null,
          )
          .filter((t: unknown): t is string => typeof t === 'string' && t.trim().length > 0);
        setStarterSuggestions(texts.length > 0 ? texts.slice(0, 4) : DEFAULT_SUGGESTIONS);
      } else {
        setStarterSuggestions(DEFAULT_SUGGESTIONS);
      }
      const op = res.data?.opener;
      const quickReplies = Array.isArray(op?.quick_replies)
        ? (op.quick_replies.map(normalizeOpenerQuickReply).filter(Boolean) as OpenerQuickReply[]).slice(0, 3)
        : [];
      setOpener(
        op && typeof op.text === 'string' && op.text.trim()
          ? {
              text: op.text,
              source: typeof op.source === 'string' ? op.source : '',
              source_id: op.source_id ?? null,
              quick_replies: quickReplies,
              deep_link: typeof op.deep_link === 'string' ? op.deep_link : null,
              priority: typeof op.priority === 'number' ? op.priority : 0,
            }
          : null,
      );
    } catch {
      setStarterSuggestions(DEFAULT_SUGGESTIONS);
      setOpener(null);
    }
  };

  useEffect(() => {
    // Only needed for the empty-state new conversation page.
    if (messages.length !== 0 || streaming) return;
    refreshConversationStarters();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeConvId]);

  const sendMessage = async (overrideText?: string, queuedPrompt?: QueuedWebPrompt) => {
    const text = (overrideText ?? input).trim();
    if (!text) return;

    if (streamingRef.current && !queuedPrompt) {
      setInput('');
      const stamp = Date.now();
      const userMessageId = -stamp;
      const assistantMessageId = -stamp - 1;
      const now = new Date().toISOString();
      queuedPromptsRef.current.push({ text, userMessageId, assistantMessageId });
      setQueuedPromptCount(queuedPromptsRef.current.length);
      setMessages(prev => [
        ...prev,
        { id: userMessageId, role: 'user', content: text, created_at: now },
        { id: assistantMessageId, role: 'assistant', content: '小巴处理中，已加入队列。', created_at: now },
      ]);
      return;
    }

    if (!queuedPrompt) setInput('');
    setStreaming(true);
    streamingRef.current = true;
    setStatusText(null);

    // 本地先插用户消息 + assistant 占位
    const tempUserId = queuedPrompt?.userMessageId ?? -Date.now();
    const tempAssistantId = queuedPrompt?.assistantMessageId ?? -Date.now() - 1;
    const now = new Date().toISOString();
    if (queuedPrompt) {
      setMessages(prev => prev.map(message => (
        message.id === tempAssistantId
          ? { ...message, content: '', created_at: now }
          : message
      )));
    } else {
      setMessages(prev => [
        ...prev,
        { id: tempUserId, role: 'user', content: text, created_at: now },
        { id: tempAssistantId, role: 'assistant', content: '', created_at: now },
      ]);
    }

    let assistantBuf = '';
    let realConvId = activeConvIdRef.current;
    statusRef.current = null;

    try {
      for await (const evt of agentApi.streamMessage(text, activeConvIdRef.current)) {
        if (!evt) continue;
        // /agent/stream event shape: { event, data: {content, conversation_id, ...} }
        const type = evt.event ?? evt.type;
        const data = evt.data ?? {};
        if (type === 'token' && typeof data.content === 'string') {
          assistantBuf += data.content;
          // 首 token 落地即清空状态行 (loader 旁的小字), 让正文接管。
          if (statusRef.current !== null) {
            statusRef.current = null;
            setStatusText(null);
          }
          setMessages(prev =>
            prev.map(m => (m.id === tempAssistantId ? { ...m, content: assistantBuf } : m)),
          );
        } else if (type === 'status') {
          // 实时状态行。两个 status 家族都进这里:
          //  - 旧家族 {event:"status",data:{stage,detail,round}} → 字段在 evt.data
          //  - P0-1 进度家族 (flat) {type:"status",stage,round?,label?} → 字段在 evt 顶层
          // evt.data 缺失时 (flat) 用 evt 本身兜底, 让 stage/label 能被解析。
          const statusData = evt.data ?? evt;
          const phrase = statusStagePhrase(statusData);
          if (phrase !== null) {
            statusRef.current = phrase;
            setStatusText(phrase);
          }
        } else if (type === 'tool_call') {
          // 用户感知: 显示"调用工具中"提示一行 (灰色 italic), 不污染主回答
        } else if (type === 'done') {
          if (data.conversation_id) realConvId = data.conversation_id;
          const serverCard = projectServerCards(data.cards);
          // 2026-05-13: 写性能字段, ChatView footer 显示
          const perf = {
            elapsed_ms: typeof data.elapsed_ms === 'number' ? data.elapsed_ms : undefined,
            llm_ms: typeof data.llm_ms === 'number' ? data.llm_ms : undefined,
            llm_rounds: typeof data.llm_rounds === 'number' ? data.llm_rounds : undefined,
            llm_rounds_ms: Array.isArray(data.llm_rounds_ms) ? data.llm_rounds_ms : undefined,
            model: typeof data.model === 'string' ? data.model : undefined,
            llm_usage: data.llm_usage && typeof data.llm_usage === 'object' ? data.llm_usage : undefined,
            perf: data.perf && typeof data.perf === 'object' ? data.perf : undefined,
            // 2026-05-14 #4: 可解释性 sources
            sources_used: Array.isArray(data.sources_used) ? data.sources_used : undefined,
            tools_used: Array.isArray(data.tools_used) ? data.tools_used : undefined,
          };
          setMessages(prev =>
            prev.map(m => (m.id === tempAssistantId ? {
              ...m,
              ...perf,
              ...(serverCard ? {
                card_type: serverCard.type,
                card_data: serverCard.data,
                card_actions: serverCard.actions,
              } : {}),
            } : m)),
          );
          setDoneIds(prev => new Set(prev).add(tempAssistantId));
        } else if (type === 'error') {
          const errMsg = data.message || data.content || evt.message || '未知错误';
          assistantBuf += `\n\n_出错: ${errMsg}_`;
          setMessages(prev =>
            prev.map(m => (m.id === tempAssistantId ? { ...m, content: assistantBuf } : m)),
          );
        }
      }
    } catch (e: any) {
      assistantBuf += `\n\n_连接中断: ${e?.message || ''}_`;
      setMessages(prev =>
        prev.map(m => (m.id === tempAssistantId ? { ...m, content: assistantBuf } : m)),
      );
    } finally {
      setStreaming(false);
      streamingRef.current = false;
      statusRef.current = null;
      setStatusText(null);
      if (!activeConvIdRef.current && realConvId) {
        activeConvIdRef.current = realConvId;
        setActiveConvId(realConvId);
        syncConvUrl(realConvId); // 首条消息拿到 realConvId 后写 ?c=<id>
      }
      void refreshConversations(convPage, historySearch);
      setTimeout(() => pumpQueuedPrompt(), 0);
    }
  };

  function pumpQueuedPrompt() {
    if (streamingRef.current) return;
    const next = queuedPromptsRef.current.shift();
    if (!next) return;
    setQueuedPromptCount(queuedPromptsRef.current.length);
    void sendMessage(next.text, next);
  }

  const startNewConversation = () => {
    queuedPromptsRef.current = [];
    setQueuedPromptCount(0);
    streamingRef.current = false;
    activeConvIdRef.current = undefined;
    setActiveConvId(undefined);
    setMessages([]);
    setShareSelectionMode(false);
    setSelectedMessageIds(new Set());
    setOpener(null);
    syncConvUrl(undefined); // 新对话回到无 ?c 的干净 URL
    refreshConversationStarters();
  };

  const loadConversation = async (conversationId: number) => {
    if (streaming) return;
    const res = await agentApi.getConversation(conversationId);
    const loaded = (res.data.messages || []).map((m: any) => {
      const serverCard = projectServerCards(m.meta?.cards);
      return {
      id: m.id,
      role: m.role,
      content: m.content,
      created_at: m.created_at,
      image_preview: normalizeImagePreview(m.image_url),
      elapsed_ms: m.meta?.elapsed_ms,
      llm_ms: m.meta?.llm_ms,
      llm_rounds: m.meta?.llm_rounds,
      llm_rounds_ms: m.meta?.llm_rounds_ms,
      model: m.meta?.model,
      llm_usage: m.meta?.llm_usage,
      perf: m.meta?.perf,
      sources_used: m.meta?.sources_used,
      tools_used: m.meta?.tools_used,
      ...(serverCard ? {
        card_type: serverCard.type,
        card_data: serverCard.data,
        card_actions: serverCard.actions,
      } : {}),
    };
    }) as ChatMessage[];
    activeConvIdRef.current = conversationId;
    setActiveConvId(conversationId);
    setMessages(loaded);
    setDoneIds(new Set(loaded.filter(m => m.role === 'assistant').map(m => m.id)));
    setShareSelectionMode(false);
    setSelectedMessageIds(new Set());
    syncConvUrl(conversationId); // 选中/加载对话写 ?c=<id>
  };

  const deleteConversation = async (conversationId: number) => {
    if (!window.confirm('删除这条对话？')) return;
    await agentApi.deleteConversation(conversationId);
    if (activeConvId === conversationId) {
      startNewConversation();
    }
    // 删后重拉以保持 total/翻页准确;若当前页删空且非首页,回退一页
    const targetPage = conversations.length <= 1 && convPage > 1 ? convPage - 1 : convPage;
    void refreshConversations(targetPage, historySearch);
  };

  const renameConversation = async (conversationId: number, title: string) => {
    const res = await agentApi.updateConversationTitle(conversationId, title);
    const updated = res.data;
    setConversations(prev =>
      prev.map(conv =>
        conv.id === conversationId
          ? { ...conv, title: updated.title, updated_at: updated.updated_at || conv.updated_at }
          : conv,
      ),
    );
  };

  const submitSuggestion = (text: string) => {
    sendMessage(text);
  };

  const handleCardAction = async (
    messageId: number,
    action: ChatCardActionDescriptor,
  ) => {
    if (action.action !== 'diet_record.create' || action.endpoint !== '/diet/records') return;
    const record = action.payload?.record;
    if (!record || typeof record !== 'object' || Array.isArray(record)) return;
    if (!window.confirm('确认记录这顿餐食？')) return;
    try {
      const response = await api.post('/diet/records', record);
      const receipt = response.data;
      setMessages(prev => prev.map(message => (
        message.id === messageId
          ? {
            ...message,
            card_data: {
              ...(message.card_data || {}),
              recorded: true,
              record_id: receipt.id,
              receipt_message: receipt.display_message,
            },
            card_actions: [],
          }
          : message
      )));
    } catch (error: any) {
      window.alert(error?.response?.data?.detail || '饮食记录失败，请稍后重试。');
    }
  };

  const toggleMessageSelection = (messageId: number) => {
    setSelectedMessageIds(prev => {
      const next = new Set(prev);
      if (next.has(messageId)) next.delete(messageId);
      else next.add(messageId);
      return next;
    });
  };

  const exitShareSelection = () => {
    setShareSelectionMode(false);
    setSelectedMessageIds(new Set());
  };

  // 微信式入口: 长按 / 右键某条消息直接进入多选分享, 并把该条预选中.
  const enterSelectionWith = (messageId: number) => {
    setShareSelectionMode(true);
    setSelectedMessageIds(prev => {
      if (prev.has(messageId)) return prev;
      const next = new Set(prev);
      next.add(messageId);
      return next;
    });
  };

  const shareMessages = async (messageIds?: number[]) => {
    const ids = messageIds ? new Set(messageIds) : selectedMessageIds;
    const text = buildSelectedChatShareText(messages, ids);
    if (!text || sharing) return;
    setSharing(true);
    try {
      const res = await sharedApi.createTextShare('健康小巴 · 对话节选', text);
      const shareUrl = res.data.share_url;
      if (navigator.share) {
        await navigator.share({ title: '健康小巴 · 对话节选', text: '我分享了一段健康小巴对话', url: shareUrl });
      } else {
        await navigator.clipboard?.writeText(shareUrl);
        window.alert('分享链接已复制');
      }
      if (!messageIds) exitShareSelection();
    } catch (e: any) {
      window.alert(e?.response?.data?.detail || e?.message || '分享失败，请稍后重试');
    } finally {
      setSharing(false);
    }
  };

  const handleMedicalExamFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = '';
    await importMedicalExamFile(file);
  };

  // 📎 选文件与 ⌘V 粘贴共用的导入核心(与 mac 端"粘贴=附件同路"语义一致)。
  const importMedicalExamFile = async (file: File | null | undefined) => {
    if (!file || medicalExamImporting || streaming) return;

    setMedicalExamImporting(true);
    setMedicalExamImportError(null);
    try {
      const result = await executeMedicalExamImportSkillForFile(file);
      const now = new Date().toISOString();
      const stamp = Date.now();
      const userMessageId = -stamp;
      const cardMessageId = -stamp - 1;
      setMessages(prev => [
        ...prev,
        {
          id: userMessageId,
          role: 'user',
          content: `导入体检报告：${file.name}`,
          file_name: file.name,
          created_at: now,
        },
        {
          id: cardMessageId,
          role: 'assistant',
          content: '',
          card_type: result.card.type,
          card_data: result.card.data,
          created_at: now,
        },
      ]);
      setDoneIds(prev => {
        const next = new Set(prev);
        next.add(cardMessageId);
        return next;
      });
      setInput(result.prompt);
    } catch (e: any) {
      setMedicalExamImportError(e?.message || '体检报告导入失败，请重试');
    } finally {
      setMedicalExamImporting(false);
    }
  };

  return (
    <main className="fixed inset-0 z-40 flex flex-col overflow-hidden bg-[#F7F6F2] text-[#16201B]">
      <header className="relative z-[70] shrink-0 overflow-visible border-b border-[#E7E5DE] bg-[#F7F6F2]/95 px-3 py-2.5 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-1">
            <button
              onClick={() => setHistoryOpen(open => !open)}
              className="mr-1 flex h-9 w-9 items-center justify-center rounded-xl text-[#8A938D] transition-colors hover:bg-[#E8F2EC] hover:text-[#16201B]"
              title="打开/收起历史记录"
            >
              <PanelLeft className="h-4.5 w-4.5" />
            </button>
            <LlmModelPicker
              currentLabel={llmPref.label || '系统默认'}
              currentModelId={llmPref.model_id}
              options={llmOptions}
              savingModelId={llmSaving}
              disabled={streaming}
              error={llmError}
              onSelect={selectModel}
            />
          </div>
          <button
            onClick={startNewConversation}
            className="inline-flex h-9 items-center gap-2 rounded-xl border border-[#D7D5CC] bg-[#FFFFFF] px-3 text-sm font-medium text-[#16201B] transition-colors hover:border-[#1F8A5B] hover:bg-[#E8F2EC]"
          >
            <MessageSquarePlus className="h-4 w-4" />
            <span className="hidden sm:inline">新对话</span>
          </button>
          {messages.some(m => m.content?.trim()) && (
            <button
              onClick={() => {
                if (shareSelectionMode) exitShareSelection();
                else setShareSelectionMode(true);
              }}
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-[#CDE6D8] bg-[#E8F2EC] px-3 text-sm font-medium text-[#115738] transition-colors hover:border-[#1F8A5B] hover:bg-[#CDE6D8]"
            >
              {shareSelectionMode ? <X className="h-4 w-4" /> : <CheckSquare className="h-4 w-4" />}
              <span className="hidden sm:inline">{shareSelectionMode ? '取消选择' : '选择分享'}</span>
            </button>
          )}
        </div>
      </header>

      <section className="relative z-0 flex min-h-0 flex-1">
        {historyOpen && (
          <ConversationHistoryRail
            conversations={conversations}
            activeConvId={activeConvId}
            loading={historyLoading}
            onLoad={loadConversation}
            onDelete={deleteConversation}
            onNew={startNewConversation}
            onRename={renameConversation}
            searchValue={historySearch}
            onSearchChange={setHistorySearch}
            page={convPage}
            totalPages={Math.max(1, Math.ceil(convTotal / CONV_PAGE_SIZE))}
            onPrevPage={() => { if (convPage > 1) void refreshConversations(convPage - 1, historySearch); }}
            onNextPage={() => {
              if (convPage < Math.ceil(convTotal / CONV_PAGE_SIZE)) void refreshConversations(convPage + 1, historySearch);
            }}
          />
        )}

        <div className="relative flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 pb-32 pt-8 sm:px-6">
            {messages.length === 0 && !streaming ? (
              <div className="mx-auto flex min-h-[60vh] max-w-3xl flex-col items-center justify-center text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#E8F2EC] text-[#1F8A5B] ring-1 ring-[#CDE6D8]">
                  <Sparkles className="h-7 w-7" />
                </div>
                <h1 className="mt-5 text-2xl font-semibold tracking-tight text-[#16201B] sm:text-3xl">
                  今天想了解什么？
                </h1>
                {opener && (
                  <div className="mt-7 w-full">
                    <button
                      type="button"
                      onClick={() => submitSuggestion(opener.text)}
                      className="group w-full rounded-2xl border border-[#CDE6D8] bg-[#E8F2EC] px-5 py-4 text-left transition-colors hover:border-[#1F8A5B] hover:bg-[#CDE6D8]"
                    >
                      <div className="mb-1.5 flex items-center gap-2">
                        <Sparkles className="h-3.5 w-3.5 text-[#1F8A5B]" />
                        <span className="text-[11px] font-medium uppercase tracking-wider text-[#115738]">
                          {OPENER_SOURCE_LABEL[opener.source] ?? 'AI 续接'}
                        </span>
                      </div>
                      <div className="text-[15px] leading-6 text-[#16201B]">{opener.text}</div>
                    </button>
                    {opener.quick_replies && opener.quick_replies.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {opener.quick_replies.map(reply => (
                          <button
                            key={`${reply.action ?? 'text'}:${reply.text}`}
                            type="button"
                            onClick={() => submitSuggestion(reply.text)}
                            className="rounded-full border border-[#CDE6D8] bg-[#FFFFFF] px-3 py-1.5 text-xs font-medium text-[#115738] transition-colors hover:border-[#1F8A5B] hover:bg-[#E8F2EC]"
                          >
                            {reply.text}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                )}
                <div className="mt-8 grid w-full grid-cols-1 gap-2 sm:grid-cols-2">
                  {starterSuggestions.map(item => (
                    <button
                      key={item}
                      onClick={() => submitSuggestion(item)}
                      className="rounded-2xl border border-[#E7E5DE] bg-[#FFFFFF] px-4 py-3 text-left text-sm text-[#5C6660] transition-colors hover:border-[#1F8A5B] hover:bg-[#E8F2EC] hover:text-[#16201B]"
                    >
                      {item}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <ChatView
                messages={messages}
                loading={streaming}
                statusText={statusText || (queuedPromptCount > 0 ? `${queuedPromptCount} 个排队` : null)}
                doneMessageIds={doneIds}
                messageFeedback={{}}
                onFeedback={() => {}}
                shareSelectionMode={shareSelectionMode}
                selectedMessageIds={selectedMessageIds}
                onToggleMessageSelection={toggleMessageSelection}
                onEnterSelectionWith={enterSelectionWith}
                onShareMessages={ids => shareMessages(ids)}
                onCardAction={handleCardAction}
              />
            )}
          </div>

          {shareSelectionMode && (
            <div className="pointer-events-auto absolute inset-x-3 bottom-28 z-20 mx-auto flex max-w-3xl items-center justify-between gap-3 rounded-2xl border border-[#E7E5DE] bg-[#FFFFFF]/95 px-4 py-3 shadow-2xl shadow-[#142019]/12 backdrop-blur sm:inset-x-6">
              <div className="min-w-0">
                <div className="text-sm font-medium text-[#16201B]">已选择 {selectedMessageIds.size} 条</div>
                <div className="text-xs text-[#8A938D]">按对话顺序生成一个可分享链接</div>
              </div>
              <button
                type="button"
                disabled={selectedMessageIds.size === 0 || sharing}
                onClick={() => shareMessages()}
                className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-[#1F8A5B] px-4 text-sm font-semibold text-[#FFFFFF] transition-colors hover:bg-[#176F49] disabled:bg-[#E7E5DE] disabled:text-[#8A938D]"
              >
                <Share2 className="h-4 w-4" />
                {sharing ? '生成中…' : '分享'}
              </button>
            </div>
          )}

          {/* 输入区 */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-[#F7F6F2] via-[#F7F6F2] to-transparent px-3 pb-4 pt-10 sm:px-6">
            <form
              id="ai-assistant-composer"
              onSubmit={e => {
                e.preventDefault();
                sendMessage();
              }}
              className="group pointer-events-auto mx-auto flex max-w-3xl items-end gap-2 rounded-[1.75rem] border border-[#D7D5CC] bg-[#FFFFFF] p-2.5 shadow-lg shadow-[#142019]/8 transition-colors focus-within:border-[#1F8A5B] focus-within:ring-2 focus-within:ring-[#1F8A5B]/25"
            >
              <input
                ref={medicalExamInputRef}
                aria-label="选择体检报告文件"
                type="file"
                accept="application/pdf,image/*,.pdf,.jpg,.jpeg,.png,.heic,.webp"
                className="sr-only"
                onChange={handleMedicalExamFileChange}
              />
              <button
                type="button"
                disabled={streaming || medicalExamImporting}
                onClick={() => medicalExamInputRef.current?.click()}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[#8A938D] transition-colors hover:bg-[#E8F2EC] hover:text-[#1F8A5B] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1F8A5B]/40 disabled:cursor-not-allowed disabled:text-[#B7BDB7]"
                title="导入体检报告"
                aria-label="导入体检报告"
              >
                {medicalExamImporting ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <FileText className="h-5 w-5" />
                )}
              </button>
              <textarea
                value={input}
                onChange={e => setInput(e.target.value)}
                onPaste={e => {
                  // 粘贴的图片/PDF(浏览器拷图/截屏/Finder 拷文件)→ 走 📎 同一条体检导入路;
                  // 纯文字粘贴(无 file item)不拦截,照常进输入框。
                  const file = pickPastedMedicalImportFile(e.clipboardData?.items);
                  if (!file || medicalExamImporting || streaming) return;
                  e.preventDefault();
                  void importMedicalExamFile(file);
                }}
                onKeyDown={e => {
                  // IME composition (拼音/日文/韩文) 中按 Enter 是确认候选词,不是发送
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                placeholder="发消息 (Enter 发送, Shift+Enter 换行)"
                rows={1}
                className="max-h-36 min-h-10 flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 text-[#16201B] placeholder:text-[#8A938D] focus:outline-none"
              />
              <button
                type="submit"
                disabled={!input.trim()}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#1F8A5B] text-[#FFFFFF] transition-colors hover:bg-[#176F49] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#1F8A5B]/40 disabled:bg-[#E7E5DE] disabled:text-[#B7BDB7]"
                title="发送"
              >
                <ArrowUp className="h-5 w-5" />
              </button>
            </form>
            {medicalExamImportError && (
              <p role="alert" className="pointer-events-auto mx-auto mt-2 max-w-3xl text-center text-[11px] text-[#D5503A]">
                {medicalExamImportError}
              </p>
            )}
            <p className="pointer-events-none mx-auto mt-2 max-w-3xl text-center text-[11px] text-[#8A938D]">
              健康建议不能替代医生诊断；紧急或明显异常请及时就医。
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}

function normalizeImagePreview(imageUrl?: string | null): string | undefined {
  if (!imageUrl) return undefined;
  try {
    const parsed = JSON.parse(imageUrl);
    if (Array.isArray(parsed)) return parsed[0];
  } catch {
    return imageUrl || undefined;
  }
  return imageUrl || undefined;
}
