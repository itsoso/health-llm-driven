import { describe, expect, it } from 'vitest';

import { collectMedicationSafetyAlerts } from './medicationSafety';

describe('collectMedicationSafetyAlerts', () => {
  it('collects safety alerts from medication list responses', () => {
    const alerts = collectMedicationSafetyAlerts([
      {
        id: 1,
        user_id: 1,
        name: '卡马西平',
        dosage: '100mg',
        frequency: '每日 1 次',
        times_per_day: 1,
        reminder_times: ['08:00'],
        category: null,
        purpose: null,
        is_active: true,
        start_date: null,
        end_date: null,
        notes: null,
        created_at: null,
        safety_alerts: [{
          rule_id: 'pgx.cpic.hla-b_卡马西平',
          category: 'pgx',
          severity: { label: 'critical', label_zh: '紧急', value: 4 },
          title: 'HLA-B × 卡马西平',
          message: '携带 HLA-B 风险等位基因时，卡马西平相关严重皮肤不良反应风险升高。',
          action: '请先与医生或药师确认，不要自行调整用药。',
        }],
      },
      {
        id: 2,
        user_id: 1,
        name: '二甲双胍',
        dosage: '500mg',
        frequency: '每日 2 次',
        times_per_day: 2,
        reminder_times: ['08:00', '20:00'],
        category: null,
        purpose: null,
        is_active: true,
        start_date: null,
        end_date: null,
        notes: null,
        created_at: null,
      },
    ]);

    expect(alerts).toHaveLength(1);
    expect(alerts[0]?.title).toBe('HLA-B × 卡马西平');
  });
});
