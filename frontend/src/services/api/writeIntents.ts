import { api } from './client';

export type MedicationBatchDecisionStatus = 'executed' | 'dismissed' | 'expired';

export interface MedicationBatchWriteReceipt {
  operation_id: string;
  status: 'verified';
  resource_type: 'medication_log';
  resource_id: string | number;
  executed_ref?: string | null;
  completed_at: string;
  verified: true;
}

export interface MedicationBatchSafetyAlert {
  rule_id: string;
  category: string;
  severity: {
    value: number;
    label: string;
    label_zh?: string;
  } | string | number;
  title: string;
  message: string;
  action?: string | string[] | null;
  requires_medical_attention?: boolean;
}

export interface MedicationBatchActionOutcome {
  decisionStatus: MedicationBatchDecisionStatus;
  writeReceipts: MedicationBatchWriteReceipt[];
  safetyAlerts: MedicationBatchSafetyAlert[];
  /** True when the endpoint did not include enough terminal detail to render safely. */
  reconciliationRequired: boolean;
}

export async function confirmMedicationBatch(
  intentId: number,
): Promise<MedicationBatchActionOutcome> {
  const id = positiveIntentId(intentId);
  try {
    const response = await api.post(`/write-intents/${id}/confirm`);
    const status = response?.data?.status;
    if (status === 'dismissed') {
      return terminalWithoutWrite(
        dismissedDecisionStatus(response.data?.decision_status),
        false,
      );
    }
    if (status !== 'executed') {
      throw new Error('medication_batch_confirmation_not_terminal');
    }
    const outcome = executedMedicationBatchOutcome(response.data);
    if (outcome == null) {
      throw new Error('medication_batch_write_receipts_missing');
    }
    return outcome;
  } catch (error) {
    if (isExpiredMedicationBatch(error)) {
      return terminalWithoutWrite('expired', true);
    }
    throw error;
  }
}

export async function dismissMedicationBatch(
  intentId: number,
): Promise<MedicationBatchActionOutcome> {
  const id = positiveIntentId(intentId);
  const response = await api.post(`/write-intents/${id}/dismiss`);
  const status = response?.data?.status;
  if (status === 'dismissed') {
    // A dismiss is a decision, not a health write receipt.
    return terminalWithoutWrite(
      dismissedDecisionStatus(response.data?.decision_status),
      false,
    );
  }
  if (status === 'executed') {
    // Confirm won the race. Newer servers return the same authoritative
    // receipts as confirm; older/incomplete responses still require a source
    // assistant reconciliation instead of inventing write evidence.
    return executedMedicationBatchOutcome(response.data)
      ?? terminalWithoutWrite('executed', true);
  }
  throw new Error('medication_batch_dismiss_not_terminal');
}

export function readMedicationBatchIntentId(value: unknown): number | null {
  const normalized = typeof value === 'number'
    ? value
    : typeof value === 'string' && value.trim()
      ? Number(value)
      : NaN;
  return Number.isInteger(normalized) && normalized > 0 ? normalized : null;
}

function positiveIntentId(value: unknown): number {
  const id = readMedicationBatchIntentId(value);
  if (id == null) throw new Error('invalid_medication_batch_intent_id');
  return id;
}

function terminalWithoutWrite(
  decisionStatus: MedicationBatchDecisionStatus,
  reconciliationRequired: boolean,
): MedicationBatchActionOutcome {
  return {
    decisionStatus,
    writeReceipts: [],
    safetyAlerts: [],
    reconciliationRequired,
  };
}

function dismissedDecisionStatus(value: unknown): 'dismissed' | 'expired' {
  if (value == null || value === 'dismissed') return 'dismissed';
  if (value === 'expired') return 'expired';
  throw new Error('medication_batch_decision_status_invalid');
}

function executedMedicationBatchOutcome(
  data: unknown,
): MedicationBatchActionOutcome | null {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('medication_batch_response_invalid');
  }
  const payload = data as Record<string, unknown>;
  if (payload.decision_status != null && payload.decision_status !== 'executed') {
    throw new Error('medication_batch_decision_status_invalid');
  }
  const writeReceipts = medicationWriteReceipts(payload.write_receipts);
  if (writeReceipts.length === 0) return null;
  return {
    decisionStatus: 'executed',
    writeReceipts,
    safetyAlerts: medicationSafetyAlerts(payload.safety_alerts),
    reconciliationRequired: false,
  };
}

function medicationWriteReceipts(value: unknown): MedicationBatchWriteReceipt[] {
  if (!Array.isArray(value)) return [];
  const receipts = value.filter(isMedicationWriteReceipt);
  if (receipts.length !== value.length) {
    throw new Error('medication_batch_write_receipts_invalid');
  }
  return receipts;
}

function isMedicationWriteReceipt(value: unknown): value is MedicationBatchWriteReceipt {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const receipt = value as Record<string, unknown>;
  return (
    typeof receipt.operation_id === 'string'
    && receipt.operation_id.trim().length > 0
    && receipt.status === 'verified'
    && receipt.resource_type === 'medication_log'
    && (typeof receipt.resource_id === 'string' || typeof receipt.resource_id === 'number')
    && typeof receipt.completed_at === 'string'
    && receipt.verified === true
  );
}

function medicationSafetyAlerts(value: unknown): MedicationBatchSafetyAlert[] {
  if (value == null) return [];
  if (!Array.isArray(value)) throw new Error('medication_batch_safety_alerts_invalid');
  const alerts = value.filter(isMedicationSafetyAlert);
  if (alerts.length !== value.length) {
    throw new Error('medication_batch_safety_alerts_invalid');
  }
  return alerts;
}

function isMedicationSafetyAlert(value: unknown): value is MedicationBatchSafetyAlert {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const alert = value as Record<string, unknown>;
  return (
    typeof alert.rule_id === 'string'
    && typeof alert.category === 'string'
    && typeof alert.title === 'string'
    && typeof alert.message === 'string'
  );
}

function isExpiredMedicationBatch(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false;
  const response = (error as { response?: unknown }).response;
  if (!response || typeof response !== 'object') return false;
  const status = (response as { status?: unknown }).status;
  const data = (response as { data?: unknown }).data;
  const detail = data && typeof data === 'object'
    ? (data as { detail?: unknown }).detail
    : null;
  return status === 409 && typeof detail === 'string' && detail.includes('已过期');
}
