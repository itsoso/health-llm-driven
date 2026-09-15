'use client';

import { useEffect, useState } from 'react';

const TOKEN_PATTERN = /^[A-Za-z0-9_-]{22,128}$/;
const APP_STORE_URL = 'https://apps.apple.com/app/id6763569720';

function tokenFromFragment(fragment: string, search: string): string | null {
  if (search || !fragment.startsWith('#')) return null;
  const params = new URLSearchParams(fragment.slice(1));
  if (Array.from(params.keys()).some((key) => key !== 'token')) return null;
  const tokens = params.getAll('token');
  return tokens.length === 1 && TOKEN_PATTERN.test(tokens[0]) ? tokens[0] : null;
}

export default function RegistrationInviteLanding() {
  const [appUrl, setAppUrl] = useState<string | null | undefined>(undefined);

  useEffect(() => {
    const fragment = window.location.hash;
    const search = window.location.search;
    window.history.replaceState(window.history.state, '', window.location.pathname);
    const token = tokenFromFragment(fragment, search);
    setAppUrl(token ? `health://invite?token=${token}` : null);
  }, []);

  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10 text-white">
      <section className="w-full max-w-md rounded-2xl border border-white/10 bg-slate-900 p-6 shadow-2xl">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-300">Registration invitation</p>
        <h1 className="mt-2 text-2xl font-semibold">小巴健康注册邀请</h1>
        {appUrl === undefined ? (
          <p role="status" className="mt-4 text-sm text-slate-300">正在验证注册链接…</p>
        ) : appUrl ? (
          <>
            <p className="mt-4 text-sm leading-6 text-slate-300">请在受邀手机号的设备上打开小巴健康，验证手机号后即可完成注册。</p>
            <a href={appUrl} className="mt-6 flex w-full justify-center rounded-xl bg-emerald-400 px-4 py-3 font-semibold text-slate-950">在小巴健康中打开</a>
            <a href={APP_STORE_URL} referrerPolicy="no-referrer" className="mt-3 flex w-full justify-center rounded-xl border border-white/15 px-4 py-3 text-sm text-slate-200">前往 App Store 安装</a>
            <p className="mt-4 text-xs leading-5 text-slate-400">安装后请重新打开原邀请链接。邀请凭据只应发送给受邀本人。</p>
          </>
        ) : (
          <p role="alert" className="mt-4 rounded-xl border border-amber-300/20 bg-amber-300/10 p-4 text-sm text-amber-100">注册链接无效或不完整，请联系邀请人重新生成。</p>
        )}
      </section>
    </main>
  );
}
