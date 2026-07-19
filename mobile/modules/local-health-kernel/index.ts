import { Platform, requireNativeModule } from 'expo-modules-core';

export type LocalHealthCollection = 'diet_records' | 'execution_events';

export type LocalHealthEncryptedWrite = {
  collection: LocalHealthCollection;
  id: string;
  version: number;
  equalityIndexes: Record<string, string>;
  payload: string;
};

export type LocalHealthExportReceipt = {
  uri: string;
  recoveryKey: string;
};

export type LocalHealthEncryptedDelete = {
  collection: LocalHealthCollection;
  id: string;
};

export type LocalHealthMutation = {
  writes: LocalHealthEncryptedWrite[];
  deletes: LocalHealthEncryptedDelete[];
};

export type LocalFoodPhotoCandidate = {
  canonicalFoodId: string;
  displayName: string;
  category: string;
  score: number;
  evidence: 'whole_image' | 'salient_region';
};

export type LocalFoodPhotoRecognition = {
  decision: 'candidate' | 'unknown' | 'non_food';
  candidates: LocalFoodPhotoCandidate[];
  manualConfirmationRequired: true;
  canAutoSave: false;
  estimatesPortion: false;
};

type NativeLocalHealthKernel = {
  createVault(identityId: string): Promise<void>;
  openVault(identityId: string): Promise<void>;
  putEncrypted(
    collection: LocalHealthCollection,
    id: string,
    version: number,
    equalityIndexes: Record<string, string>,
    payload: string,
  ): Promise<void>;
  commitMutation(mutationJson: string): Promise<void>;
  getDecrypted(collection: LocalHealthCollection, id: string): Promise<string | null>;
  listDecrypted(
    collection: LocalHealthCollection,
    index: string,
    value: string,
  ): Promise<string[]>;
  delete(collection: LocalHealthCollection, id: string): Promise<void>;
  exportEnvelope(): Promise<LocalHealthExportReceipt>;
  restoreEnvelope(uri: string, recoveryKey: string): Promise<void>;
  deleteVault(): Promise<void>;
  recognizeFoodPhoto(uri: string): Promise<string>;
};

export class LocalHealthKernelBridgeError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = 'LocalHealthKernelBridgeError';
    this.code = code;
  }
}

let cachedNative: NativeLocalHealthKernel | null | undefined;

function nativeKernel(): NativeLocalHealthKernel | null {
  if (cachedNative !== undefined) return cachedNative;
  if (Platform.OS !== 'ios') {
    cachedNative = null;
    return null;
  }
  try {
    cachedNative = requireNativeModule('LocalHealthKernel') as NativeLocalHealthKernel;
  } catch {
    cachedNative = null;
  }
  return cachedNative;
}

function requiredKernel(): NativeLocalHealthKernel {
  const kernel = nativeKernel();
  if (!kernel) throw new LocalHealthKernelBridgeError('native_module_unavailable');
  return kernel;
}

function assertCollection(value: string): asserts value is LocalHealthCollection {
  if (value !== 'diet_records' && value !== 'execution_events') {
    throw new LocalHealthKernelBridgeError('invalid_collection');
  }
}

export async function createLocalHealthVault(identityId: string): Promise<void> {
  await requiredKernel().createVault(identityId);
}

export async function openLocalHealthVault(identityId: string): Promise<void> {
  await requiredKernel().openVault(identityId);
}

export async function putLocalHealthEncrypted(
  input: LocalHealthEncryptedWrite | (Omit<LocalHealthEncryptedWrite, 'collection'> & {
    collection: string;
  }),
): Promise<void> {
  assertCollection(input.collection);
  await requiredKernel().putEncrypted(
    input.collection,
    input.id,
    input.version,
    input.equalityIndexes,
    input.payload,
  );
}

export async function commitLocalHealthMutation(
  mutation: LocalHealthMutation,
): Promise<void> {
  for (const write of mutation.writes) {
    assertCollection(write.collection);
  }
  for (const deletion of mutation.deletes) {
    assertCollection(deletion.collection);
  }
  await requiredKernel().commitMutation(JSON.stringify(mutation));
}

export async function getLocalHealthDecrypted(
  collection: LocalHealthCollection,
  id: string,
): Promise<string | null> {
  assertCollection(collection);
  return requiredKernel().getDecrypted(collection, id);
}

export async function listLocalHealthDecrypted(
  collection: LocalHealthCollection,
  index: string,
  value: string,
): Promise<string[]> {
  assertCollection(collection);
  return requiredKernel().listDecrypted(collection, index, value);
}

export async function deleteLocalHealthEncrypted(
  collection: LocalHealthCollection,
  id: string,
): Promise<void> {
  assertCollection(collection);
  await requiredKernel().delete(collection, id);
}

export async function exportLocalHealthEnvelope(): Promise<LocalHealthExportReceipt> {
  return requiredKernel().exportEnvelope();
}

export async function restoreLocalHealthEnvelope(
  uri: string,
  recoveryKey: string,
): Promise<void> {
  await requiredKernel().restoreEnvelope(uri, recoveryKey);
}

export async function deleteLocalHealthVault(): Promise<void> {
  await requiredKernel().deleteVault();
}

export async function recognizeLocalFoodPhoto(
  uri: string,
): Promise<LocalFoodPhotoRecognition> {
  if (!uri.startsWith('file://')) {
    throw new LocalHealthKernelBridgeError('invalid_photo_uri');
  }
  const raw = await requiredKernel().recognizeFoodPhoto(uri);
  let decoded: unknown;
  try {
    decoded = JSON.parse(raw);
  } catch {
    throw new LocalHealthKernelBridgeError('invalid_vision_result');
  }
  if (!isVisionResult(decoded)) {
    throw new LocalHealthKernelBridgeError('invalid_vision_result');
  }
  return {
    decision: decoded.decision,
    candidates: decoded.candidates.map((candidate) => ({
      canonicalFoodId: candidate.canonicalFoodID,
      displayName: candidate.displayName,
      category: candidate.category,
      score: candidate.score,
      evidence: candidate.evidence,
    })),
    manualConfirmationRequired: true,
    canAutoSave: false,
    estimatesPortion: false,
  };
}

type NativeVisionResult = {
  decision: LocalFoodPhotoRecognition['decision'];
  candidates: {
    canonicalFoodID: string;
    displayName: string;
    category: string;
    score: number;
    evidence: LocalFoodPhotoCandidate['evidence'];
  }[];
};

function isVisionResult(value: unknown): value is NativeVisionResult {
  if (!value || typeof value !== 'object') return false;
  const result = value as Partial<NativeVisionResult>;
  if (!['candidate', 'unknown', 'non_food'].includes(result.decision ?? '')) return false;
  if (!Array.isArray(result.candidates)) return false;
  if (result.decision === 'candidate' && result.candidates.length === 0) return false;
  return result.candidates.every((candidate) => (
    candidate
    && typeof candidate.canonicalFoodID === 'string'
    && typeof candidate.displayName === 'string'
    && typeof candidate.category === 'string'
    && typeof candidate.score === 'number'
    && Number.isFinite(candidate.score)
    && ['whole_image', 'salient_region'].includes(candidate.evidence)
  ));
}
