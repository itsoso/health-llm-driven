import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'notifications:pending-medication-actions:v1';

export type PendingMedicationActionName = 'TAKEN' | 'SKIP';

export interface PendingMedicationActionData {
  reminder_type: 'medication';
  medication_id: number | string;
  scheduled_date: string;
  scheduled_time: string;
  scheduled_timezone: string;
  rule_id: string;
}

export interface PendingMedicationAction {
  key: string;
  action: PendingMedicationActionName;
  data: PendingMedicationActionData;
  created_at: string;
}

type PendingMedicationActionInput = Pick<PendingMedicationAction, 'action' | 'data'>;

let mutationChain: Promise<void> = Promise.resolve();

function actionKey(input: PendingMedicationActionInput): string {
  return `${input.data.rule_id}:${input.action}`;
}

function isPendingMedicationAction(value: unknown): value is PendingMedicationAction {
  if (!value || typeof value !== 'object') return false;
  const item = value as Partial<PendingMedicationAction>;
  const medicationId = item.data?.medication_id;
  const hasMedicationId = (typeof medicationId === 'number' && Number.isInteger(medicationId))
    || (typeof medicationId === 'string' && medicationId.trim().length > 0);
  return typeof item.key === 'string'
    && (item.action === 'TAKEN' || item.action === 'SKIP')
    && typeof item.created_at === 'string'
    && Boolean(item.data)
    && item.data?.reminder_type === 'medication'
    && hasMedicationId
    && typeof item.data.rule_id === 'string'
    && /^\d{4}-\d{2}-\d{2}$/.test(item.data.scheduled_date ?? '')
    && /^([01]\d|2[0-3]):[0-5]\d$/.test(item.data.scheduled_time ?? '')
    && item.data.scheduled_timezone === 'Asia/Shanghai'
    && item.data.rule_id === (
      `medication_reminder.${medicationId}.${item.data.scheduled_date}.${item.data.scheduled_time}`
    )
    && item.key === `${item.data.rule_id}:${item.action}`;
}

async function readPending(): Promise<PendingMedicationAction[]> {
  const raw = await AsyncStorage.getItem(STORAGE_KEY);
  if (!raw) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new Error('Medication action retry queue is not valid JSON', { cause: error });
  }
  if (!Array.isArray(parsed) || !parsed.every(isPendingMedicationAction)) {
    throw new Error('Medication action retry queue contains invalid occurrence data');
  }
  return parsed;
}

async function writePending(items: PendingMedicationAction[]): Promise<void> {
  if (items.length === 0) {
    await AsyncStorage.removeItem(STORAGE_KEY);
    return;
  }
  // Medication adherence facts must never be silently truncated. A persistent failure
  // remains visible and retryable instead of trading accuracy for a fixed queue length.
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(items));
}

function serializedMutation<T>(operation: () => Promise<T>): Promise<T> {
  const result = mutationChain.then(operation, operation);
  mutationChain = result.then(() => undefined, () => undefined);
  return result;
}

export async function enqueuePendingMedicationAction(
  input: PendingMedicationActionInput,
): Promise<PendingMedicationAction> {
  return serializedMutation(async () => {
    const items = await readPending();
    const key = actionKey(input);
    const existing = items.find((item) => item.key === key);
    if (existing) return existing;
    const pending: PendingMedicationAction = {
      key,
      action: input.action,
      data: input.data,
      created_at: new Date().toISOString(),
    };
    await writePending([...items, pending]);
    return pending;
  });
}

export async function listPendingMedicationActions(): Promise<PendingMedicationAction[]> {
  await mutationChain;
  return readPending();
}

export async function removePendingMedicationAction(key: string): Promise<void> {
  await serializedMutation(async () => {
    const items = await readPending();
    await writePending(items.filter((item) => item.key !== key));
  });
}
