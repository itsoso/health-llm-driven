jest.mock('expo-background-fetch', () => ({
  registerTaskAsync: jest.fn().mockResolvedValue(undefined),
  unregisterTaskAsync: jest.fn().mockResolvedValue(undefined),
  BackgroundFetchResult: { NewData: 2, NoData: 1, Failed: 3 },
}));

jest.mock('expo-task-manager', () => ({
  defineTask: jest.fn(),
  isTaskRegisteredAsync: jest.fn().mockResolvedValue(false),
}));

jest.mock('../api', () => ({
  __esModule: true,
  default: { post: jest.fn().mockResolvedValue({ data: {} }) },
}));

import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';
import {
  registerGarminSync,
  unregisterGarminSync,
  syncNow,
  isGarminSyncRegistered,
  TASK_NAME,
} from '../garminSync';

describe('garminSync', () => {
  beforeEach(() => jest.clearAllMocks());

  it('exports TASK_NAME constant', () => {
    expect(TASK_NAME).toBe('GARMIN_SYNC');
  });

  it('registerGarminSync registers when not already registered', async () => {
    (TaskManager.isTaskRegisteredAsync as jest.Mock).mockResolvedValueOnce(false);
    await registerGarminSync();
    expect(BackgroundFetch.registerTaskAsync).toHaveBeenCalledWith(
      TASK_NAME,
      expect.objectContaining({ minimumInterval: 1800 }),
    );
  });

  it('registerGarminSync skips when already registered', async () => {
    (TaskManager.isTaskRegisteredAsync as jest.Mock).mockResolvedValueOnce(true);
    await registerGarminSync();
    expect(BackgroundFetch.registerTaskAsync).not.toHaveBeenCalled();
  });

  it('unregisterGarminSync unregisters when registered', async () => {
    (TaskManager.isTaskRegisteredAsync as jest.Mock).mockResolvedValueOnce(true);
    await unregisterGarminSync();
    expect(BackgroundFetch.unregisterTaskAsync).toHaveBeenCalledWith(TASK_NAME);
  });

  it('unregisterGarminSync does nothing when not registered', async () => {
    (TaskManager.isTaskRegisteredAsync as jest.Mock).mockResolvedValueOnce(false);
    await unregisterGarminSync();
    expect(BackgroundFetch.unregisterTaskAsync).not.toHaveBeenCalled();
  });

  it('syncNow calls API and returns true on success', async () => {
    const result = await syncNow();
    expect(result).toBe(true);
  });

  it('syncNow returns false on failure', async () => {
    const api = require('../api').default;
    api.post.mockRejectedValueOnce(new Error('Network Error'));
    const result = await syncNow();
    expect(result).toBe(false);
  });

  it('isGarminSyncRegistered delegates to TaskManager', async () => {
    (TaskManager.isTaskRegisteredAsync as jest.Mock).mockResolvedValueOnce(true);
    const result = await isGarminSyncRegistered();
    expect(result).toBe(true);
  });
});
