import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Navigation from '@/components/Navigation';
import LifeNavigationWorkspace from './LifeNavigationWorkspace';
import { blankData } from './model';
import { getLifeWorkspace } from '@/services/lifeNavigation';
vi.mock('next/navigation', () => ({ usePathname: () => '/agenda', useSearchParams: () => new URLSearchParams('navigation=week') }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: { id: 7 }, isAuthenticated: true, isLoading: false, logout: vi.fn() }) }));
vi.mock('@/components/NotificationCenter', () => ({ default: () => null }));
vi.mock('@/services/lifeNavigation', () => ({ getLifeWorkspace: vi.fn(), saveLifeWorkspace: vi.fn(), getLifeHistory: vi.fn().mockResolvedValue([]) }));
async function edit() {
    render(<><Navigation /><LifeNavigationWorkspace /></>);
    fireEvent.click(await screen.findByText('添加主任务'));
    fireEvent.change(screen.getByLabelText('任务标题'), { target: { value: 'Unsaved plan' } });
}
describe('LifeNav with actual global navigation', () => {
    beforeEach(() => { vi.clearAllMocks(); window.history.replaceState({}, '', '/agenda?navigation=week'); vi.mocked(getLifeWorkspace).mockResolvedValue({ schema_version: 'life_navigation.v1', revision: 3, data: blankData(), updated_at: null }); });
    afterEach(() => { cleanup(); vi.restoreAllMocks(); });
    it.each(['健康概览', '今日议程'])('cancel blocks global %s and preserves draft', async name => {
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
        await edit();
        expect(fireEvent.click(screen.getAllByRole('link', { name })[0], { button: 0 })).toBe(false);
        expect(confirm).toHaveBeenCalledTimes(1);
        expect(screen.getByLabelText('任务标题')).toHaveValue('Unsaved plan');
        expect(screen.getByRole('button', { name: '撤销' })).not.toBeDisabled();
    });
    it('confirmation permits the link', async () => {
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
        await edit();
        const link = screen.getAllByRole('link', { name: '健康概览' })[0];
        let permitted = false;
        link.addEventListener('click', event => { permitted = !event.defaultPrevented; event.preventDefault(); });
        fireEvent.click(link);
        expect(permitted).toBe(true);
        expect(confirm).toHaveBeenCalledTimes(1);
    });
    it('cancelled client back restores this route before downstream router handlers', async () => {
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
        await edit();
        const downstream = vi.fn(); window.addEventListener('popstate', downstream);
        try {
            window.history.replaceState({}, '', '/dashboard');
            window.dispatchEvent(new PopStateEvent('popstate'));
            expect(confirm).toHaveBeenCalledTimes(1);
            expect(downstream).not.toHaveBeenCalled();
            expect(window.location.pathname + window.location.search).toBe('/agenda?navigation=week');
            expect(screen.getByLabelText('任务标题')).toHaveValue('Unsaved plan');
        } finally { window.removeEventListener('popstate', downstream); }
    });
    it('clean routes and same-page anchors do not prompt', async () => {
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
        render(<><Navigation /><LifeNavigationWorkspace /></>);
        await screen.findByText('添加主任务');
        const link = screen.getAllByRole('link', { name: '健康概览' })[0];
        link.addEventListener('click', event => event.preventDefault());
        fireEvent.click(link);
        expect(confirm).not.toHaveBeenCalled();
        cleanup();
        await edit();
        fireEvent.click(screen.getByRole('link', { name: '今日任务' }));
        expect(confirm).not.toHaveBeenCalled();
    });
    it('modified clicks opening another tab preserve this draft without prompting', async () => {
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false);
        await edit();
        const link = screen.getAllByRole('link', { name: '健康概览' })[0];
        link.addEventListener('click', event => event.preventDefault());
        fireEvent.click(link, { ctrlKey: true });
        fireEvent.click(link, { metaKey: true });
        expect(confirm).not.toHaveBeenCalled();
        expect(screen.getByLabelText('任务标题')).toHaveValue('Unsaved plan');
    });
    it('confirmed client back reaches downstream router and cleanup removes guards', async () => {
        const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true);
        await edit();
        const downstream = vi.fn(); window.addEventListener('popstate', downstream);
        try {
            window.history.replaceState({}, '', '/dashboard');
            window.dispatchEvent(new PopStateEvent('popstate'));
            expect(confirm).toHaveBeenCalledTimes(1);
            expect(downstream).toHaveBeenCalledTimes(1);
            cleanup(); confirm.mockClear();
            window.history.replaceState({}, '', '/');
            window.dispatchEvent(new PopStateEvent('popstate'));
            expect(confirm).not.toHaveBeenCalled();
            expect(downstream).toHaveBeenCalledTimes(2);
        } finally { window.removeEventListener('popstate', downstream); }
    });

});
