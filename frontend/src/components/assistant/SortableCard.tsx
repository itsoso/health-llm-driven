'use client';

/**
 * SortableCard — 拖拽包裹器。
 *
 * 包裹每张首页卡片，提供：
 * - 左侧拖动手柄（六点图标，长按拖拽）
 * - 拖拽时半透明视觉反馈
 * - 可选的隐藏按钮（右上角眼睛图标）
 */

import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { ReactNode } from 'react';

interface SortableCardProps {
  id: string;
  children: ReactNode;
  onHide?: (id: string) => void;
  editMode?: boolean; // 编辑模式下才显示拖柄和隐藏按钮
}

export default function SortableCard({ id, children, onHide, editMode }: SortableCardProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    position: 'relative' as const,
  };

  if (!editMode) {
    // 非编辑模式直接渲染，无拖拽开销
    return <>{children}</>;
  }

  return (
    <div ref={setNodeRef} style={style}>
      {/* 编辑模式下的装饰边框 */}
      <div
        className="rounded-2xl"
        style={{
          border: '2px dashed #c4b5fd',
          padding: '2px',
        }}
      >
        {/* 拖柄 + 隐藏按钮 */}
        <div className="flex items-center justify-between px-3 py-1.5 rounded-t-xl"
          style={{ background: '#f5f3ff' }}>
          {/* 拖柄 */}
          <button
            {...attributes}
            {...listeners}
            className="flex items-center gap-1.5 text-[10px] font-medium cursor-grab active:cursor-grabbing"
            style={{ color: '#7c3aed', touchAction: 'none' }}
            title="拖拽排序"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
              <circle cx="9" cy="6" r="1.5" />
              <circle cx="15" cy="6" r="1.5" />
              <circle cx="9" cy="12" r="1.5" />
              <circle cx="15" cy="12" r="1.5" />
              <circle cx="9" cy="18" r="1.5" />
              <circle cx="15" cy="18" r="1.5" />
            </svg>
            拖拽排序
          </button>

          {/* 隐藏按钮 */}
          {onHide && (
            <button
              onClick={() => onHide(id)}
              className="text-[10px] font-medium px-2 py-0.5 rounded-full active:scale-95 transition-all"
              style={{ color: '#94a3b8', background: 'white', border: '1px solid #e2e8f0' }}
              title="隐藏此卡片"
            >
              隐藏
            </button>
          )}
        </div>

        {children}
      </div>
    </div>
  );
}
