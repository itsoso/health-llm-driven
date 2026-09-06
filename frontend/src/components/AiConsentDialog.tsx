'use client';

import { useEffect, useRef, useState } from 'react';
import { AiConsent, registerAiConsentPresenter } from '@/services/aiConsent';

interface Request {
  policy: AiConsent;
  save: (accepted: boolean) => Promise<void>;
  resolve: (accepted: boolean) => void;
}

/** One native modal, so Escape and keyboard focus behave consistently on Safari. */
export default function AiConsentDialog() {
  const [request, setRequest] = useState<Request | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<Request | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  function close(accepted = false) {
    const active = pending.current;
    pending.current = null;
    setRequest(null);
    active?.resolve(accepted);
  }

  useEffect(() => {
    const unregister = registerAiConsentPresenter((policy, save) => new Promise(resolve => {
      // Never let a second background request replace an informed user decision.
      if (pending.current) { resolve(false); return; }
      const next = { policy, save, resolve };
      pending.current = next;
      setError('');
      setSaving(false);
      setRequest(next);
    }), () => close());
    return () => { unregister(); pending.current?.resolve(false); pending.current = null; };
  }, []);

  useEffect(() => {
    if (request && dialog.current && !dialog.current.open) dialog.current.showModal();
  }, [request]);

  async function save(accepted: boolean) {
    if (!request || saving) return;
    const active = request;
    setSaving(true);
    try {
      await active.save(accepted);
      if (pending.current === active) close(accepted);
    } catch (failure) {
      if (pending.current === active) setError(failure instanceof Error ? failure.message : '授权未保存，请重试。');
    } finally {
      if (pending.current === active) setSaving(false);
    }
  }

  if (!request) return null;
  return (
    <dialog ref={dialog} aria-labelledby="ai-consent-title" aria-describedby="ai-consent-purpose"
      className="m-auto w-[calc(100%-2rem)] max-w-lg rounded-2xl bg-[#F7F6F2] p-0 text-[#16201B] shadow-xl backdrop:bg-black/40"
      onCancel={event => { event.preventDefault(); if (!saving) close(); }}>
      <div className="max-h-[80dvh] overflow-y-auto p-6">
        <h2 id="ai-consent-title" className="text-xl font-semibold">第三方 AI 数据使用</h2>
        <p id="ai-consent-purpose" className="mt-3 text-sm leading-6">{request.policy.purpose}</p>
        <h3 className="mt-5 font-semibold">接收方及用途</h3>
        <ul className="mt-2 space-y-3 text-sm leading-6">
          {request.policy.recipients.map(item => <li key={item.id}><strong>{item.name}</strong><br />{item.purpose}</li>)}
        </ul>
        <h3 className="mt-5 font-semibold">可能发送的数据</h3>
        <ul className="mt-2 list-inside list-disc text-sm leading-6">
          {request.policy.data_types.map(item => <li key={item}>{item}</li>)}
        </ul>
        <p className="mt-4 text-sm leading-6 text-[#58645D]">拒绝不影响非 AI 记录、数据导出和账号管理。你可以随时在设置中撤回；撤回停止后续发送，但不能撤回已经发送的数据。</p>
        <a href="/privacy" target="_blank" rel="noreferrer" className="mt-2 inline-block text-sm text-[#176F49] underline">查看隐私政策</a>
        <p className="mt-2 text-xs text-[#58645D]">说明版本：{request.policy.policy_version} · {request.policy.accepted ? '当前已授权' : '当前未授权'}</p>
        {error && <p role="alert" className="mt-3 text-sm text-red-700">{error}</p>}
      </div>
      <div className="flex gap-3 border-t border-[#E7E5DE] p-4">
        <button type="button" disabled={saving} onClick={() => close()} className="min-h-11 flex-1 rounded-xl border border-[#D7D5CC] px-3 disabled:opacity-50">{request.policy.accepted ? '关闭' : '暂不同意'}</button>
        <button type="button" disabled={saving} onClick={() => void save(!request.policy.accepted)} className="min-h-11 flex-1 rounded-xl bg-[#176F49] px-3 text-white disabled:opacity-50">{saving ? '正在保存…' : request.policy.accepted ? '撤回授权' : '同意并继续'}</button>
      </div>
    </dialog>
  );
}
