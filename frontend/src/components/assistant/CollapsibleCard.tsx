'use client';

import { useRef, useState, useCallback, useEffect } from 'react';

interface CollapsibleCardProps {
  cardId: string;
  label: string;
  collapsed: boolean;
  onToggle: (cardId: string, next: boolean) => void;
  children: React.ReactNode;
  /** 上滑阈值（像素），超过则收起 */
  threshold?: number;
}

/**
 * 可折叠卡片：支持手指上滑收起 / 点击恢复展开
 * - 上滑距离超过 threshold（默认 60px）→ 收起
 * - 收起态显示标题胶囊，点击整行 → 展开
 * - 只在触摸设备上生效（桌面端忽略，避免误操作）
 */
export default function CollapsibleCard({
  cardId,
  label,
  collapsed,
  onToggle,
  children,
  threshold = 60,
}: CollapsibleCardProps) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const startYRef = useRef<number | null>(null);
  const startXRef = useRef<number | null>(null);
  const activeRef = useRef(false);
  const [dragY, setDragY] = useState(0);
  const [animating, setAnimating] = useState(false);

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    if (collapsed) return;
    const t = e.touches[0];
    startYRef.current = t.clientY;
    startXRef.current = t.clientX;
    activeRef.current = false; // 只有确认是上滑手势后才拦截
    setAnimating(false);
  }, [collapsed]);

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    if (collapsed || startYRef.current == null || startXRef.current == null) return;
    const t = e.touches[0];
    const dy = t.clientY - startYRef.current;
    const dx = t.clientX - startXRef.current;

    // 确认是上滑（dy<0 且竖直主导）后才激活手势，避免干扰横滑/点击
    if (!activeRef.current) {
      if (dy < -8 && Math.abs(dy) > Math.abs(dx) * 1.2) {
        activeRef.current = true;
      } else if (Math.abs(dx) > 8 || dy > 8) {
        // 明显不是上滑 → 放弃
        startYRef.current = null;
        startXRef.current = null;
        return;
      } else {
        return;
      }
    }

    if (dy < 0) {
      setDragY(Math.max(dy, -120)); // 上滑负值，最多 -120
    } else {
      setDragY(0);
    }
  }, [collapsed]);

  const onTouchEnd = useCallback(() => {
    if (collapsed) return;
    const wasActive = activeRef.current;
    const dy = dragY;
    startYRef.current = null;
    startXRef.current = null;
    activeRef.current = false;
    setAnimating(true);
    setDragY(0);
    if (wasActive && dy < -threshold) {
      onToggle(cardId, true);
    }
  }, [cardId, collapsed, dragY, onToggle, threshold]);

  // 收起态点击 → 展开
  const handleExpand = useCallback(() => {
    onToggle(cardId, false);
  }, [cardId, onToggle]);

  // 动画结束后复位
  useEffect(() => {
    if (!animating) return;
    const t = setTimeout(() => setAnimating(false), 220);
    return () => clearTimeout(t);
  }, [animating]);

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={handleExpand}
        className="w-full flex items-center justify-between rounded-2xl bg-white/80 px-4 py-2.5 text-left shadow-sm border border-gray-100 transition-all active:scale-[0.98]"
      >
        <span className="text-xs font-medium text-gray-500 flex items-center gap-2">
          <span className="inline-block w-1 h-3 rounded-full bg-gray-300" />
          {label}
        </span>
        <span className="text-[11px] text-gray-400 flex items-center gap-1">
          展开
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
          </svg>
        </span>
      </button>
    );
  }

  const opacity = dragY < 0 ? Math.max(0.55, 1 + dragY / 240) : 1;

  return (
    <div
      ref={wrapRef}
      onTouchStart={onTouchStart}
      onTouchMove={onTouchMove}
      onTouchEnd={onTouchEnd}
      onTouchCancel={onTouchEnd}
      style={{
        transform: dragY < 0 ? `translateY(${dragY}px)` : undefined,
        opacity,
        transition: animating ? 'transform 220ms ease, opacity 220ms ease' : undefined,
        touchAction: 'pan-y',
      }}
    >
      {children}
    </div>
  );
}
