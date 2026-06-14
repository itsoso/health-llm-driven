'use client';

import { Search, Wrench } from 'lucide-react';
import { toolCallLabel } from '@/components/assistant/toolCallParse';

/**
 * ToolCallChip — 把模型吐在正文里的 [tool_call: ...] 渲染成优雅的内联 pill.
 *
 * 只展示一个小图标 + 人话动作词 (查询健康数据 / 检索知识库 ...), 不显示
 * 原始 args / JSON. 检索类工具用放大镜, 其余用扳手. 流式进行中 (pulse=true)
 * 时图标轻微 pulse.
 *
 * 多个连续 chip 由 ChatView 合并成一行 (flex-wrap), 这里只管单个 pill.
 */
export default function ToolCallChip({ name, pulse }: { name: string; pulse?: boolean }) {
  const label = toolCallLabel(name);
  const isSearch = /检索|查询|搜索/.test(label) || /search|query|knowledge/.test(name.toLowerCase());
  const Icon = isSearch ? Search : Wrench;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.06] px-2.5 py-1 text-[12px] font-medium text-zinc-400 ring-1 ring-inset ring-white/[0.06]">
      <Icon className={`h-3 w-3 text-zinc-500 ${pulse ? 'animate-pulse' : ''}`} aria-hidden />
      {label}
    </span>
  );
}
