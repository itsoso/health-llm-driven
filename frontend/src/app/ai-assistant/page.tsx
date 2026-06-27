'use client';

/**
 * /ai-assistant —— Web 智能助理对话页 (2026-05-12 重建, 2026-05-13 切 agentApi).
 *
 * 之前用 openclawApi (独立 LLM key, 双倍成本). 改用 agentApi → /agent/stream
 * 跟 mobile chat tab 同管道, 共享 LLM_PROVIDER (默认 TokenPlan).
 *
 * 历史: 该路由从 nav / dashboard / footer / 测试里被引, 但 page.tsx 一直缺,
 * 用户访问就 404. 此页用 Agent stream + ChatView 渲染.
 */

import { Suspense, useEffect, useRef, useState } from 'react';
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
  canonicalModelId,
  isAdvancedChatModelId,
  sanitizeLlmPreference,
  sanitizeModelOptions,
} from '@/components/assistant/modelCatalog';
import { executeMedicalExamImportSkillForFile } from '@/services/chatMedicalExamImportSkill';

const DEFAULT_SUGGESTIONS = [
  '分析我最近的代谢健康',
  '今天怎么安排训练和恢复',
  '结合基因和体检给我建议',
  '帮我复盘最近的睡眠质量',
];

interface ConversationOpener {
  text: string;
  source: string;
  source_id?: number | null;
  quick_replies?: string[];
  deep_link?: string | null;
  priority?: number;
}

const OPENER_SOURCE_LABEL: Record<string, string> = {
  action_card_due: '今日检验',
  anomaly: '数据异常',
  case_thread: '持续话题',
  memory_fact: '记忆回顾',
};

const CONV_PAGE_SIZE = 20; // 历史记录每页条数

export default function AIAssistantPage() {
  // useSearchParams 需要 Suspense 边界, 否则 Next.js 14 build 报
  // "useSearchParams() should be wrapped in a suspense boundary".
  return (
    <Suspense fallback={<div className="fixed inset-0 z-40 bg-[#212121]" />}>
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
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
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
  const medicalExamInputRef = useRef<HTMLInputElement | null>(null);
  const [starterSuggestions, setStarterSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS);
  const [opener, setOpener] = useState<ConversationOpener | null>(null);
  const [medicalExamImporting, setMedicalExamImporting] = useState(false);
  const [medicalExamImportError, setMedicalExamImportError] = useState<string | null>(null);

  // 自动滚到底
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, streaming]);

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

  const refreshConversations = async (targetPage: number = convPage) => {
    setHistoryLoading(true);
    try {
      const offset = (targetPage - 1) * CONV_PAGE_SIZE;
      const res = await agentApi.getConversations(CONV_PAGE_SIZE, offset);
      setConversations(res.data.items || []);
      setConvTotal(res.data.total || 0);
      setConvPage(targetPage);
    } catch {
      setConversations([]);
    } finally {
      setHistoryLoading(false);
    }
  };

  useEffect(() => {
    refreshConversations();
  }, []);

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
      setOpener(
        op && typeof op.text === 'string' && op.text.trim()
          ? {
              text: op.text,
              source: typeof op.source === 'string' ? op.source : '',
              source_id: op.source_id ?? null,
              quick_replies: Array.isArray(op.quick_replies) ? op.quick_replies.slice(0, 3) : [],
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

  const sendMessage = async (overrideText?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;
    setInput('');
    setStreaming(true);

    // 本地先插用户消息 + assistant 占位
    const tempUserId = -Date.now();
    const tempAssistantId = -Date.now() - 1;
    const now = new Date().toISOString();
    setMessages(prev => [
      ...prev,
      { id: tempUserId, role: 'user', content: text, created_at: now },
      { id: tempAssistantId, role: 'assistant', content: '', created_at: now },
    ]);

    let assistantBuf = '';
    let realConvId = activeConvId;

    try {
      for await (const evt of agentApi.streamMessage(text, activeConvId)) {
        if (!evt) continue;
        // /agent/stream event shape: { event, data: {content, conversation_id, ...} }
        const type = evt.event ?? evt.type;
        const data = evt.data ?? {};
        if (type === 'token' && typeof data.content === 'string') {
          assistantBuf += data.content;
          setMessages(prev =>
            prev.map(m => (m.id === tempAssistantId ? { ...m, content: assistantBuf } : m)),
          );
        } else if (type === 'tool_call') {
          // 用户感知: 显示"调用工具中"提示一行 (灰色 italic), 不污染主回答
        } else if (type === 'done') {
          if (data.conversation_id) realConvId = data.conversation_id;
          // 2026-05-13: 写性能字段, ChatView footer 显示
          const perf = {
            elapsed_ms: typeof data.elapsed_ms === 'number' ? data.elapsed_ms : undefined,
            llm_ms: typeof data.llm_ms === 'number' ? data.llm_ms : undefined,
            llm_rounds: typeof data.llm_rounds === 'number' ? data.llm_rounds : undefined,
            llm_rounds_ms: Array.isArray(data.llm_rounds_ms) ? data.llm_rounds_ms : undefined,
            model: typeof data.model === 'string' ? data.model : undefined,
            // 2026-05-14 #4: 可解释性 sources
            sources_used: Array.isArray(data.sources_used) ? data.sources_used : undefined,
          };
          setMessages(prev =>
            prev.map(m => (m.id === tempAssistantId ? { ...m, ...perf } : m)),
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
      if (!activeConvId && realConvId) {
        setActiveConvId(realConvId);
        syncConvUrl(realConvId); // 首条消息拿到 realConvId 后写 ?c=<id>
      }
      refreshConversations();
    }
  };

  const startNewConversation = () => {
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
    const loaded = (res.data.messages || []).map((m: any) => ({
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
      sources_used: m.meta?.sources_used,
    })) as ChatMessage[];
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
    refreshConversations(targetPage);
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
    if (streaming) return;
    sendMessage(text);
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
      const res = await sharedApi.createTextShare('健康 Agent · 对话节选', text);
      const shareUrl = res.data.share_url;
      if (navigator.share) {
        await navigator.share({ title: '健康 Agent · 对话节选', text: '我分享了一段健康 Agent 对话', url: shareUrl });
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
    <main className="fixed inset-0 z-40 flex flex-col overflow-hidden bg-[#212121] text-zinc-100">
      <header className="relative z-[70] shrink-0 overflow-visible border-b border-white/[0.08] bg-[#212121]/95 px-3 py-2.5 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-1">
            <button
              onClick={() => setHistoryOpen(open => !open)}
              className="mr-1 flex h-9 w-9 items-center justify-center rounded-xl text-zinc-400 transition-colors hover:bg-white/[0.08] hover:text-zinc-100"
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
            className="inline-flex h-9 items-center gap-2 rounded-xl border border-white/10 bg-white/[0.06] px-3 text-sm font-medium text-zinc-100 transition-colors hover:bg-white/[0.1]"
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
              className="inline-flex h-9 items-center gap-2 rounded-xl border border-teal-300/20 bg-teal-400/10 px-3 text-sm font-medium text-teal-200 transition-colors hover:bg-teal-400/15"
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
            page={convPage}
            totalPages={Math.max(1, Math.ceil(convTotal / CONV_PAGE_SIZE))}
            onPrevPage={() => { if (convPage > 1) refreshConversations(convPage - 1); }}
            onNextPage={() => {
              if (convPage < Math.ceil(convTotal / CONV_PAGE_SIZE)) refreshConversations(convPage + 1);
            }}
          />
        )}

        <div className="relative flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-3 pb-32 pt-8 sm:px-6">
            {messages.length === 0 && !streaming ? (
              <div className="mx-auto flex min-h-[60vh] max-w-3xl flex-col items-center justify-center text-center">
                <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-teal-500/15 text-teal-300 ring-1 ring-teal-300/15">
                  <Sparkles className="h-7 w-7" />
                </div>
                <h1 className="mt-5 text-2xl font-semibold tracking-tight text-zinc-50 sm:text-3xl">
                  今天想了解什么？
                </h1>
                {opener && (
                  <div className="mt-7 w-full">
                    <button
                      type="button"
                      onClick={() => submitSuggestion(opener.text)}
                      className="group w-full rounded-2xl border border-teal-300/25 bg-teal-400/[0.06] px-5 py-4 text-left transition-colors hover:border-teal-300/45 hover:bg-teal-400/[0.1]"
                    >
                      <div className="mb-1.5 flex items-center gap-2">
                        <Sparkles className="h-3.5 w-3.5 text-teal-300" />
                        <span className="text-[11px] font-medium uppercase tracking-wider text-teal-300/80">
                          {OPENER_SOURCE_LABEL[opener.source] ?? 'AI 续接'}
                        </span>
                      </div>
                      <div className="text-[15px] leading-6 text-zinc-100">{opener.text}</div>
                    </button>
                    {opener.quick_replies && opener.quick_replies.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {opener.quick_replies.map(reply => (
                          <button
                            key={reply}
                            type="button"
                            onClick={() => submitSuggestion(reply)}
                            className="rounded-full border border-teal-300/25 bg-teal-400/[0.08] px-3 py-1.5 text-xs font-medium text-teal-100 transition-colors hover:border-teal-300/45 hover:bg-teal-400/[0.15]"
                          >
                            {reply}
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
                      className="rounded-2xl border border-white/10 bg-white/[0.04] px-4 py-3 text-left text-sm text-zinc-300 transition-colors hover:border-teal-300/30 hover:bg-white/[0.07] hover:text-zinc-50"
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
                doneMessageIds={doneIds}
                messageFeedback={{}}
                onFeedback={() => {}}
                shareSelectionMode={shareSelectionMode}
                selectedMessageIds={selectedMessageIds}
                onToggleMessageSelection={toggleMessageSelection}
                onEnterSelectionWith={enterSelectionWith}
                onShareMessages={ids => shareMessages(ids)}
              />
            )}
          </div>

          {shareSelectionMode && (
            <div className="pointer-events-auto absolute inset-x-3 bottom-28 z-20 mx-auto flex max-w-3xl items-center justify-between gap-3 rounded-2xl border border-teal-300/20 bg-[#171717]/95 px-4 py-3 shadow-2xl shadow-black/40 backdrop-blur sm:inset-x-6">
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-100">已选择 {selectedMessageIds.size} 条</div>
                <div className="text-xs text-zinc-500">按对话顺序生成一个可分享链接</div>
              </div>
              <button
                type="button"
                disabled={selectedMessageIds.size === 0 || sharing}
                onClick={() => shareMessages()}
                className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-teal-300 px-4 text-sm font-semibold text-zinc-950 transition-colors hover:bg-teal-200 disabled:bg-zinc-700 disabled:text-zinc-500"
              >
                <Share2 className="h-4 w-4" />
                {sharing ? '生成中…' : '分享'}
              </button>
            </div>
          )}

          {/* 输入区 */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-[#212121] via-[#212121] to-transparent px-3 pb-4 pt-10 sm:px-6">
            <form
              id="ai-assistant-composer"
              onSubmit={e => {
                e.preventDefault();
                sendMessage();
              }}
              className="pointer-events-auto mx-auto flex max-w-3xl items-end gap-2 rounded-[1.7rem] border border-white/10 bg-[#2f2f2f] p-2 shadow-2xl shadow-black/30"
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
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-zinc-400 transition-colors hover:bg-white/[0.08] hover:text-zinc-100 disabled:cursor-not-allowed disabled:text-zinc-600"
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
                onKeyDown={e => {
                  // IME composition (拼音/日文/韩文) 中按 Enter 是确认候选词,不是发送
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return;
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                placeholder={streaming ? '回答中…' : '发消息 (Enter 发送, Shift+Enter 换行)'}
                disabled={streaming}
                rows={1}
                className="max-h-36 min-h-10 flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 text-zinc-100 placeholder:text-zinc-500 focus:outline-none disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || streaming}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-zinc-100 text-zinc-950 transition-colors hover:bg-white disabled:bg-zinc-600 disabled:text-zinc-400"
                title="发送"
              >
                <ArrowUp className="h-5 w-5" />
              </button>
            </form>
            {medicalExamImportError && (
              <p role="alert" className="pointer-events-auto mx-auto mt-2 max-w-3xl text-center text-[11px] text-rose-300">
                {medicalExamImportError}
              </p>
            )}
            <p className="pointer-events-none mx-auto mt-2 max-w-3xl text-center text-[11px] text-zinc-600">
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
