'use client';

import { useEffect, useRef, useState } from 'react';
import { Brain, Check, ChevronDown, Loader2 } from 'lucide-react';

export interface ModelOption {
  id: string;
  label: string;
  provider: string;
  model: string;
  speed_tier: 'fast' | 'balanced' | 'reasoning' | string;
  note?: string;
}

const TIER_LABEL: Record<string, string> = {
  fast: '快',
  balanced: '均衡',
  reasoning: '推理',
};

const TIER_STYLE: Record<string, string> = {
  fast: 'bg-emerald-400/10 text-emerald-300',
  balanced: 'bg-sky-400/10 text-sky-300',
  reasoning: 'bg-violet-400/10 text-violet-300',
};

export default function LlmModelPicker({
  currentLabel,
  currentModelId,
  options,
  savingModelId,
  disabled,
  error,
  onSelect,
}: {
  currentLabel: string;
  currentModelId: string | null;
  options: ModelOption[];
  savingModelId: string | null;
  disabled?: boolean;
  error?: string | null;
  onSelect: (modelId: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handlePointerDown);
    return () => document.removeEventListener('mousedown', handlePointerDown);
  }, [open]);

  const selectModel = (modelId: string | null) => {
    setOpen(false);
    onSelect(modelId);
  };

  return (
    <div ref={rootRef} className="relative z-[80] min-w-0">
      <button
        type="button"
        aria-label={`当前模型 ${currentLabel}`}
        aria-expanded={open}
        onClick={() => setOpen(value => !value)}
        disabled={disabled}
        className="inline-flex min-w-0 items-center gap-2 rounded-xl px-2.5 py-2 text-sm font-medium text-zinc-200 transition-colors hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:opacity-60"
        title="切换当前对话使用的 AI 模型"
      >
        <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-teal-500/15 text-teal-300">
          <Brain className="h-3.5 w-3.5" />
        </span>
        <span className="truncate">健康 Agent</span>
        <span className="hidden max-w-[12rem] truncate text-xs font-normal text-zinc-500 sm:inline">
          {savingModelId ? '切换中...' : currentLabel}
        </span>
        {savingModelId ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-zinc-500" />
        ) : (
          <ChevronDown className={`h-3.5 w-3.5 shrink-0 text-zinc-500 transition-transform ${open ? 'rotate-180' : ''}`} />
        )}
      </button>

      {open && (
        <div
          data-testid="llm-model-picker-menu"
          className="absolute left-0 top-full z-[80] mt-2 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-white/10 bg-[#2b2b2b] p-2 shadow-2xl shadow-black/50"
        >
          <div className="px-2 pb-2 pt-1 text-xs text-zinc-500">本页直接切换，下一条消息立即生效</div>
          <button
            type="button"
            onClick={() => selectModel(null)}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors ${
              currentModelId === null ? 'bg-teal-500/10 text-teal-200' : 'text-zinc-200 hover:bg-white/[0.07]'
            }`}
          >
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">系统默认</span>
              <span className="block truncate text-xs text-zinc-500">使用管理员全局配置或服务器默认模型</span>
            </span>
            {currentModelId === null && <Check className="h-4 w-4 text-teal-300" />}
          </button>

          <div className="my-2 h-px bg-white/[0.08]" />

          <div className="max-h-80 overflow-y-auto">
            {options.length === 0 ? (
              <div className="rounded-xl border border-dashed border-white/10 px-3 py-6 text-center text-xs text-zinc-500">
                暂无可用模型
              </div>
            ) : (
              options.map(option => {
                const active = option.id === currentModelId;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => selectModel(option.id)}
                    className={`flex w-full items-start gap-2 rounded-xl px-3 py-2.5 text-left transition-colors ${
                      active ? 'bg-teal-500/10 text-teal-200' : 'text-zinc-200 hover:bg-white/[0.07]'
                    }`}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-sm font-medium">{option.label}</span>
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${TIER_STYLE[option.speed_tier] || 'bg-zinc-400/10 text-zinc-300'}`}>
                          {TIER_LABEL[option.speed_tier] || option.speed_tier}
                        </span>
                      </span>
                      <span className="mt-0.5 block truncate font-mono text-[11px] text-zinc-500">
                        {option.provider} · {option.model}
                      </span>
                      {option.note && (
                        <span className="mt-0.5 block line-clamp-2 text-xs text-zinc-500">{option.note}</span>
                      )}
                    </span>
                    {active && <Check className="mt-0.5 h-4 w-4 shrink-0 text-teal-300" />}
                  </button>
                );
              })
            )}
          </div>

          {error && (
            <div className="mt-2 rounded-xl border border-rose-400/20 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
