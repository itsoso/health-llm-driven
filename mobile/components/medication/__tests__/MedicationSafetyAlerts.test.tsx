import React from 'react';
import { render } from '@testing-library/react-native';
import MedicationSafetyAlerts from '../MedicationSafetyAlerts';
import type { MedicationSafetyAlert } from '../../../services/medications';

jest.mock('../../../hooks/useTheme', () => ({
  useTheme: () => ({
    c: {
      bgCard: '#fff',
      labelPrimary: '#111', labelSecondary: '#555',
      red: '#FF453A', orange: '#FF6723', amber: '#FF9F0A',
      tintRed: '#FFE8E6', tintOrange: '#FFF0E6', tintAmber: '#FFF5E6',
    },
    isDark: false,
  }),
}));

const alert = (over: Partial<MedicationSafetyAlert> = {}): MedicationSafetyAlert => ({
  rule_id: 'ddi.warfarin_bleeding',
  category: 'ddi',
  severity: { value: 3, label: 'high', label_zh: '警告' },
  title: '华法林与出血风险药物合用',
  message: '华法林 + NSAID 显著升高出血风险。',
  action: '尽快联系处方医生评估。',
  requires_medical_attention: true,
  ...over,
});

describe('MedicationSafetyAlerts', () => {
  it('renders nothing when there are no alerts (saved & clean state)', () => {
    const { queryByTestId } = render(<MedicationSafetyAlerts alerts={[]} />);
    expect(queryByTestId('med-safety-alerts')).toBeNull();
  });

  it('shows a count banner and the alert title/message/action when alerts are present', () => {
    const { getByTestId, getByText } = render(<MedicationSafetyAlerts alerts={[alert()]} />);
    expect(getByTestId('med-safety-alerts')).toBeTruthy();
    expect(getByText('检测到 1 项用药相互作用风险')).toBeTruthy();
    expect(getByText('华法林与出血风险药物合用')).toBeTruthy();
    expect(getByText('华法林 + NSAID 显著升高出血风险。')).toBeTruthy();
    expect(getByText('建议：尽快联系处方医生评估。')).toBeTruthy();
    expect(getByText('警告')).toBeTruthy(); // severity.label_zh badge
  });

  it('surfaces the "see a doctor" line when requires_medical_attention is set', () => {
    const { getByText } = render(<MedicationSafetyAlerts alerts={[alert()]} />);
    expect(getByText('⚠️ 建议联系医生评估')).toBeTruthy();
  });

  it('renders one card per alert', () => {
    const alerts = [
      alert(),
      alert({
        rule_id: 'ddi.ssri_maoi',
        severity: { value: 4, label: 'critical', label_zh: '紧急' },
        title: 'SSRI 与 MAOI 合用',
        action: null,
        requires_medical_attention: true,
      }),
    ];
    const { getByText } = render(<MedicationSafetyAlerts alerts={alerts} />);
    expect(getByText('检测到 2 项用药相互作用风险')).toBeTruthy();
    expect(getByText('SSRI 与 MAOI 合用')).toBeTruthy();
    expect(getByText('紧急')).toBeTruthy();
  });
});
