'use client';

/**
 * ActionCardPanel —— 对话固化的行动卡片面板。
 *
 * 从 /api/action-cards/me 加载活跃卡片，显示在智能助理首页。
 * 支持展开/折叠、标记完成、归档。
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  ActionCard,
  archiveActionCard,
  getMyActionCards,
  updateActionCard,
} from '@/services/api/actionCard';

interface TrustSummary {
  graded: number;
  hits: number;
  pending: number;
  bestSpecialist: string | null;
  bestRate: number;
}

function buildTrustSummary(cards: ActionCard[]): TrustSummary | null {
  const graded = cards.filter((c) => c.accuracy_score !== null && c.accuracy_score !== undefined && c.graded_at);
  const pending = cards.filter((c) => c.check_back_date && !c.graded_at).length;
  if (graded.length === 0 && pending === 0) return null;

  const hits = graded.filter((c) => (c.accuracy_score ?? 0) >= 70).length;

  const bySpec: Record<string, { total: number; hits: number }> = {};
  graded.forEach((c) => {
    const k = c.creator_specialist || 'unknown';
    if (!bySpec[k]) bySpec[k] = { total: 0, hits: 0 };
    bySpec[k].total++;
    if ((c.accuracy_score ?? 0) >= 70) bySpec[k].hits++;
  });
  const ranked = Object.entries(bySpec).sort(
    (a, b) => b[1].hits / b[1].total - a[1].hits / a[1].total
  );
  const [bestName, bestStats] = ranked[0] || [null, null];

  return {
    graded: graded.length,
    hits,
    pending,
    bestSpecialist: bestName,
    bestRate: bestStats ? Math.round((bestStats.hits / bestStats.total) * 100) : 0,
  };
}

const TYPE_STYLE: Record<string, { bg: string; border: string; fg: string; icon: string }> = {
  guide: { bg: '#f0fdfa', border: '#99f6e4', fg: '#0d9488', icon: '📖' },
  plan: { bg: '#faf5ff', border: '#e9d5ff', fg: '#7c3aed', icon: '📋' },
  insight: { bg: '#eff6ff', border: '#bfdbfe', fg: '#2563eb', icon: '💡' },
  recommendation: { bg: '#f0fdf4', border: '#bbf7d0', fg: '#16a34a', icon: '✅' },
  note: { bg: '#f8fafc', border: '#e2e8f0', fg: '#475569', icon: '📝' },
};

function TrustLoopBadge({ card }: { card: ActionCard }) {
  // 没启用信用循环 → 不渲染
  if (!card.metric_key || !card.target_value) return null;

  const graded = card.accuracy_score !== null && card.accuracy_score !== undefined && card.graded_at;
  const specialist = card.creator_specialist;

  // 已评分: 显示进度条 + 分数
  if (graded) {
    const score = card.accuracy_score!;
    const color = score >= 70 ? '#16a34a' : score >= 40 ? '#f59e0b' : '#dc2626';
    const label = score >= 70 ? '命中' : score >= 40 ? '部分' : '未达';
    return (
      <div className="mt-1.5 flex items-center gap-2 text-[10px]">
        {specialist && (
          <span className="px-1.5 py-0.5 rounded font-mono" style={{ background: '#f1f5f9', color: '#475569' }}>
            {specialist}
          </span>
        )}
        <span className="font-mono" style={{ color: '#64748b' }}>
          {card.baseline_value} → <strong>{card.actual_value}</strong> (目标 {card.target_value})
        </span>
        <span
          className="ml-auto px-1.5 py-0.5 rounded font-bold"
          style={{ background: color, color: 'white' }}
        >
          {label} {score}
        </span>
      </div>
    );
  }

  // 待复查: 显示倒计时
  if (card.check_back_date) {
    const days = Math.max(0, Math.ceil((new Date(card.check_back_date).getTime() - Date.now()) / 86400000));
    return (
      <div className="mt-1.5 flex items-center gap-2 text-[10px]" style={{ color: '#64748b' }}>
        {specialist && (
          <span className="px-1.5 py-0.5 rounded font-mono" style={{ background: '#f1f5f9' }}>
            {specialist}
          </span>
        )}
        <span className="font-mono">
          {card.baseline_value} → 目标 {card.target_value} ({card.metric_key})
        </span>
        <span className="ml-auto" style={{ color: days <= 1 ? '#dc2626' : '#64748b' }}>
          {days === 0 ? '今天评分' : `${days} 天后评分`}
        </span>
      </div>
    );
  }

  return null;
}

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
          <TrustLoopBadge card={card} />
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
          {/* 信用循环评分注释 */}
          {card.grading_notes && (
            <div
              className="text-[11px] px-3 py-2 rounded-lg border"
              style={{
                background: card.accuracy_score && card.accuracy_score >= 70 ? '#f0fdf4' : '#fef9c3',
                borderColor: card.accuracy_score && card.accuracy_score >= 70 ? '#bbf7d0' : '#fde68a',
                color: '#475569',
              }}
            >
              📊 <strong>评分:</strong> {card.grading_notes}
            </div>
          )}

          <SafeActionCardContent content={card.content} />

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

export function SafeActionCardContent({ content }: { content: string }) {
  return (
    <div className="text-xs leading-relaxed text-slate-700">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
          ul: ({ children }) => <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>,
          li: ({ children }) => <li className="leading-5">{children}</li>,
          h1: ({ children }) => <h2 className="mb-1 mt-3 text-sm font-bold text-slate-900">{children}</h2>,
          h2: ({ children }) => <h3 className="mb-1 mt-3 text-sm font-semibold text-slate-900">{children}</h3>,
          h3: ({ children }) => <h4 className="mb-1 mt-2 font-semibold text-slate-800">{children}</h4>,
          code: ({ children }) => <code className="rounded bg-slate-100 px-1 py-0.5 font-mono text-[11px]">{children}</code>,
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto">
              <table className="w-full border-collapse text-[11px]">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border-b border-slate-200 bg-slate-50 px-2 py-1 text-left font-semibold">{children}</th>,
          td: ({ children }) => <td className="border-b border-slate-100 px-2 py-1">{children}</td>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-emerald-700 underline">
              {children}
            </a>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default function ActionCardPanel() {
  const [cards, setCards] = useState<ActionCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      // 加载 active + 最近 graded 的, 信用面板才能显示历史命中率
      const [active, completed] = await Promise.all([
        getMyActionCards('active', 10),
        getMyActionCards('completed', 10).catch(() => []),
      ]);
      // 去重 (按 id), 取最多 15 张
      const seen = new Set<number>();
      const merged = [...active, ...completed].filter((c) => {
        if (seen.has(c.id)) return false;
        seen.add(c.id);
        return true;
      });
      setCards(merged.slice(0, 15));
    } catch (e) {
      console.error('加载行动卡片失败', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const trustSummary = useMemo(() => buildTrustSummary(cards), [cards]);

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

      {trustSummary && (
        <div
          className="rounded-xl px-3 py-2 text-[11px] flex items-center gap-3"
          style={{ background: '#fef3c7', border: '1px solid #fde68a', color: '#92400e' }}
        >
          <span>🎯 <strong>Specialist 信用</strong></span>
          {trustSummary.bestSpecialist ? (
            <span>
              最准: <code className="px-1 rounded bg-amber-200/50">{trustSummary.bestSpecialist}</code> {trustSummary.bestRate}%
            </span>
          ) : (
            <span style={{ color: '#a16207' }}>等待第一次评分</span>
          )}
          <span className="ml-auto">
            {trustSummary.graded > 0 && <>已评 {trustSummary.hits}/{trustSummary.graded}</>}
            {trustSummary.graded > 0 && trustSummary.pending > 0 && <> · </>}
            {trustSummary.pending > 0 && <>{trustSummary.pending} 张待评</>}
          </span>
        </div>
      )}

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
