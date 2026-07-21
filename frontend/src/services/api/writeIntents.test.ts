import { beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();

vi.mock('./client', () => ({
  api: { post: (...args: unknown[]) => post(...args) },
}));

import {
  confirmMedicationBatch,
  dismissMedicationBatch,
} from './writeIntents';

const receipts = [
  {
    operation_id: 'write_intent:medication_intake_batch:42:101',
    status: 'verified' as const,
    resource_type: 'medication_log',
    resource_id: '101',
    completed_at: '2026-07-21T21:15:01-04:00',
    verified: true as const,
  },
  {
    operation_id: 'write_intent:medication_intake_batch:42:102',
    status: 'verified' as const,
    resource_type: 'medication_log',
    resource_id: '102',
    completed_at: '2026-07-21T21:15:02-04:00',
    verified: true as const,
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

describe('medication batch write-intent API', () => {
  beforeEach(() => {
    post.mockReset();
  });

  it('confirmMedicationBatch preserves every verified receipt and safety alert', async () => {
    post.mockResolvedValueOnce({
      data: {
        id: 42,
        status: 'executed',
        executed_ref: 'medication_logs:101,102',
        write_receipts: receipts,
        safety_alerts: alerts,
      },
    });

    await expect(confirmMedicationBatch(42)).resolves.toEqual({
      decisionStatus: 'executed',
      writeReceipts: receipts,
      safetyAlerts: alerts,
      reconciliationRequired: false,
    });
    expect(post).toHaveBeenCalledWith('/write-intents/42/confirm');
  });

  it('confirmMedicationBatch fails closed when executed has no item receipts', async () => {
    post.mockResolvedValueOnce({
      data: {
        id: 42,
        status: 'executed',
        executed_ref: 'medication_logs:101,102',
        write_receipts: [],
        safety_alerts: [],
      },
    });

    await expect(confirmMedicationBatch(42)).rejects.toThrow(
      'medication_batch_write_receipts_missing',
    );
  });

  it('confirmMedicationBatch maps the authoritative 409 expiry without inventing a receipt', async () => {
    post.mockRejectedValueOnce({
      response: {
        status: 409,
        data: { detail: '确认计划已过期，请重新提交记录' },
      },
    });

    await expect(confirmMedicationBatch(42)).resolves.toEqual({
      decisionStatus: 'expired',
      writeReceipts: [],
      safetyAlerts: [],
      reconciliationRequired: true,
    });
  });

  it('preserves expired decision status on an idempotent dismissed replay', async () => {
    post.mockResolvedValueOnce({
      data: { id: 42, status: 'dismissed', decision_status: 'expired' },
    });

    await expect(confirmMedicationBatch(42)).resolves.toEqual({
      decisionStatus: 'expired',
      writeReceipts: [],
      safetyAlerts: [],
      reconciliationRequired: false,
    });
  });

  it('dismissMedicationBatch returns dismissed with no fabricated write receipt', async () => {
    post.mockResolvedValueOnce({ data: { id: 42, status: 'dismissed' } });

    await expect(dismissMedicationBatch(42)).resolves.toEqual({
      decisionStatus: 'dismissed',
      writeReceipts: [],
      safetyAlerts: [],
      reconciliationRequired: false,
    });
    expect(post).toHaveBeenCalledWith('/write-intents/42/dismiss');
  });

  it('dismissMedicationBatch requests server-meta reconciliation when confirm won the race', async () => {
    post.mockResolvedValueOnce({ data: { id: 42, status: 'executed' } });

    await expect(dismissMedicationBatch(42)).resolves.toEqual({
      decisionStatus: 'executed',
      writeReceipts: [],
      safetyAlerts: [],
      reconciliationRequired: true,
    });
  });

  it('dismissMedicationBatch consumes authoritative receipts when confirm won the race', async () => {
    post.mockResolvedValueOnce({
      data: {
        id: 42,
        status: 'executed',
        decision_status: 'executed',
        write_receipts: receipts,
        safety_alerts: alerts,
      },
    });

    await expect(dismissMedicationBatch(42)).resolves.toEqual({
      decisionStatus: 'executed',
      writeReceipts: receipts,
      safetyAlerts: alerts,
      reconciliationRequired: false,
    });
  });
});
