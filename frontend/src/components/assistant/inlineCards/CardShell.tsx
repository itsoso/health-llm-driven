'use client';
import React from 'react';

interface CardShellProps {
  emoji: string;
  title: string;
  badge?: string;
  badgeColor?: string;
  onClick?: () => void;
  bg?: string;
  border?: string;
  children: React.ReactNode;
}

/** 统一卡片容器 - 圆角 + 浅色背景 + 小投影; 暗色气泡里也清晰 */
export function CardShell({
  emoji, title, badge, badgeColor = '#30D158',
  onClick, bg = '#F8FFFE', border = '#E5E5EA', children,
}: CardShellProps) {
  const Inner = (
    <div className="rounded-2xl px-4 py-3 my-2 min-w-[240px] md:min-w-[280px] shadow-sm"
         style={{ background: bg, border: `1px solid ${border}` }}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-sm">{emoji}</span>
        <span className="text-xs font-semibold text-slate-700">{title}</span>
        {badge && (
          <span className="ml-auto px-1.5 py-0.5 rounded-lg text-[10px] font-bold text-white"
                style={{ background: badgeColor }}>
            {badge}
          </span>
        )}
        {onClick && (
          <svg className="w-3.5 h-3.5 text-slate-300 ml-1" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
          </svg>
        )}
      </div>
      {children}
    </div>
  );
  if (onClick) {
    return <button type="button" onClick={onClick} className="block w-full text-left active:scale-[0.99] transition-transform">{Inner}</button>;
  }
  return Inner;
}
