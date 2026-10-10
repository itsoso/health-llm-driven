'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useAuth } from '@/contexts/AuthContext';

interface Consent {
  client_name: string;
  scope: 'health:read';
  expires_in_days: number;
  data_categories: string[];
  user_id: number;
}

interface Connection {
  id: string;
  client_name: string;
  scope: 'health:read';
  created_at: number;
  expires_at: number;
}

type View =
  | { status: 'loading' }
  | { status: 'error'; message: string; needsLogin?: boolean }
  | { status: 'consent'; userId: number; request: string; consent: Consent }
  | { status: 'connections'; userId: number; connections: Connection[] };

const API = '/api/v1/remote-health';
const ACCOUNT_CHANGED = '登录账户已变化或连接请求已过期，请重新检查后再授权。';
const buttonClass = 'rounded-xl px-5 py-3 text-sm font-semibold transition-colors disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600';

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function validName(value: unknown): value is string {
  return typeof value === 'string' && value.length > 0 && value.length <= 200;
}

function isConsent(value: unknown): value is Consent {
  if (!isObject(value)) return false;
  const categories = value.data_categories;
  return validName(value.client_name) && value.scope === 'health:read'
    && typeof value.expires_in_days === 'number' && Number.isInteger(value.expires_in_days)
    && value.expires_in_days >= 1 && value.expires_in_days <= 3650 && Number.isSafeInteger(value.user_id)
    && Array.isArray(categories) && categories.length === 3
    && ['sleep', 'diet', 'exercise'].every(category => categories.includes(category));
}

function isConnection(value: unknown): value is Connection {
  return isObject(value) && typeof value.id === 'string' && /^[A-Za-z0-9_-]{1,100}$/.test(value.id)
    && validName(value.client_name) && value.scope === 'health:read'
    && typeof value.created_at === 'number' && Number.isFinite(value.created_at)
    && typeof value.expires_at === 'number' && Number.isFinite(value.expires_at)
    && value.created_at > 0 && value.expires_at > value.created_at;
}

function ConnectionContent() {
  const { user, isLoading, refreshUser } = useAuth();
  const userId = user?.id ?? null;
  const params = useSearchParams();
  const requests = params.getAll('request');
  const request = requests.length === 1 ? requests[0] : null;
  const invalidRequest = requests.length > 1 || (request !== null && !/^[A-Za-z0-9_-]{43}$/.test(request));
  const router = useRouter();
  const [view, setView] = useState<View>({ status: 'loading' });
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [reload, setReload] = useState(0);
  const context = useRef({ userId, request });
  context.current = { userId, request };
  const busyRef = useRef(false);
  const returnPath = `/connect/health${request && !invalidRequest ? `?request=${encodeURIComponent(request)}` : ''}`;
  const loginPath = `/login?redirect=${encodeURIComponent(returnPath)}`;

  useEffect(() => {
    setView({ status: 'loading' });
    setActionError('');
    setBusy(false);
    busyRef.current = false;
    if (isLoading || userId === null || invalidRequest) return;
    let cancelled = false;
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(request ? `${API}/consent?request=${encodeURIComponent(request)}` : `${API}/connections`, {
          credentials: 'include', cache: 'no-store', signal: controller.signal,
        });
        if (cancelled) return;
        if (response.status === 401) {
          await refreshUser();
          if (cancelled) return;
          setView({ status: 'error', message: '登录已过期，请重新登录。', needsLogin: true });
          return;
        }
        if (!response.ok) throw new Error('unavailable');
        const data: unknown = await response.json();
        if (cancelled) return;
        if (request) {
          if (!isConsent(data)) throw new Error('invalid response');
          if (data.user_id !== userId) {
            await refreshUser();
            if (cancelled) return;
            setView({ status: 'error', message: ACCOUNT_CHANGED });
            return;
          }
          setView({ status: 'consent', userId: data.user_id, request, consent: data });
        } else {
          if (!Array.isArray(data) || data.length > 100 || !data.every(isConnection) || userId === null) throw new Error('invalid response');
          setView({ status: 'connections', userId, connections: data });
        }
      } catch {
        if (!cancelled) setView({ status: 'error', message: '暂时无法读取连接信息。请求可能已过期，请从发起连接的应用重试。' });
      }
    }
    void load();
    return () => { cancelled = true; controller.abort(); };
  }, [isLoading, userId, request, invalidRequest, reload, refreshUser]);

  async function decide(approved: boolean) {
    if (view.status !== 'consent' || view.userId !== userId || view.request !== request || busyRef.current) return;
    const expectedUserId = view.userId;
    const expectedRequest = view.request;
    busyRef.current = true;
    setBusy(true);
    setActionError('');
    const stillCurrent = () => context.current.userId === expectedUserId && context.current.request === expectedRequest;
    let navigating = false;
    try {
      const response = await fetch(`${API}/consent`, {
        method: 'POST', credentials: 'include', cache: 'no-store',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ request: expectedRequest, expected_user_id: expectedUserId, approved }),
      });
      if (!stillCurrent()) return;
      if (!response.ok) {
        if (response.status === 401) await refreshUser();
        if (!stillCurrent()) return;
        setView({ status: 'error', message: ACCOUNT_CHANGED, needsLogin: response.status === 401 });
        return;
      }
      const data: unknown = await response.json();
      if (!stillCurrent()) return;
      if (!isObject(data) || typeof data.redirect_uri !== 'string') throw new Error('invalid response');
      const callback = new URL(data.redirect_uri);
      if (callback.protocol !== 'https:' || callback.username || callback.password) throw new Error('invalid callback');
      router.replace(callback.href);
      navigating = true;
    } catch {
      if (stillCurrent()) setView({ status: 'error', message: '未能完成连接，请从发起连接的应用重新开始。' });
    } finally {
      if (stillCurrent() && !navigating) { busyRef.current = false; setBusy(false); }
    }
  }

  async function revoke(connection: Connection) {
    if (view.status !== 'connections' || view.userId !== userId || busyRef.current) return;
    const expectedUserId = view.userId;
    busyRef.current = true;
    setBusy(true);
    setActionError('');
    try {
      const response = await fetch(`${API}/connections/${encodeURIComponent(connection.id)}`, {
        method: 'DELETE', credentials: 'include', cache: 'no-store',
      });
      if (context.current.userId !== expectedUserId || context.current.request !== null) return;
      if (!response.ok) {
        if (response.status === 401) await refreshUser();
        throw new Error('unavailable');
      }
      setView(current => current.status === 'connections' && current.userId === expectedUserId
        ? { ...current, connections: current.connections.filter(item => item.id !== connection.id) } : current);
    } catch {
      if (context.current.userId === expectedUserId && context.current.request === null) setActionError('未能撤销访问，请稍后重试。');
    } finally {
      if (context.current.userId === expectedUserId && context.current.request === null) { busyRef.current = false; setBusy(false); }
    }
  }

  const ready = (view.status === 'consent' || view.status === 'connections') && view.userId === userId
    && (view.status === 'consent' ? view.request === request : request === null);
  const needsLogin = !isLoading && (!user || (view.status === 'error' && view.needsLogin));

  return (
    <div className="min-h-[70vh] bg-slate-50 px-4 py-10 sm:py-16">
      <section aria-labelledby="connection-title" className="mx-auto max-w-xl rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-9">
        <p className="mb-3 text-sm font-semibold text-indigo-600">小巴健康 · 数据连接</p>
        <h1 id="connection-title" className="text-2xl font-semibold text-slate-900">{request ? '允许读取健康数据？' : '管理健康数据连接'}</h1>
        {user && !needsLogin && !isLoading && (
          <div className="my-6 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
            <p>当前登录账户：<strong className="font-semibold text-slate-900">{user.name}</strong></p>
            <p className="mt-1">账户 #{user.id}</p>
          </div>
        )}
        {invalidRequest ? <p role="alert" className="mt-6 text-sm text-red-700">连接请求无效，请从发起连接的应用重新开始。</p>
          : needsLogin ? (
            <div className="mt-6 space-y-5">
              <p className="text-sm leading-6 text-slate-600">请登录你要连接的健康账户，查看权限并确认授权。</p>
              <Link href={loginPath} className={`${buttonClass} inline-block bg-indigo-600 text-white`}>登录后继续</Link>
            </div>
          ) : isLoading || view.status === 'loading' || ((view.status === 'consent' || view.status === 'connections') && !ready) ? (
            <p role="status" className="mt-6 text-sm text-slate-600">正在读取连接信息…</p>
          ) : view.status === 'error' ? (
            <div className="mt-6 space-y-4">
              <p role="alert" className="text-sm leading-6 text-red-700">{view.message}</p>
              <button type="button" className={`${buttonClass} border border-slate-300 text-slate-700`} onClick={() => setReload(value => value + 1)}>重新检查</button>
            </div>
          ) : view.status === 'consent' && ready ? (
            <div className="space-y-6">
              <p className="text-slate-700"><strong className="break-words text-slate-900">{view.consent.client_name}</strong> 请求访问此账户的健康记录。</p>
              <div className="space-y-3 text-sm leading-6 text-slate-600">
                <p>允许读取：睡眠、饮食和运动记录。该连接只有读取权限，不能新增、修改或删除健康记录。</p>
                <p>授权有效期为 {view.consent.expires_in_days} 天。你可以随时在本页的连接管理中撤销访问。访问令牌短期有效，刷新令牌定期轮换。</p>
                <p>连接的应用将收到你查询范围内的健康数据，请确认你信任此应用。</p>
              </div>
              <div className="flex flex-wrap gap-3">
                <button type="button" disabled={busy} onClick={() => void decide(true)} className={`${buttonClass} bg-indigo-600 text-white hover:bg-indigo-700`}>{busy ? '正在返回…' : '允许只读访问'}</button>
                <button type="button" disabled={busy} onClick={() => void decide(false)} className={`${buttonClass} border border-slate-300 text-slate-700 hover:bg-slate-50`}>拒绝</button>
              </div>
              <Link href="/connect/health" className="inline-block text-sm text-indigo-700 underline underline-offset-4">查看已授权的连接</Link>
            </div>
          ) : view.status === 'connections' && ready ? (
            <div className="space-y-5">
              <p className="text-sm leading-6 text-slate-600">以下应用可读取你的睡眠、饮食和运动记录。撤销后，该连接将无法继续访问。</p>
              {actionError && <p role="alert" className="text-sm text-red-700">{actionError}</p>}
              {view.connections.length === 0 ? <p role="status" className="py-5 text-sm text-slate-500">暂无已授权的连接</p> : (
                <ul className="space-y-3">
                  {view.connections.map(connection => (
                    <li key={connection.id} className="rounded-xl border border-slate-200 p-4">
                      <p className="break-words font-semibold text-slate-900">{connection.client_name}</p>
                      <p className="mt-2 text-sm text-slate-600">只读权限 · 到期时间：{new Date(connection.expires_at * 1000).toLocaleString('zh-CN')}</p>
                      <button type="button" disabled={busy} aria-label={`撤销 ${connection.client_name} 的访问`} onClick={() => void revoke(connection)} className={`${buttonClass} mt-3 border border-slate-300 text-slate-700 hover:bg-slate-50`}>撤销访问</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
      </section>
    </div>
  );
}

export default function HealthConnectionPage() {
  return <Suspense fallback={<p role="status" className="p-8 text-center">正在读取连接信息…</p>}><ConnectionContent /></Suspense>;
}
