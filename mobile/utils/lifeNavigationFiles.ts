import * as FS from 'expo-file-system/legacy';
import * as Picker from 'expo-document-picker';
import * as Sharing from 'expo-sharing';
import type { LifeBackup } from '../types/lifeNavigation';
import { newId, parseBackup } from './lifeNavigationModel';
const maximum = 6 * 1024 * 1024;
const requireCurrent = (current: () => boolean) => { if (!current())
    throw new Error('登录状态已变化，请重新打开导航。'); };
/** Only an explicit user action exports personal planning; no Health or account fields. */
export async function exportLifeBackup(backup: LifeBackup, isCurrent = () => true): Promise<boolean> {
    requireCurrent(isCurrent);
    const text = JSON.stringify(backup);
    parseBackup(text);
    if (!await Sharing.isAvailableAsync())
        throw new Error('当前设备无法分享文件。');
    requireCurrent(isCurrent);
    if (!FS.cacheDirectory)
        throw new Error('临时文件目录不可用。');
    const uri = `${FS.cacheDirectory}reva-life-${newId()}.json`;
    try {
        await FS.writeAsStringAsync(uri, text);
        requireCurrent(isCurrent);
        await Sharing.shareAsync(uri, { mimeType: 'application/json', UTI: 'public.json', dialogTitle: '导出个人周导航备份' });
        requireCurrent(isCurrent);
        return true;
    }
    finally {
        await FS.deleteAsync(uri, { idempotent: true });
    }
}
/** Picker copies into private cache; validate before any replace action, then remove copy. */
export async function pickLifeBackup(isCurrent = () => true): Promise<LifeBackup | null> {
    requireCurrent(isCurrent);
    const picked = await Picker.getDocumentAsync({ type: ['application/json', 'text/plain'], copyToCacheDirectory: true, multiple: false });
    if (picked.canceled)
        return null;
    const asset = picked.assets[0];
    const cache = FS.cacheDirectory;
    const owned = Boolean(cache && asset.uri.startsWith(cache) && !asset.uri.slice(cache.length).split('/').some(p => p === '..'));
    try {
        requireCurrent(isCurrent);
        const info = await FS.getInfoAsync(asset.uri);
        requireCurrent(isCurrent);
        if (!info.exists || info.isDirectory)
            throw new Error('无法读取备份文件。');
        if (!Number.isFinite(info.size) || info.size > maximum || (asset.size ?? 0) > maximum)
            throw new Error('备份过大或无法确认大小。');
        const text = await FS.readAsStringAsync(asset.uri);
        requireCurrent(isCurrent);
        return parseBackup(text);
    }
    finally {
        if (owned)
            await FS.deleteAsync(asset.uri, { idempotent: true });
    }
}
