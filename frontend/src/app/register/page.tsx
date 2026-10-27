'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { api } from '@/services/api/client';

function normalizedPhone(value: string): string | null {
  const phone = value.replace(/[\s()-]/g, '');
  if (/^1[3-9]\d{9}$/.test(phone)) return `+86${phone}`;
  return /^\+[1-9]\d{6,14}$/.test(phone) ? phone : null;
}

export default function RegisterPage() {
  const router = useRouter();
  const { isAuthenticated, verifyPhoneCode } = useAuth();
  const [phone, setPhone] = useState('');
  const [sentPhone, setSentPhone] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [countdown, setCountdown] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => { if (isAuthenticated) router.push('/'); }, [isAuthenticated, router]);
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown((value) => Math.max(0, value - 1)), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  const requestCode = async () => {
    if (isLoading || countdown > 0) return;
    const normalized = normalizedPhone(phone);
    if (!normalized) { setError('请输入有效手机号；其他地区请填写国家区号。'); return; }
    setError('');
    setIsLoading(true);
    setCode('');
    try {
      await api.post('/auth/phone/code', { phone: normalized, purpose: 'login' });
      setSentPhone(normalized);
      setCountdown(60);
    } catch (cause: unknown) {
      const detail = (cause as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      const message = typeof detail === 'object' && detail !== null && 'message' in detail ? detail.message : null;
      setError(typeof detail === 'string' ? detail : typeof message === 'string' ? message : '验证码发送失败，请稍后重试。');
    } finally {
      setIsLoading(false);
    }
  };

  const verify = async (event: React.FormEvent) => {
    event.preventDefault();
    if (isLoading || !sentPhone || !/^\d{4,8}$/.test(code.trim())) return;
    setError('');
    setIsLoading(true);
    try {
      const result = await verifyPhoneCode(sentPhone, code.trim());
      if (result.success) router.push('/');
      else setError(result.error || '验证码验证失败，请重试。');
    } catch {
      setError('登录状态验证失败，请稍后重试。');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gradient-to-br from-indigo-50 via-white to-purple-50 flex items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 shadow-xl">
        <h1 className="text-2xl font-bold text-gray-900">手机号注册 / 登录</h1>
        <p className="mt-2 text-sm text-gray-600">新用户验证手机号后即可注册；已有账号将直接登录。</p>
        {error && <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}
        <form onSubmit={verify} className="mt-6 space-y-4">
          <div>
            <label htmlFor="register-phone" className="block text-sm font-semibold text-gray-700">手机号</label>
            <input id="register-phone" type="tel" autoComplete="tel" value={phone} disabled={isLoading || sentPhone !== null}
              onChange={(event) => setPhone(event.target.value)} placeholder="例如 138 0013 8000"
              className="mt-2 w-full rounded-lg border border-gray-300 p-3 text-gray-900 disabled:bg-gray-100" />
            <p className="mt-1 text-xs text-gray-500">中国大陆号码可直接输入 11 位手机号；其他地区请填写国家区号。</p>
          </div>
          <button type="button" onClick={() => void requestCode()} disabled={isLoading || countdown > 0 || !normalizedPhone(phone)}
            className="w-full rounded-lg border border-indigo-600 p-3 font-semibold text-indigo-700 disabled:opacity-50">
            {countdown > 0 ? `${countdown} 秒后重新获取` : '获取验证码'}
          </button>
          {sentPhone && <>
            <div>
              <label htmlFor="register-code" className="block text-sm font-semibold text-gray-700">短信验证码</label>
              <input id="register-code" inputMode="numeric" autoComplete="one-time-code" maxLength={8} value={code}
                onChange={(event) => setCode(event.target.value)} disabled={isLoading}
                className="mt-2 w-full rounded-lg border border-gray-300 p-3 text-gray-900" />
            </div>
            <button type="submit" disabled={isLoading || !/^\d{4,8}$/.test(code.trim())}
              className="w-full rounded-lg bg-indigo-600 p-3 font-semibold text-white disabled:opacity-50">
              {isLoading ? '验证中...' : '验证并登录 / 注册'}
            </button>
            <button type="button" disabled={isLoading} onClick={() => { setSentPhone(null); setCode(''); setError(''); }}
              className="text-sm text-indigo-700 disabled:opacity-50">更换手机号</button>
          </>}
        </form>
        <p className="mt-6 text-center text-sm"><Link href="/login" className="text-indigo-700">使用账号密码登录</Link></p>
      </div>
    </main>
  );
}
