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

import { Suspense, useEffect, useRef, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
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
import { pickPastedMedicalImportFile } from '@/services/pastedMedicalImportFile';
import { statusStagePhrase } from '@/components/assistant/statusStagePhrase';
import {
  ConversationOpener,
  QuickReply,
  buildConversationOpenerReplyContext,
  buildConversationOpenerReplyMessage,
  normalizeOpener,
  routeForQuickReplyAction,
} from '@/components/assistant/conversationOpener';

const DEFAULT_SUGGESTIONS = [
  '分析我最近的代谢健康',
  '今天怎么安排训练和恢复',
  '结合基因和体检给我建议',
  '帮我复盘最近的睡眠质量',
];

const OPENER_SOURCE_LABEL: Record<string, string> = {
  action_card_due: '今日检验',
  anomaly: '数据异常',
  case_thread: '持续话题',
  memory_fact: '记忆回顾',
};

const CONV_PAGE_SIZE = 20; // 历史记录每页条数

/**
 * 页面级暖色主题 (Claude / Anthropic 设计语言, 2026-07-05 重设计).
 *
 * 作用域严格限定在本页 —— 变量只挂在 .ai-assistant-theme 包裹层, 不改
 * globals.css / tailwind.config, 其他路由外观零影响。颜色直接用 mockup hex,
 * 组件里的 arbitrary-value class 也读同一批 hex (rail/picker/chat/markdown warm)。
 */
const THEME_CSS = `
.ai-assistant-theme{
  --rd-paper:#F7F5EF; --rd-rail:#F0EDE4; --rd-card:#FCFBF7;
  --rd-hair:#E5E1D5; --rd-hair-strong:#D8D3C4;
  --rd-ink:#29261F; --rd-ink-2:#6B665A; --rd-ink-3:#948F80;
  --rd-clay:#C96442; --rd-clay-soft:#F3E4DC;
  --rd-amber:#B8791F; --rd-amber-soft:#F5EBD6;
  --rd-sans:-apple-system,BlinkMacSystemFont,"PingFang SC","Segoe UI","Microsoft YaHei",sans-serif;
  --rd-serif:"Songti SC","Noto Serif SC","Iowan Old Style",Georgia,"Times New Roman",serif;
  background:var(--rd-paper); color:var(--rd-ink); font-family:var(--rd-sans);
}
.ai-assistant-theme ::-webkit-scrollbar{width:9px;height:9px}
.ai-assistant-theme ::-webkit-scrollbar-thumb{background:var(--rd-hair-strong);border-radius:8px}
.ai-assistant-theme ::-webkit-scrollbar-track{background:transparent}
.rd-serif{font-family:var(--rd-serif)}
.rd-num{font-variant-numeric:tabular-nums}
`;

export default function AIAssistantPage() {
  // useSearchParams 需要 Suspense 边界, 否则 Next.js 14 build 报
  // "useSearchParams() should be wrapped in a suspense boundary".
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: THEME_CSS }} />
      <Suspense fallback={<div className="fixed inset-0 z-40 bg-[#F7F5EF]" />}>
        <AIAssistantInner />
      </Suspense>
    </>
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
  // 状态行去抖: for-await 循环内读闭包会拿到陈旧 statusText, 用 ref 避免重复 setState。
  const statusRef = useRef<string | null>(null);
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
  //
  // 跨页「提问」入口: 其他页 (如 /genetic 的基因卡) 点提问会带 ?prompt=<encoded>
  // 跳过来, 把问题预填进输入框 (不自动发送)。契约名 `prompt` 与 Mac / 后端
  // 动态卡 `chat?prompt=...` 一致。仅在新/空对话生效, ?c= 会话恢复优先; 消费后
  // 清掉该 param, 刷新不重复注入。
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
      return;
    }
    const prefill = searchParams.get('prompt');
    if (prefill && prefill.trim()) {
      // searchParams 已是解码后的值; 再兜一层 decode 容忍双重编码, 失败保底原值。
      let text = prefill;
      try {
        text = decodeURIComponent(prefill);
      } catch {
        text = prefill;
      }
      // 跨页提问强制开新对话: 不接着上一条老对话续写 (省 context/token)。
      // 页面 mount 时 activeConvId 本就是 undefined, 这里显式清空 messages 兜底,
      // 保证 empty-state 新会话空态 + 预填输入, 用户直接回车即发。
      setActiveConvId(undefined);
      setMessages([]);
      setInput(text);
      syncConvUrl(undefined); // 清掉 ?prompt=, 回到干净 /ai-assistant
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
      // normalizeOpener 保留 source_id + 把 quick_replies 归一成 {text, action?}
      // (镜像 mobile), 让带 action 的 chip 走本地导航、文本 chip 带 opener 上下文发送。
      setOpener(normalizeOpener(res.data?.opener));
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

  const sendMessage = async (overrideText?: string, extraContext?: string) => {
    const text = (overrideText ?? input).trim();
    if (!text || streaming) return;
    setInput('');
    setStreaming(true);
    setStatusText(null);

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
    statusRef.current = null;

    try {
      for await (const evt of agentApi.streamMessage(
        text,
        activeConvId,
        undefined,
        undefined,
        undefined,
        undefined,
        extraContext,
      )) {
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
      statusRef.current = null;
      setStatusText(null);
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
      llm_usage: m.meta?.llm_usage,
      perf: m.meta?.perf,
      sources_used: m.meta?.sources_used,
      tools_used: m.meta?.tools_used,
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

  // opener 一键回复。镜像 mobile 的两路分流:
  //  - 带 action 的 chip (photo_meal/record_weight/connect_device, 冷启动包) →
  //    本地导航, 不发消息。
  //  - 纯文本 chip (做到了 / 没做 / 调整下计划) → 带 opener 上下文发送, 让后端
  //    apply_opener_quick_reply_context 把回复绑定到具体 ActionCard (自报依从 /
  //    调整请求 → 确定性写库), 而非当孤立文本。
  const submitOpenerQuickReply = (reply: QuickReply) => {
    if (streaming) return;
    const activeOpener = opener;
    if (reply.action) {
      // 本地导航路: 与 mobile navigateForQuickReplyAction 一致, 只跳路由不发文本。
      router.push(routeForQuickReplyAction(reply.action));
      return;
    }
    if (!activeOpener) {
      sendMessage(reply.text);
      return;
    }
    const extraContext = buildConversationOpenerReplyContext(activeOpener, reply.text);
    const messageText = buildConversationOpenerReplyMessage(activeOpener, reply.text);
    setOpener(null); // 一次性开场, 点后收起 chip 组
    sendMessage(messageText, extraContext);
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
    <main className="ai-assistant-theme fixed inset-0 z-40 flex flex-col overflow-hidden text-[#29261F]">
      <header className="relative z-[70] shrink-0 overflow-visible border-b border-[#E5E1D5] bg-[#F7F5EF]/95 px-4 py-2.5 backdrop-blur sm:px-6">
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          <button
            onClick={() => setHistoryOpen(open => !open)}
            className="flex h-9 w-9 items-center justify-center rounded-xl text-[#948F80] transition-colors hover:bg-[#EFEADD] hover:text-[#29261F]"
            title="打开/收起历史记录"
          >
            <PanelLeft className="h-[1.05rem] w-[1.05rem]" />
          </button>
          {/* 千问式:左上角纯文字字标(图标在右上角 brand 位,豆包/阿福同款,免得左侧三件套挤成一坨) */}
          <Link href="/" title="回到首页" className="hidden shrink-0 transition-opacity hover:opacity-80 sm:inline">
            <span className="rd-serif text-[17px] font-semibold tracking-[0.01em] text-[#29261F]">
              小巴
            </span>
          </Link>
          <div className="min-w-0">
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
          <div className="flex-1" />
          <button
            onClick={startNewConversation}
            className="inline-flex h-9 items-center gap-2 rounded-[9px] border border-[#D8D3C4] px-3 text-[13px] font-medium text-[#6B665A] transition-colors hover:bg-[#FCFBF7] hover:text-[#29261F]"
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
              className="inline-flex h-9 items-center gap-2 rounded-[9px] border border-[#C96442] px-3 text-[13px] font-medium text-[#C96442] transition-colors hover:bg-[#F3E4DC]"
            >
              {shareSelectionMode ? <X className="h-4 w-4" /> : <CheckSquare className="h-4 w-4" />}
              <span className="hidden sm:inline">{shareSelectionMode ? '取消选择' : '选择分享'}</span>
            </button>
          )}
          {/* 右上角品牌图标(千问/豆包/阿福 的 avatar 位)— mac 同款小巴图标,点击回首页;
              此页 fixed 全屏盖住全站导航,这是主要回家路 */}
          <Link href="/" title="回到首页" className="ml-0.5 shrink-0 transition-opacity hover:opacity-80">
            <Image src="/logo.png" alt="小巴" width={36} height={36} className="h-9 w-9" />
          </Link>
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
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 pb-32 pt-8 sm:px-6">
            {messages.length === 0 && !streaming ? (
              <div className="mx-auto flex min-h-[60vh] max-w-3xl flex-col items-center justify-center text-center">
                <Image src="/logo.png" alt="小巴" width={64} height={64} className="h-16 w-16" />
                <h1 className="rd-serif mt-5 pb-1 text-2xl font-semibold leading-[1.3] tracking-[0.01em] text-[#29261F] sm:text-[28px] sm:leading-[1.25]">
                  今天想了解什么？
                </h1>
                {opener && (
                  <div className="mt-7 w-full">
                    <button
                      type="button"
                      onClick={() => submitSuggestion(opener.text)}
                      className="group w-full rounded-2xl border border-[#EDD9CF] bg-[#FBF3EE] px-5 py-4 text-left transition-colors hover:border-[#C96442]"
                    >
                      <div className="mb-1.5 flex items-center gap-2">
                        <Sparkles className="h-3.5 w-3.5 text-[#C96442]" />
                        <span className="text-[11px] font-semibold uppercase tracking-[0.11em] text-[#C96442]">
                          {OPENER_SOURCE_LABEL[opener.source] ?? 'AI 续接'}
                        </span>
                      </div>
                      <div className="text-[15px] leading-6 text-[#29261F]">{opener.text}</div>
                    </button>
                    {opener.quick_replies && opener.quick_replies.length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-2">
                        {opener.quick_replies.map(reply => (
                          <button
                            key={reply.text}
                            type="button"
                            onClick={() => submitOpenerQuickReply(reply)}
                            className="rounded-full border border-[#EDD9CF] bg-[#F3E4DC] px-3 py-1.5 text-xs font-medium text-[#C96442] transition-colors hover:bg-[#EFD6CB]"
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
                      className="rounded-2xl border border-[#E5E1D5] bg-[#FCFBF7] px-4 py-3 text-left text-sm text-[#6B665A] transition-colors hover:border-[#C96442] hover:text-[#29261F]"
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
                statusText={statusText}
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
            <div className="pointer-events-auto absolute inset-x-4 bottom-28 z-20 mx-auto flex max-w-3xl items-center justify-between gap-3 rounded-2xl border border-[#D8D3C4] bg-[#FCFBF7]/97 px-4 py-3 shadow-xl shadow-[#29261F]/10 backdrop-blur sm:inset-x-6">
              <div className="min-w-0">
                <div className="text-sm font-medium text-[#29261F]">已选择 {selectedMessageIds.size} 条</div>
                <div className="text-xs text-[#948F80]">按对话顺序生成一个可分享链接</div>
              </div>
              <button
                type="button"
                disabled={selectedMessageIds.size === 0 || sharing}
                onClick={() => shareMessages()}
                className="inline-flex h-10 shrink-0 items-center gap-2 rounded-xl bg-[#C96442] px-4 text-sm font-semibold text-white transition-colors hover:bg-[#B4573A] disabled:bg-[#E5E1D5] disabled:text-[#948F80]"
              >
                <Share2 className="h-4 w-4" />
                {sharing ? '生成中…' : '分享'}
              </button>
            </div>
          )}

          {/* 输入区 */}
          <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 bg-gradient-to-t from-[#F7F5EF] via-[#F7F5EF] to-transparent px-4 pb-4 pt-10 sm:px-6">
            <form
              id="ai-assistant-composer"
              onSubmit={e => {
                e.preventDefault();
                sendMessage();
              }}
              className="pointer-events-auto mx-auto flex max-w-3xl items-end gap-2 rounded-[1.5rem] border border-[#D8D3C4] bg-[#FCFBF7] p-2 shadow-[0_1px_0_rgba(41,38,31,0.03),0_8px_24px_-12px_rgba(41,38,31,0.14)] focus-within:border-[#C96442]"
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
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-[#948F80] transition-colors hover:bg-[#F0EDE4] hover:text-[#29261F] disabled:cursor-not-allowed disabled:text-[#C7C2B4]"
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
                placeholder={streaming ? '回答中…' : '发消息 (Enter 发送, Shift+Enter 换行)'}
                disabled={streaming}
                rows={1}
                className="max-h-36 min-h-10 flex-1 resize-none bg-transparent px-3 py-2.5 text-[15px] leading-6 text-[#29261F] placeholder:text-[#948F80] focus:outline-none disabled:opacity-50"
              />
              <button
                type="submit"
                disabled={!input.trim() || streaming}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-[#C96442] text-white transition-colors hover:bg-[#B4573A] disabled:bg-[#E5E1D5] disabled:text-[#B4AF9F]"
                title="发送"
              >
                <ArrowUp className="h-5 w-5" />
              </button>
            </form>
            {medicalExamImportError && (
              <p role="alert" className="pointer-events-auto mx-auto mt-2 max-w-3xl text-center text-[11px] text-[#B4573A]">
                {medicalExamImportError}
              </p>
            )}
            <p className="pointer-events-none mx-auto mt-2 max-w-3xl text-center text-[11px] text-[#948F80]">
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
