import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MedicationSafetyAlertsPanel } from './MedicationSafetyAlertsPanel';

describe('MedicationSafetyAlertsPanel', () => {
  it('renders PGx medication safety alerts with clinical boundary copy', () => {
    render(
      <MedicationSafetyAlertsPanel
        alerts={[{
          rule_id: 'pgx.cpic.hla-b_卡马西平',
          category: 'pgx',
          severity: { label: 'critical', label_zh: '紧急', value: 4 },
          title: 'HLA-B × 卡马西平',
          message: '携带 HLA-B 风险等位基因时，卡马西平相关严重皮肤不良反应风险升高。',
          action: '请先与医生或药师确认，不要自行调整用药。',
        }]}
      />,
    );

    expect(screen.getByText('用药安全提醒')).toBeDefined();
    expect(screen.getByText('紧急')).toBeDefined();
    expect(screen.getByText('HLA-B × 卡马西平')).toBeDefined();
    expect(screen.getByText('请先与医生或药师确认，不要自行调整用药。')).toBeDefined();
    expect(screen.getByText('这些提醒用于风险分层，不替代医生诊断或处方决定。')).toBeDefined();
  });
});
