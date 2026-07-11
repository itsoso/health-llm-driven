export type WriteReceiptStatus = 'verified' | 'dismissed';

export interface WriteReceipt {
  operationId: string;
  status: WriteReceiptStatus;
  resourceType: string;
  resourceId: string;
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
  return {
    operationId,
    status,
    resourceType,
    resourceId,
    ...(executedRef ? { executedRef } : {}),
    completedAt,
    verified: true,
  };
}
