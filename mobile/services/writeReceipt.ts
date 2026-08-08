export type WriteReceiptStatus = 'verified' | 'dismissed';
export type WriteReceiptAction = 'create' | 'update' | 'delete';

const WRITE_RECEIPT_RESOURCE_LABELS: ReadonlyMap<string, string> = new Map([
  ['agenda_event', '今日行动'],
  ['intervention_event', '今日行动'],
  ['diet_record', '饮食记录'],
  ['write_intent', '待确认项'],
  ['smart_reminder', '提醒'],
  ['health_record', '健康记录'],
  ['medication_log', '用药记录'],
]);

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
  const operationId = ownRequiredString(source, 'operationId', 'operation_id');
  const resourceType = ownRequiredString(source, 'resourceType', 'resource_type');
  const completedAt = ownRequiredString(source, 'completedAt', 'completed_at');
  const resourceIdField = readOwnField(source, 'resourceId', 'resource_id');
  const resourceId = normalizeResourceId(resourceIdField.value);
  if (
    !hasOwn(source, 'verified')
    || source.verified !== true
    || !operationId
    || !resourceType
    || !resourceIdField.present
    || !resourceId
    || !completedAt
  ) {
    return undefined;
  }

  const statusField = readOwnField(source, 'status');
  let status: WriteReceiptStatus = 'verified';
  if (statusField.present) {
    if (statusField.value !== 'verified' && statusField.value !== 'dismissed') return undefined;
    status = statusField.value;
  }

  const executedRefField = readOwnField(source, 'executedRef', 'executed_ref');
  let executedRef = '';
  if (executedRefField.present) {
    if (typeof executedRefField.value !== 'string') return undefined;
    executedRef = executedRefField.value.trim();
  }

  const actionField = readOwnField(source, 'action');
  if (actionField.present && typeof actionField.value !== 'string') return undefined;
  const action = actionField.value === 'create'
    || actionField.value === 'update'
    || actionField.value === 'delete'
    ? actionField.value
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

function hasOwn(source: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(source, key);
}

function readOwnField(
  source: Record<string, unknown>,
  ...keys: string[]
): { present: boolean; value: unknown } {
  for (const key of keys) {
    if (hasOwn(source, key)) return { present: true, value: source[key] };
  }
  return { present: false, value: undefined };
}

function ownRequiredString(source: Record<string, unknown>, ...keys: string[]): string | undefined {
  const field = readOwnField(source, ...keys);
  if (!field.present || typeof field.value !== 'string') return undefined;
  const normalized = field.value.trim();
  return normalized || undefined;
}

function normalizeResourceId(value: unknown): string | undefined {
  if (typeof value === 'string') return value.trim() || undefined;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return undefined;
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
  return WRITE_RECEIPT_RESOURCE_LABELS.get(resourceType) || '健康数据';
}
