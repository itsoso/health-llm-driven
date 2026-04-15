'use client';

/**
 * ActionCardPanel —— 对话固化的行动卡片面板。
 *
 * 从 /api/action-cards/me 加载活跃卡片，显示在智能助理首页。
 * 支持展开/折叠、标记完成、归档。
 */

import { useCallback, useEffect, useState } from 'react';
import {
  ActionCard,
  archiveActionCard,
  getMyActionCards,
  updateActionCard,
} from '@/services/api/actionCard';

const TYPE_STYLE: Record<string, { bg: string; border: string; fg: string; icon: string }> = {
  guide: { bg: '#f0fdfa', border: '#99f6e4', fg: '#0d9488', icon: '📖' },
  plan: { bg: '#faf5ff', border: '#e9d5ff', fg: '#7c3aed', icon: '📋' },
  insight: { bg: '#eff6ff', border: '#bfdbfe', fg: '#2563eb', icon: '💡' },
  recommendation: { bg: '#f0fdf4', border: '#bbf7d0', fg: '#16a34a', icon: '✅' },
  note: { bg: '#f8fafc', border: '#e2e8f0', fg: '#475569', icon: '📝' },
};

function CardItem({
  card,
  expanded,
  onToggle,
  onComplete,
  onArchive,
}: {
  card: ActionCard;
  expanded: boolean;
  onToggle: () => void;
  onComplete: () => void;
  onArchive: () => void;
}) {
  const style = TYPE_STYLE[card.card_type] || TYPE_STYLE.note;

  return (
    <div
      className="rounded-2xl px-4 py-3 transition-all"
      style={{ background: style.bg, border: `1px solid ${style.border}` }}
    >
      <button
        onClick={onToggle}
        className="w-full flex items-start gap-3 text-left active:opacity-70"
      >
        <span className="text-base shrink-0 mt-0.5">{style.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold" style={{ color: style.fg }}>
              {card.title}
            </span>
            {card.status === 'completed' && (
              <span
                className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                style={{ background: '#16a34a', color: 'white' }}
              >
                已完成
              </span>
            )}
          </div>
          {!expanded && (
            <div className="mt-0.5 text-[11px] line-clamp-2" style={{ color: '#475569' }}>
              {card.content.replace(/[#*`>-]/g, '').slice(0, 100)}
            </div>
          )}
        </div>
        <span
          className="shrink-0 text-xs mt-1"
          style={{
            color: '#94a3b8',
            transform: expanded ? 'rotate(90deg)' : 'none',
            transition: 'transform 150ms',
          }}
        >
          ›
        </span>
      </button>

      {expanded && (
        <div className="mt-3 pl-7 space-y-3">
          {/* Markdown 内容 */}
          <div
            className="text-xs leading-relaxed prose prose-sm max-w-none"
            style={{ color: '#334155' }}
            dangerouslySetInnerHTML={{ __html: simpleMarkdown(card.content) }}
          />

          {/* 操作按钮 */}
          <div className="flex gap-2">
            {card.status === 'active' && (
              <button
                onClick={(e) => { e.stopPropagation(); onComplete(); }}
                className="text-[11px] font-medium px-3 py-1 rounded-full active:scale-95 transition-all"
                style={{ background: '#16a34a', color: 'white' }}
              >
                标记完成
              </button>
            )}
            <button
              onClick={(e) => { e.stopPropagation(); onArchive(); }}
              className="text-[11px] font-medium px-3 py-1 rounded-full active:scale-95 transition-all"
              style={{ background: '#f1f5f9', color: '#64748b' }}
            >
              归档
            </button>
            {card.created_at && (
              <span className="ml-auto text-[10px] self-center" style={{ color: '#94a3b8' }}>
                {new Date(card.created_at).toLocaleDateString('zh-CN')}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// 极简 markdown → HTML（不引入重依赖）
function simpleMarkdown(md: string): string {
  // 先处理表格（在 HTML 转义之前提取）
  const lines = md.split('\n');
  const result: string[] = [];
  let inTable = false;
  let tableRows: string[] = [];

  const flushTable = () => {
    if (tableRows.length < 2) {
      result.push(...tableRows);
    } else {
      let html = '<table class="w-full text-[11px] my-2 border-collapse">';
      tableRows.forEach((row, i) => {
        // 跳过分隔行 |---|---|
        if (/^\|[\s\-:]+\|/.test(row)) return;
        const cells = row.split('|').filter(c => c.trim() !== '');
        const tag = i === 0 ? 'th' : 'td';
        const style = i === 0
          ? 'class="text-left font-semibold py-1 px-2 border-b border-gray-200 bg-gray-50"'
          : 'class="py-1 px-2 border-b border-gray-100"';
        html += '<tr>' + cells.map(c => `<${tag} ${style}>${c.trim()}</${tag}>`).join('') + '</tr>';
      });
      html += '</table>';
      result.push(html);
    }
    tableRows = [];
    inTable = false;
  };

  for (const line of lines) {
    if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
      inTable = true;
      tableRows.push(line);
    } else {
      if (inTable) flushTable();
      result.push(line);
    }
  }
  if (inTable) flushTable();

  return result.join('\n')
    .replace(/^### (.+)$/gm, '<h4 class="font-semibold mt-2 mb-1">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="font-semibold text-sm mt-3 mb-1">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="font-bold text-sm mt-3 mb-1">$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code class="bg-gray-100 px-1 rounded text-[11px]">$1</code>')
    .replace(/^- (.+)$/gm, '<li class="ml-3 list-disc list-inside">$1</li>')
    .replace(/^\d+\.\s+(.+)$/gm, '<li class="ml-3">$1</li>')
    .replace(/(?<!\n)\n(?!\n|<)/g, '<br/>')
    .replace(/\n\n+/g, '<br/><br/>');
}

export default function ActionCardPanel() {
  const [cards, setCards] = useState<ActionCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getMyActionCards('active', 10);
      setCards(data);
    } catch (e) {
      console.error('加载行动卡片失败', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleComplete = async (id: number) => {
    try {
      await updateActionCard(id, { status: 'completed' });
      setCards((prev) => prev.map((c) => (c.id === id ? { ...c, status: 'completed' as const } : c)));
    } catch (e) {
      console.error('更新失败', e);
    }
  };

  const handleArchive = async (id: number) => {
    try {
      await archiveActionCard(id);
      setCards((prev) => prev.filter((c) => c.id !== id));
    } catch (e) {
      console.error('归档失败', e);
    }
  };

  if (loading && cards.length === 0) return null;
  if (cards.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-1">
        <span className="text-[11px] font-semibold" style={{ color: '#0f172a' }}>
          行动卡片
        </span>
        <span className="text-[10px]" style={{ color: '#94a3b8' }}>
          · {cards.filter((c) => c.status === 'active').length} 个进行中
        </span>
        <button onClick={load} className="ml-auto text-[10px]" style={{ color: '#94a3b8' }} title="刷新">
          ↻
        </button>
      </div>

      {cards.map((card) => (
        <CardItem
          key={card.id}
          card={card}
          expanded={expandedId === card.id}
          onToggle={() => setExpandedId(expandedId === card.id ? null : card.id)}
          onComplete={() => handleComplete(card.id)}
          onArchive={() => handleArchive(card.id)}
        />
      ))}
    </div>
  );
}
