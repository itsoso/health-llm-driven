import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';
import * as SecureStore from 'expo-secure-store';
import api, { TOKEN_KEY } from './api';

const TASK_NAME = 'GARMIN_SYNC';
const LAST_SYNC_KEY = 'garmin_last_sync';

TaskManager.defineTask(TASK_NAME, async () => {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (!token) return BackgroundFetch.BackgroundFetchResult.NoData;

    await api.post('/data-collection/garmin/me/sync', null, {
      params: { days: 1 },
    });

    await SecureStore.setItemAsync(LAST_SYNC_KEY, new Date().toISOString());
    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch {
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export async function registerGarminSync(): Promise<void> {
  const isRegistered = await TaskManager.isTaskRegisteredAsync(TASK_NAME);
  if (isRegistered) return;

  await BackgroundFetch.registerTaskAsync(TASK_NAME, {
    minimumInterval: 30 * 60,
    stopOnTerminate: false,
    startOnBoot: true,
  });
}

export async function unregisterGarminSync(): Promise<void> {
  const isRegistered = await TaskManager.isTaskRegisteredAsync(TASK_NAME);
  if (!isRegistered) return;
  await BackgroundFetch.unregisterTaskAsync(TASK_NAME);
}

export async function getLastSyncTime(): Promise<string | null> {
  return SecureStore.getItemAsync(LAST_SYNC_KEY);
}

export async function syncNow(): Promise<boolean> {
  try {
    await api.post('/data-collection/garmin/me/sync', null, {
      params: { days: 1 },
    });
    await SecureStore.setItemAsync(LAST_SYNC_KEY, new Date().toISOString());
    return true;
  } catch {
    return false;
  }
}

export async function isGarminSyncRegistered(): Promise<boolean> {
  return TaskManager.isTaskRegisteredAsync(TASK_NAME);
}

export { TASK_NAME };
