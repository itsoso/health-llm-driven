'use client';

import { Fragment, useCallback, useRef, useState } from 'react';
import { Bookmark, Check, Copy, Share2, Sparkles, ThumbsDown, ThumbsUp } from 'lucide-react';
import { ChatMessage } from '@/services/api/ai';
import MarkdownRenderer from '@/components/assistant/MarkdownRenderer';
import MealPlanCard from '@/components/assistant/MealPlanCard';
import ToolCallChip from '@/components/assistant/ToolCallChip';
import { preprocessAssistantContent } from '@/components/assistant/assistantContent';
import { ChatSegment, hasToolCall, parseToolCalls } from '@/components/assistant/toolCallParse';
import { prettyModelName } from '@/components/assistant/modelName';
import { renderCard } from '@/components/assistant/inlineCards';
import { getShareableMessageIds } from '@/components/assistant/shareSelection';

interface ChatViewProps {
  messages: ChatMessage[];
  loading: boolean;
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
}

/** 长按计时: pointer 持续按住约 500ms 触发, 移动/松开/离开均取消. */
const LONG_PRESS_MS = 500;

const STYLE = {
  badgeClass: 'bg-teal-500/15 text-teal-300 ring-1 ring-teal-300/15',
  assistantTextClass: 'text-zinc-100',
  userBubbleClass: 'bg-[#2f2f2f] text-zinc-50',
};

export default function ChatView({
  messages,
  loading,
  doneMessageIds,
  messageFeedback,
  onFeedback,
  onPinMessage,
  shareSelectionMode = false,
  selectedMessageIds = new Set(),
  onToggleMessageSelection,
  onEnterSelectionWith,
  onShareMessages,
}: ChatViewProps) {
  // 允许空内容但是有卡片的消息显示
  const visibleMessages = messages.filter(m => !(m.role === 'assistant' && !m.content && !m.card_type));
  const shareableMessageIds = getShareableMessageIds(visibleMessages);

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
      {visibleMessages.map(msg => {
        const canSelectForShare = shareableMessageIds.has(msg.id);
        const selectedForShare = selectedMessageIds.has(msg.id);
        // 动态卡片消息 - 独立分支, 气泡外直接贴卡片
        if (msg.card_type && msg.card_data) {
          const cardEl = renderCard({ type: msg.card_type, data: msg.card_data });
          if (cardEl) {
            return (
              <div key={msg.id} className="flex gap-3 justify-start">
                <div className={`mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${STYLE.badgeClass}`}>
                  <Sparkles className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">{cardEl}</div>
              </div>
            );
          }
        }
        return (
        <div
          key={msg.id}
          className={`group flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'} ${shareSelectionMode && selectedForShare ? 'rounded-2xl bg-teal-400/[0.06] ring-1 ring-teal-300/20' : ''}`}
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
                  ? 'border-teal-300 bg-teal-400 text-zinc-950'
                  : canSelectForShare
                    ? 'border-white/15 bg-white/[0.04] text-transparent hover:border-teal-300/60'
                    : 'border-white/[0.06] bg-white/[0.02] text-transparent opacity-40'
              }`}
              aria-label={selectedForShare ? '取消选择这条消息' : '选择这条消息'}
            >
              <Check className="h-3.5 w-3.5" />
            </button>
          )}
          {msg.role === 'assistant' && (
            <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${STYLE.badgeClass}`}>
              <Sparkles className="h-4 w-4" />
            </div>
          )}
          {msg.role === 'user' && msg.created_at && (
            <span className="self-center select-none text-[11px] text-zinc-600 opacity-0 transition-opacity group-hover:opacity-100 shrink-0">
              {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}
            </span>
          )}
          <div className={`${msg.role === 'user' ? 'max-w-[min(80%,34rem)] rounded-[1.35rem] px-4 py-2.5 shadow-sm' : 'min-w-0 flex-1'} ${msg.role === 'user' ? STYLE.userBubbleClass : STYLE.assistantTextClass}`}>
            {msg.role === 'assistant' ? (
              <div>
                <div className="text-[15px] leading-7">
                  <AssistantBody content={msg.content} streaming={!doneMessageIds.has(msg.id)} />
                </div>
                {/* 元信息行: 模型友好名 + 数据来源. 耗时/轮数收进 hover tooltip. */}
                {doneMessageIds.has(msg.id) && (msg.model || msg.llm_usage || (msg.sources_used && msg.sources_used.length > 0)) && (
                  <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                    {prettyModelName(msg.model) && (
                      <span
                        className="text-[11px] text-zinc-600"
                        title={buildPerfTooltip(msg)}
                      >
                        {prettyModelName(msg.model)}
                      </span>
                    )}
                    {msg.llm_usage && (
                      <span
                        className="text-[11px] font-mono text-zinc-600"
                        title={buildTokenUsageTooltip(msg)}
                      >
                        {formatTokenUsage(msg.llm_usage)}
                      </span>
                    )}
                    {/* 2026-05-14 #4: 可解释性 chip — AI 用了什么数据 */}
                    {msg.sources_used && msg.sources_used.length > 0 && (
                      <SourcesChip sources={msg.sources_used} />
                    )}
                  </div>
                )}
              </div>
            ) : (
              <div>
                {msg.image_preview && <img src={msg.image_preview} alt="上传图片" className="mb-2 max-h-56 max-w-xs rounded-xl object-cover" />}
                {msg.file_name && (
                  <div className="mb-2 flex items-center gap-2 rounded-xl bg-white/15 px-3 py-1.5 text-sm">
                    <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}><path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>
                    <span className="truncate">{msg.file_name}</span>
                  </div>
                )}
                <div className="whitespace-pre-wrap text-[15px] leading-6">{msg.content}</div>
              </div>
            )}
          </div>
          {msg.role === 'assistant' && msg.created_at && (
            <span className="mb-1 ml-1 self-end select-none text-[11px] text-zinc-600 opacity-0 transition-opacity group-hover:opacity-100 shrink-0">
              {new Date(msg.created_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}
            </span>
          )}
          {msg.role === 'assistant' && msg.content && doneMessageIds.has(msg.id) && (
            <div className="ml-1 mt-1 flex items-center gap-0.5 self-end opacity-0 transition-opacity group-hover:opacity-100">
              <button onClick={() => navigator.clipboard?.writeText(msg.content)} className="rounded-lg p-1.5 text-zinc-500 transition-all hover:bg-white/5 hover:text-zinc-200" title="复制">
                <Copy className="h-3.5 w-3.5" />
              </button>
              {onShareMessages && (
                <button onClick={() => onShareMessages([msg.id])} className="rounded-lg p-1.5 text-zinc-500 transition-all hover:bg-white/5 hover:text-teal-300" title="分享这条">
                  <Share2 className="h-3.5 w-3.5" />
                </button>
              )}
              <button onClick={() => onFeedback(msg.id, 5)} className={`rounded-lg p-1.5 transition-all ${messageFeedback[msg.id] === 5 ? 'bg-teal-400/15 text-teal-300' : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-200'}`} title="helpful">
                <ThumbsUp className="h-3.5 w-3.5" />
              </button>
              <button onClick={() => onFeedback(msg.id, 1)} className={`rounded-lg p-1.5 transition-all ${messageFeedback[msg.id] === 1 ? 'bg-rose-400/15 text-rose-300' : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-200'}`} title="not helpful">
                <ThumbsDown className="h-3.5 w-3.5" />
              </button>
              {onPinMessage && (
                <button onClick={() => onPinMessage(msg.content, msg.id)} className="rounded-lg p-1.5 text-zinc-500 transition-all hover:bg-white/5 hover:text-amber-300" title="固化到首页">
                  <Bookmark className="h-3.5 w-3.5" />
                </button>
              )}
            </div>
          )}
        </div>
        );
      })}
      {loading && (
        <div className="flex gap-3">
          <div className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${STYLE.badgeClass}`}>
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="px-1 py-2.5">
            <div className="flex gap-1.5 rounded-full bg-[#2f2f2f] px-3 py-2">
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-300" style={{ animationDelay: '0ms' }} />
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-300" style={{ animationDelay: '150ms' }} />
              <div className="h-1.5 w-1.5 animate-bounce rounded-full bg-teal-300" style={{ animationDelay: '300ms' }} />
            </div>
          </div>
        </div>
      )}
    </div>
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
    return <MarkdownRenderer content={content} variant="dark" />;
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
            <MarkdownRenderer content={text} variant="dark" />
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

/** 把耗时/轮数收进 model 名的 hover tooltip, 默认不在 UI 上占位. */
function buildPerfTooltip(msg: ChatMessage): string {
  const parts: string[] = [];
  if (msg.elapsed_ms != null) parts.push(`耗时 ${(msg.elapsed_ms / 1000).toFixed(1)}s`);
  if (msg.llm_rounds != null && msg.llm_rounds > 1) parts.push(`${msg.llm_rounds} 轮`);
  return parts.length ? `本次回答的模型 · ${parts.join(' · ')}` : '本次回答的模型';
}

function formatTokenCount(value?: number | null): string {
  const n = typeof value === 'number' && Number.isFinite(value) ? value : 0;
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')}k`;
  return String(Math.max(0, Math.round(n)));
}

function formatTokenUsage(usage: NonNullable<ChatMessage['llm_usage']>): string {
  const calls = usage.calls && usage.calls > 1 ? ` · ${usage.calls}次` : '';
  return `Token 输入 ${formatTokenCount(usage.prompt_tokens)} · 输出 ${formatTokenCount(usage.completion_tokens)}${calls}`;
}

function buildTokenUsageTooltip(msg: ChatMessage): string {
  const usage = msg.llm_usage;
  if (!usage) return '';
  const lines = [
    `输入 ${formatTokenCount(usage.prompt_tokens)} · 输出 ${formatTokenCount(usage.completion_tokens)} · 总 ${formatTokenCount(usage.total_tokens)}`,
  ];
  if (usage.cost_usd && usage.cost_usd > 0) {
    lines.push(`估算成本 $${usage.cost_usd.toFixed(6)}`);
  }
  const items = Array.isArray(usage.items) ? usage.items : [];
  items.slice(0, 8).forEach((item, index) => {
    const latency = typeof item.latency_ms === 'number' ? ` · ${(item.latency_ms / 1000).toFixed(1)}s` : '';
    const model = item.model || item.provider || `调用 ${index + 1}`;
    lines.push(`${index + 1}. ${model}: 输入 ${formatTokenCount(item.prompt_tokens)} · 输出 ${formatTokenCount(item.completion_tokens)}${latency}`);
  });
  return lines.join('\n');
}

/** 2026-05-14 #4 可解释性 chip — 默认折叠 "🔍 AI 用了什么数据 (N)", 点开列出来. */
function SourcesChip({ sources }: { sources: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-zinc-500 transition-colors hover:border-teal-300/30 hover:text-teal-300"
        title="点击展开 / 折叠"
      >
        <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        AI 用了 {sources.length} 项数据
        <svg className={`h-3 w-3 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <ul className="mt-1.5 ml-3 space-y-0.5 text-[11px] text-zinc-500">
          {sources.map((s, i) => (
            <li key={i} className="flex items-start gap-1.5">
              <span className="shrink-0 text-teal-400/60">·</span>
              <span>{s}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
