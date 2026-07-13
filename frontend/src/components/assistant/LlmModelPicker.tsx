'use client';

import { useEffect, useRef, useState } from 'react';
import { Brain, Check, ChevronDown, Loader2 } from 'lucide-react';
import { canonicalModelId, sanitizeModelOptions } from './modelCatalog';

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
  fast: 'bg-[#E4EDDD] text-[#5B7B4E]',
  balanced: 'bg-[#E1EAF2] text-[#4A6B87]',
  reasoning: 'bg-[#ECE3F1] text-[#7A5E8A]',
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
  const visibleOptions = sanitizeModelOptions(options);
  const activeModelId = canonicalModelId(currentModelId);

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
    onSelect(canonicalModelId(modelId));
  };

  return (
    <div ref={rootRef} className="relative z-[80] min-w-0">
      <button
        type="button"
        aria-label={`当前模型 ${currentLabel}`}
        aria-expanded={open}
        onClick={() => setOpen(value => !value)}
        disabled={disabled}
        className="inline-flex min-w-0 items-center gap-1.5 rounded-full border border-[#D8D3C4] px-3 py-[5px] text-[12.5px] text-[#6B665A] transition-colors hover:border-[#C96442] disabled:cursor-not-allowed disabled:opacity-60"
        title="切换当前对话使用的 AI 模型"
      >
        <Brain className="h-3.5 w-3.5 shrink-0 text-[#948F80]" />
        <span className="max-w-[12rem] truncate font-medium text-[#29261F]">
          {savingModelId ? '切换中...' : currentLabel}
        </span>
        {savingModelId ? (
          <Loader2 className="h-3 w-3 shrink-0 animate-spin text-[#948F80]" />
        ) : (
          <ChevronDown className={`h-3 w-3 shrink-0 text-[#948F80] transition-transform ${open ? 'rotate-180' : ''}`} />
        )}
      </button>

      {open && (
        <div
          data-testid="llm-model-picker-menu"
          className="absolute left-0 top-full z-[80] mt-2 w-[min(22rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-[#E5E1D5] bg-[#FCFBF7] p-2 shadow-xl shadow-[#29261F]/12"
        >
          <div className="px-2 pb-2 pt-1 text-xs text-[#948F80]">本页直接切换，下一条消息立即生效</div>
          <button
            type="button"
            onClick={() => selectModel(null)}
            className={`flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left transition-colors ${
              activeModelId === null ? 'bg-[#F3E4DC] text-[#C96442]' : 'text-[#29261F] hover:bg-[#F0EDE4]'
            }`}
          >
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-medium">系统默认</span>
              <span className="block truncate text-xs text-[#948F80]">使用管理员全局配置或服务器默认模型</span>
            </span>
            {activeModelId === null && <Check className="h-4 w-4 text-[#C96442]" />}
          </button>

          <div className="my-2 h-px bg-[#E5E1D5]" />

          <div className="max-h-80 overflow-y-auto">
            {visibleOptions.length === 0 ? (
              <div className="rounded-xl border border-dashed border-[#D8D3C4] px-3 py-6 text-center text-xs text-[#948F80]">
                暂无可用模型
              </div>
            ) : (
              visibleOptions.map(option => {
                const active = option.id === activeModelId;
                return (
                  <button
                    key={option.id}
                    type="button"
                    onClick={() => selectModel(option.id)}
                    className={`flex w-full items-start gap-2 rounded-xl px-3 py-2.5 text-left transition-colors ${
                      active ? 'bg-[#F3E4DC] text-[#C96442]' : 'text-[#29261F] hover:bg-[#F0EDE4]'
                    }`}
                  >
                    <span className="min-w-0 flex-1">
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-sm font-medium">{option.label}</span>
                        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${TIER_STYLE[option.speed_tier] || 'bg-[#EAE6DA] text-[#6B665A]'}`}>
                          {TIER_LABEL[option.speed_tier] || option.speed_tier}
                        </span>
                      </span>
                      <span className="mt-0.5 block truncate font-mono text-[11px] text-[#948F80]">
                        {option.provider} · {option.model}
                      </span>
                      {option.note && (
                        <span className="mt-0.5 block line-clamp-2 text-xs text-[#948F80]">{option.note}</span>
                      )}
                    </span>
                    {active && <Check className="mt-0.5 h-4 w-4 shrink-0 text-[#C96442]" />}
                  </button>
                );
              })
            )}
          </div>

          {error && (
            <div className="mt-2 rounded-xl border border-[#E3B9AC] bg-[#F7E3DC] px-3 py-2 text-xs text-[#B4573A]">
              {error}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
