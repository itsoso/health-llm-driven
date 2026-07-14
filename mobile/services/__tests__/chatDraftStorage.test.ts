const storage: Record<string, string> = {};
const files: Record<string, string> = {};
const secureStorage: Record<string, string> = {};
let mockScope = 'user-7';
const mockMakeDirectory = jest.fn(async (_uri?: string, _options?: unknown) => undefined);
const mockWriteFile = jest.fn(async (uri: string, content: string, _options?: unknown) => { files[uri] = content; });
const mockCopyFile = jest.fn(async ({ from, to }: { from: string; to: string }) => {
  files[to] = files[from] ?? 'copied-bytes';
});
const mockDeleteFile = jest.fn(async (uri: string, _options?: unknown) => { delete files[uri]; });
const mockReadFile = jest.fn(async (uri: string, _options?: unknown) => files[uri]);

jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: {
    getItem: jest.fn(async (key: string) => storage[key] ?? null),
    setItem: jest.fn(async (key: string, value: string) => { storage[key] = value; }),
    removeItem: jest.fn(async (key: string) => { delete storage[key]; }),
  },
}));

jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn(async (key: string) => secureStorage[key] ?? null),
  setItemAsync: jest.fn(async (key: string, value: string) => { secureStorage[key] = value; }),
  deleteItemAsync: jest.fn(async (key: string) => { delete secureStorage[key]; }),
}));

jest.mock('../authStorageScope', () => ({
  getAuthStorageScope: jest.fn(async () => mockScope),
}));

jest.mock('expo-file-system/legacy', () => ({
  documentDirectory: 'file:///documents/',
  EncodingType: { Base64: 'base64' },
  makeDirectoryAsync: (uri: string, options?: unknown) => mockMakeDirectory(uri, options),
  writeAsStringAsync: (uri: string, content: string, options?: unknown) => (
    mockWriteFile(uri, content, options)
  ),
  copyAsync: (options: { from: string; to: string }) => mockCopyFile(options),
  deleteAsync: (uri: string, options?: unknown) => mockDeleteFile(uri, options),
  readAsStringAsync: (uri: string, options?: unknown) => mockReadFile(uri, options),
  getInfoAsync: jest.fn(async (uri: string) => ({ exists: Object.prototype.hasOwnProperty.call(files, uri) })),
  readDirectoryAsync: jest.fn(async () => []),
}));

import AsyncStorage from '@react-native-async-storage/async-storage';
import {
  chatDraftDirectory,
  chatDraftStorageKey,
  chatDraftTextStorageKey,
  clearPersistedChatDraft,
  deleteDraftImage,
  hydrateDraftImagesForSend,
  loadChatDraft,
  materializeDraftImages,
  persistChatDraft,
} from '../chatDraftStorage';

describe('chatDraftStorage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    Object.keys(storage).forEach(key => delete storage[key]);
    Object.keys(files).forEach(key => delete files[key]);
    Object.keys(secureStorage).forEach(key => delete secureStorage[key]);
    mockScope = 'user-7';
  });

  it('uses a SecureStore-compatible key for protected draft text', () => {
    expect(chatDraftTextStorageKey('user-7')).toMatch(/^[A-Za-z0-9._-]+$/);
  });

  it('persists text and image metadata without base64 health content', async () => {
    await persistChatDraft('午餐照片待确认', [{
      uri: `${chatDraftDirectory(mockScope)}photo.jpeg`,
      base64: 'private-image-bytes',
      type: 'jpeg',
      draftCreatedAt: 100,
    }]);

    const raw = storage[chatDraftStorageKey(mockScope)];
    expect(raw).not.toContain('午餐照片待确认');
    expect(raw).toContain('photo.jpeg');
    expect(raw).not.toContain('private-image-bytes');
    expect(secureStorage[chatDraftTextStorageKey(mockScope)]).toBe('午餐照片待确认');
  });

  it('copies selected image bytes into the app-private draft directory', async () => {
    const [saved] = await materializeDraftImages([{
      uri: 'file:///tmp/camera.jpg',
      base64: 'camera-base64',
      type: 'jpeg',
    }], 1234);

    expect(saved.uri).toMatch(/^file:\/\/\/documents\/chat-drafts\/user-7\/1234-/);
    expect(saved.base64).toBe('camera-base64');
    expect(saved.draftCreatedAt).toBe(1234);
    expect(mockWriteFile).toHaveBeenCalledWith(
      saved.uri,
      'camera-base64',
      expect.objectContaining({ encoding: 'base64' }),
    );
  });

  it('restores valid metadata and prunes missing private files', async () => {
    const keptUri = `${chatDraftDirectory(mockScope)}kept.jpeg`;
    files[keptUri] = 'kept-base64';
    storage[chatDraftStorageKey(mockScope)] = JSON.stringify({
      version: 2,
      updatedAt: 200,
      images: [
        { uri: keptUri, type: 'jpeg', createdAt: 100 },
        { uri: `${chatDraftDirectory(mockScope)}missing.jpeg`, type: 'jpeg', createdAt: 100 },
      ],
    });
    secureStorage[chatDraftTextStorageKey(mockScope)] = '继续补充';

    await expect(loadChatDraft()).resolves.toEqual({
      text: '继续补充',
      images: [{ uri: keptUri, base64: '', type: 'jpeg', draftCreatedAt: 100 }],
    });
    expect(JSON.parse(storage[chatDraftStorageKey(mockScope)]).images).toHaveLength(1);
  });

  it('removes corrupt snapshots instead of crashing composer startup', async () => {
    storage[chatDraftStorageKey(mockScope)] = '{bad-json';

    await expect(loadChatDraft()).resolves.toEqual({ text: '', images: [] });
    expect(AsyncStorage.removeItem).toHaveBeenCalledWith(chatDraftStorageKey(mockScope));
  });

  it('hydrates private image base64 only when preparing a send', async () => {
    const uri = `${chatDraftDirectory(mockScope)}send.jpeg`;
    files[uri] = 'send-base64';

    await expect(hydrateDraftImagesForSend([{
      uri,
      base64: '',
      type: 'jpeg',
      draftCreatedAt: 100,
    }])).resolves.toEqual([expect.objectContaining({ uri, base64: 'send-base64' })]);
  });

  it('deletes private files on explicit remove and acknowledged cleanup', async () => {
    const first = `${chatDraftDirectory(mockScope)}first.jpeg`;
    const second = `${chatDraftDirectory(mockScope)}second.jpeg`;
    files[first] = 'first';
    files[second] = 'second';

    await deleteDraftImage({ uri: first, base64: '', type: 'jpeg' });
    await clearPersistedChatDraft([{ uri: second, base64: '', type: 'jpeg' }]);

    expect(files[first]).toBeUndefined();
    expect(files[second]).toBeUndefined();
    expect(AsyncStorage.removeItem).toHaveBeenCalledWith(chatDraftStorageKey(mockScope));
  });

  it('does not restore another account text or image metadata', async () => {
    await persistChatDraft('用户七的午餐', []);
    mockScope = 'user-8';

    await expect(loadChatDraft()).resolves.toEqual({ text: '', images: [] });
    expect(secureStorage[chatDraftTextStorageKey('user-7')]).toBe('用户七的午餐');
  });
});
