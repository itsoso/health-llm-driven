'use client';

/**
 * SpecialistsPanel —— 所有 specialist 的前端出口。
 *
 * 一次请求 POST /api/orchestrator/chat，展示 Recovery Coach / Fuel Strategist /
 * Movement Coach / Mental Health Companion / Chronic Specialists 的结构化输出。
 *
 * 展示策略：
 * - 顶部摘要卡 + 刷新按钮
 * - 每个 specialist 一张卡片，显示 summary + 可展开 findings
 * - 不做 LLM 合成（那是 SafetyPanel 的"AI 综合分析"职责）
 */

import { useCallback, useEffect, useState } from 'react';
import { runOrchestrator, OrchestratorFinding } from '@/services/api/orchestrator';

// ─── 类别元数据 ─────────────────────────

const CATEGORY_META: Record<string, { label: string; color: string; bg: string; icon: string }> = {
  safety: { label: '安全', color: '#dc2626', bg: '#fef2f2', icon: '🛡️' },
  recovery: { label: '恢复', color: '#0891b2', bg: '#ecfeff', icon: '🌙' },
  fuel: { label: '营养', color: '#16a34a', bg: '#f0fdf4', icon: '🍎' },
  movement: { label: '运动', color: '#9333ea', bg: '#faf5ff', icon: '💪' },
  mental: { label: '心理', color: '#db2777', bg: '#fdf2f8', icon: '🧠' },
  chronic: { label: '慢病', color: '#ea580c', bg: '#fff7ed', icon: '📋' },
};

const SPECIALIST_TITLE: Record<string, string> = {
  safety_guardian: '安全哨兵',
  recovery_coach: '恢复教练',
  fuel_strategist: '营养策略师',
  movement_coach: '运动教练',
  mental_health_companion: '心理陪伴',
  hypertension_specialist: '高血压管理',
  metabolic_specialist: '代谢管理',
  rhinitis_specialist: '鼻炎管理',
};

// ─── 单个 specialist 卡 ────────────────

function SpecialistCard({ finding }: { finding: OrchestratorFinding }) {
  const [expanded, setExpanded] = useState(false);
  const meta = CATEGORY_META[finding.category] || CATEGORY_META.chronic;
  const title = SPECIALIST_TITLE[finding.specialist_name] || finding.specialist_name;

  return (
    <div
      className="rounded-2xl px-4 py-3"
      style={{ background: meta.bg, border: `1px solid ${meta.color}30` }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start gap-3 text-left active:opacity-70"
      >
        <span className="text-base shrink-0 mt-0.5">{meta.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span
              className="text-[10px] font-bold px-1.5 py-0.5 rounded"
              style={{ background: meta.color, color: 'white' }}
            >
              {meta.label}
            </span>
            <span className="text-xs font-semibold" style={{ color: '#0f172a' }}>
              {title}
            </span>
            {finding.ms_elapsed > 0 && (
              <span className="text-[10px]" style={{ color: '#94a3b8' }}>
                {finding.ms_elapsed}ms
              </span>
            )}
          </div>
          <div className="mt-1 text-xs" style={{ color: meta.color }}>
            {finding.summary || '(无输出)'}
          </div>
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

      {expanded && finding.findings.length > 0 && (
        <div className="mt-3 pl-7 space-y-2">
          {finding.findings.map((item, idx) => (
            <FindingItem key={idx} item={item} accentColor={meta.color} />
          ))}
        </div>
      )}
    </div>
  );
}

function FindingItem({ item, accentColor }: { item: Record<string, any>; accentColor: string }) {
  const type = item.type || 'unknown';

  // Action 类型：突出显示文字
  if (type === 'action' || type === 'support_action') {
    return (
      <div className="text-xs leading-relaxed pl-2 py-1" style={{ borderLeft: `2px solid ${accentColor}` }}>
        <span className="font-semibold" style={{ color: accentColor }}>
          {item.order ? `${item.order}. ` : '• '}
        </span>
        <span style={{ color: '#334155' }}>{item.text}</span>
      </div>
    );
  }

  // Readiness score 特殊渲染
  if (type === 'readiness_score') {
    return (
      <div className="rounded-lg px-3 py-2" style={{ background: 'white', border: `1px solid ${accentColor}20` }}>
        <div className="flex items-center gap-2">
          <span className="text-2xl font-bold" style={{ color: accentColor }}>
            {item.score}
          </span>
          <span className="text-[10px]" style={{ color: '#64748b' }}>
            / 100 · {item.zone}
          </span>
        </div>
        {item.components && (
          <div className="mt-2 text-[10px] flex flex-wrap gap-2" style={{ color: '#475569' }}>
            {Object.entries(item.components).map(([k, v]) => (
              <span key={k}>
                {k}: {typeof v === 'number' ? (v as number).toFixed(2) : String(v)}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Energy / protein / hydration: 进度条
  if (type === 'energy' || type === 'protein' || type === 'hydration') {
    const progress = (item.progress_pct ?? 0) as number;
    return (
      <div className="rounded-lg px-3 py-2" style={{ background: 'white', border: `1px solid ${accentColor}20` }}>
        <div className="flex items-center justify-between text-[11px]">
          <span style={{ color: '#475569' }}>
            {type === 'energy' && '热量'}
            {type === 'protein' && '蛋白'}
            {type === 'hydration' && '饮水'}
          </span>
          <span style={{ color: accentColor }}>
            {type === 'energy' && `${item.intake_kcal}/${item.tdee_kcal} kcal`}
            {type === 'protein' && `${item.today_g}/${item.target_g} g`}
            {type === 'hydration' && `${item.ml_today}/${item.goal_ml} ml`}
          </span>
        </div>
        <div className="mt-1 h-1 rounded-full" style={{ background: '#e2e8f0' }}>
          <div
            className="h-full rounded-full"
            style={{
              width: `${Math.min(100, progress)}%`,
              background: accentColor,
            }}
          />
        </div>
      </div>
    );
  }

  // Crisis warning: 大红框
  if (type === 'crisis_warning') {
    return (
      <div
        className="rounded-lg px-3 py-2 text-xs"
        style={{ background: '#fef2f2', border: '1px solid #fecaca', color: '#7f1d1d' }}
      >
        <div className="font-semibold mb-1">⚠️ {item.message}</div>
        {item.hotlines && (
          <div className="mt-1 space-y-0.5 text-[11px]">
            {item.hotlines.map((h: any, i: number) => (
              <div key={i}>
                • {h.name}: <span className="font-mono">{h.number}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // Training prescription
  if (type === 'today_prescription') {
    return (
      <div className="rounded-lg px-3 py-2" style={{ background: 'white', border: `1px solid ${accentColor}20` }}>
        <div className="flex items-center gap-2">
          <span
            className="text-[10px] font-bold px-1.5 py-0.5 rounded"
            style={{ background: accentColor, color: 'white' }}
          >
            {item.intensity}
          </span>
          <span className="text-[11px]" style={{ color: '#475569' }}>
            {item.guidance}
          </span>
        </div>
      </div>
    );
  }

  // 通用 fallback：key-value 列表
  return (
    <div className="text-[11px] space-y-0.5" style={{ color: '#475569' }}>
      {Object.entries(item).slice(0, 6).map(([k, v]) => {
        if (k === 'type') return null;
        const display = typeof v === 'object' ? JSON.stringify(v) : String(v);
        return (
          <div key={k}>
            <span style={{ color: '#94a3b8' }}>{k}:</span> {display.slice(0, 120)}
          </div>
        );
      })}
    </div>
  );
}

// ─── 主面板 ─────────────────────────────

export default function SpecialistsPanel({
  query = '综合分析我的健康状态并给出今日建议',
}: {
  query?: string;
}) {
  const [findings, setFindings] = useState<OrchestratorFinding[]>([]);
  const [usedSpecialists, setUsedSpecialists] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [twinBuildMs, setTwinBuildMs] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await runOrchestrator({ query, stream: false });
      // 过滤掉 safety_guardian（它已经在 SafetyPanel 独立展示）
      setFindings(res.findings.filter((f) => f.specialist_name !== 'safety_guardian'));
      setUsedSpecialists(res.used_specialists);
      setTwinBuildMs(res.twin_build_ms || 0);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '加载专家分析失败');
    } finally {
      setLoading(false);
    }
  }, [query]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && findings.length === 0) {
    return (
      <div className="rounded-2xl bg-white px-4 py-3 flex items-center gap-2" style={{ boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}>
        <span className="text-xs" style={{ color: '#94a3b8' }}>正在运行专家舰队…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="rounded-2xl px-4 py-3 flex items-center gap-2"
        style={{ background: '#fef2f2', border: '1px solid #fecaca' }}
      >
        <span className="text-xs" style={{ color: '#dc2626' }}>专家分析失败：{error}</span>
        <button onClick={load} className="ml-auto text-xs underline" style={{ color: '#dc2626' }}>
          重试
        </button>
      </div>
    );
  }

  if (findings.length === 0) {
    return null;  // 没有专家参与就不显示
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 px-1">
        <span className="text-[11px] font-semibold" style={{ color: '#0f172a' }}>
          专家舰队
        </span>
        <span className="text-[10px]" style={{ color: '#94a3b8' }}>
          · {usedSpecialists.length} 个专家参与 · Twin {twinBuildMs}ms
        </span>
        <button
          onClick={load}
          className="ml-auto text-[10px]"
          style={{ color: '#94a3b8' }}
          title="重新运行"
        >
          ↻
        </button>
      </div>

      {findings.map((f) => (
        <SpecialistCard key={f.specialist_name} finding={f} />
      ))}
    </div>
  );
}
