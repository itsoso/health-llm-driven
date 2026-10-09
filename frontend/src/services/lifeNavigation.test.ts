import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from './api/client';
import { saveLifeWorkspace, getLifeWorkspace } from './lifeNavigation';
import { blankData } from '@/components/life-navigation/model';
vi.mock('./api/client', () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));
describe('Life workspace owner and revision binding', () => {
    beforeEach(() => vi.clearAllMocks());
    it('captures owner identity on both read and write without health routes', async () => {
        (api.get as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
        (api.put as ReturnType<typeof vi.fn>).mockResolvedValue({ data: {} });
        await getLifeWorkspace(7);
        await saveLifeWorkspace(7, 3, blankData());
        expect(api.get).toHaveBeenCalledWith('/life-navigation/workspace', expect.objectContaining({ headers: { 'X-Reva-AI-Subject': '7' } }));
        expect(api.put).toHaveBeenCalledWith('/life-navigation/workspace', { expected_revision: 3, data: blankData() }, { headers: { 'X-Reva-AI-Subject': '7' } });
    });
    it('propagates conflicts rather than overwriting stale drafts', async () => {
        (api.put as ReturnType<typeof vi.fn>).mockRejectedValue({ response: { status: 409 } });
        await expect(saveLifeWorkspace(7, 2, blankData())).rejects.toEqual({ response: { status: 409 } });
    });
});
