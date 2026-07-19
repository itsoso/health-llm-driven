'use client';

import { Fragment, memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bookmark, Check, ChevronDown, Copy, Share2, ThumbsDown, ThumbsUp } from 'lucide-react';
import { ChatMessage } from '@/services/api/ai';
import MarkdownRenderer from '@/components/assistant/MarkdownRenderer';
import MealPlanCard from '@/components/assistant/MealPlanCard';
import ToolCallChip from '@/components/assistant/ToolCallChip';
import { preprocessAssistantContent } from '@/components/assistant/assistantContent';
import { ChatSegment, hasToolCall, parseToolCalls } from '@/components/assistant/toolCallParse';
import { prettyModelName } from '@/components/assistant/modelName';
import { renderCard } from '@/components/assistant/inlineCards';
import type { ChatCardActionDescriptor } from '@/components/assistant/inlineCards';
import { getShareableMessageIds } from '@/components/assistant/shareSelection';
import { buildAgentTransparency, formatDurationMs, type AgentTransparencyBand } from '@/components/assistant/chatTransparency';

interface ChatViewProps {
  messages: ChatMessage[];
  loading: boolean;
  /** 实时状态短语 (status SSE 事件映射), 渲染在 loader 圆点旁; 首 token 到达清空。 */
  statusText?: string | null;
  doneMessageIds: Set<number>;
  messageFeedback: Record<number, 1 | 5>;
  onFeedback: (msgId: number, rating: 1 | 5) => void;
  onPinMessage?: (content: string, msgId: number) => void;
  shareSelectionMode?: boolean;
  selectedMessageIds?: Set<number>;
  onToggleMessageSelection?: (msgId: number) => void;
  /** 微信式入口: 右键 / 长按某条消息直接进入多选分享并预选中该条. */
  onEnterSelectionWith?: (msgId: number) => void;
  onShareMessages?: (msgIds: number[]) => void;
  onCardAction?: (messageId: number, action: ChatCardActionDescriptor) => void | Promise<void>;
}

/** 长按计时: pointer 持续按住约 500ms 触发, 移动/松开/离开均取消. */
const LONG_PRESS_MS = 500;
const MESSAGE_TIME_DIVIDER_GAP_MS = 5 * 60 * 1000;

const STYLE = {
  assistantTextClass: 'text-[#29261F]',
  userBubbleClass: 'bg-[#F3E4DC] text-[#29261F]',
};

/** 助理头像 — clay 圆角方块 "巴", 与顶栏品牌 mark 一致。 */
function AssistantAvatar({ className = '' }: { className?: string }) {
  return (
    <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[#C96442] text-[13px] font-semibold text-white ${className}`}>
      巴
    </div>
  );
}

function parseMessageDate(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatMessageShortTime(value?: string | null): string {
  const date = parseMessageDate(value);
  if (!date) return '';
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function formatMessageFullTime(value?: string | null): string {
  const date = parseMessageDate(value);
  if (!date) return '';
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function sameLocalDate(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate();
}

function shouldShowMessageTimeDivider(previous?: string | null, current?: string | null): boolean {
  const currentDate = parseMessageDate(current);
  if (!currentDate) return false;
  const previousDate = parseMessageDate(previous);
  if (!previousDate) return true;
  return !sameLocalDate(previousDate, currentDate)
    || currentDate.getTime() - previousDate.getTime() >= MESSAGE_TIME_DIVIDER_GAP_MS;
}

function formatMessageTimeDivider(value?: string | null, now = new Date()): string {
  const date = parseMessageDate(value);
  if (!date) return '';
  const time = date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  if (sameLocalDate(date, now)) return `今天 ${time}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (sameLocalDate(date, yesterday)) return `昨天 ${time}`;
  return `${date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })} ${time}`;
}

function MessageTimePill({ value, side }: { value?: string | null; side: 'user' | 'assistant' }) {
  const label = formatMessageShortTime(value);
  if (!label) return null;
  return (
    <span
      data-testid="message-hover-time"
      className={`pointer-events-none absolute -top-4 select-none rounded-full bg-[#F0EDE4]/95 px-2 py-0.5 text-[11px] leading-4 text-[#948F80] opacity-0 shadow-sm ring-1 ring-[#E5E1D5]/70 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100 ${
        side === 'user' ? 'right-2' : 'left-10'
      }`}
    >
      {label}
    </span>
  );
}

function MessageTimeDivider({ value }: { value?: string | null }) {
  const label = formatMessageTimeDivider(value);
  if (!label) return null;
  return (
    <div className="flex justify-center" data-testid="message-time-divider">
      <span className="rounded-full border border-[#E5E1D5] bg-[#F8F6EF] px-3 py-1 font-mono text-[11px] font-semibold leading-4 text-[#948F80] shadow-sm">
        {label}
      </span>
    </div>
  );
}

export default function ChatView({
  messages,
  loading,
  statusText = null,
  doneMessageIds,
  messageFeedback,
  onFeedback,
  onPinMessage,
  shareSelectionMode = false,
  selectedMessageIds = new Set(),
  onToggleMessageSelection,
  onEnterSelectionWith,
  onShareMessages,
  onCardAction,
}: ChatViewProps) {
  // 允许空内容但是有卡片的消息显示
  const visibleMessages = useMemo(
    () => messages.filter(m => !(m.role === 'assistant' && !m.content && !m.card_type)),
    [messages],
  );
  // P1: 稳定 Set 引用 — 否则每 token 重算的新 Set 会击穿下面 MessageRow 的 memo。
  const shareableMessageIds = useMemo(() => getShareableMessageIds(visibleMessages), [visibleMessages]);
  const [copiedMessageId, setCopiedMessageId] = useState<number | null>(null);
  const copyResetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (copyResetTimer.current) clearTimeout(copyResetTimer.current);
  }, []);

  const handleCopyMessage = useCallback(async (message: ChatMessage) => {
    if (!navigator.clipboard) return;
    try {
      await navigator.clipboard.writeText(message.content);
      setCopiedMessageId(message.id);
      if (copyResetTimer.current) clearTimeout(copyResetTimer.current);
      copyResetTimer.current = setTimeout(() => {
        setCopiedMessageId(null);
        copyResetTimer.current = null;
      }, 1500);
    } catch (error) {
      console.error('[chat] copy failed', error);
    }
  }, []);

  // 长按计时器 (触屏补充入口). 右键是桌面主入口, 见下方 onContextMenu.
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cancelLongPress = useCallback(() => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  }, []);

  // 进入选择模式入口: 仅在「非选择模式 + 可分享 + 有 handler」时生效. 已在选择
  // 模式则交给 checkbox 的正常 toggle, 不重复触发.
  const enterFor = useCallback(
    (msgId: number) => {
      if (shareSelectionMode || !onEnterSelectionWith) return;
      if (!shareableMessageIds.has(msgId)) return;
      onEnterSelectionWith(msgId);
    },
    [shareSelectionMode, onEnterSelectionWith, shareableMessageIds],
  );

  const handlePointerDown = useCallback(
    (e: React.PointerEvent, msgId: number) => {
      // 仅触屏走长按; 鼠标/触控笔走右键入口, 不和文本选择抢.
      if (e.pointerType !== 'touch') return;
      if (shareSelectionMode || !shareableMessageIds.has(msgId)) return;
      cancelLongPress();
      longPressTimer.current = setTimeout(() => enterFor(msgId), LONG_PRESS_MS);
    },
    [shareSelectionMode, shareableMessageIds, cancelLongPress, enterFor],
  );

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {visibleMessages.map((msg, index) => (
        <Fragment key={msg.id}>
          {shouldShowMessageTimeDivider(visibleMessages[index - 1]?.created_at, msg.created_at) && (
            <MessageTimeDivider value={msg.created_at} />
          )}
          <MessageRow
            msg={msg}
            done={doneMessageIds.has(msg.id)}
            copied={copiedMessageId === msg.id}
            canSelectForShare={shareableMessageIds.has(msg.id)}
            selectedForShare={selectedMessageIds.has(msg.id)}
            shareSelectionMode={shareSelectionMode}
            feedback={messageFeedback[msg.id]}
            onFeedback={onFeedback}
            onCopy={handleCopyMessage}
            onPinMessage={onPinMessage}
            onToggleMessageSelection={onToggleMessageSelection}
            onEnterSelectionWith={onEnterSelectionWith}
            onShareMessages={onShareMessages}
            onCardAction={onCardAction}
            enterFor={enterFor}
            handlePointerDown={handlePointerDown}
            cancelLongPress={cancelLongPress}
          />
        </Fragment>
      ))}
      {loading && (
        <div className="flex gap-3.5">
          <AssistantAvatar className="mt-0.5" />
          <div className="flex items-center gap-2 px-1 py-2">
            <div className="flex gap-1.5 rounded-full bg-[#F0EDE4] px-3 py-2">
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#C96442]" style={{ animationDelay: '0ms' }} />
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#C96442]" style={{ animationDelay: '150ms' }} />
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-[#C96442]" style={{ animationDelay: '300ms' }} />
            </div>
            {statusText && (
              <span className="min-w-0 truncate text-[12px] leading-5 text-[#948F80]">{statusText}</span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

interface MessageRowProps {
  msg: ChatMessage;
  done: boolean;
  copied: boolean;
  canSelectForShare: boolean;
  selectedForShare: boolean;
  shareSelectionMode: boolean;
  feedback?: 1 | 5;
  onFeedback: (msgId: number, rating: 1 | 5) => void;
  onCopy: (message: ChatMessage) => void;
  onPinMessage?: (content: string, msgId: number) => void;
  onToggleMessageSelection?: (msgId: number) => void;
  onEnterSelectionWith?: (msgId: number) => void;
  onShareMessages?: (msgIds: number[]) => void;
  onCardAction?: (messageId: number, action: ChatCardActionDescriptor) => void | Promise<void>;
  enterFor: (msgId: number) => void;
  handlePointerDown: (e: React.PointerEvent, msgId: number) => void;
  cancelLongPress: () => void;
}

/**
 * MessageRow — 单条消息行. React.memo 化 (P1): 流式期间父组件每 token 重渲整列表,
 * 但只有正在流式的那一行 (done=false, content 增长) 真正 diff; 已完成行 props 不变则跳过.
 * buildAgentTransparency 在 AssistantTransparencyPanel 里另用 useMemo, 双重护栏.
 *
 * 比较器只看影响该行输出的字段 (msg 内容/性能字段 + 交互态). handler 视为稳定引用,
 * 不参与比较 —— 它们的行为由上层 setState 保证幂等, 且参与比较会击穿 memo.
 */
const MessageRow = memo(function MessageRow({
  msg,
  done,
  copied,
  canSelectForShare,
  selectedForShare,
  shareSelectionMode,
  feedback,
  onFeedback,
  onCopy,
  onPinMessage,
  onToggleMessageSelection,
  onEnterSelectionWith,
  onShareMessages,
  onCardAction,
  enterFor,
  handlePointerDown,
  cancelLongPress,
}: MessageRowProps) {
  const sentAtFull = formatMessageFullTime(msg.created_at);
  const accessibilityPrefix = msg.role === 'user' ? '你发送于' : '小巴回复于';
  // 动态卡片消息 - 独立分支, 气泡外直接贴卡片
  if (msg.card_type && msg.card_data) {
    const cardEl = renderCard(
      { type: msg.card_type, data: msg.card_data, actions: msg.card_actions as ChatCardActionDescriptor[] | undefined },
      { onAction: (action) => onCardAction?.(msg.id, action) },
    );
    if (cardEl) {
      return (
        <div
          className="group relative flex gap-3.5 justify-start"
          title={sentAtFull || undefined}
          aria-label={sentAtFull ? `${accessibilityPrefix} ${sentAtFull}` : undefined}
        >
          <AssistantAvatar className="mt-1" />
          <div className="min-w-0 flex-1">{cardEl}</div>
          <MessageTimePill value={msg.created_at} side="assistant" />
        </div>
      );
    }
  }
  return (
    <div
      className={`group relative flex gap-3.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'} ${shareSelectionMode && selectedForShare ? 'rounded-2xl bg-[#F3E4DC]/60 ring-1 ring-[#C96442]/25' : ''}`}
      title={sentAtFull || undefined}
      aria-label={sentAtFull ? `${accessibilityPrefix} ${sentAtFull}` : undefined}
      onContextMenu={
        canSelectForShare && !shareSelectionMode && onEnterSelectionWith
          ? e => {
              e.preventDefault();
              enterFor(msg.id);
            }
          : undefined
      }
      onPointerDown={canSelectForShare ? e => handlePointerDown(e, msg.id) : undefined}
      onPointerUp={cancelLongPress}
      onPointerMove={cancelLongPress}
      onPointerLeave={cancelLongPress}
      onPointerCancel={cancelLongPress}
    >
      {shareSelectionMode && (
        <button
          type="button"
          disabled={!canSelectForShare}
          onClick={() => canSelectForShare && onToggleMessageSelection?.(msg.id)}
          className={`mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border transition-all ${
            selectedForShare
              ? 'border-[#C96442] bg-[#C96442] text-white'
              : canSelectForShare
                ? 'border-[#D8D3C4] bg-[#FCFBF7] text-transparent hover:border-[#C96442]'
                : 'border-[#E5E1D5] bg-transparent text-transparent opacity-40'
          }`}
          aria-label={selectedForShare ? '取消选择这条消息' : '选择这条消息'}
        >
          <Check className="h-3.5 w-3.5" />
        </button>
      )}
      {msg.role === 'assistant' && <AssistantAvatar className="mt-0.5" />}
      {msg.role === 'user' && <MessageTimePill value={msg.created_at} side="user" />}
      <div className={`${msg.role === 'user' ? 'max-w-[min(80%,34rem)] rounded-[1.25rem] px-4 py-2.5' : 'min-w-0 flex-1'} ${msg.role === 'user' ? STYLE.userBubbleClass : STYLE.assistantTextClass}`}>
        {msg.role === 'assistant' ? (
          <div>
            <div className="mb-2 text-[12px] font-semibold tracking-[0.04em] text-[#948F80]">健康小巴</div>
            <div className="text-[15px] leading-7">
              <AssistantBody content={msg.content} streaming={!done} />
            </div>
            {done && <AssistantTransparencyPanel msg={msg} />}
          </div>
        ) : (
          <div>
            {msg.image_preview && <img src={msg.image_preview} alt="上传图片" className="mb-2 max-h-56 max-w-xs rounded-xl object-cover" />}
            {msg.file_name && (
              <div className="mb-2 flex items-center gap-2 rounded-xl bg-[#FCFBF7] px-3 py-1.5 text-sm text-[#6B665A]">
                <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                <span className="truncate">{msg.file_name}</span>
              </div>
            )}
            <div className="whitespace-pre-wrap text-[15px] leading-6">{msg.content}</div>
          </div>
        )}
      </div>
      {msg.role === 'assistant' && <MessageTimePill value={msg.created_at} side="assistant" />}
      {msg.role === 'assistant' && msg.content && done && (
        <div className="ml-1 mt-1 flex items-center gap-0.5 self-end opacity-0 transition-opacity group-hover:opacity-100">
          <button
            type="button"
            onClick={() => onCopy(msg)}
            className={`rounded-lg p-1.5 transition-all ${copied ? 'bg-[#E4EDDD] text-[#5B7B4E]' : 'text-[#948F80] hover:bg-[#F0EDE4] hover:text-[#29261F]'}`}
            title={copied ? '已复制' : '复制'}
            aria-label={copied ? '已复制' : '复制'}
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          </button>
          {onShareMessages && (
            <button onClick={() => onShareMessages([msg.id])} className="rounded-lg p-1.5 text-[#948F80] transition-all hover:bg-[#F0EDE4] hover:text-[#C96442]" title="分享这条">
              <Share2 className="h-3.5 w-3.5" />
            </button>
          )}
          <button onClick={() => onFeedback(msg.id, 5)} className={`rounded-lg p-1.5 transition-all ${feedback === 5 ? 'bg-[#E4EDDD] text-[#5B7B4E]' : 'text-[#948F80] hover:bg-[#F0EDE4] hover:text-[#29261F]'}`} title="helpful">
            <ThumbsUp className="h-3.5 w-3.5" />
          </button>
          <button onClick={() => onFeedback(msg.id, 1)} className={`rounded-lg p-1.5 transition-all ${feedback === 1 ? 'bg-[#F5E0DA] text-[#B4573A]' : 'text-[#948F80] hover:bg-[#F0EDE4] hover:text-[#29261F]'}`} title="not helpful">
            <ThumbsDown className="h-3.5 w-3.5" />
          </button>
          {onPinMessage && (
            <button onClick={() => onPinMessage(msg.content, msg.id)} className="rounded-lg p-1.5 text-[#948F80] transition-all hover:bg-[#F0EDE4] hover:text-[#B8791F]" title="固化到首页">
              <Bookmark className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}, areMessageRowEqual);

/**
 * 比较器: 仅比较影响该行渲染的数据 + 交互态; handler 视作稳定引用不比较。
 * 完成态消息 (done=true) 这些字段全稳定 → 流式期间整表重渲时该行直接跳过。
 */
function areMessageRowEqual(prev: MessageRowProps, next: MessageRowProps): boolean {
  const a = prev.msg;
  const b = next.msg;
  return (
    a.id === b.id &&
    a.content === b.content &&
    a.role === b.role &&
    a.created_at === b.created_at &&
    a.image_preview === b.image_preview &&
    a.file_name === b.file_name &&
    a.card_type === b.card_type &&
    a.card_data === b.card_data &&
    // 完成后回填的性能/透视字段 (引用相等即可; done 后一次性设置, 不再变)
    a.elapsed_ms === b.elapsed_ms &&
    a.llm_rounds === b.llm_rounds &&
    a.llm_rounds_ms === b.llm_rounds_ms &&
    a.model === b.model &&
    a.llm_usage === b.llm_usage &&
    a.perf === b.perf &&
    a.sources_used === b.sources_used &&
    a.tools_used === b.tools_used &&
    prev.done === next.done &&
    prev.copied === next.copied &&
    prev.canSelectForShare === next.canSelectForShare &&
    prev.selectedForShare === next.selectedForShare &&
    prev.shareSelectionMode === next.shareSelectionMode &&
    prev.feedback === next.feedback
  );
}

/**
 * AssistantBody — 渲染 assistant 正文. 先预处理 (剥离内部标记 + 抽计划 JSON),
 * 再把模型当文本吐出来的 [tool_call: ...] 切出来渲染成内联 chip, 其余文本走
 * MarkdownRenderer. 连续的 tool_call 段 (中间只有空白) 合并成一行 chips.
 */
function AssistantBody({ content, streaming }: { content: string; streaming?: boolean }) {
  // 预处理: 剥离 [claim:]/[工具调用:] 内部标记 + 抽出计划 JSON (menu_share schema).
  // marker 剥离始终安全; 计划 JSON 在流式中途多半解析失败 → 自动回退裸文本, 完成后成形.
  const { text, mealPlan } = preprocessAssistantContent(content);
  const body = renderTextBody(text, streaming);
  if (!mealPlan) return body;
  return (
    <>
      {body}
      <MealPlanCard plan={mealPlan} />
    </>
  );
}

/** 渲染纯文本正文 (已剥离标记/计划 JSON): 处理内联 tool_call chip + markdown. */
function renderTextBody(content: string, streaming?: boolean) {
  // 没有工具调用文本就走老路径 — 绝大多数消息命中这里.
  if (!hasToolCall(content)) {
    if (!content.trim()) return null;
    return <MarkdownRenderer content={content} variant="warm" />;
  }
  const segments = parseToolCalls(content);
  const groups = groupSegments(segments);
  return (
    <>
      {groups.map((group, gi) => {
        if (group[0].kind === 'tool_call') {
          const chips = group as Extract<ChatSegment, { kind: 'tool_call' }>[];
          return (
            <div key={gi} className="my-1.5 flex flex-wrap items-center gap-1.5">
              {chips.map((c, ci) => (
                <ToolCallChip key={ci} name={c.name} pulse={streaming} />
              ))}
            </div>
          );
        }
        const text = (group[0] as Extract<ChatSegment, { kind: 'text' }>).text;
        if (!text.trim()) return null;
        return (
          <Fragment key={gi}>
            <MarkdownRenderer content={text} variant="warm" />
          </Fragment>
        );
      })}
    </>
  );
}

/** 把相邻的 tool_call 段聚成一组 (一行 chips); 文本段各自成组. */
function groupSegments(segments: ChatSegment[]): ChatSegment[][] {
  const groups: ChatSegment[][] = [];
  for (const seg of segments) {
    const last = groups[groups.length - 1];
    if (seg.kind === 'tool_call' && last && last[0].kind === 'tool_call') {
      last.push(seg);
    } else {
      groups.push([seg]);
    }
  }
  return groups;
}

function bandClass(kind: AgentTransparencyBand['kind']): string {
  switch (kind) {
    case 'prellm': return 'bg-[#B4AF9F]';
    case 'ttft': return 'bg-[#D6A24A]';
    case 'gen': return 'bg-[#7FA06B]';
    case 'tool': return 'bg-[#6E93B4]';
    case 'orch': return 'bg-[#C96442]';
    case 'total':
    default:
      return 'bg-[#8A9E7A]';
  }
}

function AssistantTransparencyPanel({ msg }: { msg: ChatMessage }) {
  const [open, setOpen] = useState(false);
  // P1: 只有 msg 相关性能字段变化时才重算 (完成态消息这些字段稳定, 完全跳过重算)。
  const profile = useMemo(
    () =>
      buildAgentTransparency({
        elapsedMs: msg.elapsed_ms,
        llmRounds: msg.llm_rounds,
        llmRoundsMs: msg.llm_rounds_ms,
        model: prettyModelName(msg.model) || msg.model,
        llmUsage: msg.llm_usage,
        sourcesUsed: msg.sources_used,
        toolsUsed: msg.tools_used,
        perf: msg.perf,
      }),
    [
      msg.elapsed_ms,
      msg.llm_rounds,
      msg.llm_rounds_ms,
      msg.model,
      msg.llm_usage,
      msg.sources_used,
      msg.tools_used,
      msg.perf,
    ],
  );
  if (!profile.visible) return null;

  return (
    <div className="mt-3.5 w-fit max-w-full overflow-hidden rounded-[9px] border border-[#E5E1D5] bg-[#FCFBF7]">
      <button
        onClick={() => setOpen(o => !o)}
        className="flex w-full items-center gap-2 px-3 py-[7px] text-left text-[11.5px] text-[#948F80] transition-colors hover:text-[#C96442]"
        title="查看本轮执行透视"
      >
        <span className="h-[5px] w-[5px] shrink-0 rounded-full bg-[#5B7B4E]" />
        <span className="min-w-0 flex-1 truncate font-medium rd-num">透视 · {profile.headline || '本轮执行'}</span>
        <ChevronDown className={`h-3.5 w-3.5 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="border-t border-[#E5E1D5] px-3 py-2.5 text-[11px] text-[#6B665A]">
          {profile.bands.length > 0 && (
            <>
              <div className="flex h-1.5 overflow-hidden rounded-full bg-[#EAE6DA]">
                {profile.bands.map((band, index) => (
                  <span
                    key={`${band.kind}-${index}`}
                    className={bandClass(band.kind)}
                    style={{ flexGrow: band.ratio, flexBasis: 0 }}
                  />
                ))}
              </div>
              <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10.5px] text-[#948F80]">
                {profile.bands.map((band, index) => (
                  <span key={`${band.kind}-legend-${index}`}>{band.label} {formatDurationMs(band.ms)}</span>
                ))}
              </div>
            </>
          )}

          <div className="mt-2.5 grid gap-1.5">
            {profile.stages.length > 0 && (
              <MetaRow label="继续阶段" value={profile.stages.map(s => `${s.label} ${s.value}`).join(' · ')} />
            )}
            {profile.rounds.length > 0 && (
              <MetaRow label="LLM 轮次" value={profile.rounds.map(r => `${r.label} ${r.value}`).join('\n')} preserveLines />
            )}
            {profile.costLine && <MetaRow label="成本" value={profile.costLine} />}
            {profile.tokenLine && <MetaRow label="Token" value={profile.tokenLine} />}
            {profile.errorLine && <MetaRow label="失败" value={profile.errorLine} />}
            {profile.traceLine && <MetaRow label="追踪" value={profile.traceLine} />}
            {profile.sources.length > 0 && (
              <MetaRow label="引用数据" value={profile.sources.slice(0, 8).map(s => `· ${s}`).join('\n')} preserveLines />
            )}
            {profile.tools.length > 0 && (
              <div className="grid grid-cols-[4.5rem_1fr] gap-2">
                <span className="text-[#948F80]">调用 Skill</span>
                <div className="flex flex-wrap gap-1.5">
                  {profile.tools.map(tool => (
                    <span key={tool} className="rounded-full border border-[#E5E1D5] bg-[#F0EDE4] px-2 py-0.5 font-mono text-[10.5px] text-[#6B665A]">
                      {tool}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MetaRow({ label, value, preserveLines = false }: { label: string; value: string; preserveLines?: boolean }) {
  return (
    <div className="grid grid-cols-[4.5rem_1fr] gap-2">
      <span className="text-[#948F80]">{label}</span>
      <span className={`text-[#6B665A] rd-num ${preserveLines ? 'whitespace-pre-wrap' : ''}`}>{value}</span>
    </div>
  );
}
