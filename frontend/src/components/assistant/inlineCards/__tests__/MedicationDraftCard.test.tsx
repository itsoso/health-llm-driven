// @vitest-environment jsdom

import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { MedicationDraftCardView } from '../cards';

const items = [
  { medication_name: '伊托必利', actual_dosage: '1粒' },
  { medication_name: '替普瑞酮', actual_dosage: '1粒', observed_strength: '50mg' },
];

const receipts = [
  {
    operation_id: 'write_intent:medication_intake_batch:42:101',
    status: 'verified',
    resource_type: 'medication_log',
    resource_id: '101',
    completed_at: '2026-07-21T21:15:01-04:00',
    verified: true,
  },
  {
    operation_id: 'write_intent:medication_intake_batch:42:102',
    status: 'verified',
    resource_type: 'medication_log',
    resource_id: '102',
    completed_at: '2026-07-21T21:15:02-04:00',
    verified: true,
  },
];

const alerts = [
  {
    rule_id: 'ddi.high.1',
    category: 'ddi',
    severity: { value: 3, label: 'high', label_zh: '高风险' },
    title: '相互作用提示一',
    message: '第一条安全提示。',
    action: '请联系医生或药师。',
  },
  {
    rule_id: 'medication.safety_precheck_incomplete',
    category: 'ddi',
    severity: { value: 3, label: 'high', label_zh: '高风险' },
    title: '安全预检未完成',
    message: '这不代表当前组合安全。',
    action: '新增或调整用药前请咨询医生或药师。',
  },
];

describe('MedicationDraftCardView', () => {
  it('renders every item and keeps strength separate from actual dosage', () => {
    render(<MedicationDraftCardView items={items} taken_at="2026-07-21 21:15" />);

    expect(screen.getByText('伊托必利')).toBeInTheDocument();
    expect(screen.getByText('替普瑞酮')).toBeInTheDocument();
    expect(screen.getAllByText('本次 1粒')).toHaveLength(2);
    expect(screen.getByText('规格 50mg')).toBeInTheDocument();
    expect(screen.getByText('用药 · 待确认')).toBeInTheDocument();
  });

  it('renders all item receipts and every safety alert after execution', () => {
    render(
      <MedicationDraftCardView
        items={items}
        decision_status="executed"
        write_receipts={receipts}
        safety_alerts={alerts}
      />,
    );

    expect(screen.getByText('用药 · 已记录')).toBeInTheDocument();
    const receiptList = screen.getByRole('list', { name: '逐项写入回执' });
    expect(within(receiptList).getByText(/伊托必利 · 1粒/)).toBeInTheDocument();
    expect(within(receiptList).getByText(/替普瑞酮 · 1粒/)).toBeInTheDocument();
    expect(within(receiptList).getByText(/回执 #101/)).toBeInTheDocument();
    expect(within(receiptList).getByText(/回执 #102/)).toBeInTheDocument();

    const alertList = screen.getByRole('list', { name: '用药安全提示' });
    expect(within(alertList).getByText('相互作用提示一')).toBeInTheDocument();
    expect(within(alertList).getByText('安全预检未完成')).toBeInTheDocument();
    expect(within(alertList).getByText('第一条安全提示。')).toBeInTheDocument();
    expect(within(alertList).getByText('这不代表当前组合安全。')).toBeInTheDocument();
  });

  it('does not claim success when an executed projection is missing item receipts', () => {
    render(
      <MedicationDraftCardView
        items={items}
        decision_status="executed"
        write_receipts={[receipts[0]]}
      />,
    );

    expect(screen.getByText('用药 · 状态待核对')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('逐项回执尚未完整恢复');
    expect(screen.queryByText('用药 · 已记录')).not.toBeInTheDocument();
  });

  it('keeps every available receipt and safety alert visible while terminal integrity is reconciling', () => {
    render(
      <MedicationDraftCardView
        items={items}
        decision_status="executed"
        write_receipts={[receipts[0]]}
        safety_alerts={alerts}
      />,
    );

    const receiptList = screen.getByRole('list', { name: '逐项写入回执' });
    expect(within(receiptList).getAllByRole('listitem')).toHaveLength(1);
    expect(within(receiptList).getByText(/回执 #101/)).toBeInTheDocument();

    const alertList = screen.getByRole('list', { name: '用药安全提示' });
    expect(within(alertList).getAllByRole('listitem')).toHaveLength(2);
    expect(within(alertList).getAllByRole('alert')).toHaveLength(2);
    expect(within(alertList).getByText('相互作用提示一')).toBeInTheDocument();
    expect(within(alertList).getByText('安全预检未完成')).toBeInTheDocument();
  });

  it('renders dismiss and expiry as explicit no-write terminals without receipts', () => {
    const { rerender } = render(
      <MedicationDraftCardView
        items={items}
        decision_status="dismissed"
        write_receipts={receipts}
      />,
    );

    expect(screen.getByText('用药 · 已取消')).toBeInTheDocument();
    expect(screen.getByText('这组记录已取消，没有写入。')).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '逐项写入回执' })).not.toBeInTheDocument();

    rerender(<MedicationDraftCardView items={items} decision_status="expired" />);
    expect(screen.getByText('用药 · 确认已过期')).toBeInTheDocument();
    expect(screen.getByText(/没有写入/)).toBeInTheDocument();
  });
});
