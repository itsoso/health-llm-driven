'use client';

interface InsightItem {
  id: number;
  notification_type: string;
  title: string;
  content: string;
  created_at: string;
}

const CONFIG: Record<string, { icon: string; color: string }> = {
  health_alert: { icon: '\u26A0', color: 'border-red-500/30 bg-red-500/10' },
  morning_summary: { icon: '\u2600', color: 'border-emerald-500/30 bg-emerald-500/10' },
  daily_insights: { icon: '\u2139', color: 'border-blue-500/30 bg-blue-500/10' },
  trend_report: { icon: '\u2191', color: 'border-cyan-500/30 bg-cyan-500/10' },
  family_daily_brief: { icon: '\u2764', color: 'border-purple-500/30 bg-purple-500/10' },
};

export default function InsightsCard({ insights, accentClass }: { insights: InsightItem[]; accentClass: string }) {
  const seen = new Set<string>();
  const unique = insights.filter(ins => {
    if (seen.has(ins.notification_type)) return false;
    seen.add(ins.notification_type);
    return true;
  });

  return (
    <div className="rounded-[30px] border border-white/10 bg-slate-950/60 p-5 shadow-[0_20px_60px_rgba(2,6,23,0.35)] backdrop-blur-xl">
      <div className={`text-[10px] uppercase tracking-[0.3em] ${accentClass}`}>{"today\u2019s insights"}</div>
      <div className="mt-3 space-y-3">
        {unique.map(ins => {
          const cfg = CONFIG[ins.notification_type] || { icon: '*', color: 'border-white/10 bg-white/5' };
          return (
            <div key={ins.id} className={`rounded-xl border p-3 ${cfg.color}`}>
              <div className="flex items-start gap-2">
                <span className="text-base shrink-0 w-5 text-center" aria-hidden="true">{cfg.icon}</span>
                <div className="min-w-0">
                  <div className="text-sm font-medium text-white">{ins.title}</div>
                  <div className="mt-1 text-xs leading-5 text-slate-300 line-clamp-2">{ins.content}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
