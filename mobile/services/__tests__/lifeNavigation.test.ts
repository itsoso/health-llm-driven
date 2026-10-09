import api from '../api';
import { blankData } from '../../utils/lifeNavigationModel';
import type { LifeBackup } from '../lifeNavigation';
import { fetchLifeWorkspace, saveLifeWorkspace, fetchLifeHistory, fetchLifeBackup, restoreLifeWorkspace, importLifeBackup } from '../lifeNavigation';
jest.mock('../api', () => ({ __esModule: true, default: { get: jest.fn(), put: jest.fn(), post: jest.fn() } }));
it('binds private writes to the initiating owner and revision', async () => {
    (api.put as jest.Mock).mockResolvedValue({ data: { revision: 2 } });
    const data = blankData();
    await saveLifeWorkspace(7, 1, data);
    expect(api.put).toHaveBeenCalledWith('/life-navigation/workspace', { expected_revision: 1, data }, expect.objectContaining({ headers: { 'X-Reva-AI-Subject': '7' } }));
});
it('binds backup and history to the owner and replacement to current CAS revision', async () => {
    (api.get as jest.Mock).mockResolvedValue({ data: [] });
    (api.post as jest.Mock).mockResolvedValue({ data: { revision: 8 } });
    await fetchLifeHistory(7);
    await fetchLifeBackup(7);
    const backup: LifeBackup = { schema_version: 'life_navigation.backup.v1', workspace: { schema_version: 'life_navigation.v1', revision: 0, data: blankData(), updated_at: null }, history: [] };
    await importLifeBackup(7, 6, backup);
    await restoreLifeWorkspace(7, 3, 6);
    const config = expect.objectContaining({ headers: { 'X-Reva-AI-Subject': '7' } });
    expect(api.get).toHaveBeenCalledWith('/life-navigation/history', config);
    expect(api.get).toHaveBeenCalledWith('/life-navigation/backup', config);
    expect(api.post).toHaveBeenCalledWith('/life-navigation/import', { expected_revision: 6, backup }, config);
    expect(api.post).toHaveBeenCalledWith('/life-navigation/restore/3', { expected_revision: 6 }, config);
});
it('discards a late previous-session planning response', async () => {
    let done!: (value: unknown) => void;
    (api.get as jest.Mock).mockImplementation(() => new Promise(resolve => { done = resolve; }));
    const pending = fetchLifeWorkspace(1);
    require('../aiConsentState').invalidateAIConsent();
    done({ data: { revision: 1 } });
    await expect(pending).rejects.toThrow('登录状态已变化');
});
it.each(['history', 'backup', 'restore', 'import'] as const)('discards late %s responses after account invalidation', async (kind) => {
    let done!: (value: unknown) => void;
    const send = () => new Promise(resolve => { done = resolve; });
    (api.get as jest.Mock).mockImplementation(send);
    (api.post as jest.Mock).mockImplementation(send);
    const backup: LifeBackup = { schema_version: 'life_navigation.backup.v1', workspace: { schema_version: 'life_navigation.v1', revision: 0, data: blankData(), updated_at: null }, history: [] };
    const pending = kind === 'history' ? fetchLifeHistory(1) : kind === 'backup' ? fetchLifeBackup(1) : kind === 'restore' ? restoreLifeWorkspace(1, 1, 3) : importLifeBackup(1, 3, backup);
    require('../aiConsentState').invalidateAIConsent();
    done({ data: { revision: 4 } });
    await expect(pending).rejects.toThrow('登录状态已变化');
});
