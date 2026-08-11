import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'gps_auto_refresh_status_v1';

export type GPSRefreshState = 'idle' | 'refreshing' | 'ready' | 'permission_required' | 'error';

export type GPSRefreshStatus = {
  state: GPSRefreshState;
  updatedAt?: number;
  lastSuccessAt?: number;
  errorKind?: 'permission_check' | 'location' | 'network_or_server';
};

type GPSRefreshStatusListener = (status: GPSRefreshStatus) => void;
const listeners = new Set<GPSRefreshStatusListener>();

const VALID_STATES = new Set<GPSRefreshState>([
  'idle',
  'refreshing',
  'ready',
  'permission_required',
  'error',
]);

export async function readGPSRefreshStatus(): Promise<GPSRefreshStatus> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return { state: 'idle' };
    const parsed = JSON.parse(raw) as GPSRefreshStatus;
    return VALID_STATES.has(parsed.state) ? parsed : { state: 'idle' };
  } catch {
    return { state: 'idle' };
  }
}

export async function writeGPSRefreshStatus(status: GPSRefreshStatus): Promise<void> {
  const next = {
    ...status,
    updatedAt: status.updatedAt ?? Date.now(),
  };
  listeners.forEach(listener => listener(next));
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(next));
}

export function subscribeGPSRefreshStatus(listener: GPSRefreshStatusListener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
