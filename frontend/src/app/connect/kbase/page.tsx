'use client';

import { Suspense, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

function KBaseLogin() {
  const { user, isLoading } = useAuth();
  const params = useSearchParams();
  const states = params.getAll('state');
  const state = states.length === 1 && /^[A-Za-z0-9_-]{43}$/.test(states[0]) ? states[0] : null;
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [error, setError] = useState('');
  const current = useRef({ userId: user?.id, state });
  current.current = { userId: user?.id, state };
  const returnPath = `/connect/kbase?state=${encodeURIComponent(state || '')}`;

  async function continueLogin() {
    if (!user || !state || busyRef.current) return;
    const expectedId = user.id;
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      const response = await fetch('/api/v1/auth/sso/kbase', {
        method: 'POST', credentials: 'include', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ state, expected_user_id: expectedId }),
      });
      if (current.current.userId !== expectedId || current.current.state !== state) {
        throw new Error('登录账号已变化，请重新发起。');
      }
      if (!response.ok) throw new Error(response.status === 503
        ? '统一登录尚未启用，请联系管理员。' : '登录请求已过期或当前账号未关联知识库。');
      const data: unknown = await response.json();
      if (current.current.userId !== expectedId || current.current.state !== state) {
        throw new Error('登录账号已变化，请重新发起。');
      }
      if (!data || typeof data !== 'object' || !('ticket' in data) || !('callback_url' in data)
          || typeof data.ticket !== 'string' || !/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]{43}$/.test(data.ticket)
          || typeof data.callback_url !== 'string') throw new Error('登录响应无效。');
      const callback = new URL(data.callback_url);
      if (callback.protocol !== 'https:' || callback.username || callback.password
          || callback.pathname !== '/browser/health/callback' || callback.search || callback.hash) {
        throw new Error('登录地址无效。');
      }
      // The backend supplies the operator-registered destination; no redirect comes from query params.
      const form = document.createElement('form');
      form.method = 'POST';
      form.action = callback.href;
      const input = document.createElement('input');
      input.type = 'hidden'; input.name = 'ticket'; input.value = data.ticket;
      form.appendChild(input); document.body.appendChild(form); form.submit(); form.remove();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '暂时无法登录，请重试。');
    } finally {
      busyRef.current = false; setBusy(false);
    }
  }

  return <main className="mx-auto max-w-sm space-y-4 p-6">
    <h1 className="text-lg font-semibold">登录知识库</h1>
    {!state ? <p role="alert">登录请求无效，请从知识库重新发起。</p>
      : isLoading ? <p>正在检查账号…</p>
      : !user ? <Link href={`/login?redirect=${encodeURIComponent(returnPath)}`}>先登录 Health</Link>
      : <><p className="text-sm">使用 {user.name || '当前账号'} 继续，仅验证身份。</p>
        <button type="button" disabled={busy} onClick={continueLogin}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white disabled:opacity-50">
          {busy ? '正在登录…' : '使用当前账号继续'}</button></>}
    {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
  </main>;
}

export default function KBaseLoginPage() {
  return <Suspense fallback={<p>正在加载…</p>}><KBaseLogin /></Suspense>;
}
