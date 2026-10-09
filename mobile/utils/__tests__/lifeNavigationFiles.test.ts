import * as FS from 'expo-file-system/legacy';
import * as Picker from 'expo-document-picker';
import * as Sharing from 'expo-sharing';
import { exportLifeBackup, pickLifeBackup } from '../lifeNavigationFiles';
import { blankData } from '../lifeNavigationModel';
jest.mock('expo-file-system/legacy', () => ({ cacheDirectory: 'file:///cache/', writeAsStringAsync: jest.fn(), readAsStringAsync: jest.fn(), getInfoAsync: jest.fn(), deleteAsync: jest.fn() }));
jest.mock('expo-document-picker', () => ({ getDocumentAsync: jest.fn() }));
jest.mock('expo-sharing', () => ({ isAvailableAsync: jest.fn(), shareAsync: jest.fn() }));
const backup = { schema_version: 'life_navigation.backup.v1' as const, workspace: { schema_version: 'life_navigation.v1' as const, revision: 0, data: blankData(), updated_at: null }, history: [] };
beforeEach(() => { jest.clearAllMocks(); (Sharing.isAvailableAsync as jest.Mock).mockResolvedValue(true); (FS.getInfoAsync as jest.Mock).mockResolvedValue({ exists: true, isDirectory: false, size: 100 }); (Picker.getDocumentAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///cache/picked.json', size: 100 }] }); (FS.readAsStringAsync as jest.Mock).mockResolvedValue(JSON.stringify(backup)); });
it('removes the private temporary export even if sharing fails', async () => {
    (Sharing.shareAsync as jest.Mock).mockRejectedValue(new Error('分享失败'));
    await expect(exportLifeBackup(backup)).rejects.toThrow('分享失败');
    const uri = (FS.writeAsStringAsync as jest.Mock).mock.calls[0][0];
    expect(uri).toMatch(/^file:\/\/\/cache\/reva-life-/);
    expect(FS.deleteAsync).toHaveBeenCalledWith(uri, { idempotent: true });
});
it('rejects oversized import before loading and removes only the cached copy', async () => {
    (FS.getInfoAsync as jest.Mock).mockResolvedValue({ exists: true, isDirectory: false, size: 6 * 1024 * 1024 + 1 });
    await expect(pickLifeBackup()).rejects.toThrow('备份过大');
    expect(FS.readAsStringAsync).not.toHaveBeenCalled();
    expect(FS.deleteAsync).toHaveBeenCalledWith('file:///cache/picked.json', { idempotent: true });
});
it('validates preview and removes cache; never deletes the user original', async () => {
    expect(await pickLifeBackup()).toEqual(backup);
    expect(FS.deleteAsync).toHaveBeenCalledTimes(1);
    (Picker.getDocumentAsync as jest.Mock).mockResolvedValue({ canceled: false, assets: [{ uri: 'file:///documents/original.json', size: 100 }] });
    await pickLifeBackup();
    expect(FS.deleteAsync).toHaveBeenCalledTimes(1);
});
it('does not open a share sheet or return a preview after account invalidation', async () => {
    let current = true;
    (Sharing.isAvailableAsync as jest.Mock).mockImplementation(async () => { current = false; return true; });
    await expect(exportLifeBackup(backup, () => current)).rejects.toThrow('登录状态');
    expect(Sharing.shareAsync).not.toHaveBeenCalled();
    (FS.readAsStringAsync as jest.Mock).mockImplementation(async () => { current = false; return JSON.stringify(backup); });
    current = true;
    await expect(pickLifeBackup(() => current)).rejects.toThrow('登录状态');
});
