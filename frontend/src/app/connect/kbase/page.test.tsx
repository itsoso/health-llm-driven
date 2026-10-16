import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import KBaseLoginPage from './page';
const mocks = vi.hoisted(() => ({ query: '', user: { id: 7, name: '测试用户' } as { id: number; name: string } | null, fetch: vi.fn() }));
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams(mocks.query) }));
vi.mock('@/contexts/AuthContext', () => ({ useAuth: () => ({ user: mocks.user, isLoading: false }) }));
beforeEach(() => { mocks.query = `state=${'a'.repeat(43)}`; mocks.user = { id: 7, name: '测试用户' }; mocks.fetch.mockReset(); vi.stubGlobal('fetch', mocks.fetch); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
it('requires login and retains only a validated local return path', () => { mocks.user=null; render(<KBaseLoginPage />); expect(screen.getByRole('link').getAttribute('href')).toContain('/login?redirect=%2Fconnect%2Fkbase'); expect(mocks.fetch).not.toHaveBeenCalled(); });
it('rejects duplicate state without issuing a ticket', () => { mocks.query += '&state=attacker'; render(<KBaseLoginPage />); expect(screen.getByRole('alert')).toHaveTextContent('登录请求无效'); expect(screen.queryByRole('button')).toBeNull(); });
it('posts only a short lived ticket to the backend registered callback', async () => {
 const submit=vi.spyOn(HTMLFormElement.prototype,'submit').mockImplementation(function(this:HTMLFormElement){ expect(this.action).toBe('https://library.example.test/browser/health/callback'); expect(this.method).toBe('post'); expect(new FormData(this).get('ticket')).toBe(`abc.${'s'.repeat(43)}`); });
 mocks.fetch.mockResolvedValue(new Response(JSON.stringify({ticket:`abc.${'s'.repeat(43)}`,callback_url:'https://library.example.test/browser/health/callback'})));
 render(<KBaseLoginPage />); expect(mocks.fetch).not.toHaveBeenCalled(); fireEvent.click(screen.getByRole('button'));
 await waitFor(()=>expect(submit).toHaveBeenCalledOnce()); expect(JSON.parse(mocks.fetch.mock.calls[0][1].body)).toEqual({state:'a'.repeat(43),expected_user_id:7});
});
it('does not continue after an account change', async () => {
 let resolve!: (r:Response)=>void; mocks.fetch.mockReturnValue(new Promise<Response>(r=>{resolve=r;})); const submit=vi.spyOn(HTMLFormElement.prototype,'submit').mockImplementation(()=>{});
 const view=render(<KBaseLoginPage />); fireEvent.click(screen.getByRole('button')); mocks.user={id:8,name:'其它用户'}; view.rerender(<KBaseLoginPage />);
 resolve(new Response(JSON.stringify({ticket:`abc.${'s'.repeat(43)}`,callback_url:'https://library.example.test/browser/health/callback'})));
 await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('登录账号已变化')); expect(submit).not.toHaveBeenCalled();
});
it('shows a disabled integration without submitting a form',async()=>{ mocks.fetch.mockResolvedValue(new Response('{}',{status:503}));const submit=vi.spyOn(HTMLFormElement.prototype,'submit').mockImplementation(()=>{});render(<KBaseLoginPage />);fireEvent.click(screen.getByRole('button'));await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('尚未启用'));expect(submit).not.toHaveBeenCalled(); });
