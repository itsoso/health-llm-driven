'use client';

/**
 * SafetyPanel —— Phase 1.5 Safety Guardian 的前端出口。
 *
 * 展示 /api/safety/me 返回的告警，按严重度排序，支持展开/折叠详细信息
 * 和对每条告警请求 LLM 个性化解读。
 *
 * 设计要点：
 * - 严重度颜色映射遵循标准交通灯语义
 * - 默认只展示前 3 条；点 "查看全部" 展开
 * - requires_medical_attention 单独高亮
 * - "详细解读" 是可选的 LLM 调用，按需付费
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  explainSafetyAlert,
  getSafetyReport,
  SafetyAlert,
  SafetyReport,
} from '@/services/api/safety';

// ─────────────────────── 颜色映射 ───────────────────────────

const SEVERITY_STYLE: Record<number, { fg: string; bg: string; border: string; icon: string }> = {
  4: { fg: '#dc2626', bg: '#fef2f2', border: '#fecaca', icon: '🚨' }, // CRITICAL
  3: { fg: '#ea580c', bg: '#fff7ed', border: '#fed7aa', icon: '⚠️' }, // HIGH
  2: { fg: '#d97706', bg: '#fffbeb', border: '#fde68a', icon: '⚠' },  // MEDIUM
  1: { fg: '#2563eb', bg: '#eff6ff', border: '#bfdbfe', icon: 'ℹ️' }, // LOW
  0: { fg: '#64748b', bg: '#f8fafc', border: '#e2e8f0', icon: '•' },  // INFO
};

const CATEGORY_LABEL: Record<string, string> = {
  vitals: '生命体征',
  labs: '化验指标',
  ddi: '药物相互作用',
  dsi: '药物-补剂',
  pgx: '药物基因',
  training_load: '训练负荷',
};

// ─────────────────────── 单条卡片 ───────────────────────────

interface AlertCardProps {
  alert: SafetyAlert;
  expanded: boolean;
  onToggle: () => void;
}

function AlertCard({ alert, expanded, onToggle }: AlertCardProps) {
  const style = SEVERITY_STYLE[alert.severity.value] || SEVERITY_STYLE[0];
  const [explanation, setExplanation] = useState<string | null>(null);
  const [explaining, setExplaining] = useState(false);
  const [explainError, setExplainError] = useState<string | null>(null);

  const handleExplain = async () => {
    if (explaining || explanation) return;
    setExplaining(true);
    setExplainError(null);
    try {
      const res = await explainSafetyAlert(alert.rule_id, {
        data_citation: alert.data_citation,
        message: alert.message,
      });
      setExplanation(res.explanation);
    } catch (e: any) {
      setExplainError(e?.response?.data?.detail || e?.message || '解读失败');
    } finally {
      setExplaining(false);
    }
  };

  return (
    <div
      className="rounded-2xl px-4 py-3 transition-all"
      style={{
        background: style.bg,
        border: `1px solid ${style.border}`,
      }}
    >
      {/* 头部：严重度 + 标题 + 展开箭头 */}
      <button
        onClick={onToggle}
        className="w-full flex items-start gap-3 text-left active:opacity-70"
      >
        <span className="text-base shrink-0 mt-0.5">{style.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className="text-[10px] font-bold px-1.5 py-0.5 rounded"
              style={{ background: style.fg, color: 'white' }}
            >
              {alert.severity.label_zh}
            </span>
            <span className="text-[10px] font-medium" style={{ color: '#64748b' }}>
              {CATEGORY_LABEL[alert.category] || alert.category}
            </span>
            {alert.requires_medical_attention && (
              <span
                className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                style={{ background: '#dc2626', color: 'white' }}
              >
                建议就医
              </span>
            )}
          </div>
          <div
            className="mt-1 text-sm font-semibold"
            style={{ color: style.fg }}
          >
            {alert.title}
          </div>
          {!expanded && (
            <div
              className="mt-0.5 text-xs line-clamp-1"
              style={{ color: '#475569' }}
            >
              {alert.message}
            </div>
          )}
        </div>
        <span
          className="shrink-0 text-xs mt-1"
          style={{ color: '#94a3b8', transform: expanded ? 'rotate(90deg)' : 'none' }}
        >
          ›
        </span>
      </button>

      {expanded && (
        <div className="mt-3 space-y-2 pl-7">
          <div className="text-xs leading-relaxed" style={{ color: '#334155' }}>
            {alert.message}
          </div>
          {alert.action && (
            <div
              className="text-xs leading-relaxed rounded-lg px-3 py-2"
              style={{ background: 'white', color: '#0f172a', border: `1px solid ${style.border}` }}
            >
              <span className="font-semibold" style={{ color: style.fg }}>建议动作：</span>
              {alert.action}
            </div>
          )}

          {/* 详细解读 */}
          <div>
            {explanation ? (
              <div
                className="text-xs leading-relaxed rounded-lg px-3 py-2 whitespace-pre-wrap"
                style={{ background: 'white', color: '#334155', border: `1px solid ${style.border}` }}
              >
                <div className="font-semibold mb-1" style={{ color: style.fg }}>个性化解读</div>
                {explanation}
              </div>
            ) : (
              <button
                onClick={handleExplain}
                disabled={explaining}
                className="text-[11px] font-medium px-3 py-1 rounded-full active:scale-95 transition-all"
                style={{
                  background: 'white',
                  color: style.fg,
                  border: `1px solid ${style.border}`,
                  opacity: explaining ? 0.6 : 1,
                }}
              >
                {explaining ? '生成中…' : '详细解读'}
              </button>
            )}
            {explainError && (
              <div className="mt-1 text-[11px]" style={{ color: '#dc2626' }}>
                {explainError}
              </div>
            )}
          </div>

          {/* 数据溯源 */}
          {Object.keys(alert.data_citation || {}).length > 0 && (
            <details className="text-[10px]" style={{ color: '#94a3b8' }}>
              <summary className="cursor-pointer">数据来源</summary>
              <pre
                className="mt-1 rounded px-2 py-1 overflow-x-auto"
                style={{ background: 'white', color: '#64748b' }}
              >
                {JSON.stringify(alert.data_citation, null, 2)}
              </pre>
            </details>
          )}

          {/* 文献 */}
          {alert.references && alert.references.length > 0 && (
            <div className="text-[10px]" style={{ color: '#94a3b8' }}>
              参考:
              {alert.references.map((ref, i) => (
                <a
                  key={i}
                  href={ref}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="ml-1 underline"
                  style={{ color: '#3b82f6' }}
                >
                  [{i + 1}]
                </a>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─────────────────────── 主面板 ───────────────────────────

export default function SafetyPanel() {
  const [report, setReport] = useState<SafetyReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getSafetyReport();
      setReport(data);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '加载安全报告失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const visibleAlerts = useMemo(() => {
    if (!report) return [];
    return showAll ? report.alerts : report.alerts.slice(0, 3);
  }, [report, showAll]);

  // 不展示的情况：加载中第一次、出错、空告警
  if (loading && !report) {
    return (
      <div className="rounded-2xl bg-white px-4 py-3 flex items-center gap-2" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <span className="text-xs" style={{ color: '#94a3b8' }}>正在检查安全告警…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="rounded-2xl px-4 py-3 flex items-center gap-2"
        style={{ background: '#fef2f2', border: '1px solid #fecaca' }}
      >
        <span className="text-xs" style={{ color: '#dc2626' }}>安全告警加载失败：{error}</span>
        <button
          onClick={loadReport}
          className="ml-auto text-xs underline"
          style={{ color: '#dc2626' }}
        >
          重试
        </button>
      </div>
    );
  }

  if (!report || report.alerts.length === 0) {
    return (
      <div
        className="rounded-2xl px-4 py-3 flex items-center gap-2"
        style={{ background: '#f0fdf4', border: '1px solid #bbf7d0' }}
      >
        <span className="text-base">✓</span>
        <span className="text-xs font-medium" style={{ color: '#16a34a' }}>
          当前无安全告警（已评估 {report?.summary.rules_evaluated ?? 0} 条规则）
        </span>
      </div>
    );
  }

  const { summary } = report;
  const criticalCount = summary.critical;
  const highCount = summary.high;

  return (
    <div className="space-y-2">
      {/* 摘要条 */}
      <div className="flex items-center gap-2 px-1">
        <span className="text-[11px] font-semibold" style={{ color: '#0f172a' }}>
          安全检查
        </span>
        {criticalCount > 0 && (
          <span
            className="text-[10px] font-bold px-1.5 py-0.5 rounded"
            style={{ background: '#dc2626', color: 'white' }}
          >
            {criticalCount} 紧急
          </span>
        )}
        {highCount > 0 && (
          <span
            className="text-[10px] font-bold px-1.5 py-0.5 rounded"
            style={{ background: '#ea580c', color: 'white' }}
          >
            {highCount} 警告
          </span>
        )}
        <span className="text-[10px]" style={{ color: '#94a3b8' }}>
          · 共 {summary.total} 条 / {summary.rules_evaluated} 规则
        </span>
        <button
          onClick={loadReport}
          className="ml-auto text-[10px]"
          style={{ color: '#94a3b8' }}
          title="重新评估"
        >
          ↻
        </button>
      </div>

      {/* 告警卡片列表 */}
      {visibleAlerts.map((alert) => (
        <AlertCard
          key={alert.rule_id}
          alert={alert}
          expanded={expandedId === alert.rule_id}
          onToggle={() => setExpandedId(expandedId === alert.rule_id ? null : alert.rule_id)}
        />
      ))}

      {/* 查看全部 */}
      {report.alerts.length > 3 && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="w-full text-xs py-2 rounded-xl"
          style={{ color: '#64748b', background: '#f1f5f9' }}
        >
          查看全部 {report.alerts.length} 条告警
        </button>
      )}
      {showAll && report.alerts.length > 3 && (
        <button
          onClick={() => setShowAll(false)}
          className="w-full text-xs py-2 rounded-xl"
          style={{ color: '#64748b', background: '#f1f5f9' }}
        >
          收起
        </button>
      )}
    </div>
  );
}
