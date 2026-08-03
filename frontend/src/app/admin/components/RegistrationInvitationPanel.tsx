'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import type { KeyboardEvent, ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { isAxiosError, isCancel } from 'axios';
import type { components } from '@/types/api.generated';
import { api } from '@/services/api/client';

type Invitation = components['schemas']['RegistrationInvitationSafe'];
type InvitationList = components['schemas']['RegistrationInvitationList'];
type ApiPreparedInvitation = components['schemas']['RegistrationInvitationPrepared'];
type PreparedInvitation = Pick<ApiPreparedInvitation,
  | 'id' | 'phone_masked' | 'note' | 'status' | 'expires_at' | 'created_at' | 'updated_at'
  | 'prepared_for_delivery' | 'manual_code' | 'deep_link' | 'delivery_status' | 'delivery_error_code'
>;
type CreateInvitation = components['schemas']['RegistrationInvitationCreate'];

const PAGE_SIZE = 20;
const ACTIVE_STATUSES = new Set(['created', 'sent', 'send_failed']);
const TERMINAL_STATUSES = new Set(['consumed', 'revoked', 'expired']);
const STATUS_LABELS: Record<string, string> = {
  created: '已创建', sent: '已发送', send_failed: '发送失败', consumed: '已使用', revoked: '已撤销', expired: '已过期', invalid: '状态异常',
};
const STATUS_STYLES: Record<string, string> = {
  created: 'border-sky-400/30 bg-sky-400/10 text-sky-200', sent: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200',
  send_failed: 'border-amber-400/30 bg-amber-400/10 text-amber-100', consumed: 'border-white/15 bg-white/5 text-slate-300',
  revoked: 'border-rose-400/30 bg-rose-400/10 text-rose-200', expired: 'border-white/15 bg-white/5 text-slate-400',
  invalid: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
};

function maskPhone(phone: string): string {
  const compact = phone.trim().replace(/[\s()-]/g, '');
  const digits = compact.replace(/\D/g, '');
  if (digits.length === 13 && digits.startsWith('86')) return `+86 ${digits.slice(2, 5)}****${digits.slice(-4)}`;
  if (digits.length < 7) return '手机号格式待确认';
  const prefix = compact.startsWith('+') ? '+' : '';
  return `${prefix}${digits.slice(0, Math.min(3, digits.length - 4))}****${digits.slice(-4)}`;
}

function safeErrorMessage(error: unknown): string {
  let status = isAxiosError(error) ? error.response?.status : undefined;
  if (status === undefined && typeof error === 'object' && error !== null && 'response' in error) {
    const response = Reflect.get(error, 'response');
    if (typeof response === 'object' && response !== null && 'status' in response) {
      const candidate = Reflect.get(response, 'status');
      if (typeof candidate === 'number') status = candidate;
    }
  }
  if (status === 400 || status === 422) return '提交信息不符合要求，请检查后重试。';
  if (status === 401 || status === 403) return '没有权限执行此操作。';
  if (status === 404) return '邀请不存在或已不可用，请刷新列表。';
  if (status === 409) return '邀请状态已经变化，请刷新后重试。';
  if (status === 429) return '操作过于频繁，请稍后重试。';
  return '服务暂时不可用，请稍后重试。';
}

function deliveryMessage(prepared: PreparedInvitation): string {
  if (prepared.delivery_status === 'sent') return '短信已提交发送。';
  if (prepared.delivery_status === 'send_failed') {
    const safeReasons: Record<string, string> = {
      sms_not_configured: '短信服务未配置', provider_rejected: '短信服务拒绝请求', provider_invalid_ack: '短信服务回执异常',
      provider_timeout: '短信服务响应超时', transport_failed: '短信服务连接失败',
    };
    const reason = prepared.delivery_error_code ? (safeReasons[prepared.delivery_error_code] ?? '短信发送未成功') : '短信发送未成功';
    return `短信发送失败（${reason}），请立即复制下方凭据通过可信渠道发送。`;
  }
  return '邀请已生成，请确认短信状态，并复制凭据作为备用。';
}

function formatDate(value: string): string {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString('zh-CN', { hour12: false }) : '-';
}

function invitationCapability(invitation: Invitation): { status: string; actionable: boolean } {
  const expiration = Date.parse(invitation.expires_at);
  if (!Number.isFinite(expiration)) return { status: 'invalid', actionable: false };
  if (ACTIVE_STATUSES.has(invitation.status)) {
    return expiration <= Date.now()
      ? { status: 'expired', actionable: false }
      : { status: invitation.status, actionable: true };
  }
  if (TERMINAL_STATUSES.has(invitation.status)) return { status: invitation.status, actionable: false };
  return { status: 'invalid', actionable: false };
}

function defaultExpiryLocal(): string {
  const date = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
  const pad = (value: number) => String(value).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function localTimezoneDescription(value: string): string {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) return '时间格式无效，请返回修改';
  try {
    const date = new Date(parsed);
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || '本地时区';
    const offsetMinutes = -date.getTimezoneOffset();
    if (!Number.isFinite(offsetMinutes)) return '时间格式无效，请返回修改';
    const sign = offsetMinutes >= 0 ? '+' : '-';
    const pad = (part: number) => String(Math.abs(part)).padStart(2, '0');
    return `${formatDate(date.toISOString())}（本地时区：${timezone}，UTC${sign}${pad(Math.trunc(offsetMinutes / 60))}:${pad(offsetMinutes % 60)}）`;
  } catch {
    return '时间格式无效，请返回修改';
  }
}

interface AccessibleModalProps {
  labelledBy: string;
  describedBy: string;
  onClose: () => void;
  initialFocusSelector: string;
  children: ReactNode;
  widthClass: string;
  restoreFocusTo?: HTMLElement | null;
}

function AccessibleModal({ labelledBy, describedBy, onClose, initialFocusSelector, children, widthClass, restoreFocusTo }: AccessibleModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const [portalHost, setPortalHost] = useState<HTMLElement | null>(null);

  useEffect(() => {
    const host = document.createElement('div');
    host.dataset.accessibleModalHost = 'true';
    document.body.appendChild(host);
    setPortalHost(host);
    return () => {
      host.remove();
    };
  }, []);

  useEffect(() => {
    if (!portalHost) return;
    restoreFocusRef.current = restoreFocusTo ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null);
    const initial = dialogRef.current?.querySelector<HTMLElement>(initialFocusSelector);
    initial?.focus();
    const backgrounds = initial && document.activeElement === initial
      ? Array.from(document.body.children)
        .filter((element): element is HTMLElement => element instanceof HTMLElement && element !== portalHost)
        .map((element) => ({
          element,
          inert: element.getAttribute('inert'),
          ariaHidden: element.getAttribute('aria-hidden'),
        }))
      : [];
    for (const background of backgrounds) {
      background.element.setAttribute('inert', '');
      background.element.setAttribute('aria-hidden', 'true');
    }
    return () => {
      for (const background of backgrounds) {
        if (background.inert === null) background.element.removeAttribute('inert');
        else background.element.setAttribute('inert', background.inert);
        if (background.ariaHidden === null) background.element.removeAttribute('aria-hidden');
        else background.element.setAttribute('aria-hidden', background.ariaHidden);
      }
      const target = restoreFocusRef.current;
      setTimeout(() => {
        const focusKey = target?.dataset.focusKey;
        const currentTarget = focusKey
          ? document.querySelector<HTMLElement>(`[data-focus-key="${focusKey}"]`)
          : target;
        if (currentTarget?.isConnected) currentTarget.focus();
      }, 0);
    };
  }, [initialFocusSelector, portalHost, restoreFocusTo]);

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])') ?? []);
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  if (!portalHost) return null;

  return createPortal(
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      onKeyDown={handleKeyDown}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 p-4"
    >
      <div className={`w-full ${widthClass} rounded-2xl border border-white/15 bg-slate-900 p-6 shadow-2xl`}>
        {children}
      </div>
    </div>,
    portalHost,
  );
}

function retainDisplayCredentials(response: ApiPreparedInvitation): PreparedInvitation {
  return {
    id: response.id,
    phone_masked: response.phone_masked,
    note: response.note,
    status: response.status,
    expires_at: response.expires_at,
    created_at: response.created_at,
    updated_at: response.updated_at,
    prepared_for_delivery: response.prepared_for_delivery,
    manual_code: response.manual_code,
    deep_link: response.deep_link,
    delivery_status: response.delivery_status,
    delivery_error_code: response.delivery_error_code,
  };
}

export default function RegistrationInvitationPanel() {
  const [items, setItems] = useState<Invitation[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | 'create' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [phone, setPhone] = useState('');
  const [note, setNote] = useState('');
  const [expiresAt, setExpiresAt] = useState(defaultExpiryLocal);
  const [confirming, setConfirming] = useState(false);
  const [prepared, setPrepared] = useState<PreparedInvitation | null>(null);
  const [preparedFromResend, setPreparedFromResend] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const operationTriggerRef = useRef<HTMLElement | null>(null);
  const mountedRef = useRef(false);
  const requestSequenceRef = useRef(0);
  const listAbortRef = useRef<AbortController | null>(null);

  const load = useCallback(async (nextOffset: number) => {
    if (!mountedRef.current) return;
    const requestId = ++requestSequenceRef.current;
    listAbortRef.current?.abort();
    const controller = new AbortController();
    listAbortRef.current = controller;
    setLoading(true); setError(null);
    try {
      // The shared client mounts at /api; Next rewrites this to the backend's /api/v1 route.
      const response = await api.get<InvitationList>('/admin/registration-invitations', {
        params: { limit: PAGE_SIZE, offset: nextOffset },
        signal: controller.signal,
      });
      if (!mountedRef.current || requestId !== requestSequenceRef.current) return;
      setItems(response.data.items); setTotal(response.data.total); setOffset(response.data.offset);
    } catch (caught) {
      const aborted = controller.signal.aborted
        || isCancel(caught)
        || (caught instanceof Error && caught.name === 'AbortError');
      if (!mountedRef.current || requestId !== requestSequenceRef.current || aborted) return;
      setItems([]); setTotal(0); setOffset(0); setError(safeErrorMessage(caught));
    } finally {
      if (mountedRef.current && requestId === requestSequenceRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    void load(0);
    return () => {
      mountedRef.current = false;
      listAbortRef.current?.abort();
    };
  }, [load]);

  const startOperation = (id: number | 'create') => {
    setPrepared(null); setCopyError(false); setError(null); setBusyId(id);
  };

  const submitCreate = async () => {
    startOperation('create'); setConfirming(false);
    try {
      const parsedExpiry = Date.parse(expiresAt);
      if (!Number.isFinite(parsedExpiry) || parsedExpiry <= Date.now()) {
        setError('有效期必须晚于当前时间，请修改后重试。');
        return;
      }
      const payload: CreateInvitation = {
        phone: phone.trim(), note: note.trim() || null, expires_at: new Date(parsedExpiry).toISOString(),
      };
      const response = await api.post<ApiPreparedInvitation>('/admin/registration-invitations', payload);
      setPrepared(retainDisplayCredentials(response.data)); setPreparedFromResend(false);
      setPhone(''); setNote(''); setExpiresAt(defaultExpiryLocal()); await load(0);
    } catch (caught) { setError(safeErrorMessage(caught)); }
    finally { setBusyId(null); }
  };

  const resend = async (invitation: Invitation, trigger: HTMLElement) => {
    operationTriggerRef.current = trigger;
    startOperation(invitation.id);
    try {
      const response = await api.post<ApiPreparedInvitation>(`/admin/registration-invitations/${invitation.id}/resend`);
      setPrepared(retainDisplayCredentials(response.data)); setPreparedFromResend(true); await load(offset);
    } catch (caught) { setError(safeErrorMessage(caught)); }
    finally { setBusyId(null); }
  };

  const revoke = async (invitation: Invitation) => {
    if (!confirm(`确认撤销发给 ${invitation.phone_masked} 的注册邀请？撤销后凭据立即失效。`)) return;
    startOperation(invitation.id);
    try { await api.post<Invitation>(`/admin/registration-invitations/${invitation.id}/revoke`); await load(offset); }
    catch (caught) { setError(safeErrorMessage(caught)); }
    finally { setBusyId(null); }
  };

  const copy = async (value: string) => {
    setCopyError(false);
    try { await navigator.clipboard.writeText(value); }
    catch { setCopyError(true); }
  };

  const parsedPreviewExpiry = Date.parse(expiresAt);
  const canPreview = phone.trim().replace(/\D/g, '').length >= 7
    && Number.isFinite(parsedPreviewExpiry)
    && parsedPreviewExpiry > Date.now()
    && note.length <= 200;
  const interactionLocked = busyId !== null || prepared !== null;

  return (
    <section aria-labelledby="registration-invitations-title" className="overflow-hidden rounded-2xl border border-emerald-300/20 bg-slate-950/35 shadow-2xl shadow-slate-950/20 backdrop-blur-xl">
      <div className="border-b border-white/10 bg-gradient-to-r from-emerald-400/10 to-cyan-400/5 p-5 md:p-6">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start">
          <div>
            <p className="mb-1 text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">Registration access</p>
            <h2 id="registration-invitations-title" className="text-xl font-semibold text-white">手机号注册邀请</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">仅受邀手机号可完成首次注册。创建并发送即代表管理员批准；一次性凭据只在当前弹窗展示。</p>
          </div>
          <button type="button" onClick={() => void load(offset)} className="self-start rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-slate-100 hover:bg-white/10">刷新列表</button>
        </div>
      </div>

      <div className="grid gap-6 p-5 md:grid-cols-[minmax(260px,0.8fr)_minmax(0,1.7fr)] md:p-6">
        <form className="space-y-4 rounded-xl border border-white/10 bg-white/[0.04] p-4" onSubmit={(event) => { event.preventDefault(); operationTriggerRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null; setConfirming(true); }}>
          <div><h3 className="font-medium text-white">创建并发送</h3><p className="mt-1 text-xs leading-5 text-amber-100/80">提交前会再次显示脱敏手机号供确认。</p></div>
          <label className="block text-sm text-slate-200">受邀手机号<input required disabled={interactionLocked} maxLength={32} autoComplete="tel" value={phone} onChange={(event) => setPhone(event.target.value)} className="mt-1.5 w-full rounded-lg border border-white/15 bg-slate-950/40 px-3 py-2.5 text-white outline-none focus:border-emerald-300" placeholder="+86 138 0013 8000" /></label>
          <label className="block text-sm text-slate-200">备注<textarea disabled={interactionLocked} maxLength={200} value={note} onChange={(event) => setNote(event.target.value)} className="mt-1.5 min-h-20 w-full resize-y rounded-lg border border-white/15 bg-slate-950/40 px-3 py-2.5 text-white outline-none focus:border-emerald-300" placeholder="邀请原因或归属（可选）" /></label>
          <label className="block text-sm text-slate-200">有效期<input required disabled={interactionLocked} type="datetime-local" value={expiresAt} onChange={(event) => setExpiresAt(event.target.value)} className="mt-1.5 w-full rounded-lg border border-white/15 bg-slate-950/40 px-3 py-2.5 text-white outline-none focus:border-emerald-300" /></label>
          <button data-focus-key="create-preview" type="submit" disabled={!canPreview || interactionLocked} className="w-full rounded-lg bg-emerald-500 px-4 py-2.5 font-medium text-slate-950 hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50">{busyId === 'create' ? '正在创建…' : '预览并确认'}</button>
        </form>

        <div className="min-w-0">
          {error ? <div role="alert" className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-rose-300/25 bg-rose-400/10 p-3 text-sm text-rose-100"><span>{error}</span><button type="button" onClick={() => void load(offset)} className="shrink-0 underline underline-offset-4">重新加载</button></div> : loading ? <div role="status" className="py-12 text-center text-sm text-slate-300">正在加载手机号注册邀请…</div> : items.length === 0 ? <div className="rounded-xl border border-dashed border-white/15 py-12 text-center text-sm text-slate-400">还没有手机号注册邀请</div> : (
            <div className="space-y-3">
              {items.map((item) => {
                const capability = invitationCapability(item);
                const status = capability.status;
                return <article key={item.id} className="rounded-xl border border-white/10 bg-white/[0.035] p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex flex-wrap items-center gap-2"><span className="font-mono font-medium text-white">{item.phone_masked}</span><span className={`rounded-full border px-2 py-0.5 text-xs ${STATUS_STYLES[status] ?? STATUS_STYLES.invalid}`}>{STATUS_LABELS[status] ?? STATUS_LABELS.invalid}</span></div>{item.note ? <p className="mt-2 text-sm text-slate-300">{item.note}</p> : null}</div><div className="flex gap-2"><button data-focus-key={`resend-${item.id}`} type="button" aria-label={`重发 ${item.phone_masked} 的邀请`} disabled={!capability.actionable || interactionLocked} onClick={(event) => void resend(item, event.currentTarget)} className="rounded-md border border-emerald-300/25 px-3 py-1.5 text-sm text-emerald-200 disabled:opacity-35">重发</button><button type="button" aria-label={`撤销 ${item.phone_masked} 的邀请`} disabled={!capability.actionable || interactionLocked} onClick={() => void revoke(item)} className="rounded-md border border-rose-300/25 px-3 py-1.5 text-sm text-rose-200 disabled:opacity-35">撤销</button></div></div>
                  <dl className="mt-3 grid gap-1 text-xs text-slate-400 sm:grid-cols-2"><div><dt className="inline">创建：</dt><dd className="inline">{formatDate(item.created_at)}</dd></div><div><dt className="inline">到期：</dt><dd className="inline">{formatDate(item.expires_at)}</dd></div></dl>
                </article>;
              })}
            </div>
          )}
          {!error && !loading && items.length > 0 ? <div className="mt-4 flex items-center justify-between text-xs text-slate-400"><span>共 {total} 条</span><div className="flex gap-2"><button type="button" disabled={offset === 0 || loading} onClick={() => void load(Math.max(0, offset - PAGE_SIZE))} className="rounded border border-white/15 px-2 py-1 disabled:opacity-30">上一页</button><button type="button" disabled={offset + PAGE_SIZE >= total || loading} onClick={() => void load(offset + PAGE_SIZE)} className="rounded border border-white/15 px-2 py-1 disabled:opacity-30">下一页</button></div></div> : null}
        </div>
      </div>

      {confirming ? (
        <AccessibleModal
          labelledBy="confirm-invitation-title"
          describedBy="confirm-invitation-description"
          initialFocusSelector="[data-autofocus]"
          onClose={() => setConfirming(false)}
          widthClass="max-w-md"
          restoreFocusTo={operationTriggerRef.current}
        >
          <h3 id="confirm-invitation-title" className="text-lg font-semibold text-white">确认创建手机号注册邀请</h3>
          <div id="confirm-invitation-description">
            <p className="mt-3 text-sm text-slate-300">注册资格将绑定到：</p>
            <p className="mt-2 font-mono text-xl text-emerald-200">{maskPhone(phone)}</p>
            <p className="mt-3 text-sm text-slate-300">有效期：{localTimezoneDescription(expiresAt)}</p>
            <p className="mt-3 text-sm leading-6 text-amber-100/80">确认后系统会立即创建凭据并尝试发送短信，无需再次审批。</p>
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <button data-autofocus type="button" onClick={() => setConfirming(false)} className="rounded-lg border border-white/15 px-4 py-2 text-slate-200">返回修改</button>
            <button type="button" onClick={() => void submitCreate()} className="rounded-lg bg-emerald-500 px-4 py-2 font-medium text-slate-950">确认创建并发送</button>
          </div>
        </AccessibleModal>
      ) : null}

      {prepared ? (
        <AccessibleModal
          labelledBy="prepared-invitation-title"
          describedBy="prepared-invitation-description"
          initialFocusSelector="[data-secret-autofocus]"
          onClose={() => { setPrepared(null); setCopyError(false); }}
          widthClass="max-w-xl"
          restoreFocusTo={operationTriggerRef.current}
        >
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-200">One-time credentials</p>
          <h3 id="prepared-invitation-title" className="mt-1 text-xl font-semibold text-white">一次性注册凭据</h3>
          <div id="prepared-invitation-description" className="mt-4 rounded-lg border border-amber-300/20 bg-amber-300/10 p-3 text-sm leading-6 text-amber-50">
            {deliveryMessage(prepared)}{preparedFromResend ? ' 本次为重发，旧凭据已失效。' : ' 关闭后本页面不会保留这些凭据。'}
          </div>
          <div className="mt-5 space-y-4">
            <label className="block text-sm text-slate-300">手动邀请码<div className="mt-1.5 flex gap-2"><input data-secret-autofocus aria-label="手动邀请码" readOnly value={prepared.manual_code} onFocus={(event) => event.currentTarget.select()} className="min-w-0 flex-1 rounded-lg border border-white/15 bg-slate-950/50 px-3 py-2 font-mono text-white" /><button type="button" onClick={() => void copy(prepared.manual_code)} className="rounded-lg border border-white/15 px-3 text-sm text-white">复制手动邀请码</button></div></label>
            <label className="block text-sm text-slate-300">注册链接<div className="mt-1.5 flex gap-2"><input aria-label="注册链接" readOnly value={prepared.deep_link} onFocus={(event) => event.currentTarget.select()} className="min-w-0 flex-1 rounded-lg border border-white/15 bg-slate-950/50 px-3 py-2 font-mono text-xs text-white" /><button type="button" onClick={() => void copy(prepared.deep_link)} className="rounded-lg border border-white/15 px-3 text-sm text-white">复制注册链接</button></div></label>
          </div>
          {copyError ? <p role="status" className="mt-3 text-sm text-amber-200">复制失败，请手动选择上方内容。</p> : null}
          <div className="mt-6 flex justify-end"><button type="button" onClick={() => { setPrepared(null); setCopyError(false); }} className="rounded-lg bg-white px-4 py-2 font-medium text-slate-900">关闭一次性凭据</button></div>
        </AccessibleModal>
      ) : null}
    </section>
  );
}
