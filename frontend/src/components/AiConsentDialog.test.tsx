import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import AiConsentDialog from './AiConsentDialog';
import { manageAiConsent, requireAiConsent, setAiConsentUser } from '@/services/aiConsent';

let accepted = false;
let writes = 0;
let failWrite = false;
beforeEach(() => {
  accepted = false; writes = 0; failWrite = false;
  setAiConsentUser(101);
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
    configurable: true, value() { this.setAttribute('open', ''); },
  });
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    if (url.endsWith('/auth/me')) return Response.json({ id: 101 });
    if (init?.method === 'PUT') {
      writes += 1;
      if (failWrite) return new Response('', { status: 503 });
      accepted = JSON.parse(String(init.body)).accepted;
    }
    return Response.json({
      policy_version: 'test-v1', accepted, accepted_at: null,
      recipients: [{ id: 'synthetic', name: '测试服务接收方', purpose: '处理输入' }],
      data_types: ['本次输入'], purpose: '响应请求',
    });
  });
});
afterEach(() => { cleanup(); setAiConsentUser(null); vi.unstubAllGlobals(); });

it('shows actual disclosure and lets the user decline without a write', async () => {
  render(<AiConsentDialog />);
  const result = requireAiConsent().then(() => true, () => false);
  expect(await screen.findByText('测试服务接收方')).toBeVisible();
  expect(screen.getByText('本次输入')).toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: '暂不同意' }));
  expect(await result).toBe(false);
  expect(writes).toBe(0);
});

it('keeps the dialog open after failed persistence and only resumes after retry acknowledgement', async () => {
  failWrite = true;
  render(<AiConsentDialog />);
  const result = requireAiConsent().then(() => true, () => false);
  fireEvent.click(await screen.findByRole('button', { name: '同意并继续' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('授权未保存');
  expect(accepted).toBe(false);
  failWrite = false;
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: '同意并继续' })); expect(await result).toBe(true); });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

it('supports withdrawal from the same management dialog', async () => {
  accepted = true;
  render(<AiConsentDialog />);
  const result = manageAiConsent();
  const withdraw = await screen.findByRole('button', { name: '撤回授权' });
  await act(async () => { fireEvent.click(withdraw); await result; });
  expect(accepted).toBe(false);
});

it('cancels a pending permission decision on logout', async () => {
  render(<AiConsentDialog />);
  const result = requireAiConsent().then(() => true, () => false);
  await screen.findByRole('button', { name: '同意并继续' });
  act(() => setAiConsentUser(null));
  expect(await result).toBe(false);
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(writes).toBe(0);
});
