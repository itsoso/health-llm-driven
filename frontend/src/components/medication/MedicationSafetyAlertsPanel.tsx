import type { MedicationSafetyAlert } from '@/services/api/records';

interface Props {
  alerts: MedicationSafetyAlert[];
}

function severityTone(value: number) {
  if (value >= 4) return 'border-red-200 bg-red-50 text-red-800';
  if (value >= 3) return 'border-orange-200 bg-orange-50 text-orange-800';
  return 'border-amber-200 bg-amber-50 text-amber-800';
}

export function MedicationSafetyAlertsPanel({ alerts }: Props) {
  if (alerts.length === 0) return null;

  return (
    <section className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-base font-semibold text-amber-950">用药安全提醒</h3>
        <span className="text-xs font-medium text-amber-800">风险分层</span>
      </div>
      <div className="space-y-3">
        {alerts.map((alert) => (
          <article key={alert.rule_id} className="rounded-lg border border-amber-100 bg-white p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${severityTone(alert.severity.value)}`}>
                {alert.severity.label_zh}
              </span>
              <h4 className="text-sm font-semibold text-gray-950">{alert.title}</h4>
            </div>
            <p className="text-sm leading-6 text-gray-700">{alert.message}</p>
            {alert.action && (
              <p className="mt-2 text-sm font-medium leading-6 text-amber-900">{alert.action}</p>
            )}
          </article>
        ))}
      </div>
      <p className="mt-3 text-xs leading-5 text-amber-800">
        这些提醒用于风险分层，不替代医生诊断或处方决定。
      </p>
    </section>
  );
}
