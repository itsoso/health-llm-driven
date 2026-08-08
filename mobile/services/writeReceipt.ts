export type WriteReceiptStatus = 'verified' | 'dismissed';
export type WriteReceiptAction = 'create' | 'update' | 'delete';

const WRITE_RECEIPT_RESOURCE_LABELS: Readonly<Record<string, string>> = {
  agenda_event: '今日行动',
  intervention_event: '今日行动',
  diet_record: '饮食记录',
  write_intent: '待确认项',
  smart_reminder: '提醒',
  health_record: '健康记录',
  medication_log: '用药记录',
};

export interface WriteReceipt {
  operationId: string;
  status: WriteReceiptStatus;
  resourceType: string;
  resourceId: string;
  action?: WriteReceiptAction;
  executedRef?: string;
  completedAt: string;
  verified: true;
}

interface CreateWriteReceiptInput {
  operationId: string;
  status?: WriteReceiptStatus;
  resourceType?: string;
  resourceId?: string | number;
  executedRef?: string | null;
  completedAt?: string;
}

export function parseExecutedRef(executedRef?: string | null): {
  resourceType: string;
  resourceId: string;
} | null {
  const value = String(executedRef || '').trim();
  const separator = value.indexOf(':');
  if (separator <= 0 || separator >= value.length - 1) return null;
  const resourceType = value.slice(0, separator).trim();
  const resourceId = value.slice(separator + 1).trim();
  return resourceType && resourceId ? { resourceType, resourceId } : null;
}

export function createVerifiedWriteReceipt(input: CreateWriteReceiptInput): WriteReceipt {
  const parsedRef = parseExecutedRef(input.executedRef);
  const resourceType = String(input.resourceType || parsedRef?.resourceType || '').trim();
  const resourceId = String(input.resourceId ?? parsedRef?.resourceId ?? '').trim();
  if (!resourceType || !resourceId) {
    throw new Error('write_receipt_missing_identity');
  }
  return {
    operationId: input.operationId,
    status: input.status ?? 'verified',
    resourceType,
    resourceId,
    ...(input.executedRef ? { executedRef: input.executedRef } : {}),
    completedAt: input.completedAt ?? new Date().toISOString(),
    verified: true,
  };
}

export function normalizeWriteReceipt(raw: unknown): WriteReceipt | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined;
  const source = raw as Record<string, unknown>;
  const operationId = String(source.operationId ?? source.operation_id ?? '').trim();
  const resourceType = String(source.resourceType ?? source.resource_type ?? '').trim();
  const resourceId = String(source.resourceId ?? source.resource_id ?? '').trim();
  const completedAt = String(source.completedAt ?? source.completed_at ?? '').trim();
  const status = source.status === 'dismissed' ? 'dismissed' : 'verified';
  if (source.verified !== true || !operationId || !resourceType || !resourceId || !completedAt) {
    return undefined;
  }
  const executedRef = String(source.executedRef ?? source.executed_ref ?? '').trim();
  const action = source.action === 'create' || source.action === 'update' || source.action === 'delete'
    ? source.action
    : undefined;
  return {
    operationId,
    status,
    resourceType,
    resourceId,
    ...(action ? { action } : {}),
    ...(executedRef ? { executedRef } : {}),
    completedAt,
    verified: true,
  };
}

export function formatWriteReceipt(receipt: WriteReceipt): string {
  const resourceLabel = receiptResourceLabel(receipt.resourceType);
  if (receipt.status === 'dismissed') {
    return `已忽略 · ${resourceLabel} #${receipt.resourceId}`;
  }
  if (receipt.action === 'update') {
    return `已更新 · ${resourceLabel} #${receipt.resourceId}`;
  }
  if (receipt.action === 'delete') {
    return `已删除 · ${resourceLabel} #${receipt.resourceId}`;
  }
  if (receipt.resourceType === 'diet_record') {
    return `已保存到今日饮食 · 记录 #${receipt.resourceId}`;
  }
  return `已写入 · ${resourceLabel} #${receipt.resourceId}`;
}

function receiptResourceLabel(resourceType: string): string {
  return WRITE_RECEIPT_RESOURCE_LABELS[resourceType] || '健康数据';
}
